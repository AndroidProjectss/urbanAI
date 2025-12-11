from django.db import models

class BuildingRequest(models.Model):
    BUILDING_TYPES = [
        ('school', 'Школа'),
        ('hospital', 'Больница'),
        ('kindergarten', 'Детский сад'),
        ('pharmacy', 'Аптека'),
        ('shopping_center', 'Торговый центр'),
        ('park', 'Парк'),
    ]
    
    building_type = models.CharField(max_length=50, choices=BUILDING_TYPES)
    city = models.CharField(max_length=100)
    suggested_lat = models.FloatField()
    suggested_lng = models.FloatField()
    population_density = models.FloatField()
    confidence_score = models.FloatField()
    reasoning = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.get_building_type_display()} в {self.city}"

class PopulationData(models.Model):
    """Модель для хранения данных о плотности населения"""
    district_name = models.CharField(max_length=200)
    lat = models.FloatField()
    lng = models.FloatField()
    population_density = models.IntegerField()  # человек на км²
    city = models.CharField(max_length=100)
    
    def __str__(self):
        return f"{self.district_name} - {self.population_density} чел/км²"