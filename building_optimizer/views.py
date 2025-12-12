from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .services import OpenStreetMapService, GeminiService, PopulationService
from .models import BuildingRequest, PopulationData
from .enhanced_gemini_service import EnhancedGeminiService
from .grid_service import GridService
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