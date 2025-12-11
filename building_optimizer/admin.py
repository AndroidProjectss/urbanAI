from django.contrib import admin
from .models import BuildingRequest, PopulationData

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