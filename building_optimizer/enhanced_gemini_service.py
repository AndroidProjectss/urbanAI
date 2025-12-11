import os
from django.conf import settings
import google.generativeai as genai
import traceback
import json

class EnhancedGeminiService:
    """Сервис для обогащения данных о школах через Gemini с использованием XML"""

    def __init__(self):
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY не установлен в settings.py")
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-pro')
        self.xml_data = self._load_xml_data()

    def _load_xml_data(self):
        """Загружает XML данные как строку для передачи в Gemini"""
        try:
            data_path = os.path.join(
                settings.BASE_DIR, 
                'building_optimizer', 
                'data', 
                'education_data.xml'
            )
            
            print(f"🔍 Загрузка XML файла: {data_path}")
            
            if os.path.exists(data_path):
                with open(data_path, 'r', encoding='utf-8') as file:
                    xml_content = file.read()
                
                file_size = len(xml_content)
                print(f"✅ XML файл загружен, размер: {file_size} символов")
                
                # Считаем количество школ (org_* элементов)
                import re
                org_matches = re.findall(r'<org_\d+>', xml_content)
                print(f"📊 Найдено {len(org_matches)} школ в XML файле")
                
                # Если файл слишком большой для Gemini (больше 1MB), обрезаем для примера
                if file_size > 800000:  # ~800KB лимит
                    print(f"⚠️ Файл слишком большой ({file_size} символов), обрезаем для Gemini")
                    xml_content = xml_content[:800000] + "\n</root>"
                    print(f"✂️ Обрезано до 800KB")
                
                return xml_content
            else:
                print(f"❌ Файл {data_path} не найден")
                return None
                
        except Exception as e:
            print(f"❌ Ошибка загрузки XML файла: {e}")
            traceback.print_exc()
            return None

    def generate_enhanced_school_info(self, school_name, school_lat=None, school_lng=None):
        """Генерирует дополнительную информацию о школе через Gemini API"""
        
        print(f"🤖 Запрос к Gemini для школы: '{school_name}'")
        
        if not self.xml_data:
            print("❌ XML данные не загружены")
            return self._generate_fallback_info(school_name)

        # Создаем промпт для Gemini
        prompt = f"""
Тебе дан XML файл с данными образовательных учреждений Кыргызстана. Найди информацию о школе с названием "{school_name}".

XML данные:
{self.xml_data}

Инструкции:
1. Найди в XML записи (org_1, org_2, org_3, etc.), где название школы (поле <name> или <full_name>) наиболее похоже на "{school_name}"
2. Используй нечеткий поиск - ищи частичные совпадения по словам
3. Если найдешь подходящую школу, извлеки из XML следующие данные:
   - total_stdnts (общее количество учащихся)
   - workers_in_fact (количество сотрудников)
   - owner_form (форма собственности: Private property = Частная, State property = Государственная, Municipal property = Муниципальная)
   - address (адрес)
   - phone_number (телефон)
   - district (район)
   - ru_classes_total, kg_classes_total, uz_classes_total, tj_classes_total (классы по языкам)
   - institution_type (тип учреждения)
   - have_internet, comps_amnt, dinning_hall, lib_found (инфраструктура)

4. Верни результат строго в JSON формате:

Если школа НАЙДЕНА в XML:
{{
    "found": true,
    "students_count": "количество учащихся или 'Данные не заполнены' если 0",
    "staff_count": "количество сотрудников или 'Данные не заполнены' если 0", 
    "ownership": "форма собственности на русском",
    "language": "основной язык обучения на основе количества классов по языкам",
    "specialization": "тип школы (гимназия/лицей/международная/европейская/общеобразовательная)",
    "address": "полный адрес",
    "contact_info": "номер телефона",
    "description": "подробное описание школы на основе найденных данных",
    "xml_school_name": "точное название школы из XML"
}}

Если школа НЕ НАЙДЕНА в XML:
{{
    "found": false,
    "students_count": "Не указано",
    "staff_count": "Не указано",
    "ownership": "Не указано",
    "language": "Кыргызский/Русский",
    "specialization": "Общеобразовательная школа",
    "address": "Бишкек",
    "contact_info": "Не указано",
    "description": "Информация о школе {school_name} не найдена в реестре образовательных учреждений."
}}

ВАЖНО: Отвечай ТОЛЬКО JSON, без дополнительного текста!
"""

        try:
            print("🚀 Отправляем запрос к Gemini...")
            response = self.model.generate_content(prompt)
            response_text = response.text.strip()
            
            print(f"📥 Ответ от Gemini получен (длина: {len(response_text)} символов)")
            
            # Очищаем ответ от markdown разметки
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].strip()
            
            print(f"🧹 Очищенный ответ: {response_text[:200]}...")
            
            # Парсим JSON
            try:
                school_info = json.loads(response_text)
                print("✅ JSON успешно распарсен")
            except json.JSONDecodeError as e:
                print(f"❌ Ошибка парсинга JSON: {e}")
                print(f"Сырой ответ: {response_text}")
                return self._generate_fallback_info(school_name)
            
            # Добавляем метаинформацию
            school_info['has_registry_data'] = school_info.get('found', False)
            
            if school_info.get('found', False):
                print(f"🎯 Школа найдена в XML: {school_info.get('xml_school_name', 'Неизвестно')}")
            else:
                print("❌ Школа не найдена в XML")
            
            return school_info
            
        except Exception as e:
            print(f"❌ Ошибка запроса к Gemini: {e}")
            traceback.print_exc()
            return self._generate_fallback_info(school_name)

    def _generate_fallback_info(self, school_name):
        """Генерирует базовую информацию, если основная система не работает"""
        return {
            "students_count": "Не указано",
            "staff_count": "Не указано", 
            "ownership": "Не указано",
            "language": "Кыргызский/Русский",
            "specialization": "Общеобразовательная школа",
            "address": "Бишкек",
            "contact_info": "Не указано",
            "description": f"Информация о школе {school_name} временно недоступна.",
            "has_registry_data": False
        }