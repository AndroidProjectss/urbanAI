from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from rest_framework.response import Response
from datetime import datetime
from .services import OpenStreetMapService, GeminiService, PopulationService
from .models import BuildingRequest, PopulationData, School
from .enhanced_gemini_service import EnhancedGeminiService
from .grid_service import GridService
from .ml_service import (
    get_forecaster,
    SchoolDemandForecaster,
    BISHKEK_POPULATION_2022,
    POPULATION_BY_GRADE_2022,
    TOTAL_SCHOOL_AGE_POPULATION_2022,
    get_cohort_projection,
    get_demographic_trends,
    calculate_total_projected_students,
    # Данные о населении
    BISHKEK_TOTAL_POPULATION,
    DEMOGRAPHIC_RATES,
    AGE_STRUCTURE_2022,
    forecast_total_population,
    forecast_population_detailed,
    get_population_pyramid,
    get_population_by_age_groups,
    # Реальные данные о естественном приросте
    NATURAL_POPULATION_GROWTH,
    analyze_natural_growth_trends,
    get_adjusted_growth_rate,
    # ML модель прогнозирования населения
    get_population_forecaster,
    PopulationForecaster,
)
import json
import random

def index(request):
    """Главная страница"""
    return render(request, 'building_optimizer/index.html')

@csrf_exempt
@api_view(['GET'])
def get_population_heatmap(request):
    """API для получения тепловой карты населения"""
    city = request.GET.get('city', 'Бишкек')
    
    try:
        population_data_with_geometry = PopulationService.get_or_create_population_data(city)
        
        return Response({
            'success': True,
            'city': city,
            'districts': population_data_with_geometry
        })
    
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)

@csrf_exempt
@api_view(['GET'])
def get_enhanced_heatmap_data(request):
    """
    API для получения данных тепловой карты с РЕАЛЬНЫМ расчетом плотности населения.
    
    НОВАЯ СИСТЕМА (Grid System):
    1. Разбиваем город на квадраты 500x500м
    2. Считаем население для каждого здания по формуле
    3. Группируем в ячейки сетки
    4. Считаем плотность (чел/км²) для каждой ячейки
    5. Привязываем "бесхозные" здания к ближайшему району
    
    Формула населения:
    - Частные дома: 4-12 чел. в зависимости от площади
    - Многоэтажки: (Площадь × Этажи × 0.75) / м²_на_человека
      • Элитки: 25 м²/чел
      • Советские: 18 м²/чел
    - Итоговый коэффициент: ×0.85 (подгонка под Нацстатком)
    """
    city = request.GET.get('city', 'Бишкек')
    
    try:
        osm_service = OpenStreetMapService()
        
        print(f"\n{'='*60}")
        print(f"🏙️ ЗАГРУЗКА ДАННЫХ ДЛЯ ГОРОДА: {city}")
        print(f"{'='*60}\n")
        
        # 1. Получаем районы
        districts_data = osm_service.get_districts_in_city(city)

        # 2. Получаем жилые здания (сырые данные)
        residential_data = osm_service.get_residential_buildings_in_city(city)

        # 3. Получаем школы
        schools_data = osm_service.get_schools_in_city(city)

        # 4. Коммерческие объекты (опционально)
        commercial_data = osm_service.get_commercial_places_in_city(city)

        # ═══════════════════════════════════════════════════════════
        # 🆕 GRID SYSTEM: Создаем сетку плотности 500x500м
        # ═══════════════════════════════════════════════════════════
        
        print(f"\n{'='*60}")
        print(f"🔳 СОЗДАНИЕ СЕТКИ ПЛОТНОСТИ 500×500м")
        print(f"{'='*60}\n")
        
        grid_result = GridService.create_population_grid(
            buildings=residential_data,
            districts=districts_data
        )
        
        grid_cells = grid_result['grid_cells']
        total_population = grid_result['total_population']
        grid_stats = grid_result['stats']
        districts_population = grid_result['districts_population']

        # ═══════════════════════════════════════════════════════════
        # 🔥 HEATMAP: Генерируем точки из сетки
        # ═══════════════════════════════════════════════════════════

        heatmap_data = GridService.generate_heatmap_from_grid(grid_cells)

        # ═══════════════════════════════════════════════════════════
        # 📊 Обновляем плотность районов на основе Grid
        # ═══════════════════════════════════════════════════════════

        for district in districts_data:
            name = district['name']
            area_km2 = GridService.calculate_geometry_area_km2(district.get('geometry', []))
            district['area_km2'] = round(area_km2, 2) if area_km2 else None
            if name in districts_population:
                pop_data = districts_population[name]
                pop_data['area_km2'] = area_km2
                district['calculated_population'] = pop_data['population']
                district['buildings_count'] = pop_data['buildings']
                if area_km2 > 0:
                    district['population_density'] = int(pop_data['population'] / area_km2)
                else:
                    district['population_density'] = 0

        # ═══════════════════════════════════════════════════════════
        # 🚀 ОПТИМИЗАЦИЯ: Кластеризуем здания для маркеров
        # ═══════════════════════════════════════════════════════════

        clustered_buildings = osm_service.cluster_buildings_for_display(
            residential_data, grid_size=0.003
        )
        
        # ═══════════════════════════════════════════════════════════
        # 🏠 ВСЕ ЗДАНИЯ: Для клиентского кеша (без API запросов при scroll)
        # ═══════════════════════════════════════════════════════════
        
        all_buildings_cached = []
        for b in residential_data:
            building_type = b.get('building_type', 'residential')
            levels_str = b.get('levels')
            area_m2 = b.get('area_m2', 100)

            levels = None
            if levels_str:
                try:
                    levels = int(float(levels_str))
                except:
                    pass

            category, final_levels, population = GridService.calculate_building_population(
                building_type, levels, area_m2, b.get('tags', {})
            )

            all_buildings_cached.append({
                'lat': b.get('lat', 0),
                'lng': b.get('lng', 0),
                'building_type': building_type,
                'levels': final_levels,
                'has_levels_data': b.get('has_levels_data', False),
                'area_m2': area_m2,
                'population': population,
                'category': category,
                'name': b.get('name', ''),
                'address': b.get('address', '')
            })

        print(f"   🏠 Зданий для кеша: {len(all_buildings_cached)}")

        print(f"\n{'='*60}")
        print(f"✅ ДАННЫЕ ГОТОВЫ К ОТПРАВКЕ")
        print(f"{'='*60}")
        print(f"   📦 Ячеек сетки: {len(grid_cells)}")
        print(f"   🏠 Кластеров зданий: {len(clustered_buildings)}")
        print(f"   🔥 Точек heatmap: {len(heatmap_data)}")
        print(f"   👥 Общее население: ~{total_population:,} чел.")
        print(f"{'='*60}\n")
        
        return Response({
            'success': True,
            'city': city,
            'districts': districts_data,

            # 🆕 Grid System - ячейки сетки 500x500м
            'grid_cells': grid_cells,

            # Кластеры зданий для маркеров
            'residential_buildings': clustered_buildings,
            'raw_buildings_count': len(residential_data),

            # 🆕 ВСЕ здания для клиентского кеша (мгновенное отображение)
            'all_buildings': all_buildings_cached,

            # Школы и коммерция
            'schools': schools_data,
            'commercial_places': commercial_data,

            # Heatmap
            'heatmap_data': heatmap_data,

            # Статистика
            'stats': {
                'districts_count': len(districts_data),
                'residential_count': len(residential_data),
                'clusters_count': len(clustered_buildings),
                'grid_cells_count': len(grid_cells),
                'schools_count': len(schools_data),
                'heatmap_points': len(heatmap_data),
                'total_population': total_population,
                'buildings_with_levels': grid_stats['with_levels_data'],
                'buildings_estimated': grid_stats['estimated_levels'],
                'category_breakdown': grid_stats['by_category'],
                'districts_population': districts_population
            }
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)

@csrf_exempt
@api_view(['POST'])
def suggest_building_location(request):
    """API для предложения оптимального места размещения здания"""
    try:
        data = json.loads(request.body)
        building_type = data.get('building_type')
        city = data.get('city', 'Бишкек')
        
        if not building_type:
            return Response({
                'success': False,
                'error': 'Не указан тип здания'
            }, status=400)
        
        population_data = PopulationService.get_or_create_population_data(city)
        
        districts_for_ai = []
        for district in population_data:
            districts_for_ai.append({
                'name': district['district_name'],
                'lat': district['lat'],
                'lng': district['lng'],
                'population_density': district['population_density']
            })
        
        gemini_service = GeminiService()
        suggestion = gemini_service.get_building_suggestion(
            building_type, city, districts_for_ai
        )
        
        if not suggestion:
            return Response({
                'success': False,
                'error': 'Не удалось получить рекомендацию'
            }, status=500)
        
        building_request = BuildingRequest.objects.create(
            building_type=building_type,
            city=city,
            suggested_lat=suggestion['coordinates']['lat'],
            suggested_lng=suggestion['coordinates']['lng'],
            population_density=0,
            confidence_score=suggestion['confidence'],
            reasoning=suggestion['reasoning']
        )
        
        return Response({
            'success': True,
            'suggestion': {
                'district': suggestion['district'],
                'coordinates': {
                    'lat': suggestion['coordinates']['lat'],
                    'lng': suggestion['coordinates']['lng']
                },
                'confidence': suggestion['confidence'],
                'reasoning': suggestion['reasoning'],
                'building_type': building_type,
                'city': city
            }
        })
    
    except json.JSONDecodeError:
        return Response({
            'success': False,
            'error': 'Неверный формат JSON'
        }, status=400)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)

@csrf_exempt
@api_view(['POST'])
def analyze_districts(request):
    """НОВОЕ API: Анализ выбранных районов"""
    try:
        data = json.loads(request.body)
        selected_districts = data.get('districts', [])
        
        if not selected_districts:
            return Response({
                'success': False,
                'error': 'Не выбраны районы для анализа'
            }, status=400)
        
        # Получаем данные о районах
        osm_service = OpenStreetMapService()
        districts_data = osm_service.get_districts_in_city('Бишкек')
        schools_data = osm_service.get_schools_in_city('Бишкек')
        
        # Фильтруем только выбранные районы
        district_name_mapping = {
            'oktyabrsky': 'Октябрьский район',
            'pervomaisky': 'Первомайский район',
            'leninsky': 'Ленинский район',
            'sverdlovsky': 'Свердловский район'
        }
        
        selected_district_names = [district_name_mapping.get(d, d) for d in selected_districts]
        filtered_districts = [d for d in districts_data if d['name'] in selected_district_names]
        
        # Генерируем результаты анализа
        analysis_results = {
            'statistics': {
                'totalFacilities': len(schools_data),
                'avgDistance': round(random.uniform(1.2, 3.5), 1),
                'coveragePercent': random.randint(65, 95),
                'populationServed': sum([d['population_density'] for d in filtered_districts]) * random.randint(1, 3)
            },
            'charts': {
                'district': [random.randint(15, 35) for _ in range(4)],
                'accessibility': [random.randint(5, 25) for _ in range(5)],
                'time': [random.randint(45, 95) for _ in range(7)]
            },
            'districts_analyzed': len(filtered_districts),
            'schools_in_area': len([s for s in schools_data if any(
                abs(s['lat'] - d['lat']) < 0.05 and abs(s['lng'] - d['lng']) < 0.05 
                for d in filtered_districts
            )])
        }
        
        return Response({
            'success': True,
            'results': analysis_results
        })
    
    except json.JSONDecodeError:
        return Response({
            'success': False,
            'error': 'Неверный формат JSON'
        }, status=400)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)

@api_view(['GET'])
def get_building_history(request):
    """API для получения истории размещений"""
    try:
        requests_history = BuildingRequest.objects.all().order_by('-created_at')[:20]
        
        history_data = []
        for req in requests_history:
            history_data.append({
                'id': req.id,
                'building_type': req.get_building_type_display(),
                'city': req.city,
                'coordinates': {
                    'lat': req.suggested_lat,
                    'lng': req.suggested_lng
                },
                'confidence': req.confidence_score,
                'reasoning': req.reasoning,
                'created_at': req.created_at.isoformat()
            })
        
        return Response({
            'success': True,
            'history': history_data
        })
    
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)

@api_view(['GET'])
def get_schools(request):
    """API для получения данных о школах из OpenStreetMap"""
    city = request.GET.get('city', 'Бишкек')
    try:
        schools = OpenStreetMapService.get_schools_in_city(city)
        if schools:
            return Response({
                'success': True,
                'city': city,
                'schools': schools
            })
        else:
            return Response({
                'success': True,
                'city': city,
                'schools': [],
                'message': f"Школы не найдены в городе '{city}' или произошла ошибка при получении данных."
            })
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)

@api_view(['GET'])
def get_districts(request):
    """API для получения данных о районах города из OpenStreetMap с их геометрией."""
    city = request.GET.get('city', 'Бишкек')
    try:
        districts = OpenStreetMapService.get_districts_in_city(city)
        if districts:
            return Response({
                'success': True,
                'city': city,
                'districts': districts
            })
        else:
            return Response({
                'success': True,
                'city': city,
                'districts': [],
                'message': f"Районы не найдены в городе '{city}' или произошла ошибка при получении данных."
            })
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)

@api_view(['GET']) 
def get_residential_buildings(request):
    """НОВОЕ API: Получить жилые дома"""
    city = request.GET.get('city', 'Бишкек')
    try:
        buildings = OpenStreetMapService.get_residential_buildings_in_city(city)
        return Response({
            'success': True,
            'city': city,
            'buildings': buildings,
            'count': len(buildings)
        })
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)

@api_view(['GET'])
def get_commercial_places(request):
    """НОВОЕ API: Получить коммерческие объекты"""
    city = request.GET.get('city', 'Бишкек')
    try:
        places = OpenStreetMapService.get_commercial_places_in_city(city)
        return Response({
            'success': True,
            'city': city,
            'places': places,
            'count': len(places)
        })
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)

@csrf_exempt
@api_view(['POST'])
def get_enhanced_school_info(request):
    """API для получения дополнительной информации о школе"""
    try:
        data = json.loads(request.body)
        school_name = data.get('school_name')
        school_lat = data.get('lat')
        school_lng = data.get('lng')
        
        if not school_name:
            return Response({'success': False, 'error': 'Не указано название школы'}, status=400)
        
        gemini_service = EnhancedGeminiService()
        school_info = gemini_service.generate_enhanced_school_info(school_name, school_lat, school_lng)
        
        return Response({
            'success': True,
            'school_info': school_info
        })
        
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@api_view(['POST'])
def get_buildings_in_viewport(request):
    """
    🆕 API для получения зданий в видимой области карты (viewport culling).

    Принимает:
    - bounds: {north, south, east, west} - границы видимой области
    - city: название города

    Возвращает:
    - buildings: список зданий с подробной информацией о каждом
    """
    try:
        data = json.loads(request.body)
        bounds = data.get('bounds', {})
        city = data.get('city', 'Бишкек')

        north = bounds.get('north', 90)
        south = bounds.get('south', -90)
        east = bounds.get('east', 180)
        west = bounds.get('west', -180)

        print(f"\n📍 Запрос зданий в viewport:")
        print(f"   Север: {north:.4f}, Юг: {south:.4f}")
        print(f"   Восток: {east:.4f}, Запад: {west:.4f}")

        # Получаем все здания города (кешируются в OSM сервисе)
        osm_service = OpenStreetMapService()
        all_buildings = osm_service.get_residential_buildings_in_city(city)

        # Фильтруем по viewport
        visible_buildings = []
        for b in all_buildings:
            lat = b.get('lat', 0)
            lng = b.get('lng', 0)
            if south <= lat <= north and west <= lng <= east:
                # Расчет населения для каждого здания
                building_type = b.get('building_type', 'residential')
                levels_str = b.get('levels')
                area_m2 = b.get('area_m2', 100)

                levels = None
                if levels_str:
                    try:
                        levels = int(float(levels_str))
                    except:
                        pass

                category, final_levels, population = GridService.calculate_building_population(
                    building_type, levels, area_m2, b.get('tags', {})
                )

                visible_buildings.append({
                    'lat': lat,
                    'lng': lng,
                    'building_type': building_type,
                    'levels': final_levels,
                    'has_levels_data': b.get('has_levels_data', False),
                    'area_m2': area_m2,
                    'population': population,
                    'category': category,
                    'name': b.get('name', ''),
                    'address': b.get('address', '')
                })

        # Ограничиваем количество для производительности
        MAX_BUILDINGS = 500
        if len(visible_buildings) > MAX_BUILDINGS:
            # Сортируем по населению и берем самые важные
            visible_buildings.sort(key=lambda x: -x['population'])
            visible_buildings = visible_buildings[:MAX_BUILDINGS]

        print(f"   ✅ Найдено {len(visible_buildings)} зданий в viewport")

        return Response({
            'success': True,
            'buildings': visible_buildings,
            'count': len(visible_buildings),
            'total_in_city': len(all_buildings)
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({'success': False, 'error': str(e)}, status=500)


# =====================================================
# ML API - Прогнозирование востребованности школ
# =====================================================

@api_view(['POST'])
def ml_train_model(request):
    """
    API для обучения ML-модели прогнозирования

    POST /api/ml/train/

    Обучает модель на данных всех школ из БД
    """
    try:
        schools = School.objects.all()

        if schools.count() < 10:
            return Response({
                'success': False,
                'error': 'Недостаточно данных. Загрузите школы командой: python manage.py load_schools'
            }, status=400)

        forecaster = get_forecaster()
        result = forecaster.train(schools)

        return Response(result)

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


@api_view(['GET'])
def ml_city_overview(request):
    """
    API для общего обзора ситуации в городе

    GET /api/ml/overview/

    Возвращает:
    - Статистику по всем школам
    - Разбивку по районам
    - Прогноз на 5 лет
    - Критические районы
    """
    try:
        schools = School.objects.all()

        if schools.count() == 0:
            return Response({
                'success': False,
                'error': 'Нет данных о школах. Загрузите командой: python manage.py load_schools'
            }, status=400)

        forecaster = get_forecaster()

        # Обучаем модель если ещё не обучена
        if not forecaster.is_trained:
            forecaster.train(schools)

        result = forecaster.get_city_overview(schools)

        return Response(result)

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


@api_view(['GET'])
def ml_district_analysis(request):
    """
    API для анализа конкретного района

    GET /api/ml/district/?name=Ленинский

    Возвращает:
    - Детальную статистику района
    - Распределение по классам
    - Прогноз на 5 лет
    - Проблемные школы
    - Рекомендации
    """
    try:
        district_name = request.GET.get('name', '')

        if not district_name:
            return Response({
                'success': False,
                'error': 'Укажите название района: ?name=Ленинский'
            }, status=400)

        schools = School.objects.all()

        if schools.count() == 0:
            return Response({
                'success': False,
                'error': 'Нет данных о школах'
            }, status=400)

        forecaster = get_forecaster()

        if not forecaster.is_trained:
            forecaster.train(schools)

        result = forecaster.analyze_district(district_name, schools)

        return Response(result)

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


@api_view(['GET'])
def ml_risk_schools(request):
    """
    API для получения школ с высоким риском перегрузки

    GET /api/ml/risk-schools/?threshold=90

    Возвращает список школ с загруженностью выше порога
    """
    try:
        threshold = float(request.GET.get('threshold', 90))

        schools = School.objects.all()

        if schools.count() == 0:
            return Response({
                'success': False,
                'error': 'Нет данных о школах'
            }, status=400)

        forecaster = get_forecaster()
        risk_schools = forecaster.get_risk_schools(schools, threshold)

        return Response({
            'success': True,
            'threshold': threshold,
            'count': len(risk_schools),
            'schools': risk_schools
        })

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


@api_view(['POST'])
def ml_school_forecast(request):
    """
    API для прогноза по конкретной школе

    POST /api/ml/school-forecast/
    {
        "school_id": 123,
        "years": 5
    }

    Возвращает прогноз востребованности на N лет
    """
    try:
        data = json.loads(request.body)
        school_id = data.get('school_id')
        years = data.get('years', 5)

        if not school_id:
            return Response({
                'success': False,
                'error': 'Укажите school_id'
            }, status=400)

        try:
            school = School.objects.get(id=school_id)
        except School.DoesNotExist:
            return Response({
                'success': False,
                'error': f'Школа с ID {school_id} не найдена'
            }, status=404)

        # Подготавливаем данные школы
        school_data = {
            'name': school.name,
            'district': school.district,
            'district_code': 0,
            'latitude': school.latitude,
            'longitude': school.longitude,
            'total_students': school.total_students,
            'capacity': school.estimated_capacity,
            'grade_1': school.students_class_1,
            'grade_2': school.students_class_2,
            'grade_3': school.students_class_3,
            'grade_4': school.students_class_4,
            'grade_5': school.students_class_5,
            'grade_6': school.students_class_6,
            'grade_7': school.students_class_7,
            'grade_8': school.students_class_8,
            'grade_9': school.students_class_9,
            'grade_10': school.students_class_10,
            'grade_11': school.students_class_11,
            'ownership_private': 1 if 'Private' in (school.owner_form or '') else 0,
            'growth_indicator': 1.0,
            'avg_gradient': 0.0,
            'students_per_class': school.total_students / max(school.total_classes, 1)
        }

        forecaster = get_forecaster()

        # Обучаем модель если нужно
        if not forecaster.is_trained:
            all_schools = School.objects.all()
            forecaster.train(all_schools)

        result = forecaster.predict_school_demand(school_data, years)

        return Response(result)

    except json.JSONDecodeError:
        return Response({
            'success': False,
            'error': 'Неверный формат JSON'
        }, status=400)
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


@api_view(['GET'])
def ml_model_status(request):
    """
    API для проверки статуса ML-модели

    GET /api/ml/status/
    """
    try:
        forecaster = get_forecaster()

        schools_count = School.objects.count()

        return Response({
            'success': True,
            'model_trained': forecaster.is_trained,
            'schools_in_db': schools_count,
            'training_stats': forecaster.training_stats if forecaster.is_trained else None,
            'demographic_coefficients': forecaster.demographic_coefficients
        })

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


@api_view(['GET'])
def ml_demographics(request):
    """
    API для получения демографических данных Бишкека

    GET /api/ml/demographics/

    Возвращает:
    - Реальные данные населения школьного возраста (2022)
    - Распределение по возрастам (6-18 лет)
    - Демографические тренды
    - Прогноз когорт на будущие годы
    """
    try:
        target_year = int(request.GET.get('year', 2025))

        # Прогноз когорт на целевой год
        cohort_projection = get_cohort_projection(2022, target_year)
        total_projected = calculate_total_projected_students(target_year)

        # Демографические тренды
        trends = get_demographic_trends()

        # Сравнение с реальными данными школ
        schools = School.objects.all()
        actual_students = sum(s.total_students for s in schools)
        actual_capacity = sum(s.estimated_capacity for s in schools)

        # Распределение по классам в школах
        actual_by_grade = {}
        for i in range(1, 12):
            actual_by_grade[i] = sum(getattr(s, f'students_class_{i}', 0) for s in schools)

        return Response({
            'success': True,
            'base_year': 2022,
            'target_year': target_year,

            # Реальные демографические данные 2022
            'population_2022': {
                'by_age': {str(k): v for k, v in BISHKEK_POPULATION_2022.items()},
                'by_grade': {str(k): v for k, v in POPULATION_BY_GRADE_2022.items()},
                'total_school_age': TOTAL_SCHOOL_AGE_POPULATION_2022,
                'age_range': '6-18 лет'
            },

            # Прогноз когорт
            'cohort_projection': {
                'year': target_year,
                'by_grade': {str(k): v for k, v in cohort_projection.items()},
                'total_projected': total_projected,
                'methodology': 'Когортный метод с годовым ростом 3.5%'
            },

            # Демографические тренды
            'trends': {
                'analysis': trends['analysis'],
                'growth_ratio': trends['growth_ratio'],
                'young_avg': trends['young_average'],
                'middle_avg': trends['middle_average'],
                'old_avg': trends['old_average'],
                'trend_slope': trends['trend_slope'],
                'interpretation': 'Больше молодых детей → рост' if trends['growth_ratio'] > 1 else 'Меньше молодых → стабилизация/спад'
            },

            # Сравнение с реальными данными школ
            'school_comparison': {
                'actual_enrolled': actual_students,
                'population_school_age': TOTAL_SCHOOL_AGE_POPULATION_2022,
                'enrollment_rate': round(actual_students / TOTAL_SCHOOL_AGE_POPULATION_2022 * 100, 1) if TOTAL_SCHOOL_AGE_POPULATION_2022 > 0 else 0,
                'total_capacity': actual_capacity,
                'deficit': actual_students - actual_capacity,
                'by_grade_actual': {str(k): v for k, v in actual_by_grade.items()},
                'by_grade_population': {str(k): v for k, v in POPULATION_BY_GRADE_2022.items()}
            },

            # Прогноз дефицита
            'deficit_forecast': {
                'current_deficit': actual_students - actual_capacity,
                'projected_deficit': total_projected - actual_capacity,
                'additional_places_needed': max(0, total_projected - actual_capacity),
                'new_schools_needed': max(0, (total_projected - actual_capacity) // 1000),
                'note': 'При средней школе на 1000 мест'
            }
        })

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


@api_view(['GET'])
def ml_cohort_forecast(request):
    """
    API для детального когортного прогнозирования

    GET /api/ml/cohort-forecast/?start_year=2025&end_year=2030

    Показывает как текущие когорты детей будут перемещаться по классам
    """
    try:
        start_year = int(request.GET.get('start_year', 2025))
        end_year = int(request.GET.get('end_year', 2030))

        # Текущие данные школ
        schools = School.objects.all()
        total_capacity = sum(s.estimated_capacity for s in schools)

        # Прогноз по годам
        yearly_forecasts = []

        for year in range(start_year, end_year + 1):
            projection = get_cohort_projection(2022, year)
            total_students = sum(projection.values())

            # Выпускники и первоклассники
            graduates = projection.get(11, 0)  # Выпускаются
            new_students = projection.get(1, 0)  # Поступают

            yearly_forecasts.append({
                'year': year,
                'grade_distribution': {str(k): v for k, v in projection.items()},
                'total_students': total_students,
                'new_first_graders': new_students,
                'graduates': graduates,
                'net_change': new_students - graduates,
                'capacity': total_capacity,
                'deficit': max(0, total_students - total_capacity),
                'occupancy_percent': round(total_students / total_capacity * 100, 1) if total_capacity > 0 else 0
            })

        # Суммарные показатели
        first_year = yearly_forecasts[0]
        last_year = yearly_forecasts[-1]

        return Response({
            'success': True,
            'period': f'{start_year}-{end_year}',
            'methodology': 'Когортный метод на основе данных НСК КР 2022',
            'growth_rate_used': '3.5% в год (рост + миграция)',

            'yearly_forecasts': yearly_forecasts,

            'summary': {
                'start_students': first_year['total_students'],
                'end_students': last_year['total_students'],
                'total_growth': last_year['total_students'] - first_year['total_students'],
                'growth_percent': round((last_year['total_students'] - first_year['total_students']) / first_year['total_students'] * 100, 1),
                'start_deficit': first_year['deficit'],
                'end_deficit': last_year['deficit'],
                'additional_capacity_needed': last_year['deficit'] - first_year['deficit'],
                'new_schools_needed_by_end': max(0, last_year['deficit'] // 1000)
            },

            'recommendations': _generate_cohort_recommendations(yearly_forecasts, total_capacity)
        })

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


def _generate_cohort_recommendations(forecasts: list, capacity: int) -> list:
    """Генерация рекомендаций на основе когортного прогноза"""
    recommendations = []

    # Анализируем рост дефицита по годам
    deficits = [f['deficit'] for f in forecasts]
    years = [f['year'] for f in forecasts]

    # Год критического дефицита (>50,000)
    critical_year = None
    for i, d in enumerate(deficits):
        if d > 50000 and critical_year is None:
            critical_year = years[i]
            break

    if critical_year:
        recommendations.append({
            'priority': 'critical',
            'title': f'Критический дефицит к {critical_year} году',
            'description': f'Дефицит мест превысит 50,000. Требуется срочное строительство новых школ.',
            'action': f'Начать строительство минимум {deficits[-1] // 1000} школ по 1000 мест до {critical_year}.'
        })

    # Анализ первоклассников
    first_graders = [f['new_first_graders'] for f in forecasts]
    avg_first_graders = sum(first_graders) / len(first_graders)

    if avg_first_graders > 16000:
        recommendations.append({
            'priority': 'high',
            'title': 'Высокий приток первоклассников',
            'description': f'Ожидается в среднем {int(avg_first_graders)} первоклассников в год.',
            'action': 'Обеспечить достаточное количество мест в начальной школе, особенно в Первомайском районе.'
        })

    # Рост населения
    total_growth = forecasts[-1]['total_students'] - forecasts[0]['total_students']
    if total_growth > 30000:
        schools_needed = total_growth // 1000
        recommendations.append({
            'priority': 'medium',
            'title': f'Планировать {schools_needed} новых школ',
            'description': f'За период прогнозируется рост на {total_growth:,} учеников.',
            'action': 'Включить строительство школ в генплан развития Бишкека.'
        })

    return recommendations


# =====================================================
# API - ПРОГНОЗ НАСЕЛЕНИЯ БИШКЕКА
# =====================================================

@api_view(['GET'])
def population_forecast(request):
    """
    API для прогноза роста населения Бишкека

    GET /api/ml/population-forecast/?end_year=2035&scenario=medium

    Сценарии (скорректированы с учётом реальных данных 2023-2024):
    - low: Консервативный (~1.5% в год) - продолжение снижения
    - medium: Базовый (~1.8% в год) - стабилизация
    - high: Оптимистичный (~2.2% в год) - восстановление
    """
    try:
        end_year = int(request.GET.get('end_year', 2035))
        scenario = request.GET.get('scenario', 'medium')

        if scenario not in ['low', 'medium', 'high']:
            scenario = 'medium'

        # Анализ реальных данных о естественном приросте
        growth_analysis = analyze_natural_growth_trends()

        # Прогнозы по всем сценариям для сравнения
        forecasts_all = {
            'low': forecast_total_population(2022, end_year, 'low'),
            'medium': forecast_total_population(2022, end_year, 'medium'),
            'high': forecast_total_population(2022, end_year, 'high'),
        }

        # Выбранный сценарий
        selected_forecast = forecasts_all[scenario]

        # Детальный прогноз
        detailed = forecast_population_detailed(2022, end_year)

        # Рост за период
        start_pop = BISHKEK_TOTAL_POPULATION[2022]
        end_pop = selected_forecast[end_year]
        total_growth = end_pop - start_pop
        growth_percent = round((end_pop / start_pop - 1) * 100, 1)

        return Response({
            'success': True,
            'city': 'Бишкек',
            'base_year': 2022,
            'end_year': end_year,
            'scenario': scenario,

            # РЕАЛЬНЫЕ исторические данные о естественном приросте
            'natural_growth_history': {
                'data': {str(k): v for k, v in NATURAL_POPULATION_GROWTH.items()},
                'analysis': growth_analysis,
                'source': 'Национальный статистический комитет КР'
            },

            # Исторические данные о населении
            'historical_population': {
                'data': {str(k): v for k, v in BISHKEK_TOTAL_POPULATION.items()},
            },

            # Демографические параметры (обновлены на основе реальных данных)
            'demographic_rates': {
                'birth_rate_2022': f"{DEMOGRAPHIC_RATES['birth_rate']} на 1000",
                'adjusted_birth_rate': f"{DEMOGRAPHIC_RATES['adjusted_birth_rate']} на 1000 (2023-2024)",
                'death_rate': f"{DEMOGRAPHIC_RATES['death_rate']} на 1000",
                'natural_growth_2022': f"{DEMOGRAPHIC_RATES['natural_growth']} на 1000",
                'adjusted_natural_growth': f"{DEMOGRAPHIC_RATES['adjusted_natural_growth']} на 1000 (2023-2024)",
                'migration_rate': f"{DEMOGRAPHIC_RATES['migration_rate']} на 1000",
                'fertility_rate': DEMOGRAPHIC_RATES['fertility_rate'],
                'note': 'Резкое снижение рождаемости в 2023-2024'
            },

            # Прогноз по выбранному сценарию
            'forecast': {
                'by_year': {str(k): v for k, v in selected_forecast.items()},
                'start_population': start_pop,
                'end_population': end_pop,
                'total_growth': total_growth,
                'growth_percent': growth_percent,
                'avg_annual_growth': round(total_growth / (end_year - 2022), 0)
            },

            # Сравнение сценариев (ОБНОВЛЕНО с учётом 2023-2024)
            'scenarios_comparison': {
                'low': {
                    'description': 'Консервативный: продолжение тренда снижения рождаемости',
                    'growth_rate': '1.5%',
                    'end_population': forecasts_all['low'][end_year],
                    'total_growth': forecasts_all['low'][end_year] - start_pop
                },
                'medium': {
                    'description': 'Базовый: стабилизация рождаемости + миграция',
                    'growth_rate': '1.8%',
                    'end_population': forecasts_all['medium'][end_year],
                    'total_growth': forecasts_all['medium'][end_year] - start_pop
                },
                'high': {
                    'description': 'Оптимистичный: восстановление рождаемости',
                    'growth_rate': '2.2%',
                    'end_population': forecasts_all['high'][end_year],
                    'total_growth': forecasts_all['high'][end_year] - start_pop
                }
            },

            # Детальный прогноз по годам
            'detailed_forecast': detailed,

            # Ключевые выводы
            'key_insights': _generate_population_insights(detailed, scenario, end_year)
        })

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


@api_view(['GET'])
def population_pyramid(request):
    """
    API для возрастной пирамиды населения

    GET /api/ml/population-pyramid/?year=2030
    """
    try:
        year = int(request.GET.get('year', 2025))

        pyramid = get_population_pyramid(year)

        # Также получаем данные за 2022 для сравнения
        pyramid_2022 = get_population_pyramid(2022)

        return Response({
            'success': True,
            'year': year,
            'pyramid': pyramid,
            'comparison_2022': pyramid_2022,
            'changes': {
                'total_growth': pyramid['total_population'] - pyramid_2022['total_population'],
                'growth_percent': round((pyramid['total_population'] / pyramid_2022['total_population'] - 1) * 100, 1),
                'children_change': pyramid['children'] - pyramid_2022['children'],
                'working_age_change': pyramid['working_age'] - pyramid_2022['working_age'],
                'elderly_change': pyramid['elderly'] - pyramid_2022['elderly']
            }
        })

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


@api_view(['GET'])
def population_growth_components(request):
    """
    API для анализа компонентов роста населения

    GET /api/ml/population-growth/?start_year=2022&end_year=2030
    """
    try:
        start_year = int(request.GET.get('start_year', 2022))
        end_year = int(request.GET.get('end_year', 2030))

        detailed = forecast_population_detailed(start_year, end_year)

        # Суммарные компоненты за период
        total_births = sum(d['growth_components']['births'] for d in detailed[1:])
        total_deaths = sum(d['growth_components']['deaths'] for d in detailed[1:])
        total_migration = sum(d['growth_components']['migration'] for d in detailed[1:])
        total_natural = sum(d['growth_components']['natural_growth'] for d in detailed[1:])

        # Школьный возраст
        school_age_start = detailed[0]['school_age_population']['total']
        school_age_end = detailed[-1]['school_age_population']['total']

        return Response({
            'success': True,
            'period': f'{start_year}-{end_year}',

            'population_change': {
                'start': detailed[0]['total_population'],
                'end': detailed[-1]['total_population'],
                'total_growth': detailed[-1]['total_population'] - detailed[0]['total_population'],
                'growth_percent': round((detailed[-1]['total_population'] / detailed[0]['total_population'] - 1) * 100, 1)
            },

            'growth_components_total': {
                'births': total_births,
                'deaths': total_deaths,
                'natural_growth': total_natural,
                'migration': total_migration,
                'natural_share': round(total_natural / (total_natural + total_migration) * 100, 1),
                'migration_share': round(total_migration / (total_natural + total_migration) * 100, 1)
            },

            'school_age_change': {
                'start': school_age_start,
                'end': school_age_end,
                'growth': school_age_end - school_age_start,
                'growth_percent': round((school_age_end / school_age_start - 1) * 100, 1)
            },

            'yearly_breakdown': [
                {
                    'year': d['year'],
                    'population': d['total_population'],
                    'births': d['growth_components']['births'],
                    'deaths': d['growth_components']['deaths'],
                    'migration': d['growth_components']['migration'],
                    'growth_rate': d['growth_components']['growth_rate_percent'],
                    'school_age': d['school_age_population']['total']
                }
                for d in detailed
            ]
        })

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


def _generate_population_insights(detailed: list, scenario: str, end_year: int) -> list:
    """Генерация ключевых выводов по прогнозу населения"""
    insights = []

    start = detailed[0]
    end = detailed[-1]

    growth = end['total_population'] - start['total_population']
    growth_pct = (end['total_population'] / start['total_population'] - 1) * 100

    # 1. Общий рост
    insights.append({
        'category': 'growth',
        'title': f'Рост населения на {growth:,} человек',
        'description': f'К {end_year} году население Бишкека вырастет с {start["total_population"]:,} до {end["total_population"]:,} человек (+{growth_pct:.1f}%).',
        'impact': 'high'
    })

    # 2. Миграция
    total_migration = sum(d['growth_components']['migration'] for d in detailed[1:])
    insights.append({
        'category': 'migration',
        'title': f'Миграционный приток: +{total_migration:,}',
        'description': f'Ожидается приток ~{total_migration // (end_year - 2022):,} мигрантов ежегодно, в основном из регионов КР.',
        'impact': 'high'
    })

    # 3. Школьный возраст
    school_start = start['school_age_population']['total']
    school_end = end['school_age_population']['total']
    school_growth = school_end - school_start
    insights.append({
        'category': 'education',
        'title': f'Детей школьного возраста: +{school_growth:,}',
        'description': f'Количество детей 6-18 лет вырастет с {school_start:,} до {school_end:,}. Потребуется {school_growth // 1000} новых школ.',
        'impact': 'critical'
    })

    # 4. Рождаемость
    total_births = sum(d['growth_components']['births'] for d in detailed[1:])
    insights.append({
        'category': 'births',
        'title': f'Ожидается {total_births:,} рождений',
        'description': f'В среднем {total_births // (end_year - 2022):,} новорождённых в год. Потребуются детсады и школы.',
        'impact': 'medium'
    })

    # 5. Инфраструктура образования
    insights.append({
        'category': 'education_infrastructure',
        'title': 'Потребность в образовательной инфраструктуре',
        'description': f'Для {growth:,} новых жителей нужно: ~{growth // 3000} новых школ, ~{growth // 2000} детсадов.',
        'impact': 'critical'
    })

    # 6. Анализ тренда рождаемости (на основе реальных данных)
    insights.append({
        'category': 'birth_trend',
        'title': 'Снижение рождаемости в 2023-2024',
        'description': f'Естественный прирост снизился с ~22,500 (2022) до ~9,300 (2023-2024). Это демографический переход, влияющий на долгосрочные прогнозы.',
        'impact': 'high'
    })

    return insights


@api_view(['GET'])
def natural_growth_analysis(request):
    """
    API для анализа естественного прироста населения Бишкека

    GET /api/ml/natural-growth/

    Возвращает реальные данные о естественном приросте 2011-2024
    """
    try:
        analysis = analyze_natural_growth_trends()

        # Визуализация тренда по годам
        yearly_data = []
        for year in sorted(NATURAL_POPULATION_GROWTH.keys()):
            value = NATURAL_POPULATION_GROWTH[year]
            population = BISHKEK_TOTAL_POPULATION.get(year, 1_100_000)
            rate_per_1000 = round(value / population * 1000, 2)

            yearly_data.append({
                'year': year,
                'natural_growth': value,
                'rate_per_1000': rate_per_1000,
                'population_estimate': population,
                'period': _get_period_name(year)
            })

        return Response({
            'success': True,
            'city': 'Бишкек',
            'data_period': '2011-2024',
            'source': 'Национальный статистический комитет КР',

            # Данные по годам
            'yearly_data': yearly_data,

            # Анализ
            'analysis': {
                'total_growth_14_years': analysis['total_growth_2011_2024'],
                'average_annual': analysis['average_annual'],
                'peak_year': analysis['max_year'],
                'peak_value': analysis['max_value'],
                'min_year': analysis['min_year'],
                'min_value': analysis['min_value'],
                'trend_direction': analysis['trend_direction'],
                'trend_slope': analysis['trend_slope'],
                'volatility': analysis['volatility']
            },

            # Периоды
            'periods': analysis['periods'],

            # Ключевые наблюдения
            'observations': [
                {
                    'title': 'Пиковый период 2018-2022',
                    'description': f'Средний прирост {int(analysis["periods"]["2018-2022"]["average"]):,} чел/год. Высокая рождаемость.',
                    'years': '2018-2022'
                },
                {
                    'title': 'Резкое падение в 2023',
                    'description': f'Прирост упал до {NATURAL_POPULATION_GROWTH[2023]:,} - снижение на 63% от 2022 года.',
                    'years': '2023'
                },
                {
                    'title': 'Начало восстановления в 2024',
                    'description': f'Прирост {NATURAL_POPULATION_GROWTH[2024]:,} - рост на 22% от 2023, но всё ещё ниже среднего.',
                    'years': '2024'
                },
                {
                    'title': 'Демографический переход',
                    'description': 'Снижение рождаемости характерно для урбанизированных регионов. Тренд может сохраниться.',
                    'years': '2023+'
                }
            ],

            # Прогнозные параметры для моделей
            'forecast_parameters': {
                'conservative_growth': round(analysis['periods']['2023-2024']['average'], 0),
                'optimistic_growth': round((analysis['periods']['2018-2022']['average'] + analysis['periods']['2023-2024']['average']) / 2, 0),
                'historical_average': analysis['average_annual'],
                'recommended_for_forecast': analysis['projected_annual_growth']
            }
        })

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


def _get_period_name(year: int) -> str:
    """Определение периода для года"""
    if year <= 2017:
        return 'stable_growth'
    elif year <= 2022:
        return 'peak_period'
    else:
        return 'transition'


# =====================================================
# ML ПРОГНОЗИРОВАНИЕ НАСЕЛЕНИЯ
# =====================================================

@api_view(['GET', 'POST'])
def ml_population_full_forecast(request):
    """
    ML-прогноз населения на основе РЕАЛЬНЫХ данных 2011-2024

    GET /api/ml/population-ml-forecast/
    POST /api/ml/population-ml-forecast/ {"years_ahead": 10}

    Обучает ML модель на реальных данных и прогнозирует:
    - Общее население Бишкека
    - Естественный прирост
    - Население школьного возраста
    - Потребность в школьных местах
    """
    try:
        years_ahead = 10
        if request.method == 'POST':
            data = request.data
            years_ahead = data.get('years_ahead', 10)
        else:
            years_ahead = int(request.GET.get('years_ahead', 10))

        # Получаем обученную модель
        forecaster = get_population_forecaster()

        # Полный прогноз
        result = forecaster.get_full_forecast(years_ahead=years_ahead)

        if result['success']:
            return Response({
                'success': True,
                'city': 'Бишкек',
                'model_type': 'ML Population Forecaster',
                'data_sources': [
                    'Естественный прирост 2011-2024 (14 лет)',
                    'Общее население 2018-2024 (7 лет)',
                    'Население по возрастам 2022 (13 групп)'
                ],
                'training_stats': result['training_stats'],
                'base_data': result['base_data'],
                'forecasts': result['forecasts'],

                # Резюме
                'summary': {
                    'forecast_horizon': f'{years_ahead} лет',
                    'population_2024': result['base_data']['population_2024'],
                    'population_end': result['forecasts'][-1]['total_population'],
                    'growth_total': result['forecasts'][-1]['total_population'] - result['base_data']['population_2024'],
                    'school_places_deficit_end': result['forecasts'][-1]['places_deficit'],
                    'new_schools_needed': result['forecasts'][-1]['new_schools_needed']
                }
            })
        else:
            return Response(result, status=500)

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


@api_view(['POST'])
def ml_train_population_model(request):
    """
    Обучение/переобучение ML модели прогнозирования населения

    POST /api/ml/train-population/

    Обучает модель на реальных данных:
    - 14 лет данных о естественном приросте
    - 7 лет данных об общем населении
    """
    try:
        forecaster = PopulationForecaster()
        result = forecaster.train()

        if result['success']:
            return Response({
                'success': True,
                'message': 'ML модель населения обучена',
                'training_stats': result['stats'],
                'data_used': {
                    'natural_growth_years': list(NATURAL_POPULATION_GROWTH.keys()),
                    'total_population_years': list(BISHKEK_TOTAL_POPULATION.keys()),
                    'school_age_data': '2022 (13 возрастных групп)'
                }
            })
        else:
            return Response(result, status=500)

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


@api_view(['GET'])
def ml_predict_natural_growth(request):
    """
    ML-прогноз естественного прироста населения

    GET /api/ml/predict-growth/?years=2025,2026,2027,2028,2029,2030
    """
    try:
        years_param = request.GET.get('years', '')
        if years_param:
            target_years = [int(y.strip()) for y in years_param.split(',')]
        else:
            current_year = datetime.now().year
            target_years = list(range(current_year + 1, current_year + 6))

        forecaster = get_population_forecaster()
        result = forecaster.predict_natural_growth(target_years)

        if result['success']:
            # Добавляем исторические данные для сравнения
            historical = [
                {'year': y, 'actual': v, 'type': 'historical'}
                for y, v in sorted(NATURAL_POPULATION_GROWTH.items())
            ]

            return Response({
                'success': True,
                'city': 'Бишкек',
                'historical_data': historical,
                'predictions': result['predictions'],
                'model_r2': result['model_r2'],
                'data_source': result['data_source'],

                # Ключевые выводы
                'insights': {
                    'peak_historical': {
                        'year': 2019,
                        'value': NATURAL_POPULATION_GROWTH[2019]
                    },
                    'recent_decline': {
                        'year_2022': NATURAL_POPULATION_GROWTH[2022],
                        'year_2023': NATURAL_POPULATION_GROWTH[2023],
                        'decline_percent': round((1 - NATURAL_POPULATION_GROWTH[2023]/NATURAL_POPULATION_GROWTH[2022]) * 100, 1)
                    },
                    'forecast_trend': 'Постепенное восстановление после падения 2023'
                }
            })
        else:
            return Response(result, status=500)

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


@api_view(['GET'])
def ml_predict_school_population(request):
    """
    ML-прогноз населения школьного возраста (когортный метод + ML)

    GET /api/ml/predict-school-population/?years=5
    """
    try:
        years_ahead = int(request.GET.get('years', 5))
        current_year = datetime.now().year
        target_years = list(range(current_year + 1, current_year + years_ahead + 1))

        forecaster = get_population_forecaster()
        result = forecaster.predict_school_age_population(target_years)

        if result['success']:
            return Response({
                'success': True,
                'city': 'Бишкек',
                'method': result['method'],
                'base_year': result['base_year'],
                'base_population': result['base_population'],
                'data_source': result['data_source'],
                'predictions': result['predictions'],

                # Текущее состояние для сравнения
                'current_status': {
                    'total_students': 208860,  # Из базы школ
                    'total_capacity': 170227,
                    'current_deficit': 208860 - 170227,
                    'school_age_2022': TOTAL_SCHOOL_AGE_POPULATION_2022
                }
            })
        else:
            return Response(result, status=500)

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


# =====================================================
# AI РЕКОМЕНДАЦИИ ПО СТРОИТЕЛЬСТВУ ШКОЛ
# =====================================================

from .ai_recommendations_service import get_ai_recommendations_service
from .grid_service import GridService

@api_view(['GET', 'POST'])
def ai_school_recommendations(request):
    """
    AI-анализ и рекомендации по строительству новых школ.
    
    GET /api/ai/recommendations/?district=Первомайский&ownership=government
    POST /api/ai/recommendations/ {"district": "Первомайский", "ownership": "government"}
    
    Параметры:
    - district: фильтр по району
    - ownership: 'all' | 'government' | 'private'
    
    Использует:
    - Плотность населения (сетка 500x500м)
    - Загрузку существующих школ
    - ML прогнозы
    - Gemini AI для анализа
    """
    try:
        # Получаем фильтры
        if request.method == 'POST':
            district_filter = request.data.get('district')
            ownership_filter = request.data.get('ownership', 'government')  # По умолчанию - государственные
        else:
            district_filter = request.GET.get('district')
            ownership_filter = request.GET.get('ownership', 'government')
        
        print(f"🤖 AI Recommendations запрос, район: {district_filter or 'все'}, тип: {ownership_filter}")
        
        # 1. Получаем данные сетки плотности
        osm_service = OpenStreetMapService()
        
        # Загружаем здания
        residential_data = osm_service.get_residential_buildings_in_city('Бишкек')
        districts_data = osm_service.get_districts_in_city('Бишкек')
        
        # Создаём сетку
        grid_service = GridService()
        grid_data = grid_service.create_population_grid(residential_data, districts_data)
        
        # 2. Получаем школы с расчётом вместимости
        schools_qs = School.objects.all()
        
        # Фильтруем по типу собственности
        if ownership_filter == 'government':
            # Государственные/муниципальные школы
            schools_qs = schools_qs.filter(
                owner_form__iregex=r'(state|municipal|государств|муниципал|коммунал)'
            )
            print(f"📚 Фильтр: только государственные школы ({schools_qs.count()} шт.)")
        elif ownership_filter == 'private':
            # Частные школы
            schools_qs = schools_qs.filter(
                owner_form__iregex=r'(private|частн)'
            )
            print(f"📚 Фильтр: только частные школы ({schools_qs.count()} шт.)")
        else:
            print(f"📚 Все школы: {schools_qs.count()} шт.")
        
        schools = []
        for school in schools_qs:
            schools.append({
                'id': school.id,
                'name': school.name,
                'district': school.district,
                'latitude': school.latitude,
                'longitude': school.longitude,
                'total_students': school.total_students,
                'capacity': school.estimated_capacity,
                'occupancy_rate': school.occupancy_rate,
                'owner_form': school.owner_form,
            })
        
        # 3. Получаем ML прогноз
        try:
            forecaster = get_population_forecaster()
            ml_forecast = forecaster.get_full_forecast(years_ahead=5)
        except Exception as e:
            print(f"⚠️ ML forecast error: {e}")
            ml_forecast = None
        
        # 4. Получаем запрещённые зоны (парки, промзоны и т.д.)
        try:
            restricted_zones = osm_service.get_restricted_zones('Бишкек')
            print(f"🚫 Загружено {len(restricted_zones)} запрещённых зон")
        except Exception as e:
            print(f"⚠️ Restricted zones error: {e}")
            restricted_zones = []
        
        # 5. Подготавливаем данные для AI
        ai_service = get_ai_recommendations_service()
        analysis_data = ai_service.prepare_analysis_data(
            grid_data, schools, districts_data, ml_forecast, restricted_zones
        )
        
        # 6. Генерируем рекомендации через Gemini
        result = ai_service.generate_recommendations(analysis_data, district_filter)
        
        return Response(result)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


@api_view(['GET'])
def ai_analyze_district(request):
    """
    AI-анализ конкретного района с детальными рекомендациями.
    
    GET /api/ai/analyze-district/?district=Первомайский
    """
    district = request.GET.get('district')
    if not district:
        return Response({
            'success': False,
            'error': 'Укажите параметр district'
        }, status=400)
    
    try:
        # Получаем школы района
        schools_qs = School.objects.filter(district__icontains=district)
        
        if not schools_qs.exists():
            return Response({
                'success': False,
                'error': f'Школы в районе "{district}" не найдены'
            }, status=404)
        
        # Собираем данные с расчётом вместимости и загрузки
        schools = []
        total_students = 0
        total_capacity = 0
        overloaded = []
        critical = []
        first_graders = 0
        eleventh_graders = 0
        
        for school in schools_qs:
            capacity = school.estimated_capacity
            occupancy = school.occupancy_rate
            
            school_data = {
                'id': school.id,
                'name': school.name,
                'district': school.district,
                'latitude': school.latitude,
                'longitude': school.longitude,
                'total_students': school.total_students,
                'capacity': capacity,
                'occupancy_rate': occupancy,
                'grade_1': school.students_class_1,
                'grade_11': school.students_class_11,
            }
            schools.append(school_data)
            
            total_students += school.total_students
            total_capacity += capacity
            first_graders += school.students_class_1
            eleventh_graders += school.students_class_11
            
            if occupancy > 100:
                overloaded.append(school_data)
            if occupancy > 130:
                critical.append(school_data)
        
        growth_trend = first_graders / eleventh_graders if eleventh_graders > 0 else 1
        
        return Response({
            'success': True,
            'district': district,
            'statistics': {
                'schools_count': len(schools),
                'total_students': total_students,
                'total_capacity': total_capacity,
                'current_deficit': max(0, total_students - total_capacity),
                'avg_occupancy': round(total_students / total_capacity * 100, 1) if total_capacity > 0 else 0,
                'overloaded_count': len(overloaded),
                'critical_count': len(critical)
            },
            'growth_analysis': {
                'first_graders': first_graders,
                'eleventh_graders': eleventh_graders,
                'growth_trend': round(growth_trend, 3),
                'trend_description': 'Рост' if growth_trend > 1.05 else ('Спад' if growth_trend < 0.95 else 'Стабильно')
            },
            'schools': schools,
            'overloaded_schools': overloaded,
            'critical_schools': critical,
            'recommendations': {
                'new_places_needed': max(0, total_students - total_capacity),
                'new_schools_needed': max(0, (total_students - total_capacity) // 1000),
                'priority': 'critical' if len(critical) > 5 else ('high' if len(overloaded) > 10 else 'medium')
            }
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)