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

class School(models.Model):
    """Модель для хранения данных о школах из ИСУО"""
    institution_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=500)
    full_name = models.CharField(max_length=500, blank=True, null=True)
    code = models.CharField(max_length=100, blank=True, null=True)
    address = models.TextField()
    district = models.CharField(max_length=200)
    region = models.CharField(max_length=200)
    
    # Координаты
    latitude = models.FloatField()
    longitude = models.FloatField()
    
    # Количество учеников
    total_students = models.IntegerField(default=0)
    total_students_girls = models.IntegerField(default=0)
    total_students_boys = models.IntegerField(default=0)
    
    # Количество классов и мест
    total_classes = models.IntegerField(default=0)
    max_capacity = models.IntegerField(default=0)  # максимальная вместимость
    real_capacity = models.IntegerField(default=0)  # реальная вместимость
    
    # Распределение по классам (1-11)
    students_class_1 = models.IntegerField(default=0)
    students_class_2 = models.IntegerField(default=0)
    students_class_3 = models.IntegerField(default=0)
    students_class_4 = models.IntegerField(default=0)
    students_class_5 = models.IntegerField(default=0)
    students_class_6 = models.IntegerField(default=0)
    students_class_7 = models.IntegerField(default=0)
    students_class_8 = models.IntegerField(default=0)
    students_class_9 = models.IntegerField(default=0)
    students_class_10 = models.IntegerField(default=0)
    students_class_11 = models.IntegerField(default=0)
    
    # Дополнительная информация
    phone_number = models.CharField(max_length=100, blank=True, null=True)
    director_name = models.CharField(max_length=200, blank=True, null=True)
    owner_form = models.CharField(max_length=100, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.district})"
    
    @property
    def estimated_capacity(self):
        """Оценочная вместимость школы с учетом отсутствующих данных"""
        # 1. Если есть официальная максимальная вместимость
        if self.max_capacity > 0:
            return self.max_capacity
        
        # 2. Если есть реальная вместимость
        if self.real_capacity > 0:
            return self.real_capacity
        
        # 3. Расчет по количеству классов (стандарт: 28 учеников/класс)
        if self.total_classes > 0:
            return self.total_classes * 28
        
        # 4. Если есть ученики, но нет других данных - используем текущее количество как минимум
        if self.total_students > 0:
            return self.total_students
        
        # 5. Нет данных
        return 0
    
    @property
    def occupancy_rate(self):
        """Процент загруженности школы"""
        capacity = self.estimated_capacity
        if capacity > 0:
            return round((self.total_students / capacity) * 100, 2)
        return 0
    
    @property
    def is_overloaded(self):
        """Перегружена ли школа (больше 100%)"""
        return self.occupancy_rate > 100
    
    class Meta:
        verbose_name = "Школа"
        verbose_name_plural = "Школы"
        ordering = ['name']