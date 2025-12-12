import xml.etree.ElementTree as ET
from django.core.management.base import BaseCommand
from building_optimizer.models import School
import html
import os


class Command(BaseCommand):
    help = 'Загрузка данных о школах из XML файла ИСУО'

    def handle(self, *args, **options):
        xml_file_path = 'Открытые Данные ИСУО (г.Бишкек область).xml'
        
        if not os.path.exists(xml_file_path):
            self.stdout.write(self.style.ERROR(f'Файл {xml_file_path} не найден!'))
            return
        
        self.stdout.write(self.style.SUCCESS('Начинаем парсинг XML файла...'))
        
        try:
            # Парсим XML
            tree = ET.parse(xml_file_path)
            root = tree.getroot()
            
            schools_count = 0
            updated_count = 0
            created_count = 0
            
            # Ищем все элементы с org_*
            for org_element in root:
                if not org_element.tag.startswith('org_'):
                    continue
                
                # Проверяем, что это школа
                is_schools = org_element.find('is_schools')
                if is_schools is None or is_schools.text != '1':
                    continue
                
                try:
                    # Извлекаем данные
                    institution_id_elem = org_element.find('institution_id')
                    if institution_id_elem is None or not institution_id_elem.text:
                        continue
                    
                    institution_id = int(institution_id_elem.text)
                    
                    # Получаем координаты
                    lat_elem = org_element.find('latitude')
                    lng_elem = org_element.find('longitude')
                    
                    if lat_elem is None or lng_elem is None:
                        continue
                    
                    try:
                        latitude = float(lat_elem.text)
                        longitude = float(lng_elem.text)
                    except (ValueError, TypeError):
                        continue
                    
                    # Пропускаем некорректные координаты
                    if latitude == 0 or longitude == 0:
                        continue
                    
                    # Декодируем HTML-сущности из названия
                    name = html.unescape(self._get_text(org_element, 'name', ''))
                    full_name = html.unescape(self._get_text(org_element, 'full_name', ''))
                    address = html.unescape(self._get_text(org_element, 'address', ''))
                    district = html.unescape(self._get_text(org_element, 'district', ''))
                    region = html.unescape(self._get_text(org_element, 'region', ''))
                    
                    # Проверяем, что это школа в г. Бишкек
                    if 'Бишкек' not in region:
                        continue
                    
                    # Получаем данные об учениках
                    total_students = self._get_int(org_element, 'total_stdnts', 0)
                    total_students_girls = self._get_int(org_element, 'total_stdnts_girls', 0)
                    total_students_boys = self._get_int(org_element, 'total_stdnts_boys', 0)
                    
                    # Получаем количество классов и вместимость
                    total_classes = self._get_int(org_element, 'total_classes', 0)
                    max_capacity = self._get_int(org_element, 'max_capacity_of_organization', 0)
                    real_capacity = self._get_int(org_element, 'real_capacity_of_organization', 0)
                    
                    # Получаем распределение по классам
                    students_class_1 = self._get_int(org_element, 'stdnt_1_class', 0)
                    students_class_2 = self._get_int(org_element, 'stdnt_2_class', 0)
                    students_class_3 = self._get_int(org_element, 'stdnt_3_class', 0)
                    students_class_4 = self._get_int(org_element, 'stdnt_4_class', 0)
                    students_class_5 = self._get_int(org_element, 'stdnt_5_class', 0)
                    students_class_6 = self._get_int(org_element, 'stdnt_6_class', 0)
                    students_class_7 = self._get_int(org_element, 'stdnt_7_class', 0)
                    students_class_8 = self._get_int(org_element, 'stdnt_8_class', 0)
                    students_class_9 = self._get_int(org_element, 'stdnt_9_class', 0)
                    students_class_10 = self._get_int(org_element, 'stdnt_10_class', 0)
                    students_class_11 = self._get_int(org_element, 'stdnt_11_class', 0)
                    
                    # Дополнительная информация
                    phone_number = self._get_text(org_element, 'phone_number', '')
                    director_name = html.unescape(self._get_text(org_element, 'director_fml_name', ''))
                    owner_form = self._get_text(org_element, 'owner_form', '')
                    code = self._get_text(org_element, 'code', '')
                    
                    # Создаем или обновляем запись в базе
                    school, created = School.objects.update_or_create(
                        institution_id=institution_id,
                        defaults={
                            'name': name,
                            'full_name': full_name,
                            'code': code,
                            'address': address,
                            'district': district,
                            'region': region,
                            'latitude': latitude,
                            'longitude': longitude,
                            'total_students': total_students,
                            'total_students_girls': total_students_girls,
                            'total_students_boys': total_students_boys,
                            'total_classes': total_classes,
                            'max_capacity': max_capacity,
                            'real_capacity': real_capacity,
                            'students_class_1': students_class_1,
                            'students_class_2': students_class_2,
                            'students_class_3': students_class_3,
                            'students_class_4': students_class_4,
                            'students_class_5': students_class_5,
                            'students_class_6': students_class_6,
                            'students_class_7': students_class_7,
                            'students_class_8': students_class_8,
                            'students_class_9': students_class_9,
                            'students_class_10': students_class_10,
                            'students_class_11': students_class_11,
                            'phone_number': phone_number,
                            'director_name': director_name,
                            'owner_form': owner_form,
                        }
                    )
                    
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
                    
                    schools_count += 1
                    
                    if schools_count % 10 == 0:
                        self.stdout.write(f'Обработано школ: {schools_count}...')
                
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'Ошибка при обработке школы: {e}'))
                    continue
            
            self.stdout.write(self.style.SUCCESS(f'\n✅ Загрузка завершена!'))
            self.stdout.write(self.style.SUCCESS(f'📊 Всего обработано школ: {schools_count}'))
            self.stdout.write(self.style.SUCCESS(f'➕ Создано новых: {created_count}'))
            self.stdout.write(self.style.SUCCESS(f'🔄 Обновлено: {updated_count}'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка при парсинге XML: {e}'))
            import traceback
            traceback.print_exc()
    
    def _get_text(self, element, tag, default=''):
        """Безопасное получение текста из элемента"""
        child = element.find(tag)
        if child is not None and child.text:
            return child.text.strip()
        return default
    
    def _get_int(self, element, tag, default=0):
        """Безопасное получение числа из элемента"""
        text = self._get_text(element, tag, str(default))
        try:
            return int(float(text))
        except (ValueError, TypeError):
            return default
