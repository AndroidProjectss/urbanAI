"""
AI Recommendations Service - Сервис для генерации рекомендаций по строительству школ

Использует:
1. Данные о плотности населения (сетка 500x500м)
2. ML прогнозы населения и школьников
3. Данные о текущих школах и их загрузке
4. Gemini AI для анализа и генерации рекомендаций
"""

import os
import json
import traceback
from typing import Dict, List, Optional
from datetime import datetime
import google.generativeai as genai

# Gemini API Key
GEMINI_API_KEY = "AIzaSyCrKC8qisDxCzrwHBao0nLjNsMsKDslskU"


class AIRecommendationsService:
    """
    Сервис для генерации AI-рекомендаций по строительству школ.
    
    Анализирует:
    - Плотность населения по ячейкам сетки
    - Загрузку существующих школ
    - ML прогнозы роста населения
    - Демографические данные
    
    Генерирует:
    - Конкретные локации для новых школ (из реальных данных сетки!)
    - Приоритеты строительства
    - Рекомендуемую вместимость
    """
    
    CELL_AREA_M2 = 500 * 500  # площадь ячейки 500×500м
    STUDENT_RATIO = 0.18      # доля школьников от населения
    COST_PER_STUDENT = 1200000  # ориентировочная стоимость места (KGS)
    PLOT_AREA_PER_STUDENT = 35  # м² на ребёнка по СП 118
    SPORTS_AREA_PER_STUDENT = 7
    PLAYGROUND_AREA_PER_STUDENT = 4
    MIN_SANITARY_BUFFER_M = 25
    PARKING_PER_100_STUDENTS = 8
    DROP_OFF_CAPACITY_RATIO = 0.35

    def __init__(self):
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-2.5-flash')

    # ------------------------------------------------------------------
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ------------------------------------------------------------------

    def _classify_owner(self, owner_form: Optional[str]) -> str:
        owner = (owner_form or '').lower()
        if any(keyword in owner for keyword in ['state', 'municipal', 'гос', 'муниц', 'коммун']):
            return 'government'
        if 'private' in owner or 'частн' in owner:
            return 'private'
        return 'unknown'

    def _get_growth_factor(self, ml_forecast: Optional[Dict]) -> float:
        if not ml_forecast or 'forecasts' not in ml_forecast:
            return 1.05
        forecasts = ml_forecast.get('forecasts', [])
        if len(forecasts) < 2:
            return 1.05
        base = forecasts[0].get('school_age_population') or forecasts[0].get('population')
        future = forecasts[-1].get('school_age_population') or forecasts[-1].get('population')
        if not base or base <= 0 or not future:
            return 1.05
        return max(1.0, round(future / base, 2))

    def _estimate_students(self, population: float, growth_factor: float) -> Dict[str, int]:
        current = int(population * self.STUDENT_RATIO)
        projected = int(current * growth_factor)
        return {
            'current': current,
            'projected': projected
        }

    def _get_nearest_schools(self, lat: float, lng: float, schools: List[Dict], top_k: int = 2) -> List[Dict]:
        distances = []
        for school in schools:
            school_lat = school.get('latitude') or school.get('lat')
            school_lng = school.get('longitude') or school.get('lng')
            if not school_lat or not school_lng:
                continue
            dist = self._haversine_distance(lat, lng, float(school_lat), float(school_lng))
            distances.append({
                'id': school.get('id'),
                'name': school.get('name'),
                'distance_km': round(dist, 3),
                'capacity': school.get('capacity') or school.get('estimated_capacity'),
                'occupancy_rate': school.get('occupancy_rate'),
                'district': school.get('district'),
                'owner_type': self._classify_owner(school.get('owner_form'))
            })
        distances.sort(key=lambda x: x['distance_km'])
        return distances[:top_k]

    def _summarize_quarter_cells(self, target_cell: Dict, grid_cells: List[Dict], radius_km: float = 0.35) -> Dict:
        quarters = []
        total_current = 0
        total_projected = 0
        for cell in grid_cells:
            dist = self._haversine_distance(target_cell['lat'], target_cell['lng'], cell['lat'], cell['lng'])
            if dist <= radius_km:
                current_students = cell.get('students_current')
                projected_students = cell.get('students_projected')
                if current_students is None:
                    current_students = int((cell.get('population', 0) or 0) * self.STUDENT_RATIO)
                if projected_students is None:
                    projected_students = int(current_students * 1.05)
                quarters.append({
                    'lat': cell['lat'],
                    'lng': cell['lng'],
                    'current_students': current_students,
                    'projected_students': projected_students
                })
                total_current += current_students
                total_projected += projected_students
        return {
            'quarters': quarters[:12],
            'current_students': total_current,
            'projected_students': total_projected
        }

    def _build_traffic_assessment(self, cell: Dict, recommended_capacity: int, quarter_summary: Dict) -> Dict:
        peak_students = int(recommended_capacity * 0.45)
        pickup_flow = int(peak_students * 0.3)
        parking_required = max(20, int((recommended_capacity / 100) * self.PARKING_PER_100_STUDENTS))
        local_students = quarter_summary.get('current_students', 0)

        conflict_points = []
        if cell.get('density', 0) > 20000:
            conflict_points.append('Высокая плотность застройки → интенсивное движение')
        if cell.get('buildings_count', 0) > 50:
            conflict_points.append('Много жилых домов в радиусе 500м')
        if (cell.get('nearest_school_km') or 10) < 0.6:
            conflict_points.append('Близость к существующей школе — возможно пересечение потоков')
        if local_students > recommended_capacity:
            conflict_points.append('Приток из соседних кварталов превышает проектную вместимость')

        return {
            'peak_students_15min': peak_students,
            'dropoff_flow_per_10min': pickup_flow,
            'parking_stalls_required': parking_required,
            'local_catchment_students': local_students,
            'conflict_points': conflict_points
        }

    def _evaluate_land_use(self, cell: Dict, recommended_capacity: int) -> Dict:
        required_plot = recommended_capacity * self.PLOT_AREA_PER_STUDENT
        required_sports = recommended_capacity * self.SPORTS_AREA_PER_STUDENT
        required_play = recommended_capacity * self.PLAYGROUND_AREA_PER_STUDENT

        # Приблизительно оцениваем доступную площадь (учитываем плотность застройки)
        build_ratio = min(0.85, (cell.get('buildings_count', 0) / 80))
        available_area = int(self.CELL_AREA_M2 * max(0.2, 1 - build_ratio))

        meets_plot = available_area >= required_plot

        return {
            'required_plot_area_m2': required_plot,
            'estimated_available_area_m2': available_area,
            'required_sports_area_m2': required_sports,
            'required_playground_area_m2': required_play,
            'meets_norms': meets_plot,
            'sanitary_buffer_m': self.MIN_SANITARY_BUFFER_M
        }

    def _build_contextual_factors(self, cell: Dict, recommended_capacity: int, analysis_data: Dict) -> Dict:
        growth_factor = analysis_data.get('growth_factor', 1.05)
        demand_pressure = 'high' if growth_factor > 1.08 else ('medium' if growth_factor > 1.02 else 'stable')
        social_gain = 'высокая' if (cell.get('nearest_school_km') or 1.5) > 1.2 else 'средняя'
        budget = recommended_capacity * self.COST_PER_STUDENT
        budget_level = 'крупный' if recommended_capacity > 1200 else ('средний' if recommended_capacity > 800 else 'компактный')

        return {
            'future_development_outlook': demand_pressure,
            'social_access_benefit': social_gain,
            'budget_estimate_kgs': budget,
            'budget_level': budget_level
        }
    
    def filter_schools_by_ownership(self, schools, ownership_type: str = 'all'):
        """
        Фильтрация школ по типу собственности
        ownership_type: 'all', 'government', 'private'
        """
        if ownership_type == 'all':
            return schools
        
        # Определяем типы собственности
        government_keywords = ['state', 'municipal', 'государств', 'муниципал', 'коммунал']
        private_keywords = ['private', 'частн']
        
        filtered = []
        for s in schools:
            owner = str(s.get('owner_form', '') if isinstance(s, dict) else getattr(s, 'owner_form', '')).lower()
            
            if ownership_type == 'government':
                if any(kw in owner for kw in government_keywords):
                    filtered.append(s)
            elif ownership_type == 'private':
                if any(kw in owner for kw in private_keywords):
                    filtered.append(s)
        
        return filtered if filtered else schools  # Если ничего не найдено, вернуть всё
    
    def prepare_analysis_data(
        self,
        grid_data: Dict,
        schools: List[Dict],
        districts: List[Dict],
        ml_forecast: Dict = None,
        restricted_zones: List[Dict] = None
    ) -> Dict:
        """
        Подготовка данных для анализа AI.
        
        Собирает:
        - Ячейки с высокой плотностью без школ поблизости
        - Перегруженные школы по районам
        - Прогноз роста населения
        - Запрещённые зоны (парки, промзоны и т.д.)
        """
        
        growth_factor = self._get_growth_factor(ml_forecast)
        grid_cells_full = grid_data.get('grid_cells', []) if grid_data else []

        # 1. Анализ ячеек с высокой плотностью
        high_density_cells = []
        if grid_cells_full:
            for cell in grid_cells_full:
                density = cell.get('density', 0)
                if density > 6000:  # Высокая плотность
                    # Проверяем не в запрещённой ли зоне
                    in_restricted = False
                    restricted_info = None
                    
                    if restricted_zones:
                        for zone in restricted_zones:
                            dist = self._haversine_distance(
                                cell['lat'], cell['lng'],
                                zone['lat'], zone['lng']
                            )
                            # Если ячейка внутри зоны запрета
                            if dist < zone.get('radius_km', 0.3):
                                in_restricted = True
                                restricted_info = f"{zone['name']} ({zone['type']})"
                                break
                    
                    students_est = self._estimate_students(cell.get('population', 0), growth_factor)

                    high_density_cells.append({
                        'lat': cell['lat'],
                        'lng': cell['lng'],
                        'density': density,
                        'population': cell.get('population', 0),
                        'district': cell.get('district', 'Неизвестно'),
                        'buildings_count': cell.get('buildings_count', 0),
                        'in_restricted_zone': in_restricted,
                        'restricted_info': restricted_info,
                        'students_current': students_est['current'],
                        'students_projected': students_est['projected']
                    })
        
        # Сортируем по плотности
        high_density_cells.sort(key=lambda x: x['density'], reverse=True)
        
        # 2. Анализ школ по районам
        districts_stats = {}
        for school in schools:
            district = school.get('district', 'Неизвестно')
            if district not in districts_stats:
                districts_stats[district] = {
                    'schools_count': 0,
                    'total_students': 0,
                    'total_capacity': 0,
                    'overloaded_schools': [],
                    'critical_schools': []
                }
            
            stats = districts_stats[district]
            stats['schools_count'] += 1
            stats['total_students'] += school.get('total_students', 0)
            stats['total_capacity'] += school.get('capacity', 0)
            
            occupancy = school.get('occupancy_rate', 0)
            if occupancy > 100:
                stats['overloaded_schools'].append({
                    'name': school.get('name', ''),
                    'occupancy': occupancy,
                    'lat': school.get('latitude'),
                    'lng': school.get('longitude')
                })
            if occupancy > 130:
                stats['critical_schools'].append({
                    'name': school.get('name', ''),
                    'occupancy': occupancy,
                    'deficit': school.get('total_students', 0) - school.get('capacity', 0)
                })
        
        # 3. Расчёт покрытия школами - ДЛЯ ВСЕХ ячеек высокой плотности
        # Рассчитываем расстояние до ближайшей школы для каждой ячейки
        cells_with_distance = []
        cells_without_schools = []
        
        for cell in high_density_cells[:50]:  # Топ-50 по плотности
            nearest_school_dist = float('inf')
            nearest_school_name = None
            
            for school in schools:
                school_lat = school.get('latitude')
                school_lng = school.get('longitude')
                
                if school_lat and school_lng:
                    dist = self._haversine_distance(
                        cell['lat'], cell['lng'],
                        school_lat, school_lng
                    )
                    if dist < nearest_school_dist:
                        nearest_school_dist = dist
                        nearest_school_name = school.get('name', 'Школа')
            
            # Добавляем информацию о расстоянии к ячейке
            cell_with_info = {
                **cell,
                'nearest_school_km': round(nearest_school_dist, 2) if nearest_school_dist != float('inf') else None,
                'nearest_school_name': nearest_school_name
            }
            cells_with_distance.append(cell_with_info)
            
            # Отдельно собираем ячейки далеко от школ (>800м)
            if nearest_school_dist > 0.8:
                cells_without_schools.append(cell_with_info)
        
        return {
            'high_density_cells': cells_with_distance[:30],  # С расстоянием!
            'cells_without_schools': cells_without_schools,
            'districts_stats': districts_stats,
            'total_schools': len(schools),
            'total_students': sum(s.get('total_students', 0) for s in schools),
            'total_capacity': sum(s.get('capacity', 0) for s in schools),
            'ml_forecast': ml_forecast,
            'growth_factor': growth_factor,
            'grid_cells_all': grid_cells_full,
            'schools': schools
        }
    
    def _haversine_distance(self, lat1, lon1, lat2, lon2) -> float:
        """Расстояние между двумя точками в км"""
        import math
        R = 6371  # Радиус Земли в км
        
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c
    
    def generate_recommendations(
        self,
        analysis_data: Dict,
        district_filter: str = None
    ) -> Dict:
        """
        Генерация AI-рекомендаций через Gemini.
        ВАЖНО: Координаты берутся ТОЛЬКО из реальных данных сетки!
        AI только анализирует и приоритизирует.
        """
        
        print("🤖 Генерация AI-рекомендаций по строительству школ...")
        
        # Фильтруем по району если нужно
        if district_filter:
            analysis_data['high_density_cells'] = [
                c for c in analysis_data['high_density_cells']
                if district_filter.lower() in c.get('district', '').lower()
            ]
            analysis_data['cells_without_schools'] = [
                c for c in analysis_data['cells_without_schools']
                if district_filter.lower() in c.get('district', '').lower()
            ]
        
        # Получаем ячейки для рекомендаций (реальные координаты!)
        candidate_cells = analysis_data.get('cells_without_schools', [])
        
        # Если мало ячеек без школ, добавляем из высокой плотности
        if len(candidate_cells) < 5:
            candidate_cells.extend(analysis_data.get('high_density_cells', [])[:10])
        
        # Используем алгоритмический подход для базовых рекомендаций
        # с РЕАЛЬНЫМИ координатами из данных
        base_recommendations = self._generate_smart_recommendations(
            candidate_cells, 
            analysis_data
        )
        
        # Спрашиваем AI для обогащения анализа и описаний
        try:
            enriched = self._enrich_with_ai(base_recommendations, analysis_data, district_filter)
            
            # Добавляем статистику по районам
            districts_stats = analysis_data.get('districts_stats', {})
            by_district_stats = {}
            for district, stats in districts_stats.items():
                deficit = stats.get('total_students', 0) - stats.get('total_capacity', 0)
                occupancy = round(stats['total_students'] / max(1, stats['total_capacity']) * 100) if stats['total_capacity'] > 0 else 0
                by_district_stats[district] = {
                    'schools': stats.get('schools_count', 0),
                    'students': stats.get('total_students', 0),
                    'capacity': stats.get('total_capacity', 0),
                    'deficit': max(0, deficit),
                    'occupancy': occupancy,
                    'critical_schools': len(stats.get('critical_schools', []))
                }
            
            total_deficit = analysis_data['total_students'] - analysis_data['total_capacity']
            avg_occupancy = round(analysis_data['total_students'] / max(1, analysis_data['total_capacity']) * 100) if analysis_data['total_capacity'] > 0 else 0
            
            return {
                'success': True,
                'generated_at': datetime.now().isoformat(),
                'district_filter': district_filter,
                'recommendations': enriched,
                'statistics': {
                    'total_schools': analysis_data['total_schools'],
                    'total_students': analysis_data['total_students'],
                    'total_capacity': analysis_data['total_capacity'],
                    'total_deficit': max(0, total_deficit),
                    'avg_occupancy': avg_occupancy,
                    'by_district': by_district_stats
                },
                'analysis_summary': {
                    'high_density_cells_count': len(analysis_data.get('high_density_cells', [])),
                    'cells_without_schools': len(analysis_data.get('cells_without_schools', [])),
                    'total_schools': analysis_data['total_schools'],
                    'total_deficit': total_deficit
                }
            }
            
        except Exception as e:
            print(f"⚠️ AI обогащение не удалось, используем базовые: {e}")
            
            # Добавляем статистику по районам даже при ошибке AI
            districts_stats = analysis_data.get('districts_stats', {})
            by_district_stats = {}
            for district, stats in districts_stats.items():
                deficit = stats.get('total_students', 0) - stats.get('total_capacity', 0)
                occupancy = round(stats['total_students'] / max(1, stats['total_capacity']) * 100) if stats['total_capacity'] > 0 else 0
                by_district_stats[district] = {
                    'schools': stats.get('schools_count', 0),
                    'students': stats.get('total_students', 0),
                    'capacity': stats.get('total_capacity', 0),
                    'deficit': max(0, deficit),
                    'occupancy': occupancy,
                    'critical_schools': len(stats.get('critical_schools', []))
                }
            
            total_deficit = analysis_data['total_students'] - analysis_data['total_capacity']
            avg_occupancy = round(analysis_data['total_students'] / max(1, analysis_data['total_capacity']) * 100) if analysis_data['total_capacity'] > 0 else 0
            
            return {
                'success': True,
                'generated_at': datetime.now().isoformat(),
                'district_filter': district_filter,
                'recommendations': {
                    'summary': f"Анализ выявил {len(base_recommendations)} приоритетных зон для строительства школ.",
                    'priority_district': self._get_priority_district(analysis_data),
                    'total_schools_needed': len(base_recommendations),
                    'recommendations': base_recommendations
                },
                'statistics': {
                    'total_schools': analysis_data['total_schools'],
                    'total_students': analysis_data['total_students'],
                    'total_capacity': analysis_data['total_capacity'],
                    'total_deficit': max(0, total_deficit),
                    'avg_occupancy': avg_occupancy,
                    'by_district': by_district_stats
                },
                'analysis_summary': {
                    'high_density_cells_count': len(analysis_data.get('high_density_cells', [])),
                    'cells_without_schools': len(analysis_data.get('cells_without_schools', [])),
                    'total_schools': analysis_data['total_schools'],
                    'total_deficit': total_deficit
                }
            }
    
    def _generate_smart_recommendations(self, candidate_cells: List[Dict], analysis_data: Dict) -> List[Dict]:
        """
        Генерация рекомендаций с РЕАЛЬНЫМИ координатами из сетки.
        Использует алгоритм выбора лучших локаций.
        ИСКЛЮЧАЕТ запрещённые зоны (парки, промзоны и т.д.)
        """
        
        if not candidate_cells:
            return []
        
        # Фильтруем запрещённые зоны
        valid_cells = [c for c in candidate_cells if not c.get('in_restricted_zone', False)]
        
        if not valid_cells:
            print("⚠️ Все ячейки в запрещённых зонах, используем исходные")
            valid_cells = candidate_cells
        else:
            excluded = len(candidate_cells) - len(valid_cells)
            if excluded > 0:
                print(f"🚫 Исключено {excluded} ячеек в запрещённых зонах (парки, промзоны и т.д.)")
        
        # Сортируем по приоритету: плотность * расстояние до школы
        scored_cells = []
        for cell in valid_cells:
            density = cell.get('density', 0)
            nearest_school = cell.get('nearest_school_km') or 1  # Если None, считаем 1 км
            population = cell.get('population', 0)
            
            # Чем выше плотность и дальше от школы - тем выше приоритет
            score = density * (nearest_school ** 1.5) * (population / 1000)
            
            scored_cells.append({
                **cell,
                'score': score
            })
        
        # Сортируем по убыванию score
        scored_cells.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        # Фильтруем близко расположенные (не строить школы ближе 600м друг к другу)
        selected = []
        for cell in scored_cells:
            too_close = False
            for existing in selected:
                dist = self._haversine_distance(
                    cell['lat'], cell['lng'],
                    existing['lat'], existing['lng']
                )
                if dist < 0.6:  # 600м
                    too_close = True
                    break
            
            if not too_close:
                selected.append(cell)
                if len(selected) >= 5:
                    break
        
        growth_factor = analysis_data.get('growth_factor', 1.05)
        grid_cells_full = analysis_data.get('grid_cells_all', [])
        schools_catalog = analysis_data.get('schools', [])

        # Формируем рекомендации
        recommendations = []
        for i, cell in enumerate(selected, 1):
            density = cell.get('density', 0)
            
            # Определяем приоритет
            if density > 15000 or cell.get('nearest_school_km', 0) > 1.5:
                priority = 'critical'
            elif density > 10000 or cell.get('nearest_school_km', 0) > 1.0:
                priority = 'high'
            else:
                priority = 'medium'
            
            # Рассчитываем вместимость и показатели заполнения
            student_snapshot = {
                'current': cell.get('students_current'),
                'projected': cell.get('students_projected')
            }
            if not student_snapshot['current']:
                student_snapshot = self._estimate_students(cell.get('population', 0), growth_factor)

            estimated_students = student_snapshot['projected']
            recommended_capacity = min(1500, max(500, estimated_students))

            quarter_summary = self._summarize_quarter_cells(cell, grid_cells_full)
            nearest_schools = self._get_nearest_schools(cell['lat'], cell['lng'], schools_catalog, top_k=3)
            traffic_assessment = self._build_traffic_assessment(cell, recommended_capacity, quarter_summary)
            land_use = self._evaluate_land_use(cell, recommended_capacity)
            contextual = self._build_contextual_factors(cell, recommended_capacity, analysis_data)
            coverage_gap = max(0, student_snapshot['projected'] - recommended_capacity)
            
            # Расстояние до ближайшей школы
            nearest_km = cell.get('nearest_school_km')
            nearest_school = cell.get('nearest_school_name', 'неизвестна')
            distance_text = f"{nearest_km} км" if nearest_km else "нет данных"
            
            recommendations.append({
                'id': i,
                'location': {
                    'lat': cell['lat'],
                    'lng': cell['lng'],
                    'address_hint': f"Зона высокой плотности ({cell.get('district', 'район')})"
                },
                'district': cell.get('district', 'Неизвестно'),
                'priority': priority,
                'recommended_capacity': recommended_capacity,
                'reason': f"Плотность населения {density:,} чел/км², ближайшая школа ({nearest_school}) в {distance_text}",
                'nearby_density': density,
                'estimated_students': estimated_students,
                'nearest_school_km': nearest_km,
                'nearest_school_name': nearest_school,
                'catchment_model': {
                    'students_current': student_snapshot['current'],
                    'students_projected': student_snapshot['projected'],
                    'coverage_gap': coverage_gap,
                    'microdistrict_breakdown': quarter_summary,
                    'nearest_schools': nearest_schools
                },
                'traffic_safety_assessment': traffic_assessment,
                'land_use_compliance': land_use,
                'contextual_factors': contextual
            })
        
        return recommendations
    
    def _get_priority_district(self, data: Dict) -> str:
        """Определение приоритетного района"""
        districts_stats = data.get('districts_stats', {})
        
        max_deficit_district = None
        max_deficit = 0
        
        for district, stats in districts_stats.items():
            deficit = stats.get('total_students', 0) - stats.get('total_capacity', 0)
            if deficit > max_deficit:
                max_deficit = deficit
                max_deficit_district = district
        
        return max_deficit_district or "Не определён"
    
    def _enrich_with_ai(self, recommendations: List[Dict], analysis_data: Dict, district_filter: str = None) -> Dict:
        """
        Обогащение рекомендаций через AI.
        AI НЕ меняет координаты, только добавляет анализ!
        """
        
        district_text = f"для района {district_filter}" if district_filter else "для города Бишкек"
        
        # Формируем краткий промпт только для анализа
        locations_info = []
        for rec in recommendations:
            locations_info.append(
                f"- ID {rec['id']}: координаты ({rec['location']['lat']:.4f}, {rec['location']['lng']:.4f}), "
                f"район {rec['district']}, плотность {rec['nearby_density']:,} чел/км²"
            )
        
        prompt = f"""
Ты - эксперт по городскому планированию Бишкека.

ДАННЫЕ:
- Всего школ: {analysis_data['total_schools']}
- Дефицит мест: {analysis_data['total_students'] - analysis_data['total_capacity']:,}

ВЫБРАННЫЕ ЛОКАЦИИ ДЛЯ НОВЫХ ШКОЛ (координаты ЗАФИКСИРОВАНЫ, НЕ МЕНЯЙ):
{chr(10).join(locations_info)}

ЗАДАЧА: Напиши краткий анализ {district_text}. 
НЕ МЕНЯЙ координаты! Только проанализируй и определи приоритетный район.

ОТВЕТ В JSON:
{{
    "summary": "Краткий анализ ситуации (2-3 предложения)",
    "priority_district": "Название приоритетного района",
    "additional_insights": ["наблюдение 1", "наблюдение 2"]
}}

Верни ТОЛЬКО JSON без markdown.
"""
        
        response = self.model.generate_content(prompt)
        ai_analysis = self._parse_response(response.text)
        
        # Объединяем AI анализ с нашими рекомендациями (координаты неизменны!)
        return {
            'summary': ai_analysis.get('summary', f"Выявлено {len(recommendations)} приоритетных зон."),
            'priority_district': ai_analysis.get('priority_district', self._get_priority_district(analysis_data)),
            'total_schools_needed': len(recommendations),
            'total_places_needed': sum(r['recommended_capacity'] for r in recommendations),
            'recommendations': recommendations,  # НАШИ рекомендации с реальными координатами!
            'additional_insights': ai_analysis.get('additional_insights', [])
        }
    
    def _parse_response(self, response_text: str) -> Dict:
        """Парсинг ответа Gemini"""
        
        # Убираем markdown если есть
        text = response_text.strip()
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        if text.endswith('```'):
            text = text[:-3]
        
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError as e:
            print(f"⚠️ Ошибка парсинга JSON: {e}")
            print(f"Ответ: {text[:500]}...")
            
            # Пробуем найти JSON в тексте
            import re
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except:
                    pass
            
            return {
                'summary': 'Не удалось распарсить ответ AI',
                'raw_response': response_text[:1000],
                'recommendations': []
            }
    
    def _generate_fallback(self, data: Dict) -> List[Dict]:
        """Генерация fallback рекомендаций без AI"""
        
        recommendations = []
        
        # Берём ячейки без школ и создаём рекомендации
        for i, cell in enumerate(data.get('cells_without_schools', [])[:5], 1):
            recommendations.append({
                'id': i,
                'location': {
                    'lat': cell['lat'],
                    'lng': cell['lng'],
                    'address_hint': f"Зона высокой плотности в {cell.get('district', 'неизвестном районе')}"
                },
                'district': cell.get('district', 'Неизвестно'),
                'priority': 'high' if cell['density'] > 10000 else 'medium',
                'recommended_capacity': min(1500, int(cell['population'] * 0.15)),
                'reason': f"Плотность {cell['density']:,} чел/км², ближайшая школа в {cell['nearest_school_km']} км",
                'nearby_density': cell['density'],
                'estimated_students': int(cell['population'] * 0.15)
            })
        
        return recommendations


# Синглтон для использования в views
_ai_service = None

def get_ai_recommendations_service() -> AIRecommendationsService:
    """Получить экземпляр сервиса AI рекомендаций"""
    global _ai_service
    if _ai_service is None:
        _ai_service = AIRecommendationsService()
    return _ai_service
