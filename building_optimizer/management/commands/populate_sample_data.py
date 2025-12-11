from django.core.management.base import BaseCommand
from building_optimizer.models import PopulationData
import random

class Command(BaseCommand):
    help = 'Заполняет базу данных примерными данными для демонстрации'

    def handle(self, *args, **options):
        # Очищаем существующие данные
        PopulationData.objects.all().delete()
        
        # Данные для Бишкека
        bishkek_districts = [
            {'name': 'Свердловский район', 'lat': 42.8746, 'lng': 74.5698, 'density': 3200},
            {'name': 'Первомайский район', 'lat': 42.8500, 'lng': 74.6200, 'density': 4500},
            {'name': 'Октябрьский район', 'lat': 42.8800, 'lng': 74.5400, 'density': 2800},
            {'name': 'Ленинский район', 'lat': 42.8900, 'lng': 74.5800, 'density': 3800},
            {'name': 'Центр', 'lat': 42.8756, 'lng': 74.5977, 'density': 5200},
            {'name': 'Восток-5', 'lat': 42.8400, 'lng': 74.6400, 'density': 2100},
        ]
        
        # Добавляем районы Бишкека
        for district in bishkek_districts:
            PopulationData.objects.create(
                district_name=district['name'],
                lat=district['lat'],
                lng=district['lng'],
                population_density=district['density'],
                city='Бишкек'
            )
        
        # Данные для Алматы
        almaty_districts = [
            {'name': 'Медеуский район', 'lat': 43.2220, 'lng': 76.8512, 'density': 4200},
            {'name': 'Бостандыкский район', 'lat': 43.2500, 'lng': 76.9500, 'density': 3800},
            {'name': 'Алмалинский район', 'lat': 43.2565, 'lng': 76.9286, 'density': 5500},
            {'name': 'Ауэзовский район', 'lat': 43.2100, 'lng': 76.8700, 'density': 3200},
            {'name': 'Турксибский район', 'lat': 43.2800, 'lng': 76.8800, 'density': 2900},
        ]
        
        for district in almaty_districts:
            PopulationData.objects.create(
                district_name=district['name'],
                lat=district['lat'],
                lng=district['lng'],
                population_density=district['density'],
                city='Алматы'
            )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Успешно создано {PopulationData.objects.count()} записей'
            )
        )