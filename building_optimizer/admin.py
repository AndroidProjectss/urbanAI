from django.contrib import admin
from .models import BuildingRequest, PopulationData, School

@admin.register(BuildingRequest)
class BuildingRequestAdmin(admin.ModelAdmin):
    list_display = ['building_type', 'city', 'confidence_score', 'created_at']
    list_filter = ['building_type', 'city', 'created_at']
    search_fields = ['city', 'reasoning']
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('building_type', 'city')
        }),
        ('Рекомендация', {
            'fields': ('suggested_lat', 'suggested_lng', 'confidence_score', 'reasoning')
        }),
        ('Метаданные', {
            'fields': ('population_density', 'created_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(PopulationData)
class PopulationDataAdmin(admin.ModelAdmin):
    list_display = ['district_name', 'city', 'population_density', 'lat', 'lng']
    list_filter = ['city']
    search_fields = ['district_name', 'city']
    
    fieldsets = (
        ('Район', {
            'fields': ('district_name', 'city')
        }),
        ('Геоданные', {
            'fields': ('lat', 'lng', 'population_density')
        }),
    )

@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ['name', 'district', 'total_students', 'max_capacity', 'occupancy_rate', 'is_overloaded']
    list_filter = ['district', 'region', 'owner_form']
    search_fields = ['name', 'full_name', 'address', 'district']
    readonly_fields = ['institution_id', 'occupancy_rate', 'is_overloaded', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('institution_id', 'name', 'full_name', 'code', 'address', 'district', 'region')
        }),
        ('Координаты', {
            'fields': ('latitude', 'longitude')
        }),
        ('Ученики', {
            'fields': ('total_students', 'total_students_girls', 'total_students_boys')
        }),
        ('Вместимость и загруженность', {
            'fields': ('total_classes', 'max_capacity', 'real_capacity', 'occupancy_rate', 'is_overloaded')
        }),
        ('Распределение по классам', {
            'fields': (
                'students_class_1', 'students_class_2', 'students_class_3', 'students_class_4',
                'students_class_5', 'students_class_6', 'students_class_7', 'students_class_8',
                'students_class_9', 'students_class_10', 'students_class_11'
            ),
            'classes': ('collapse',)
        }),
        ('Дополнительная информация', {
            'fields': ('phone_number', 'director_name', 'owner_form'),
            'classes': ('collapse',)
        }),
        ('Метаданные', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def occupancy_rate(self, obj):
        return f"{obj.occupancy_rate}%"
    occupancy_rate.short_description = 'Загруженность'
    
    def is_overloaded(self, obj):
        return "✅ Да" if obj.is_overloaded else "❌ Нет"
    is_overloaded.short_description = 'Перегружена'