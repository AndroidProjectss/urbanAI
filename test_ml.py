#!/usr/bin/env python
"""Тест интеграции демографических данных в ML модель"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'urbanproject.settings')
django.setup()

from building_optimizer.ml_service import SchoolDemandForecaster
from building_optimizer.models import School

# Получаем школы из БД
schools = list(School.objects.all())
print(f'Загружено школ: {len(schools)}')

# Создаем и обучаем модель
forecaster = SchoolDemandForecaster()
result = forecaster.train(schools)

print()
print('=== РЕЗУЛЬТАТЫ ОБУЧЕНИЯ ML МОДЕЛИ ===')
print(f'Успех: {result.get("success", False)}')

stats = result.get('stats', {})
print(f'Школ обучено: {stats.get("samples", 0)}')
print(f'Признаков: {stats.get("features", 0)}')
print(f'R² Score: {stats.get("cv_score_mean", 0):.2%} ± {stats.get("cv_score_std", 0):.2%}')

features = forecaster.feature_names
print(f'\n=== ПРИЗНАКИ МОДЕЛИ ({len(features)} шт.) ===')
for i, f in enumerate(features, 1):
    marker = '★' if 'demo' in f or 'growth' in f or 'expected' in f or 'share' in f else ' '
    print(f'  {marker} {i:2}. {f}')

print('\n=== ДЕМОГРАФИЧЕСКИЕ ДАННЫЕ В МОДЕЛИ ===')
demo = stats.get('demographic_data_used', {})
if demo:
    print(f'  ✓ Годы данных: {demo.get("natural_growth_years", [])[-5:]}')
    print(f'  ✓ Средний прирост: {demo.get("avg_annual_growth", 0):,.0f} чел/год')
    print(f'  ✓ Прирост 2023-2024: {demo.get("recent_growth_2023_2024", 0):,.0f} чел/год')
    print(f'  ✓ Прогноз прироста: {demo.get("projected_growth", 0):,.0f} чел/год')
    print(f'  ✓ Коэфф. роста: {demo.get("adjusted_growth_rate", 0)*100:.2f}%')
else:
    print('  (не записаны в статистику)')

# Тест прогноза
print('\n=== ТЕСТ ПРОГНОЗА ДЛЯ ШКОЛЫ ===')
if schools and forecaster.model:
    test_school = schools[0]
    forecast = forecaster.predict_school_demand(test_school, years_ahead=5)
    print(f'Школа: {test_school.name[:50]}...')
    print(f'Текущая загрузка: {test_school.occupancy_rate}%')
    for year_data in forecast.get('yearly_forecasts', [])[:3]:
        print(f'  {year_data["year"]}: {year_data["predicted_students"]} уч., '
              f'загрузка {year_data["predicted_occupancy"]:.1f}%, '
              f'рост {year_data.get("growth_rate_used", "N/A")}%')
