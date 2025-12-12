from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    
    # Существующие API
    path('population-heatmap/', views.get_population_heatmap, name='population_heatmap'),
    path('suggest-location/', views.suggest_building_location, name='suggest_building_location'),
    path('history/', views.get_building_history, name='building_history'),
    path('schools/', views.get_schools, name='get_schools'),
    path('districts/', views.get_districts, name='get_districts'),
    
    # НОВЫЕ API для Google Maps
    path('enhanced-heatmap/', views.get_enhanced_heatmap_data, name='enhanced_heatmap'),
    path('residential-buildings/', views.get_residential_buildings, name='residential_buildings'),
    path('commercial-places/', views.get_commercial_places, name='commercial_places'),
    path('enhanced-school-info/', views.get_enhanced_school_info, name='enhanced_school_info'),
    path('analyze/', views.analyze_districts, name='analyze_districts'),

    # 🆕 API для зданий в viewport (viewport culling)
    path('buildings-in-viewport/', views.get_buildings_in_viewport, name='buildings_in_viewport'),

    # ML API - Прогнозирование востребованности школ
    path('ml/status/', views.ml_model_status, name='ml_model_status'),
    path('ml/train/', views.ml_train_model, name='ml_train_model'),
    path('ml/overview/', views.ml_city_overview, name='ml_city_overview'),
    path('ml/district/', views.ml_district_analysis, name='ml_district_analysis'),
    path('ml/risk-schools/', views.ml_risk_schools, name='ml_risk_schools'),
    path('ml/school-forecast/', views.ml_school_forecast, name='ml_school_forecast'),

    # ML API - Демографические данные и когортный прогноз
    path('ml/demographics/', views.ml_demographics, name='ml_demographics'),
    path('ml/cohort-forecast/', views.ml_cohort_forecast, name='ml_cohort_forecast'),

    # ML API - Прогноз населения Бишкека
    path('ml/population-forecast/', views.population_forecast, name='population_forecast'),
    path('ml/population-pyramid/', views.population_pyramid, name='population_pyramid'),
    path('ml/population-growth/', views.population_growth_components, name='population_growth'),
    path('ml/natural-growth/', views.natural_growth_analysis, name='natural_growth_analysis'),

    # ML API - ПРОГНОЗИРОВАНИЕ НАСЕЛЕНИЯ (на основе реальных данных)
    path('ml/population-ml-forecast/', views.ml_population_full_forecast, name='ml_population_forecast'),
    path('ml/train-population/', views.ml_train_population_model, name='ml_train_population'),
    path('ml/predict-growth/', views.ml_predict_natural_growth, name='ml_predict_growth'),
    path('ml/predict-school-population/', views.ml_predict_school_population, name='ml_predict_school_pop'),
]
