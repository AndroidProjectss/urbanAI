"""
Grid Service - Сервис для расчета плотности населения по сетке 500x500м

КАЛИБРОВКА ПОД РЕАЛЬНЫЕ ДАННЫЕ ПЕРЕПИСИ 2024:
=========================================
Официальная перепись (2024):
- Общее население Бишкека: 1,103,562
  • Октябрьский район: 316,745
  • Первомайский район: 237,385  
  • Свердловский район: 283,981
  • Ленинский район: 265,451

Целевое население: ~1,350,000 (с учетом пригородов и жилмассивов)
"""

import math
from typing import List, Dict, Tuple, Optional


# ============================================================================
# КОНСТАНТЫ ДЛЯ РАСЧЕТА НАСЕЛЕНИЯ
# ============================================================================

# Размер ячейки сетки в градусах (500м × 500м)
GRID_SIZE_LAT = 0.0045  # ~500м по широте
GRID_SIZE_LNG = 0.006   # ~500м по долготе
GRID_AREA_KM2 = 0.25    # Площадь ячейки = 0.5км × 0.5км = 0.25 км²

# Коэффициент полезной площади (вычитаем стены, подъезды)
K_USEFUL_AREA = 0.72

# ЦЕЛЕВОЕ НАСЕЛЕНИЕ по районам (перепись 2024 + прирост)
TARGET_POPULATION = {
    'Октябрьский район': 320000,
    'Первомайский район': 240000,
    'Свердловский район': 290000,
    'Ленинский район': 270000,
}
TOTAL_TARGET_POPULATION = 1350000

# Пороги плотности для визуализации (чел/км²)
# <1500 — зеленый, 1500-6000 — желтый, 6000-10000 — оранжевый,
# 10000-20000 — красный, >20000 — фиолетовый
DENSITY_THRESHOLDS = {
    'green': 1500,
    'yellow': 6000,
    'orange': 10000,
    'red': 20000
}


class GridService:
    """
    Сервис для работы с сеткой плотности населения.
    Разбивает город на ячейки 500x500м и считает население/плотность для каждой.
    """
    
    @staticmethod
    def calculate_building_population(
        building_type: str,
        levels: Optional[int],
        area_m2: float,
        tags: Dict = None
    ) -> Tuple[str, int, int]:
        """
        Рассчитать население здания по УЛУЧШЕННОЙ ФОРМУЛЕ для Бишкека.
        
        Args:
            building_type: Тип здания из OSM (apartments, residential, house, etc.)
            levels: Количество этажей (может быть None)
            area_m2: Площадь основания в м²
            tags: Дополнительные теги OSM
        
        Returns:
            Tuple[category, levels, population]
            - category: Категория здания (elite, soviet, private, etc.)
            - levels: Количество этажей (определенное или оцененное)
            - population: Расчетное население
        """
        tags = tags or {}
        
        # 1. ОПРЕДЕЛЯЕМ ЭТАЖНОСТЬ (если не указана в OSM)
        if levels is None:
            if building_type == 'apartments':
                # Многоквартирный дом - оцениваем по площади основания
                if area_m2 > 1500:
                    levels = 12  # Большой дом - высотка
                elif area_m2 > 800:
                    levels = 9   # Средний большой - 9-этажка
                elif area_m2 > 400:
                    levels = 5   # Средний - хрущевка
                else:
                    levels = 4   # Маленький МКД
            elif building_type in ['house', 'residential']:
                # Частный сектор
                if area_m2 > 200:
                    levels = 2   # Большой частный дом
                else:
                    levels = 1   # Обычный частный дом
            else:
                # Неизвестный тип - оцениваем по площади
                if area_m2 < 200:
                    levels = 1
                elif area_m2 < 400:
                    levels = 2
                else:
                    levels = 4
        
        # 2. ОПРЕДЕЛЯЕМ КАТЕГОРИЮ И ПЛОТНОСТЬ ЗАСЕЛЕНИЯ
        name = tags.get('name', '').lower()
        
        # Частные дома (1-2 этажа)
        if levels <= 2:
            category = 'private'
            
            # Частный сектор в Бишкеке - семьи 3-6 человек
            if area_m2 < 60:
                population = 3
            elif area_m2 < 100:
                population = 4
            elif area_m2 < 150:
                population = 5
            elif area_m2 < 250:
                population = 6
            else:
                population = 7
        
        # Многоэтажки (3+ этажей)
        else:
            # Определяем тип по этажности и названию
            if any(word in name for word in ['элит', 'премиум', 'люкс', 'бизнес', 'резиденс', 'комфорт']):
                category = 'elite'
                sqm_per_person = 30  # Элитки - меньше людей
            elif levels >= 12:
                category = 'high_rise'
                sqm_per_person = 24  # Высотки 12+
            elif levels >= 9:
                category = 'soviet_high'
                sqm_per_person = 22  # Советские 9-этажки
            elif levels >= 6:
                category = 'mid_rise'
                sqm_per_person = 22  # 6-8 этажей
            elif levels >= 4:
                category = 'soviet'
                sqm_per_person = 22  # Хрущевки 4-5 этажей
            else:
                category = 'low_rise'
                sqm_per_person = 24  # 3 этажа
            
            # Формула для многоэтажек:
            # Население = (Площадь × Этажи × K_USEFUL_AREA) / м²_на_человека
            total_living_area = area_m2 * levels * K_USEFUL_AREA
            population = int(total_living_area / sqm_per_person)
        
        # Ограничения: минимум 2, максимум 800 человек на здание
        population = max(2, min(population, 800))
        
        return category, levels, population
    
    @staticmethod
    def create_population_grid(
        buildings: List[Dict],
        districts: List[Dict] = None
    ) -> Dict:
        """
        Создать сетку плотности населения 500x500м.
        
        Args:
            buildings: Список зданий с координатами и данными
            districts: Список районов для привязки "бесхозных" зданий
        
        Returns:
            Dict с:
            - grid_cells: список ячеек сетки с данными
            - total_population: общее население
            - stats: статистика по категориям
            - districts_population: население по районам (если переданы)
        """
        print("📊 Создаем сетку плотности населения 500×500м...")
        
        # Словарь для группировки зданий по ячейкам
        grid = {}
        
        # Статистика
        stats = {
            'total_buildings': 0,
            'total_population': 0,
            'by_category': {},
            'with_levels_data': 0,
            'estimated_levels': 0,
            'buildings_in_districts': 0,
            'buildings_outside_districts': 0
        }
        
        # Население по районам
        districts_population = {}
        if districts:
            for d in districts:
                districts_population[d['name']] = {
                    'population': 0,
                    'buildings': 0,
                    'area_km2': 0
                }
        
        # Обрабатываем каждое здание
        for building in buildings:
            lat = building['lat']
            lng = building['lng']
            
            # Данные здания
            building_type = building.get('building_type', 'yes')
            levels_str = building.get('levels')
            area_m2 = building.get('area_m2', 100)
            has_levels = building.get('has_levels_data', False)
            
            # Парсим этажность
            levels = None
            if levels_str:
                try:
                    levels = int(float(levels_str))
                except (ValueError, TypeError):
                    pass
            
            # Рассчитываем население
            category, final_levels, population = GridService.calculate_building_population(
                building_type, levels, area_m2, building.get('tags', {})
            )
            
            # Обновляем статистику
            stats['total_buildings'] += 1
            stats['total_population'] += population
            stats['by_category'][category] = stats['by_category'].get(category, 0) + 1
            
            if has_levels:
                stats['with_levels_data'] += 1
            else:
                stats['estimated_levels'] += 1
            
            # Определяем ячейку сетки
            grid_lat = round(lat / GRID_SIZE_LAT) * GRID_SIZE_LAT
            grid_lng = round(lng / GRID_SIZE_LNG) * GRID_SIZE_LNG
            grid_key = (round(grid_lat, 6), round(grid_lng, 6))
            
            if grid_key not in grid:
                grid[grid_key] = {
                    'lat': grid_lat,
                    'lng': grid_lng,
                    'population': 0,
                    'buildings_count': 0,
                    'total_levels': 0,
                    'total_area': 0,
                    'categories': {},
                    'with_levels_data': 0,
                    'district': None
                }
            
            cell = grid[grid_key]
            cell['population'] += population
            cell['buildings_count'] += 1
            cell['total_levels'] += final_levels
            cell['total_area'] += area_m2
            cell['categories'][category] = cell['categories'].get(category, 0) + 1
            if has_levels:
                cell['with_levels_data'] += 1
            
            # Привязываем к району
            if districts and cell['district'] is None:
                district_name = GridService._find_nearest_district(lat, lng, districts)
                cell['district'] = district_name
            
            # Обновляем статистику района
            if cell['district'] and cell['district'] in districts_population:
                # Добавляем население только при первой привязке здания
                pass  # Будем считать позже по ячейкам
        
        # ═══════════════════════════════════════════════════════════
        # КАЛИБРОВКА: Подгоняем под целевое население 1.35 млн
        # ═══════════════════════════════════════════════════════════
        raw_total = stats['total_population']
        if raw_total > 0:
            calibration_factor = TOTAL_TARGET_POPULATION / raw_total
        else:
            calibration_factor = 1.0
        
        print(f"\n🔧 КАЛИБРОВКА НАСЕЛЕНИЯ:")
        print(f"   Сырое население: {raw_total:,}")
        print(f"   Целевое население: {TOTAL_TARGET_POPULATION:,}")
        print(f"   Коэффициент калибровки: {calibration_factor:.3f}")
        
        # Формируем результат - список ячеек с плотностью
        grid_cells = []
        calibrated_total = 0
        
        for (grid_lat, grid_lng), cell in grid.items():
            if cell['buildings_count'] == 0:
                continue
            
            # Применяем калибровку
            calibrated_population = int(cell['population'] * calibration_factor)
            calibrated_total += calibrated_population
            
            # Плотность = население / площадь ячейки (0.25 км²)
            density = int(calibrated_population / GRID_AREA_KM2)
            
            # Средняя этажность
            avg_levels = cell['total_levels'] / cell['buildings_count']
            
            # Определяем цвет по новым порогам плотности
            if density < DENSITY_THRESHOLDS['green']:
                color = 'green'
                color_hex = '#00B050'
            elif density < DENSITY_THRESHOLDS['yellow']:
                color = 'yellow'
                color_hex = '#F4D03F'
            elif density < DENSITY_THRESHOLDS['orange']:
                color = 'orange'
                color_hex = '#FF8C00'
            elif density < DENSITY_THRESHOLDS['red']:
                color = 'red'
                color_hex = '#FF3B30'
            else:
                color = 'purple'
                color_hex = '#7E57C2'
            
            # Определяем доминирующую категорию
            dominant_cat = max(cell['categories'].items(), key=lambda x: x[1])[0] if cell['categories'] else 'unknown'
            
            grid_cell = {
                'lat': grid_lat,
                'lng': grid_lng,
                'population': calibrated_population,
                'density': density,  # чел/км²
                'buildings_count': cell['buildings_count'],
                'avg_levels': round(avg_levels, 1),
                'avg_area': round(cell['total_area'] / cell['buildings_count'], 0),
                'dominant_category': dominant_cat,
                'categories': cell['categories'],
                'with_levels_data': cell['with_levels_data'],
                'color': color,
                'color_hex': color_hex,
                'district': cell['district']
            }
            
            grid_cells.append(grid_cell)
            
            # Обновляем статистику района (с калибровкой!)
            if cell['district'] and cell['district'] in districts_population:
                districts_population[cell['district']]['population'] += calibrated_population
                districts_population[cell['district']]['buildings'] += cell['buildings_count']
        
        # Обновляем общую статистику на откалиброванные значения
        stats['total_population'] = calibrated_total
        
        # Проверяем "бесхозные" здания
        buildings_with_district = sum(1 for c in grid_cells if c['district'])
        buildings_without = len(grid_cells) - buildings_with_district
        stats['buildings_in_districts'] = buildings_with_district
        stats['buildings_outside_districts'] = buildings_without
        
        # Сортируем по плотности (для визуализации)
        grid_cells.sort(key=lambda x: -x['density'])
        
        # ═══════════════════════════════════════════════════════════
        # ИНТЕРПОЛЯЦИЯ: Заполняем пустые ячейки внутри районов
        # ═══════════════════════════════════════════════════════════
        if districts:
            print(f"\n🔲 ИНТЕРПОЛЯЦИЯ ПУСТЫХ ЯЧЕЕК...")
            existing_cells = set((c['lat'], c['lng']) for c in grid_cells)
            
            # Границы города (Бишкек)
            min_lat, max_lat = 42.78, 42.95
            min_lng, max_lng = 74.48, 74.72
            
            # Средняя плотность для каждого района
            district_avg_density = {}
            for name, data in districts_population.items():
                if data['population'] > 0:
                    # Примерная площадь района (грубо)
                    area_km2 = max(data['buildings'] * 0.05, 10)  # минимум 10 км²
                    district_avg_density[name] = data['population'] / area_km2
                else:
                    district_avg_density[name] = 500  # Минимальная плотность по умолчанию
            
            interpolated_cells = []
            lat = min_lat
            while lat <= max_lat:
                lng = min_lng
                while lng <= max_lng:
                    grid_lat = round(lat / GRID_SIZE_LAT) * GRID_SIZE_LAT
                    grid_lng = round(lng / GRID_SIZE_LNG) * GRID_SIZE_LNG
                    grid_key = (round(grid_lat, 6), round(grid_lng, 6))
                    
                    # Пропускаем если уже есть ячейка
                    if grid_key not in existing_cells:
                        # Определяем район
                        district_name = GridService._find_nearest_district(grid_lat, grid_lng, districts)
                        
                        if district_name:
                            # Оценочная плотность = средняя по району * 0.3 (частный сектор)
                            avg_dens = district_avg_density.get(district_name, 500)
                            estimated_density = int(avg_dens * 0.3)  # Низкая плотность
                            
                            if estimated_density < 100:
                                estimated_density = 100  # Минимум 100 чел/км² внутри города
                            
                            estimated_population = int(estimated_density * GRID_AREA_KM2)
                            
                            # Цвет по плотности
                            if estimated_density < DENSITY_THRESHOLDS['green']:
                                color, color_hex = 'green', '#00B050'
                            elif estimated_density < DENSITY_THRESHOLDS['yellow']:
                                color, color_hex = 'yellow', '#F4D03F'
                            else:
                                color, color_hex = 'orange', '#FF8C00'
                            
                            interpolated_cell = {
                                'lat': grid_lat,
                                'lng': grid_lng,
                                'population': estimated_population,
                                'density': estimated_density,
                                'buildings_count': 0,
                                'avg_levels': 1.0,
                                'avg_area': 0,
                                'dominant_category': 'estimated',
                                'categories': {'estimated': 1},
                                'with_levels_data': 0,
                                'color': color,
                                'color_hex': color_hex,
                                'district': district_name,
                                'interpolated': True
                            }
                            interpolated_cells.append(interpolated_cell)
                            existing_cells.add(grid_key)
                    
                    lng += GRID_SIZE_LNG
                lat += GRID_SIZE_LAT
            
            grid_cells.extend(interpolated_cells)
            print(f"   Добавлено интерполированных ячеек: {len(interpolated_cells)}")
        
        print(f"\n📊 СТАТИСТИКА СЕТКИ ПЛОТНОСТИ:")
        print(f"   ═══════════════════════════════════════")
        print(f"   📦 Ячеек сетки (500×500м): {len(grid_cells)}")
        print(f"   🏠 Всего зданий: {stats['total_buildings']:,}")
        print(f"   👥 ОТКАЛИБРОВАННОЕ НАСЕЛЕНИЕ: ~{calibrated_total:,} чел.")
        print(f"   📍 С данными OSM об этажах: {stats['with_levels_data']:,}")
        print(f"   📐 Оценено по площади: {stats['estimated_levels']:,}")
        print(f"   ───────────────────────────────────────")
        print(f"   📊 По категориям:")
        for cat, count in sorted(stats['by_category'].items(), key=lambda x: -x[1]):
            print(f"      • {cat}: {count:,} зданий")
        print(f"   ═══════════════════════════════════════\n")
        
        if districts_population:
            print(f"   📊 НАСЕЛЕНИЕ ПО РАЙОНАМ (откалибровано):")
            total_in_districts = 0
            for name, data in districts_population.items():
                print(f"      • {name}: ~{data['population']:,} чел. ({data['buildings']} зданий)")
                total_in_districts += data['population']
            print(f"   ───────────────────────────────────────")
            print(f"   📍 В районах: ~{total_in_districts:,} чел.")
            print(f"   📍 За пределами: ~{calibrated_total - total_in_districts:,} чел.")
            print(f"   ═══════════════════════════════════════\n")
        
        return {
            'grid_cells': grid_cells,
            'total_population': calibrated_total,
            'stats': stats,
            'districts_population': districts_population
        }
    
    @staticmethod
    def _find_nearest_district(lat: float, lng: float, districts: List[Dict]) -> Optional[str]:
        """
        Найти ближайший район для координат.
        Используется для привязки "бесхозных" зданий.
        """
        if not districts:
            return None
        
        min_distance = float('inf')
        nearest_district = None
        
        for district in districts:
            # Проверяем, находится ли точка внутри полигона района
            if GridService._point_in_district(lat, lng, district):
                return district['name']
            
            # Если нет - ищем ближайший центр района
            dist_lat = district.get('lat', 0)
            dist_lng = district.get('lng', 0)
            
            distance = GridService._haversine_distance(lat, lng, dist_lat, dist_lng)
            
            if distance < min_distance:
                min_distance = distance
                nearest_district = district['name']
        
        # Возвращаем ближайший, если он в пределах 5км
        if min_distance <= 5.0:
            return nearest_district
        
        return None
    
    @staticmethod
    def _point_in_district(lat: float, lng: float, district: Dict) -> bool:
        """Проверить, находится ли точка внутри полигона района."""
        geometry = district.get('geometry', [])
        if not geometry:
            # Если нет геометрии - проверяем по расстоянию до центра
            dist_lat = district.get('lat', 0)
            dist_lng = district.get('lng', 0)
            distance = GridService._haversine_distance(lat, lng, dist_lat, dist_lng)
            return distance <= 2.5  # В пределах 2.5км от центра
        
        # Проверяем каждый полигон
        for polygon in geometry:
            if GridService._point_in_polygon(lat, lng, polygon):
                return True
        
        return False
    
    @staticmethod
    def _point_in_polygon(lat: float, lng: float, polygon: List[Dict]) -> bool:
        """Ray casting алгоритм для проверки точки в полигоне."""
        if not polygon or len(polygon) < 3:
            return False
        
        n = len(polygon)
        inside = False
        
        j = n - 1
        for i in range(n):
            pi = polygon[i]
            pj = polygon[j]
            
            xi, yi = pi.get('lat', 0), pi.get('lng', 0)
            xj, yj = pj.get('lat', 0), pj.get('lng', 0)
            
            if ((yi > lng) != (yj > lng)) and (lat < (xj - xi) * (lng - yi) / (yj - yi) + xi):
                inside = not inside
            
            j = i
        
        return inside
    
    @staticmethod
    def _haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Расстояние между двумя точками в километрах (формула гаверсинуса)."""
        R = 6371  # Радиус Земли в км
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        
        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlng/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    @staticmethod
    def generate_heatmap_from_grid(grid_cells: List[Dict]) -> List[Dict]:
        """
        Генерировать точки тепловой карты из сетки.
        
        Каждая ячейка сетки становится точкой с весом пропорциональным плотности.
        """
        heatmap_points = []
        
        for cell in grid_cells:
            # Интенсивность на основе плотности (логарифмическая шкала)
            density = cell['density']
            
            # Нормализация: логарифм от плотности
            if density > 0:
                # log10(20000) ≈ 4.3, log10(4000) ≈ 3.6, log10(1000) ≈ 3
                intensity = min(math.log10(density + 1) / 1.2, 4.0)
            else:
                intensity = 0.1
            
            heatmap_points.append({
                'lat': cell['lat'],
                'lng': cell['lng'],
                'weight': max(intensity, 0.1)
            })
        
        print(f"🔥 Сгенерировано {len(heatmap_points)} точек heatmap из сетки")
        
        return heatmap_points
    
    @staticmethod
    def calculate_polygon_area_km2(polygon: List[Dict]) -> float:
        """Приблизительная площадь полигона в км² (метод Гаусса с учетом широты)."""
        if not polygon or len(polygon) < 3:
            return 0.0
        avg_lat = sum(point.get('lat', 0) for point in polygon) / len(polygon)
        avg_lng = sum(point.get('lng', 0) for point in polygon) / len(polygon)
        # Переводим градусы в километры (учитывая сжатие меридианов)
        lat_factor = 110.574  # км на градус широты
        lng_factor = 111.320 * math.cos(math.radians(avg_lat))  # км на градус долготы
        points = []
        for pt in polygon:
            x = (pt.get('lng', avg_lng) - avg_lng) * lng_factor
            y = (pt.get('lat', avg_lat) - avg_lat) * lat_factor
            points.append((x, y))
        area = 0.0
        n = len(points)
        for i in range(n):
            x1, y1 = points[i]
            x2, y2 = points[(i + 1) % n]
            area += x1 * y2 - x2 * y1
        return abs(area) / 2.0
    
    @staticmethod
    def calculate_geometry_area_km2(geometry: List[List[Dict]]) -> float:
        """Площадь мультиполигона (сумма всех полигонов) в км²."""
        if not geometry:
            return 0.0
        total_area = 0.0
        for polygon in geometry:
            total_area += GridService.calculate_polygon_area_km2(polygon)
        return total_area
    
    @staticmethod
    def get_cell_info(grid_cells: List[Dict], lat: float, lng: float) -> Optional[Dict]:
        """
        Получить информацию о ячейке по координатам.
        Для отображения при клике на карту.
        """
        # Находим ближайшую ячейку
        grid_lat = round(lat / GRID_SIZE_LAT) * GRID_SIZE_LAT
        grid_lng = round(lng / GRID_SIZE_LNG) * GRID_SIZE_LNG
        
        for cell in grid_cells:
            if abs(cell['lat'] - grid_lat) < 0.0001 and abs(cell['lng'] - grid_lng) < 0.0001:
                return cell
        
        return None
