import requests
import google.generativeai as genai
from django.conf import settings
from .models import PopulationData
import json
import random
import time
import traceback
import math

class OpenStreetMapService:
    """Расширенный сервис для работы с OpenStreetMap API для Google Maps"""
    
    @staticmethod
    def get_city_boundaries(city_name):
        """Получить границы города"""
        url = f"https://nominatim.openstreetmap.org/search"
        params = {
            'q': city_name,
            'format': 'json',
            'limit': 1,
            'polygon_geojson': 1,
            'dedupe': 0
        }
        
        headers = {
            'User-Agent': 'BuildingOptimizerApp/1.0 (murgalag05@gmail.com)' 
        }

        try:
            print(f"Nominatim: Поиск границ города '{city_name}'...")
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data:
                for item in data:
                    if item.get('osm_type') == 'relation' and item.get('class') == 'boundary' and item.get('type') == 'administrative' and item.get('admin_level') == '4':
                        print(f"Nominatim: Найден город '{city_name}' как административное отношение admin_level=4.")
                        return item
                    elif item.get('type') in ['city', 'town', 'village']:
                        print(f"Nominatim: Найден город '{city_name}' как {item.get('type')}.")
                        return item
                if data:
                    print(f"Nominatim: Найден город '{city_name}' (первый результат).")
                    return data[0]
            print(f"Nominatim: Город '{city_name}' не найден.")
            return None
        except Exception as e:
            print(f"Nominatim: Ошибка при получении границ города: {e}")
            return None

    @staticmethod
    def get_districts_in_city(city_name):
        """Получить районы города - исправленная версия с fallback данными"""
        districts_data = []
        
        try:
            print(f"get_districts_in_city: Запуск для города '{city_name}'...")
            
            # Сначала пробуем получить из OpenStreetMap
            districts_from_nominatim = OpenStreetMapService._get_districts_via_nominatim(city_name)
            if districts_from_nominatim and len(districts_from_nominatim) > 0:
                print(f"Успешно получено {len(districts_from_nominatim)} районов через Nominatim")
                return districts_from_nominatim
            
            print("Nominatim не дал результатов, используем fallback данные...")
            # Если не получилось, используем статические данные для Бишкека
            return OpenStreetMapService._get_bishkek_districts_fallback()
                
        except Exception as e:
            print(f"Общая ошибка в get_districts_in_city: {e}")
            traceback.print_exc()
            # В случае любой ошибки возвращаем fallback данные
            return OpenStreetMapService._get_bishkek_districts_fallback()

    @staticmethod
    def _get_bishkek_districts_fallback():
        """Fallback данные для районов Бишкека с упрощенными границами"""
        print("Используем статические данные районов Бишкека...")
        
        districts_data = [
            {
                'name': 'Октябрьский район',
                'lat': 42.8800,
                'lng': 74.5400,
                'population_density': 2800,
                'geometry': [[
                    {'lat': 42.8650, 'lng': 74.5200},
                    {'lat': 42.8950, 'lng': 74.5200},
                    {'lat': 42.8950, 'lng': 74.5600},
                    {'lat': 42.8650, 'lng': 74.5600},
                    {'lat': 42.8650, 'lng': 74.5200}
                ]],
                'osm_id': 1001
            },
            {
                'name': 'Первомайский район',
                'lat': 42.8500,
                'lng': 74.6200,
                'population_density': 4500,
                'geometry': [[
                    {'lat': 42.8350, 'lng': 74.6000},
                    {'lat': 42.8650, 'lng': 74.6000},
                    {'lat': 42.8650, 'lng': 74.6400},
                    {'lat': 42.8350, 'lng': 74.6400},
                    {'lat': 42.8350, 'lng': 74.6000}
                ]],
                'osm_id': 1002
            },
            {
                'name': 'Ленинский район',
                'lat': 42.8900,
                'lng': 74.5800,
                'population_density': 3800,
                'geometry': [[
                    {'lat': 42.8750, 'lng': 74.5600},
                    {'lat': 42.9050, 'lng': 74.5600},
                    {'lat': 42.9050, 'lng': 74.6000},
                    {'lat': 42.8750, 'lng': 74.6000},
                    {'lat': 42.8750, 'lng': 74.5600}
                ]],
                'osm_id': 1003
            },
            {
                'name': 'Свердловский район',
                'lat': 42.8746,
                'lng': 74.5698,
                'population_density': 3200,
                'geometry': [[
                    {'lat': 42.8596, 'lng': 74.5498},
                    {'lat': 42.8896, 'lng': 74.5498},
                    {'lat': 42.8896, 'lng': 74.5898},
                    {'lat': 42.8596, 'lng': 74.5898},
                    {'lat': 42.8596, 'lng': 74.5498}
                ]],
                'osm_id': 1004
            }
        ]
        
        print(f"Возвращаем {len(districts_data)} статических районов")
        return districts_data

    @staticmethod
    def _get_districts_via_nominatim(city_name):
        """Получить районы через прямой поиск в Nominatim с polygon_geojson"""
        districts_data = []
        
        district_names = [
            'Ленинский район, Бишкек',
            'Октябрьский район, Бишкек', 
            'Первомайский район, Бишкек',
            'Свердловский район, Бишкек',
            'Ленин району, Бишкек',
            'Октябрь району, Бишкек',
            'Биринчи май району, Бишкек',
            'Свердлов району, Бишкек'
        ]
        
        temp_densities = {
            'Ленинский': 4500, 'Ленин': 4500,
            'Октябрьский': 3800, 'Октябрь': 3800,
            'Первомайский': 5200, 'Биринчи май': 5200,
            'Свердловский': 3000, 'Свердлов': 3000,
        }
        
        headers = {'User-Agent': 'BuildingOptimizerApp/1.0 (murgalag05@gmail.com)'}
        found_districts = set()
        
        for district_query in district_names:
            if len(found_districts) >= 4:
                break
                
            try:
                print(f"Nominatim: Поиск района '{district_query}'...")
                
                url = f"https://nominatim.openstreetmap.org/search"
                params = {
                    'q': district_query,
                    'format': 'json',
                    'limit': 3,
                    'polygon_geojson': 1,
                    'addressdetails': 1,
                    'extratags': 1
                }
                
                time.sleep(1)
                response = requests.get(url, params=params, headers=headers, timeout=15)
                response.raise_for_status()
                data = response.json()
                
                for item in data:
                    if (item.get('osm_type') == 'relation' and 
                        item.get('class') == 'boundary' and 
                        item.get('type') == 'administrative'):
                        
                        district_name = OpenStreetMapService._extract_district_name(item)
                        if district_name and district_name not in found_districts:
                            
                            geojson = item.get('geojson')
                            if geojson:
                                geometry_coords = OpenStreetMapService._convert_geojson_to_googlemaps(geojson)
                                
                                if geometry_coords and len(geometry_coords) > 0:
                                    center_lat, center_lng = OpenStreetMapService._calculate_polygon_center(geometry_coords)
                                    
                                    density_key = next((key for key in temp_densities.keys() if key in district_name), 'default')
                                    population_density = temp_densities.get(density_key, random.randint(3000, 5000))
                                    
                                    districts_data.append({
                                        'name': district_name,
                                        'lat': center_lat,
                                        'lng': center_lng,
                                        'population_density': population_density,
                                        'geometry': geometry_coords,
                                        'osm_id': item.get('osm_id', 0)
                                    })
                                    found_districts.add(district_name)
                                    print(f"✓ Добавлен район '{district_name}' с {len(geometry_coords)} полигонами")
                                    break
                
            except Exception as e:
                print(f"Ошибка при поиске района '{district_query}': {e}")
                continue
        
        print(f"Nominatim вернул {len(districts_data)} районов")
        return districts_data

    @staticmethod
    def _extract_district_name(nominatim_item):
        """Извлечь нормализованное имя района"""
        display_name = nominatim_item.get('display_name', '')
        name = nominatim_item.get('name', '')
        
        district_patterns = [
            'Ленинский район', 'Ленин району',
            'Октябрьский район', 'Октябрь району', 
            'Первомайский район', 'Биринчи май району',
            'Свердловский район', 'Свердлов району'
        ]
        
        text_to_search = (display_name + ' ' + name).lower()
        
        for pattern in district_patterns:
            if pattern.lower() in text_to_search:
                if 'ленин' in pattern.lower():
                    return 'Ленинский район'
                elif 'октябр' in pattern.lower():
                    return 'Октябрьский район'  
                elif 'первомай' in pattern.lower() or 'биринчи май' in pattern.lower():
                    return 'Первомайский район'
                elif 'свердлов' in pattern.lower():
                    return 'Свердловский район'
        
        return name

    @staticmethod
    def _convert_geojson_to_googlemaps(geojson):
        """Конвертировать GeoJSON геометрию в формат для Google Maps"""
        geometry_coords = []
        
        try:
            geometry_type = geojson.get('type')
            coordinates = geojson.get('coordinates', [])
            
            if geometry_type == 'Polygon':
                for ring in coordinates:
                    if ring and len(ring) >= 3:
                        # Google Maps ожидает {lat, lng} объекты
                        googlemaps_coords = [{'lat': point[1], 'lng': point[0]} for point in ring if len(point) >= 2]
                        if len(googlemaps_coords) >= 3:
                            geometry_coords.append(googlemaps_coords)
                            
            elif geometry_type == 'MultiPolygon':
                for polygon in coordinates:
                    for ring in polygon:
                        if ring and len(ring) >= 3:
                            googlemaps_coords = [{'lat': point[1], 'lng': point[0]} for point in ring if len(point) >= 2]
                            if len(googlemaps_coords) >= 3:
                                geometry_coords.append(googlemaps_coords)
            
            print(f"Конвертировано {geometry_type} в {len(geometry_coords)} полигонов для Google Maps")
            return geometry_coords
            
        except Exception as e:
            print(f"Ошибка конвертации GeoJSON: {e}")
            return []

    @staticmethod
    def _get_districts_via_overpass(city_name):
        """Fallback метод через Overpass API"""
        print("Используется fallback метод через Overpass API")
        
        city_info = OpenStreetMapService.get_city_boundaries(city_name)
        if not city_info:
            return []

        bbox = city_info.get('boundingbox')
        if not bbox or len(bbox) != 4:
            return []
        
        try:
            south, north, west, east = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
        except ValueError:
            return []

        overpass_query = f"""[out:json][timeout:60];
(
  relation["boundary"="administrative"]["admin_level"="6"]({south},{west},{north},{east});
);
out geom;"""
        
        try:
            overpass_url = "https://overpass-api.de/api/interpreter"
            headers = {'User-Agent': 'BuildingOptimizerApp/1.0 (murgalag05@gmail.com)'}
            
            time.sleep(2)
            response = requests.post(overpass_url, data=overpass_query.encode('utf-8'), headers=headers)
            response.raise_for_status()
            data = response.json()
            
            districts_data = []
            
            for element in data.get('elements', []):
                if element['type'] == 'relation' and 'tags' in element:
                    name = element['tags'].get('name:ru') or element['tags'].get('name', 'Неизвестный район')
                    
                    geometry_coords = OpenStreetMapService._extract_relation_geometry_for_googlemaps(element)
                    if geometry_coords:
                        center_lat, center_lng = OpenStreetMapService._calculate_polygon_center(geometry_coords)
                        
                        districts_data.append({
                            'name': name,
                            'lat': center_lat,
                            'lng': center_lng,
                            'population_density': 4000,
                            'geometry': geometry_coords,
                            'osm_id': element.get('id', 0)
                        })
            
            return districts_data
            
        except Exception as e:
            print(f"Ошибка в Overpass fallback: {e}")
            return []

    @staticmethod
    def _extract_relation_geometry_for_googlemaps(relation_element):
        """Извлечение геометрии для Google Maps формата"""
        geometry_coords = []
        
        if 'geometry' in relation_element and relation_element['geometry']:
            geometry = relation_element['geometry']
            
            if isinstance(geometry, list) and len(geometry) > 0:
                if isinstance(geometry[0], dict) and 'lat' in geometry[0] and 'lon' in geometry[0]:
                    current_polygon = []
                    for point in geometry:
                        current_polygon.append({'lat': point['lat'], 'lng': point['lon']})
                    if current_polygon and len(current_polygon) >= 3:
                        geometry_coords.append(current_polygon)
        
        return geometry_coords

    @staticmethod
    def _calculate_polygon_center(geometry_coords):
        """Вычисляет центр полигона для Google Maps формата"""
        if not geometry_coords:
            return 0.0, 0.0
        
        all_lats = []
        all_lngs = []
        
        for polygon in geometry_coords:
            for coord in polygon:
                if isinstance(coord, dict) and 'lat' in coord and 'lng' in coord:
                    all_lats.append(coord['lat'])
                    all_lngs.append(coord['lng'])
                elif len(coord) >= 2:  # Fallback для [lat, lng] формата
                    all_lats.append(coord[0])
                    all_lngs.append(coord[1])
        
        if all_lats and all_lngs:
            center_lat = sum(all_lats) / len(all_lats)
            center_lng = sum(all_lngs) / len(all_lngs)
            return center_lat, center_lng
        
        return 0.0, 0.0

    @staticmethod
    def _estimate_building_population(building_type, levels):
        """
        Рассчитывает примерное население здания на основе типа и этажности.
        
        Формула:
        - Apartments (многоквартирные): этажи × 4 квартиры на этаж × 3 человека
        - Residential (частные дома): обычно 1-2 этажа × 5 человек
        """
        try:
            # Пытаемся конвертировать этажи в число
            if levels:
                floors = int(float(levels))
            else:
                # Если данных нет, используем средние значения
                floors = 5 if building_type == 'apartments' else 2
        except (ValueError, TypeError):
            # Если не удалось распарсить, используем дефолтные значения
            floors = 5 if building_type == 'apartments' else 2
        
        if building_type == 'apartments':
            # Многоквартирные дома: 4 квартиры × 3 человека на этаж
            apartments_per_floor = 4
            people_per_apartment = 3
            population = floors * apartments_per_floor * people_per_apartment
        else:
            # Частные дома/residential: обычно одна семья
            population = 5
        
        return population

    @staticmethod
    def get_schools_in_city(city_name):
        """
        Получить школы в городе из базы данных ИСУО.
        Данные загружаются из XML файла командой: python manage.py load_schools
        """
        from .models import School
        
        schools_data = []
        
        try:
            print(f"📚 Загрузка школ из базы данных для города '{city_name}'...")
            
            # Получаем все школы из региона (например, "г.Бишкек")
            schools = School.objects.filter(region__icontains=city_name)
            
            for school in schools:
                # Используем оценочную вместимость с учетом отсутствующих данных
                estimated_capacity = school.estimated_capacity
                occupancy = school.occupancy_rate
                
                # Определяем статус загруженности
                status = "Нормальная"
                status_color = "green"
                if occupancy > 120:
                    status = "Критическая перегрузка"
                    status_color = "red"
                elif occupancy > 100:
                    status = "Перегружена"
                    status_color = "orange"
                elif occupancy > 80:
                    status = "Высокая загруженность"
                    status_color = "yellow"
                
                schools_data.append({
                    'id': school.id,
                    'institution_id': school.institution_id,
                    'name': school.name,
                    'full_name': school.full_name or school.name,
                    'address': school.address,
                    'district': school.district,
                    'lat': school.latitude,
                    'lng': school.longitude,
                    'type': 'school',
                    # Данные об учениках
                    'total_students': school.total_students,
                    'students_girls': school.total_students_girls,
                    'students_boys': school.total_students_boys,
                    # Вместимость и загруженность
                    'max_capacity': school.max_capacity,
                    'real_capacity': school.real_capacity,
                    'estimated_capacity': estimated_capacity,  # Оценочная вместимость
                    'total_classes': school.total_classes,
                    'occupancy_rate': occupancy,
                    'status': status,
                    'status_color': status_color,
                    'is_overloaded': occupancy > 100,
                    'has_capacity_data': school.max_capacity > 0 or school.real_capacity > 0,
                    # Распределение по классам
                    'students_by_grade': {
                        '1': school.students_class_1,
                        '2': school.students_class_2,
                        '3': school.students_class_3,
                        '4': school.students_class_4,
                        '5': school.students_class_5,
                        '6': school.students_class_6,
                        '7': school.students_class_7,
                        '8': school.students_class_8,
                        '9': school.students_class_9,
                        '10': school.students_class_10,
                        '11': school.students_class_11,
                    },
                    # Дополнительная информация
                    'phone': school.phone_number,
                    'director': school.director_name,
                    'owner_form': school.owner_form,
                })

            print(f"📚 Загружено {len(schools_data)} школ из базы данных")
            print(f"📊 Статистика: перегружено {sum(1 for s in schools_data if s['is_overloaded'])} школ")
            
            return schools_data
        
        except Exception as e:
            print(f"❌ Ошибка при загрузке школ из БД: {e}")
            import traceback
            traceback.print_exc()
            return []

    @staticmethod
    def get_residential_buildings_in_city(city_name):
        """
        Получить ВСЕ жилые здания в городе с расчетом реального населения.
        
        Учитывает:
        - Многоквартирные дома (apartments) - советские панельки, элитки
        - Жилые дома (residential) - частный сектор
        - Дома без указания типа (building=yes) с определением по площади
        - Новостройки и все типы жилья
        
        Использует площадь и этажность для расчета населения.
        """
        buildings_data = []
        
        city_info = OpenStreetMapService.get_city_boundaries(city_name)
        if not city_info:
            return []
        
        bbox = city_info.get('boundingbox')
        if not bbox or len(bbox) != 4:
            return []
        
        try:
            south, north, west, east = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
        except ValueError:
            return []

        # Расширенный запрос для ВСЕХ жилых зданий с геометрией для расчета площади
        overpass_query = f"""[out:json][timeout:180];
(
  // Многоквартирные дома
  way["building"="apartments"]({south},{west},{north},{east});
  relation["building"="apartments"]({south},{west},{north},{east});
  
  // Жилые дома (частный сектор)
  way["building"="residential"]({south},{west},{north},{east});
  relation["building"="residential"]({south},{west},{north},{east});
  
  // Дома (building=house) - частные дома
  way["building"="house"]({south},{west},{north},{east});
  
  // Общежития
  way["building"="dormitory"]({south},{west},{north},{east});
  
  // Таунхаусы
  way["building"="terrace"]({south},{west},{north},{east});
  
  // Здания без типа, но с residential landuse
  way["building"="yes"]["landuse"="residential"]({south},{west},{north},{east});
  
  // Все здания в жилых зонах (для новостроек/частного сектора без тегов)
  way["building"]["addr:street"]({south},{west},{north},{east});
);
out body geom;"""
        
        overpass_url = "https://overpass-api.de/api/interpreter"
        headers = {'User-Agent': 'BuildingOptimizerApp/1.0 (murgalag05@gmail.com)'}

        try:
            print(f"🏠 Overpass: Загрузка жилых зданий для {city_name}...")
            time.sleep(2)
            response = requests.post(overpass_url, data=overpass_query.encode('utf-8'), headers=headers)
            response.raise_for_status()
            data = response.json()
            
            # Статистика по типам зданий
            stats = {
                'apartments': 0, 'residential': 0, 'house': 0, 
                'dormitory': 0, 'terrace': 0, 'yes': 0, 'other': 0,
                'with_levels': 0, 'without_levels': 0,
                'total_population': 0
            }
            
            for element in data.get('elements', []):
                if element['type'] not in ['way', 'relation']:
                    continue  # Пропускаем точки - нам нужны полигоны для расчета площади
                    
                tags = element.get('tags', {})
                building_type = tags.get('building', 'yes')
                
                # Пропускаем нежилые здания
                if building_type in ['commercial', 'industrial', 'retail', 'office', 
                                     'warehouse', 'garage', 'garages', 'shed', 'roof',
                                     'service', 'kiosk', 'hangar', 'barn', 'greenhouse']:
                    continue
                
                # Получаем геометрию для расчета площади
                geometry = element.get('geometry', [])
                area_m2 = OpenStreetMapService._calculate_polygon_area(geometry)
                
                # Получаем количество этажей из OSM
                levels_str = tags.get('building:levels', tags.get('levels', None))
                
                # Определяем тип застройки и рассчитываем население
                building_category, levels, population = OpenStreetMapService._calculate_real_population(
                    building_type, levels_str, area_m2, tags
                )
                
                # Пропускаем здания со слишком маленьким населением (нежилые)
                if population < 1:
                    continue
                
                # Статистика
                stats[building_type] = stats.get(building_type, 0) + 1
                if levels_str:
                    stats['with_levels'] += 1
                else:
                    stats['without_levels'] += 1
                stats['total_population'] += population
                
                # Рассчитываем центр здания
                center = element.get('center')
                if center:
                    lat, lng = center['lat'], center['lon']
                elif geometry:
                    lat, lng = OpenStreetMapService._calculate_geometry_center(geometry)
                else:
                    continue
                
                # Интенсивность для тепловой карты (нормализация: 100 чел = 1.0)
                intensity = min(population / 80, 3.5)
                
                buildings_data.append({
                    'lat': lat,
                    'lng': lng,
                    'type': 'residential',
                    'building_type': building_type,
                    'building_category': building_category,  # 'elite', 'soviet', 'private'
                    'levels': levels,
                    'area_m2': round(area_m2, 1),
                    'estimated_population': population,
                    'intensity': intensity,
                    'has_levels_data': levels_str is not None,
                    'address': tags.get('addr:street', '') + ' ' + tags.get('addr:housenumber', '')
                })

            # Выводим детальную статистику
            print(f"📊 Статистика загрузки зданий:")
            print(f"   • Многоквартирные (apartments): {stats.get('apartments', 0)}")
            print(f"   • Жилые (residential): {stats.get('residential', 0)}")
            print(f"   • Частные дома (house): {stats.get('house', 0)}")
            print(f"   • Общежития (dormitory): {stats.get('dormitory', 0)}")
            print(f"   • Таунхаусы (terrace): {stats.get('terrace', 0)}")
            print(f"   • Без типа (yes): {stats.get('yes', 0)}")
            print(f"   • С данными об этажах: {stats['with_levels']}")
            print(f"   • Без данных об этажах (оценка): {stats['without_levels']}")
            print(f"   • ИТОГО зданий: {len(buildings_data)}")
            print(f"   • ИТОГО население: ~{stats['total_population']:,} человек")
            
            return buildings_data
        
        except Exception as e:
            print(f"❌ Ошибка при получении жилых домов: {e}")
            traceback.print_exc()
            return []

    @staticmethod
    def _calculate_polygon_area(geometry):
        """
        Рассчитать площадь полигона в квадратных метрах по координатам.
        Использует формулу Shoelace (формула площади Гаусса).
        """
        if not geometry or len(geometry) < 3:
            return 0
        
        try:
            # Преобразуем координаты в список точек
            points = []
            for point in geometry:
                if isinstance(point, dict) and 'lat' in point and 'lon' in point:
                    points.append((point['lat'], point['lon']))
            
            if len(points) < 3:
                return 0
            
            # Формула Shoelace для расчета площади полигона
            n = len(points)
            area = 0.0
            
            for i in range(n):
                j = (i + 1) % n
                # Координаты в метрах (приблизительно для широты Бишкека ~42°)
                # 1° широты ≈ 111 км, 1° долготы ≈ 82 км на этой широте
                lat1, lon1 = points[i]
                lat2, lon2 = points[j]
                
                # Переводим в метры относительно центра
                x1 = lon1 * 82000  # м на градус долготы
                y1 = lat1 * 111000  # м на градус широты
                x2 = lon2 * 82000
                y2 = lat2 * 111000
                
                area += x1 * y2
                area -= x2 * y1
            
            area = abs(area) / 2.0
            return area
            
        except Exception as e:
            print(f"Ошибка расчета площади: {e}")
            return 0

    @staticmethod
    def _calculate_geometry_center(geometry):
        """Рассчитать центр геометрии"""
        if not geometry:
            return 0, 0
        
        lats = []
        lngs = []
        
        for point in geometry:
            if isinstance(point, dict) and 'lat' in point and 'lon' in point:
                lats.append(point['lat'])
                lngs.append(point['lon'])
        
        if lats and lngs:
            return sum(lats) / len(lats), sum(lngs) / len(lngs)
        return 0, 0

    @staticmethod
    def _calculate_real_population(building_type, levels_str, area_m2, tags):
        """
        Рассчитать РЕАЛЬНОЕ население здания по формуле:
        
        Население = (Площадь основания × Этажи × K) / Метров_на_человека
        
        Где:
        - K = 0.75-0.8 (коэффициент полезной площади, вычитаем стены, подъезды)
        - Метров на человека зависит от типа здания:
          • Элитки: 25-30 м²/чел
          • Советские панельки: 18-20 м²/чел  
          • Частный сектор: 15 м²/чел (2-3 поколения)
        
        Если этажность не указана в OSM:
        - Мелкие полигоны (< 200 м²): 1 этаж (частный дом)
        - Средние (200-400 м²): 2 этажа (большой частный дом)
        - Крупные (> 400 м²): 5 этажей (многоквартирный)
        """
        
        K = 0.75  # Коэффициент полезной площади
        
        # 1. Определяем количество этажей
        if levels_str:
            try:
                levels = int(float(levels_str))
            except (ValueError, TypeError):
                levels = None
        else:
            levels = None
        
        # 2. Определяем категорию здания и этажность по умолчанию
        if building_type == 'apartments':
            # Многоквартирный дом
            if levels is None:
                # Оцениваем по площади
                if area_m2 > 1000:
                    levels = 9  # Большой дом - скорее всего 9-этажка
                elif area_m2 > 500:
                    levels = 5  # Средний - 5-этажка (хрущевка)
                else:
                    levels = 4  # Маленький - 4-этажка
            
            # Определяем тип (элитка vs советский) по косвенным признакам
            name = tags.get('name', '').lower()
            if any(word in name for word in ['элит', 'премиум', 'люкс', 'бизнес', 'резиденс']):
                category = 'elite'
                sqm_per_person = 28  # Элитное жилье
            elif levels >= 9:
                category = 'soviet_high'
                sqm_per_person = 18  # Советские высотки
            else:
                category = 'soviet'
                sqm_per_person = 19  # Советские панельки
                
        elif building_type == 'house':
            # Частный дом - в Бишкеке обычно живет семья 4-6 человек
            category = 'private'
            sqm_per_person = 25  # Частный дом, но с семьей
            if levels is None:
                levels = 1 if area_m2 < 150 else 2
                
        elif building_type == 'residential':
            # Может быть и частный сектор, и небольшой многоквартирный
            if area_m2 < 300:
                category = 'private'
                sqm_per_person = 15
                if levels is None:
                    levels = 1 if area_m2 < 150 else 2
            else:
                category = 'soviet'
                sqm_per_person = 19
                if levels is None:
                    levels = 4 if area_m2 < 600 else 5
                    
        elif building_type == 'dormitory':
            # Общежитие - высокая плотность
            category = 'dormitory'
            sqm_per_person = 12
            if levels is None:
                levels = 5
                
        elif building_type == 'terrace':
            # Таунхаус
            category = 'terrace'
            sqm_per_person = 20
            if levels is None:
                levels = 2
                
        else:
            # building=yes или другое - определяем по площади
            if area_m2 < 200:
                category = 'private'
                sqm_per_person = 15
                levels = 1 if levels is None else levels
            elif area_m2 < 400:
                category = 'private_large'
                sqm_per_person = 15
                levels = 2 if levels is None else levels
            else:
                category = 'unknown_apartment'
                sqm_per_person = 18
                levels = 4 if levels is None else levels
        
        # 3. Рассчитываем население
        # 
        # РЕАЛИСТИЧНАЯ ФОРМУЛА для Бишкека:
        # - Частный дом: 4-6 человек (семья с родителями)
        # - Хрущевка 5 эт, 4 подъезда: ~150-200 человек
        # - 9-этажка 4 подъезда: ~400-500 человек
        #
        if category == 'private' or category == 'private_large':
            # Частный сектор - в Бишкеке 2-3 поколения под одной крышей
            if area_m2 < 80:
                population = 3  # Маленький дом
            elif area_m2 < 150:
                population = 5  # Средний дом - типичная семья
            elif area_m2 < 250:
                population = 7  # Большой дом - расширенная семья
            else:
                population = 10  # Очень большой дом - 2-3 поколения
        
        elif category in ['soviet', 'soviet_high', 'unknown_apartment']:
            # Многоквартирные дома
            # Формула: подъезды × этажи × квартир_на_площадке × людей_в_квартире
            # Оцениваем количество подъездов по площади основания
            if area_m2 > 0:
                # Типичный подъезд ~150-200 м² основания
                estimated_entrances = max(1, int(area_m2 / 180))
                flats_per_floor = 4  # Типично для советских домов
                people_per_flat = 2.8  # Средняя заполненность в Бишкеке
                
                population = int(estimated_entrances * levels * flats_per_floor * people_per_flat)
            else:
                # Fallback: 3 подъезда среднего дома
                population = int(3 * levels * 4 * 2.8)
        
        elif category == 'elite':
            # Элитные дома - меньше людей на квартиру, больше площадь квартир
            if area_m2 > 0:
                estimated_entrances = max(1, int(area_m2 / 250))  # Подъезды шире
                flats_per_floor = 2  # Меньше квартир на этаже
                people_per_flat = 3  
                population = int(estimated_entrances * levels * flats_per_floor * people_per_flat)
            else:
                population = int(2 * levels * 2 * 3)
        
        elif category == 'dormitory':
            # Общежития - очень высокая плотность
            if area_m2 > 0:
                rooms_total = int(area_m2 * levels * 0.7 / 18)  # ~18м² на комнату
                population = int(rooms_total * 2)  # 2 человека на комнату
            else:
                population = levels * 20
        
        elif category == 'terrace':
            # Таунхаусы - как большие частные дома
            population = 5 * levels
        
        else:
            # Неизвестный тип - fallback по площади
            if area_m2 > 0 and levels > 0:
                total_living_area = area_m2 * levels * K
                population = int(total_living_area / sqm_per_person)
            else:
                population = 5
        
        # Минимум 2 человека (хотя бы пара), максимум 600 (большой дом)
        population = max(2, min(population, 600))
        
        return category, levels, population

    @staticmethod
    def get_commercial_places_in_city(city_name):
        """НОВОЕ: Получить торговые центры и места скопления людей"""
        commercial_data = []
        
        city_info = OpenStreetMapService.get_city_boundaries(city_name)
        if not city_info:
            return []
        
        bbox = city_info.get('boundingbox')
        if not bbox or len(bbox) != 4:
            return []
        
        try:
            south, north, west, east = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
        except ValueError:
            return []

        # Запрос торговых центров, магазинов, ресторанов и других мест скопления людей
        overpass_query = f"""[out:json][timeout:120];
(
  node["shop"="mall"]({south},{west},{north},{east});
  node["shop"="supermarket"]({south},{west},{north},{east});
  node["amenity"="marketplace"]({south},{west},{north},{east});
  node["amenity"="restaurant"]({south},{west},{north},{east});
  node["amenity"="cafe"]({south},{west},{north},{east});
  node["amenity"="hospital"]({south},{west},{north},{east});
  node["amenity"="bank"]({south},{west},{north},{east});
  way["shop"="mall"]({south},{west},{north},{east});
  way["shop"="supermarket"]({south},{west},{north},{east});
  way["amenity"="marketplace"]({south},{west},{north},{east});
  way["amenity"="hospital"]({south},{west},{north},{east});
  relation["shop"="mall"]({south},{west},{north},{east});
);
out center;"""
        
        overpass_url = "https://overpass-api.de/api/interpreter"
        headers = {'User-Agent': 'BuildingOptimizerApp/1.0 (murgalag05@gmail.com)'}

        try:
            print(f"Overpass: Отправка запроса для коммерческих объектов в {city_name}...")
            time.sleep(2)
            response = requests.post(overpass_url, data=overpass_query.encode('utf-8'), headers=headers)
            response.raise_for_status()
            data = response.json()
            
            # Маппинг интенсивности по типам
            intensity_map = {
                'mall': 1.0,
                'supermarket': 0.8,
                'marketplace': 0.9,
                'hospital': 0.7,
                'restaurant': 0.6,
                'cafe': 0.4,
                'bank': 0.5
            }
            
            for element in data.get('elements', []):
                tags = element.get('tags', {})
                amenity = tags.get('amenity', '')
                shop = tags.get('shop', '')
                
                # Определяем тип и интенсивность
                place_type = amenity or shop
                intensity = intensity_map.get(place_type, 0.5)
                
                if element['type'] == 'node':
                    commercial_data.append({
                        'lat': element['lat'],
                        'lng': element['lon'],
                        'type': 'commercial',
                        'place_type': place_type,
                        'intensity': intensity,
                        'name': tags.get('name', f'{place_type.title()}')
                    })
                elif element['type'] in ['way', 'relation'] and 'center' in element:
                    commercial_data.append({
                        'lat': element['center']['lat'],
                        'lng': element['center']['lon'],
                        'type': 'commercial',
                        'place_type': place_type,
                        'intensity': intensity,
                        'name': tags.get('name', f'{place_type.title()}')
                    })

            print(f"Overpass: Найдено {len(commercial_data)} коммерческих объектов в городе {city_name}.")
            return commercial_data
        
        except Exception as e:
            print(f"Ошибка при получении коммерческих объектов: {e}")
            return []

    @staticmethod
    def generate_gradient_heatmap_data(districts_data, residential_data, commercial_data):
        """
        Генерировать тепловую карту на основе РЕАЛЬНЫХ данных о населении зданий.
        
        Используется формула:
        Население = (Площадь × Этажи × 0.75) / м²_на_человека
        
        Интенсивность точки пропорциональна населению здания.
        """
        heatmap_points = []
        
        print(f"🔥 Генерация тепловой карты на основе реальных данных...")
        print(f"   Исходные данные: {len(residential_data)} зданий, {len(commercial_data)} коммерческих объектов")
        
        # Статистика по категориям зданий
        stats = {
            'elite': {'count': 0, 'population': 0},
            'soviet': {'count': 0, 'population': 0},
            'soviet_high': {'count': 0, 'population': 0},
            'private': {'count': 0, 'population': 0},
            'private_large': {'count': 0, 'population': 0},
            'dormitory': {'count': 0, 'population': 0},
            'terrace': {'count': 0, 'population': 0},
            'unknown_apartment': {'count': 0, 'population': 0},
        }
        
        total_population = 0
        buildings_with_levels = 0
        
        for building in residential_data:
            population = building.get('estimated_population', 1)
            category = building.get('building_category', 'private')
            total_population += population
            
            # Обновляем статистику
            if category in stats:
                stats[category]['count'] += 1
                stats[category]['population'] += population
            
            if building.get('has_levels_data', False):
                buildings_with_levels += 1
            
            # Интенсивность для heatmap
            # Нормализация: 60 человек = 1.0 интенсивность
            # Максимум 4.0 для очень больших зданий
            intensity = min(population / 60, 4.0)
            
            # Усиливаем многоквартирные дома
            if category in ['soviet', 'soviet_high', 'elite', 'unknown_apartment']:
                intensity *= 1.2
            
            heatmap_points.append({
                'lat': building['lat'],
                'lng': building['lng'],
                'weight': max(intensity, 0.1)  # Минимум 0.1
            })
        
        # Добавляем коммерческие объекты (места дневного скопления людей)
        for place in commercial_data:
            place_intensity = place.get('intensity', 1.0) * 0.8  # Немного снижаем
            
            heatmap_points.append({
                'lat': place['lat'],
                'lng': place['lng'],
                'weight': min(place_intensity, 2.0)
            })
        
        # Выводим детальную статистику
        avg_population = total_population / len(residential_data) if residential_data else 0
        
        print(f"\n📊 СТАТИСТИКА НАСЕЛЕНИЯ БИШКЕКА:")
        print(f"   ═══════════════════════════════════════")
        print(f"   📍 Всего жилых зданий: {len(residential_data):,}")
        print(f"   📍 С данными об этажности: {buildings_with_levels:,} ({100*buildings_with_levels/max(len(residential_data),1):.1f}%)")
        print(f"   📍 Оценено по площади: {len(residential_data) - buildings_with_levels:,}")
        print(f"   ───────────────────────────────────────")
        
        # Статистика по категориям
        print(f"   🏢 Элитные дома: {stats['elite']['count']:,} зд. → ~{stats['elite']['population']:,} чел.")
        print(f"   🏗️ Советские высотки (9+): {stats['soviet_high']['count']:,} зд. → ~{stats['soviet_high']['population']:,} чел.")
        print(f"   🏠 Советские панельки (5): {stats['soviet']['count']:,} зд. → ~{stats['soviet']['population']:,} чел.")
        print(f"   🏡 Частный сектор: {stats['private']['count']:,} зд. → ~{stats['private']['population']:,} чел.")
        print(f"   🏘️ Большие частные: {stats['private_large']['count']:,} зд. → ~{stats['private_large']['population']:,} чел.")
        print(f"   🏨 Общежития: {stats['dormitory']['count']:,} зд. → ~{stats['dormitory']['population']:,} чел.")
        print(f"   🏚️ Таунхаусы: {stats['terrace']['count']:,} зд. → ~{stats['terrace']['population']:,} чел.")
        print(f"   ❓ Неопределенные МКД: {stats['unknown_apartment']['count']:,} зд. → ~{stats['unknown_apartment']['population']:,} чел.")
        print(f"   ───────────────────────────────────────")
        print(f"   👥 ИТОГО НАСЕЛЕНИЕ: ~{total_population:,} человек")
        print(f"   👤 Среднее на здание: {avg_population:.1f} человек")
        print(f"   🔥 Точек на тепловой карте: {len(heatmap_points):,}")
        print(f"   ═══════════════════════════════════════\n")
        
        return heatmap_points

    @staticmethod
    def calculate_district_population_density(districts_data, residential_data):
        """
        Рассчитать РЕАЛЬНУЮ плотность населения по районам на основе жилых зданий
        
        Возвращает обновленные данные районов с реальной плотностью
        """
        print("🧮 Расчет РЕАЛЬНОЙ плотности населения по районам...")
        print("   (на основе зданий, этажности и площади)\n")
        
        for district in districts_data:
            district_lat = district['lat']
            district_lng = district['lng']
            
            # Находим все здания в радиусе ~2.5км от центра района
            buildings_in_district = []
            category_stats = {}
            
            for building in residential_data:
                distance = OpenStreetMapService._calculate_distance(
                    district_lat, district_lng,
                    building['lat'], building['lng']
                )
                
                # Если здание в радиусе 2.5 км от центра района
                if distance <= 2.5:
                    buildings_in_district.append(building)
                    cat = building.get('building_category', 'unknown')
                    category_stats[cat] = category_stats.get(cat, 0) + 1
            
            # Рассчитываем общее население района
            total_population = sum(
                building.get('estimated_population', 1) 
                for building in buildings_in_district
            )
            
            # Площадь круга радиусом 2.5км = π * 2.5² ≈ 19.6 км²
            area_km2 = 19.6
            
            # Плотность = население / площадь
            density = int(total_population / area_km2) if area_km2 > 0 else 0
            
            # Количество зданий с реальными данными об этажах
            buildings_with_data = sum(
                1 for b in buildings_in_district if b.get('has_levels_data', False)
            )
            
            # Обновляем плотность района
            district['population_density'] = density
            district['calculated_population'] = total_population
            district['buildings_count'] = len(buildings_in_district)
            district['buildings_with_levels'] = buildings_with_data
            district['category_breakdown'] = category_stats
            
            print(f"   📍 {district['name']}:")
            print(f"      • Зданий: {len(buildings_in_district):,} (с этажами: {buildings_with_data})")
            print(f"      • Население: ~{total_population:,} чел.")
            print(f"      • Плотность: {density:,} чел/км²")
            if category_stats:
                cats = ', '.join([f"{k}:{v}" for k,v in sorted(category_stats.items(), key=lambda x: -x[1])[:3]])
                print(f"      • Типы: {cats}")
            print()
        
        return districts_data

    @staticmethod
    def _calculate_distance(lat1, lng1, lat2, lng2):
        """
        Рассчитать расстояние между двумя точками в километрах (формула гаверсинуса)
        """
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371  # Радиус Земли в км
        
        lat1_rad = radians(lat1)
        lat2_rad = radians(lat2)
        dlat = radians(lat2 - lat1)
        dlng = radians(lng2 - lng1)
        
        a = sin(dlat/2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlng/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
        distance = R * c
        return distance

    @staticmethod
    def cluster_buildings_for_display(buildings_data, grid_size=0.003):
        """
        🚀 ОПТИМИЗАЦИЯ: Кластеризация зданий в сетку для быстрого отображения.
        
        Вместо отправки 10000+ зданий, группируем их в ячейки сетки (~500-800 кластеров).
        Каждый кластер содержит агрегированную информацию о всех зданиях в ячейке.
        
        Args:
            buildings_data: список зданий с координатами и данными о населении
            grid_size: размер ячейки сетки в градусах (~300м для 0.003)
        
        Returns:
            list: кластеры с агрегированными данными
        """
        if not buildings_data:
            return []
        
        print(f"🔄 Кластеризация {len(buildings_data)} зданий (размер ячейки: {grid_size}°)...")
        
        # Словарь для группировки зданий по ячейкам сетки
        grid = {}
        
        for building in buildings_data:
            lat = building['lat']
            lng = building['lng']
            
            # Вычисляем индекс ячейки
            grid_lat = round(lat / grid_size) * grid_size
            grid_lng = round(lng / grid_size) * grid_size
            grid_key = (grid_lat, grid_lng)
            
            if grid_key not in grid:
                grid[grid_key] = {
                    'buildings': [],
                    'total_population': 0,
                    'total_levels': 0,
                    'total_area': 0,
                    'categories': {},
                    'with_levels_data': 0
                }
            
            cell = grid[grid_key]
            cell['buildings'].append(building)
            cell['total_population'] += building.get('estimated_population', 0)
            cell['total_levels'] += building.get('levels', 1)
            cell['total_area'] += building.get('area_m2', 0)
            
            if building.get('has_levels_data', False):
                cell['with_levels_data'] += 1
            
            cat = building.get('building_category', 'unknown')
            cell['categories'][cat] = cell['categories'].get(cat, 0) + 1
        
        # Формируем результат - агрегированные кластеры
        clusters = []
        
        for (grid_lat, grid_lng), cell in grid.items():
            buildings = cell['buildings']
            count = len(buildings)
            
            if count == 0:
                continue
            
            # Средневзвешенные координаты кластера
            avg_lat = sum(b['lat'] for b in buildings) / count
            avg_lng = sum(b['lng'] for b in buildings) / count
            
            # Определяем доминирующую категорию
            dominant_category = max(cell['categories'].items(), key=lambda x: x[1])[0] if cell['categories'] else 'unknown'
            
            # Средняя этажность
            avg_levels = cell['total_levels'] / count
            
            # Определяем цвет по доминирующей категории или средней этажности
            if avg_levels >= 9:
                color_category = 'high_rise'  # Красный
            elif avg_levels >= 6:
                color_category = 'mid_rise'   # Оранжевый  
            elif avg_levels >= 4:
                color_category = 'soviet'     # Желтый (хрущевки)
            elif avg_levels >= 2:
                color_category = 'low_rise'   # Салатовый
            else:
                color_category = 'private'    # Зеленый
            
            cluster = {
                'lat': round(avg_lat, 6),
                'lng': round(avg_lng, 6),
                'buildings_count': count,
                'total_population': cell['total_population'],
                'avg_levels': round(avg_levels, 1),
                'avg_area': round(cell['total_area'] / count, 0) if count > 0 else 0,
                'dominant_category': dominant_category,
                'color_category': color_category,
                'with_levels_data': cell['with_levels_data'],
                'categories': cell['categories']
            }
            
            clusters.append(cluster)
        
        # Сортируем по населению (для приоритетного отображения)
        clusters.sort(key=lambda x: -x['total_population'])
        
        print(f"✅ Создано {len(clusters)} кластеров из {len(buildings_data)} зданий")
        print(f"   Сжатие данных: {len(buildings_data)} → {len(clusters)} ({100*len(clusters)/len(buildings_data):.1f}%)")
        
        return clusters

    @staticmethod
    def generate_optimized_heatmap(buildings_data, grid_size=0.002):
        """
        🔥 Генерация оптимизированной тепловой карты.
        
        Вместо точки на каждое здание, генерируем точки на каждую ячейку сетки.
        Это значительно уменьшает количество точек и ускоряет рендеринг.
        """
        if not buildings_data:
            return []
        
        print(f"🔥 Генерация оптимизированной heatmap (grid: {grid_size}°)...")
        
        # Группируем население по ячейкам
        grid = {}
        
        for building in buildings_data:
            lat = building['lat']
            lng = building['lng']
            population = building.get('estimated_population', 1)
            
            grid_lat = round(lat / grid_size) * grid_size
            grid_lng = round(lng / grid_size) * grid_size
            grid_key = (grid_lat, grid_lng)
            
            if grid_key not in grid:
                grid[grid_key] = {'population': 0, 'count': 0}
            
            grid[grid_key]['population'] += population
            grid[grid_key]['count'] += 1
        
        # Генерируем точки heatmap
        heatmap_points = []
        
        for (grid_lat, grid_lng), data in grid.items():
            # Интенсивность: логарифмическая шкала для лучшего визуального распределения
            population = data['population']
            
            # Формула: log(population) нормализованный к 0-4
            if population > 0:
                intensity = min(math.log(population + 1) / 2.5, 4.0)
            else:
                intensity = 0.1
            
            heatmap_points.append({
                'lat': grid_lat,
                'lng': grid_lng,
                'weight': intensity
            })
        
        print(f"✅ Heatmap: {len(heatmap_points)} точек (вместо {len(buildings_data)} зданий)")
        
        return heatmap_points


class GeminiService:
    """Сервис для работы с Gemini API"""

    def __init__(self):
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY не установлен в settings.py")
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-pro')

    def get_building_suggestion(self, building_type, city, population_data):
        """Получить рекомендацию по размещению здания от Gemini"""
        
        districts_info = ""
        if population_data:
            districts_info = "Доступные районы и их плотность населения (чел/км²):\n"
            for district in population_data:
                districts_info += f"- {district['name']}: {district['population_density']} (lat: {district['lat']:.4f}, lng: {district['lng']:.4f})\n"
        else:
            districts_info = "Данные о плотности населения для районов отсутствуют."

        prompt = f"""
        Я ищу оптимальное место для размещения нового здания типа "{building_type}" в городе "{city}".
        
        Вот данные о плотности населения по районам в этом городе:
        {districts_info}

        Учитывая тип здания, порекомендуйте наиболее подходящий район или укажите координаты, если конкретный район не подходит, но есть оптимальная точка.
        
        Правила для рекомендации:
        1.  **Школа, Детский сад**: Предпочтительны районы со средней или высокой плотностью населения (от 1500 до 5000 чел/км²), чтобы обеспечить доступность для большого количества детей. Избегать слишком высоких значений (>5000) из-за перенаселенности и низких (<1000) из-за недостатка целевой аудитории. Важна близость к жилым зонам.
        2.  **Больница, Аптека**: Предпочтительны районы со средней или высокой плотностью населения (от 1500 до 4000 чел/км²) для обеспечения спроса на медицинские услуги. Доступность для большинства жителей.
        3.  **Торговый центр**: Лучше всего подходят районы со средней или высокой плотностью населения (от 2000 до 6000 чел/км²) с хорошей транспортной доступностью.
        4.  **Парк**: Желательны районы со средней или высокой плотностью населения (от 1000 до 3000 чел/км²), где есть потребность в зеленых зонах, но при этом достаточно свободного пространства. Избегать слишком плотных районов, где земли мало, и слишком редких, где спрос будет низким.

        Ваш ответ должен быть в формате JSON и содержать следующие поля:
        {{
            "district": "Название_района_или_ближайший_район",
            "coordinates": {{"lat": широта, "lng": долгота}},
            "confidence": баллы_уверенности_от_1_до_10,
            "reasoning": "Краткое_объяснение_почему_это_место_оптимально"
        }}
        
        Если по какой-то причине невозможно дать рекомендацию или город не найден, укажите "Нет данных" для района и объясните причину в reasoning, установив уверенность на 1.
        
        Пример ответа:
        {{
            "district": "Октябрьский",
            "coordinates": {{"lat": 42.8712, "lng": 74.5823}},
            "confidence": 8.5,
            "reasoning": "Октябрьский район имеет оптимальную плотность населения 3500 чел/км² для школы и хорошую транспортную доступность."
        }}
        """
        
        try:
            response = self.model.generate_content(prompt)
            response_text = response.text.replace("```json\n", "").replace("\n```", "").strip()
            print(f"Gemini raw response: {response_text}")
            suggestion = json.loads(response_text)
            return suggestion
        except Exception as e:
            print(f"Ошибка при получении рекомендации от Gemini: {e}")
            traceback.print_exc()
            return {
                "district": "Нет данных",
                "coordinates": {"lat": 0.0, "lng": 0.0},
                "confidence": 1,
                "reasoning": f"Не удалось получить рекомендацию от ИИ: {e}"
            }


class PopulationService:
    """Сервис для работы с данными о населении"""
    
    @staticmethod
    def calculate_real_population_density(city, districts_data, residential_buildings):
        """
        Рассчитывает РЕАЛЬНУЮ плотность населения на основе этажности зданий.
        Возвращает обновленные данные районов с реальной плотностью.
        """
        print(f"📊 Расчет реальной плотности населения для {city}...")
        
        updated_districts = []
        
        for district in districts_data:
            district_name = district['name']
            district_lat = district['lat']
            district_lng = district['lng']
            
            # Определяем границы района (примерно ±0.03 градуса = ~3км)
            lat_min = district_lat - 0.03
            lat_max = district_lat + 0.03
            lng_min = district_lng - 0.03
            lng_max = district_lng + 0.03
            
            # Находим все здания в этом районе
            buildings_in_district = [
                b for b in residential_buildings
                if lat_min <= b['lat'] <= lat_max and lng_min <= b['lng'] <= lng_max
            ]
            
            # Считаем общее население района
            total_population = sum(
                b.get('estimated_population', 15) for b in buildings_in_district
            )
            
            # Площадь района (примерно 6км × 6км = 36 км²)
            district_area_km2 = 36
            
            # Плотность = население / площадь
            if total_population > 0:
                real_density = int(total_population / district_area_km2)
            else:
                # Если зданий нет, используем минимальное значение
                real_density = district.get('population_density', 1000)
            
            print(f"   {district_name}: {len(buildings_in_district)} зданий, "
                  f"~{total_population:,} чел, плотность {real_density} чел/км²")
            
            updated_districts.append({
                **district,
                'population_density': real_density,
                'buildings_count': len(buildings_in_district),
                'estimated_population': total_population
            })
        
        return updated_districts
    
    @staticmethod
    def get_or_create_population_data(city):
        """Получить или создать данные о населении города с РЕАЛЬНЫМ расчетом плотности"""
        existing_data = PopulationData.objects.filter(city=city)
        
        osm_service = OpenStreetMapService()
        districts_from_osm = osm_service.get_districts_in_city(city)
        
        # Получаем жилые здания для расчета реальной плотности
        print("🏘️ Получение данных о жилых зданиях для расчета плотности...")
        residential_buildings = osm_service.get_residential_buildings_in_city(city)
        
        # Рассчитываем реальную плотность на основе зданий
        if residential_buildings:
            districts_from_osm = PopulationService.calculate_real_population_density(
                city, districts_from_osm, residential_buildings
            )
        else:
            print("⚠️ Нет данных о зданиях, используются статические значения плотности")
        
        population_data_for_response = []
        for district_osm in districts_from_osm:
            pop_data, created = PopulationData.objects.get_or_create(
                district_name=district_osm['name'], 
                city=city,
                defaults={
                    'lat': district_osm['lat'],
                    'lng': district_osm['lng'],
                    'population_density': district_osm['population_density'],
                }
            )
            if not created:
                if pop_data.population_density != district_osm['population_density']:
                    pop_data.population_density = district_osm['population_density']
                    pop_data.lat = district_osm['lat']
                    pop_data.lng = district_osm['lng']
                    pop_data.save()

            population_data_for_response.append({
                'district_name': pop_data.district_name,
                'name': pop_data.district_name,
                'lat': pop_data.lat,
                'lng': pop_data.lng,
                'population_density': pop_data.population_density,
                'city': pop_data.city,
                'geometry': district_osm.get('geometry', [])
            })
        
        if not districts_from_osm and existing_data.exists():
            for existing_district in existing_data:
                 population_data_for_response.append({
                    'district_name': existing_district.district_name,
                    'name': existing_district.district_name,
                    'lat': existing_district.lat,
                    'lng': existing_district.lng,
                    'population_density': existing_district.population_density,
                    'city': existing_district.city,
                    'geometry': []
                })

        return population_data_for_response