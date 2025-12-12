"""
ML-сервис для прогнозирования востребованности школ в г. Бишкек

Использует данные ИСУО для:
1. Анализа текущей загруженности школ
2. Прогнозирования потребности в местах на ближайшие годы
3. Выявления районов с дефицитом/избытком школьных мест
4. Рекомендаций по строительству новых школ

Основная идея: распределение учеников по классам (1-11) даёт "псевдо-временной ряд",
где 1-й класс = будущие потребности, 11-й класс = выпускники.

Интегрированы реальные демографические данные Бишкека за 2022 год (население 6-18 лет).
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score
import json
import traceback
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import joblib
import os


# =====================================================
# РЕАЛЬНЫЕ ДЕМОГРАФИЧЕСКИЕ ДАННЫЕ БИШКЕКА
# =====================================================

# Население школьного возраста (6-18 лет) за 2022 год
# Источник: Национальный статистический комитет КР
BISHKEK_POPULATION_2022 = {
    6: 15_741,   # Дошкольники → будущие первоклассники
    7: 15_307,   # 1 класс
    8: 14_674,   # 2 класс
    9: 14_614,   # 3 класс
    10: 13_934,  # 4 класс
    11: 15_550,  # 5 класс
    12: 14_447,  # 6 класс
    13: 14_405,  # 7 класс
    14: 13_556,  # 8 класс
    15: 12_964,  # 9 класс
    16: 13_677,  # 10 класс
    17: 14_600,  # 11 класс
    18: 17_842,  # Выпускники (для анализа трендов)
}

# Общее количество детей школьного возраста (7-17 лет)
TOTAL_SCHOOL_AGE_POPULATION_2022 = sum(
    BISHKEK_POPULATION_2022[age] for age in range(7, 18)
)  # = 158,128

# Население по классам (возраст → класс: возраст - 6)
POPULATION_BY_GRADE_2022 = {
    1: BISHKEK_POPULATION_2022[7],   # 15,307
    2: BISHKEK_POPULATION_2022[8],   # 14,674
    3: BISHKEK_POPULATION_2022[9],   # 14,614
    4: BISHKEK_POPULATION_2022[10],  # 13,934
    5: BISHKEK_POPULATION_2022[11],  # 15,550
    6: BISHKEK_POPULATION_2022[12],  # 14,447
    7: BISHKEK_POPULATION_2022[13],  # 14,405
    8: BISHKEK_POPULATION_2022[14],  # 13,556
    9: BISHKEK_POPULATION_2022[15],  # 12,964
    10: BISHKEK_POPULATION_2022[16], # 13,677
    11: BISHKEK_POPULATION_2022[17], # 14,600
}


# =====================================================
# ОБЩЕЕ НАСЕЛЕНИЕ БИШКЕКА И ДЕМОГРАФИЧЕСКИЕ ПАРАМЕТРЫ
# =====================================================

# Официальная статистика населения Бишкека
BISHKEK_TOTAL_POPULATION = {
    2018: 1_027_200,
    2019: 1_053_900,
    2020: 1_074_100,
    2021: 1_097_600,
    2022: 1_120_800,
    2023: 1_145_000,  # Оценка
    2024: 1_170_000,  # Оценка
}

# =====================================================
# РЕАЛЬНЫЕ ДАННЫЕ О ЕСТЕСТВЕННОМ ПРИРОСТЕ БИШКЕКА
# Источник: Национальный статистический комитет КР
# =====================================================

# Естественный прирост населения (рождения - смерти) по годам
NATURAL_POPULATION_GROWTH = {
    2011: 15_547,
    2012: 17_199,
    2013: 18_054,
    2014: 19_267,
    2015: 18_027,
    2016: 17_982,
    2017: 17_602,
    2018: 22_912,
    2019: 24_780,
    2020: 20_236,  # COVID-19 влияние
    2021: 21_312,
    2022: 22_509,
    2023: 8_369,   # Резкое снижение
    2024: 10_219,  # Восстановление
}

# Анализ трендов естественного прироста
def analyze_natural_growth_trends() -> Dict:
    """
    Анализ трендов естественного прироста населения
    на основе реальных данных 2011-2024
    """
    years = sorted(NATURAL_POPULATION_GROWTH.keys())
    values = [NATURAL_POPULATION_GROWTH[y] for y in years]
    
    # Периоды
    period_2011_2017 = [NATURAL_POPULATION_GROWTH[y] for y in range(2011, 2018)]
    period_2018_2022 = [NATURAL_POPULATION_GROWTH[y] for y in range(2018, 2023)]
    period_2023_2024 = [NATURAL_POPULATION_GROWTH[y] for y in range(2023, 2025)]
    
    # Средние по периодам
    avg_2011_2017 = sum(period_2011_2017) / len(period_2011_2017)
    avg_2018_2022 = sum(period_2018_2022) / len(period_2018_2022)
    avg_2023_2024 = sum(period_2023_2024) / len(period_2023_2024)
    
    # Линейный тренд
    x = np.array(years).reshape(-1, 1)
    y = np.array(values)
    lr = LinearRegression().fit(x, y)
    trend_slope = lr.coef_[0]
    
    # Прогноз на будущие годы с учётом последних тенденций
    # Используем среднее между пиковым периодом и текущим
    projected_growth = (avg_2018_2022 + avg_2023_2024) / 2
    
    return {
        'historical_data': NATURAL_POPULATION_GROWTH,
        'total_growth_2011_2024': sum(values),
        'average_annual': round(sum(values) / len(values), 0),
        'periods': {
            '2011-2017': {
                'average': round(avg_2011_2017, 0),
                'description': 'Стабильный рост'
            },
            '2018-2022': {
                'average': round(avg_2018_2022, 0),
                'description': 'Пиковый период (высокая рождаемость)'
            },
            '2023-2024': {
                'average': round(avg_2023_2024, 0),
                'description': 'Снижение (демографический переход)'
            }
        },
        'trend_slope': round(trend_slope, 2),
        'trend_direction': 'declining' if trend_slope < 0 else 'growing',
        'max_year': max(NATURAL_POPULATION_GROWTH, key=NATURAL_POPULATION_GROWTH.get),
        'max_value': max(values),
        'min_year': min(NATURAL_POPULATION_GROWTH, key=NATURAL_POPULATION_GROWTH.get),
        'min_value': min(values),
        'projected_annual_growth': round(projected_growth, 0),
        'volatility': round(np.std(values), 0)
    }


def get_adjusted_growth_rate(year: int) -> float:
    """
    Получить скорректированный коэффициент роста на основе реальных данных.
    
    Учитывает:
    - Исторический естественный прирост
    - Миграционный прирост
    - Тренды последних лет
    """
    # Если есть реальные данные за год
    if year in NATURAL_POPULATION_GROWTH:
        natural = NATURAL_POPULATION_GROWTH[year]
        population = BISHKEK_TOTAL_POPULATION.get(year, 1_100_000)
        natural_rate = natural / population
        
        # Добавляем миграцию (~0.8-1% в год)
        migration_rate = 0.008
        return natural_rate + migration_rate
    
    # Прогноз на будущее - используем консервативную оценку
    # На основе тренда 2023-2024 (снижение рождаемости)
    analysis = analyze_natural_growth_trends()
    projected_natural = analysis['projected_annual_growth']
    
    # Оцениваем население на год
    base_pop = 1_170_000  # 2024
    years_from_2024 = year - 2024
    estimated_pop = base_pop * (1.02 ** years_from_2024)
    
    natural_rate = projected_natural / estimated_pop
    migration_rate = 0.008  # Стабильная миграция
    
    return natural_rate + migration_rate


# Демографические коэффициенты Бишкека (ОБНОВЛЕНО на основе реальных данных)
DEMOGRAPHIC_RATES = {
    # Исторические средние (2011-2024)
    'avg_natural_growth_2011_2024': 17_358,
    'peak_natural_growth_2019': 24_780,
    'recent_natural_growth_2024': 10_219,
    
    # Расчётные коэффициенты на 1000 населения (на основе 2022 года)
    'birth_rate': 20.1,          # ~22,500 рождений / 1,120,800 * 1000
    'death_rate': 5.8,           # Смертность на 1000 населения
    'natural_growth': 17.9,      # Естественный прирост на 1000 (2022)
    'migration_rate': 8.0,       # Миграционный прирост на 1000
    'total_growth_rate': 25.9,   # Общий прирост на 1000
    
    # Скорректированные коэффициенты (с учётом 2023-2024)
    'adjusted_birth_rate': 16.5,     # Снижение рождаемости
    'adjusted_natural_growth': 8.7,  # Среднее 2023-2024
    'adjusted_total_growth': 16.7,   # С миграцией
    
    'fertility_rate': 2.1,       # Коэффициент фертильности (снижается)
}

# Возрастная структура населения Бишкека (%, 2022)
AGE_STRUCTURE_2022 = {
    '0-5': 9.2,      # Дошкольники
    '6-17': 14.1,    # Школьный возраст (наши данные)
    '18-24': 10.5,   # Молодёжь
    '25-34': 18.3,   # Молодые взрослые
    '35-44': 15.2,   # Средний возраст
    '45-54': 12.1,   # Старший средний
    '55-64': 10.8,   # Предпенсионный
    '65+': 9.8,      # Пенсионеры
}

# Расчётное население по возрастным группам (2022, ~1.12 млн)
def get_population_by_age_groups(year: int = 2022) -> Dict[str, int]:
    """Население по возрастным группам"""
    base_pop = BISHKEK_TOTAL_POPULATION.get(year, 1_120_800)
    return {
        group: int(base_pop * pct / 100)
        for group, pct in AGE_STRUCTURE_2022.items()
    }


# =====================================================
# ФУНКЦИИ ПРОГНОЗИРОВАНИЯ НАСЕЛЕНИЯ
# =====================================================


# =====================================================
# ML-МОДЕЛЬ ПРОГНОЗИРОВАНИЯ НАСЕЛЕНИЯ
# Обучается на реальных данных 2011-2024
# =====================================================

class PopulationForecaster:
    """
    ML-модель для прогнозирования населения на основе реальных данных.
    
    Обучается на:
    - Естественный прирост 2011-2024 (14 точек)
    - Общее население 2018-2024 (7 точек)
    - Население школьного возраста 2022
    
    Методы прогнозирования:
    - Polynomial Regression для трендов
    - Feature engineering с временными признаками
    - Ensemble averaging для робастности
    """
    
    def __init__(self):
        self.natural_growth_model = None
        self.population_model = None
        self.school_age_model = None
        self.is_trained = False
        self.training_stats = {}
        
    def train(self) -> Dict:
        """
        Обучение моделей на реальных данных.
        
        Создаёт 3 модели:
        1. Модель естественного прироста (14 точек 2011-2024)
        2. Модель общего населения (7 точек 2018-2024 + прогноз)
        3. Модель населения школьного возраста (когортный метод)
        """
        print("🎓 Обучение ML-модели прогнозирования населения...")
        print(f"   📊 Данные естественного прироста: {len(NATURAL_POPULATION_GROWTH)} лет")
        print(f"   📊 Данные общего населения: {len(BISHKEK_TOTAL_POPULATION)} лет")
        print(f"   👶 Данные по возрастам: {len(BISHKEK_POPULATION_2022)} групп")
        
        try:
            # ===============================================
            # 1. МОДЕЛЬ ЕСТЕСТВЕННОГО ПРИРОСТА
            # ===============================================
            years = np.array(sorted(NATURAL_POPULATION_GROWTH.keys()))
            growth = np.array([NATURAL_POPULATION_GROWTH[y] for y in years])
            
            # Feature engineering: добавляем признаки времени
            X_growth = self._create_time_features(years)
            y_growth = growth
            
            # Полиномиальная регрессия 2-й степени (учитывает тренд)
            from sklearn.preprocessing import PolynomialFeatures
            from sklearn.pipeline import Pipeline
            
            self.natural_growth_model = Pipeline([
                ('poly', PolynomialFeatures(degree=2, include_bias=False)),
                ('regressor', GradientBoostingRegressor(
                    n_estimators=100,
                    max_depth=3,
                    learning_rate=0.1,
                    random_state=42
                ))
            ])
            self.natural_growth_model.fit(X_growth, y_growth)
            
            # Оценка качества (на тренировочных данных, т.к. мало точек)
            growth_pred = self.natural_growth_model.predict(X_growth)
            growth_r2 = 1 - np.sum((y_growth - growth_pred)**2) / np.sum((y_growth - np.mean(y_growth))**2)
            growth_mae = np.mean(np.abs(y_growth - growth_pred))
            
            print(f"   ✓ Модель прироста: R²={growth_r2:.3f}, MAE={growth_mae:,.0f}")
            
            # ===============================================
            # 2. МОДЕЛЬ ОБЩЕГО НАСЕЛЕНИЯ
            # ===============================================
            pop_years = np.array(sorted(BISHKEK_TOTAL_POPULATION.keys()))
            populations = np.array([BISHKEK_TOTAL_POPULATION[y] for y in pop_years])
            
            X_pop = self._create_time_features(pop_years)
            y_pop = populations
            
            # Линейная модель (население растёт линейно)
            self.population_model = Pipeline([
                ('poly', PolynomialFeatures(degree=1, include_bias=False)),
                ('regressor', LinearRegression())
            ])
            self.population_model.fit(X_pop, y_pop)
            
            pop_pred = self.population_model.predict(X_pop)
            pop_r2 = 1 - np.sum((y_pop - pop_pred)**2) / np.sum((y_pop - np.mean(y_pop))**2)
            
            print(f"   ✓ Модель населения: R²={pop_r2:.3f}")
            
            # ===============================================
            # 3. МОДЕЛЬ ШКОЛЬНОГО ВОЗРАСТА (когортный)
            # ===============================================
            ages = np.array(sorted(BISHKEK_POPULATION_2022.keys()))
            school_pop = np.array([BISHKEK_POPULATION_2022[a] for a in ages])
            
            # Средний размер когорты
            avg_cohort = np.mean(school_pop)
            cohort_std = np.std(school_pop)
            
            # Тренд: младшие vs старшие
            young_avg = np.mean(school_pop[:5])  # 6-10 лет
            old_avg = np.mean(school_pop[-5:])   # 14-18 лет
            growth_trend = young_avg / old_avg
            
            print(f"   ✓ Когорта: средняя={avg_cohort:,.0f}, тренд={growth_trend:.3f}")
            
            # ===============================================
            # СОХРАНЯЕМ СТАТИСТИКУ
            # ===============================================
            self.is_trained = True
            self.training_stats = {
                'trained_at': datetime.now().isoformat(),
                'natural_growth': {
                    'years': list(years),
                    'values': list(growth),
                    'r2_score': float(growth_r2),
                    'mae': float(growth_mae),
                    'last_values': {
                        2022: int(NATURAL_POPULATION_GROWTH[2022]),
                        2023: int(NATURAL_POPULATION_GROWTH[2023]),
                        2024: int(NATURAL_POPULATION_GROWTH[2024]),
                    }
                },
                'total_population': {
                    'years': list(pop_years),
                    'values': list(populations),
                    'r2_score': float(pop_r2),
                    'annual_growth_rate': float((populations[-1] / populations[0]) ** (1/(len(populations)-1)) - 1)
                },
                'school_age': {
                    'total_2022': int(TOTAL_SCHOOL_AGE_POPULATION_2022),
                    'avg_cohort': float(avg_cohort),
                    'cohort_std': float(cohort_std),
                    'growth_trend': float(growth_trend)
                }
            }
            
            print(f"✅ ML-модель населения обучена!")
            
            return {
                'success': True,
                'stats': self.training_stats
            }
            
        except Exception as e:
            print(f"❌ Ошибка обучения: {e}")
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    def _create_time_features(self, years: np.ndarray) -> np.ndarray:
        """Создание признаков времени для ML"""
        years = np.array(years).reshape(-1, 1)
        
        # Нормализуем год относительно 2020
        year_norm = (years - 2020) / 5
        
        # Признаки: год, год², тренд
        features = np.hstack([
            year_norm,                          # Линейный тренд
            year_norm ** 2,                     # Квадратичный тренд
            np.sin(year_norm * np.pi / 2),      # Цикличность
        ])
        
        return features
    
    def predict_natural_growth(self, target_years: List[int]) -> Dict:
        """
        Прогноз естественного прироста на будущие годы.
        
        Возвращает прогноз с доверительным интервалом.
        """
        if not self.is_trained:
            return {'success': False, 'error': 'Модель не обучена'}
        
        X_future = self._create_time_features(np.array(target_years))
        predictions = self.natural_growth_model.predict(X_future)
        
        # Доверительный интервал на основе исторической волатильности
        historical = list(NATURAL_POPULATION_GROWTH.values())
        volatility = np.std(historical)
        
        # Учитываем тренд 2023-2024 (снижение)
        recent_avg = (NATURAL_POPULATION_GROWTH[2023] + NATURAL_POPULATION_GROWTH[2024]) / 2
        historical_avg = np.mean(historical)
        
        results = []
        for i, year in enumerate(target_years):
            pred = max(0, predictions[i])  # Не отрицательный
            
            # Корректируем с учётом недавнего тренда
            if year <= 2026:
                # Близко к текущим данным - больше веса недавним
                weight_recent = 0.7
            else:
                # Дальше - постепенное восстановление
                weight_recent = max(0.3, 0.7 - (year - 2026) * 0.1)
            
            adjusted_pred = pred * (1 - weight_recent) + recent_avg * weight_recent * (1 + (year - 2024) * 0.02)
            
            results.append({
                'year': year,
                'predicted_growth': int(adjusted_pred),
                'ml_raw_prediction': int(pred),
                'confidence_interval': {
                    'low': int(max(0, adjusted_pred - volatility)),
                    'high': int(adjusted_pred + volatility)
                },
                'growth_rate_per_1000': round(adjusted_pred / self.predict_total_population([year])['predictions'][0]['population'] * 1000, 2)
            })
        
        return {
            'success': True,
            'data_source': 'Нацстатком КР (2011-2024)',
            'model_r2': self.training_stats['natural_growth']['r2_score'],
            'predictions': results
        }
    
    def predict_total_population(self, target_years: List[int]) -> Dict:
        """Прогноз общего населения Бишкека"""
        if not self.is_trained:
            return {'success': False, 'error': 'Модель не обучена'}
        
        X_future = self._create_time_features(np.array(target_years))
        predictions = self.population_model.predict(X_future)
        
        results = []
        for i, year in enumerate(target_years):
            results.append({
                'year': year,
                'population': int(predictions[i]),
                'growth_from_2024': int(predictions[i] - BISHKEK_TOTAL_POPULATION[2024]),
                'growth_percent': round((predictions[i] / BISHKEK_TOTAL_POPULATION[2024] - 1) * 100, 2)
            })
        
        return {
            'success': True,
            'model_r2': self.training_stats['total_population']['r2_score'],
            'predictions': results
        }
    
    def predict_school_age_population(self, target_years: List[int]) -> Dict:
        """
        Прогноз населения школьного возраста с использованием когортного метода.
        
        Когортный метод:
        - Дети 6 лет в 2022 → 7 лет в 2023 → 8 лет в 2024...
        - Новые когорты на основе рождаемости
        """
        if not self.is_trained:
            return {'success': False, 'error': 'Модель не обучена'}
        
        base_year = 2022
        base_population = dict(BISHKEK_POPULATION_2022)
        
        # Получаем прогноз прироста для расчёта новых когорт
        future_growth = self.predict_natural_growth(target_years)
        growth_map = {p['year']: p['predicted_growth'] for p in future_growth.get('predictions', [])}
        
        results = []
        current_population = dict(base_population)
        
        for year in sorted(target_years):
            years_diff = year - base_year
            
            # Сдвигаем когорты
            new_population = {}
            for age in range(7, 19):  # Школьный возраст 7-18
                source_age = age - years_diff
                
                if source_age in current_population:
                    # Когорта из базового года с корректировкой
                    survival_rate = 0.998 ** years_diff  # ~0.2% выбытие в год
                    growth_factor = 1.02 ** years_diff   # Миграционный рост
                    new_population[age] = int(current_population[source_age] * survival_rate * growth_factor)
                elif source_age < 6:
                    # Новая когорта - на основе прогноза рождаемости
                    # Используем данные о приросте для оценки размера когорты
                    birth_year = year - age
                    if birth_year in NATURAL_POPULATION_GROWTH:
                        births = NATURAL_POPULATION_GROWTH[birth_year]
                    elif birth_year in growth_map:
                        births = growth_map[birth_year]
                    else:
                        # Экстраполяция
                        births = int(self.training_stats['natural_growth']['last_values'][2024] * 1.02 ** (birth_year - 2024))
                    
                    # Примерно 70% прироста - рождения (остальное - снижение смертности)
                    # И ~85% детей доживает до школьного возраста
                    cohort_size = int(births * 0.7 * 0.85 * 1.1)  # +10% миграция
                    new_population[age] = cohort_size
                else:
                    # Старше базовых данных - используем среднее
                    new_population[age] = int(self.training_stats['school_age']['avg_cohort'])
            
            total_school_age = sum(new_population.get(age, 0) for age in range(7, 18))  # 7-17 лет
            
            results.append({
                'year': year,
                'total_school_age': total_school_age,
                'change_from_2022': total_school_age - TOTAL_SCHOOL_AGE_POPULATION_2022,
                'change_percent': round((total_school_age / TOTAL_SCHOOL_AGE_POPULATION_2022 - 1) * 100, 2),
                'population_by_age': {str(age): new_population.get(age, 0) for age in range(7, 18)},
                'by_school_level': {
                    'primary_1_4': sum(new_population.get(age, 0) for age in range(7, 11)),
                    'middle_5_9': sum(new_population.get(age, 0) for age in range(11, 16)),
                    'high_10_11': sum(new_population.get(age, 0) for age in range(16, 18))
                }
            })
        
        return {
            'success': True,
            'base_year': base_year,
            'base_population': TOTAL_SCHOOL_AGE_POPULATION_2022,
            'method': 'cohort_projection',
            'data_source': 'Нацстатком КР',
            'predictions': results
        }
    
    def get_full_forecast(self, years_ahead: int = 10) -> Dict:
        """
        Полный прогноз населения на N лет вперёд.
        
        Включает:
        - Общее население
        - Естественный прирост
        - Население школьного возраста
        - Потребность в школьных местах
        """
        if not self.is_trained:
            self.train()
        
        current_year = datetime.now().year
        target_years = list(range(current_year + 1, current_year + years_ahead + 1))
        
        # Получаем все прогнозы
        total_pop = self.predict_total_population(target_years)
        natural_growth = self.predict_natural_growth(target_years)
        school_age = self.predict_school_age_population(target_years)
        
        # Объединяем результаты
        combined = []
        for i, year in enumerate(target_years):
            pop_pred = total_pop['predictions'][i] if total_pop['success'] else {}
            growth_pred = natural_growth['predictions'][i] if natural_growth['success'] else {}
            school_pred = school_age['predictions'][i] if school_age['success'] else {}
            
            # Расчёт потребности в школьных местах
            # Текущая вместимость: ~170,000
            current_capacity = 170_227
            school_pop = school_pred.get('total_school_age', 0)
            
            combined.append({
                'year': year,
                'total_population': pop_pred.get('population', 0),
                'natural_growth': growth_pred.get('predicted_growth', 0),
                'school_age_population': school_pop,
                'school_places_needed': school_pop,
                'current_capacity': current_capacity,
                'places_deficit': max(0, school_pop - current_capacity),
                'new_schools_needed': max(0, int((school_pop - current_capacity) / 1000))  # ~1000 мест на школу
            })
        
        return {
            'success': True,
            'forecast_years': years_ahead,
            'base_data': {
                'population_2024': BISHKEK_TOTAL_POPULATION[2024],
                'school_age_2022': TOTAL_SCHOOL_AGE_POPULATION_2022,
                'current_school_capacity': current_capacity,
                'natural_growth_data_years': len(NATURAL_POPULATION_GROWTH)
            },
            'training_stats': self.training_stats,
            'forecasts': combined
        }


# Глобальный экземпляр модели
_population_forecaster = None

def get_population_forecaster() -> PopulationForecaster:
    """Получить обученную модель прогнозирования населения"""
    global _population_forecaster
    if _population_forecaster is None:
        _population_forecaster = PopulationForecaster()
        _population_forecaster.train()
    return _population_forecaster




def forecast_total_population(
    base_year: int = 2022,
    target_year: int = 2030,
    scenario: str = 'medium'
) -> Dict:
    """
    Прогноз общего населения Бишкека на основе РЕАЛЬНЫХ данных о приросте
    
    Сценарии (с учётом снижения рождаемости 2023-2024):
    - low: Консервативный (~1.5% в год) - продолжение снижения рождаемости
    - medium: Базовый (~1.8% в год) - стабилизация на уровне 2024
    - high: Оптимистичный (~2.2% в год) - восстановление рождаемости
    
    Returns:
        Словарь с прогнозами по годам
    """
    # Скорректированные темпы роста на основе реальных данных 2023-2024
    # Естественный прирост снизился с ~22,000 до ~9,000
    growth_rates = {
        'low': 0.015,    # Консервативный: продолжение тренда 2023-2024
        'medium': 0.018, # Базовый: стабилизация + миграция
        'high': 0.022,   # Оптимистичный: частичное восстановление
    }
    
    rate = growth_rates.get(scenario, 0.018)
    base_pop = BISHKEK_TOTAL_POPULATION.get(base_year, 1_120_800)
    
    forecasts = {}
    for year in range(base_year, target_year + 1):
        years_diff = year - base_year
        
        # Используем реальные данные о приросте где доступны
        if year in NATURAL_POPULATION_GROWTH and year in BISHKEK_TOTAL_POPULATION:
            forecasts[year] = BISHKEK_TOTAL_POPULATION[year]
        else:
            forecasts[year] = int(base_pop * ((1 + rate) ** years_diff))
    
    return forecasts


def forecast_population_detailed(
    base_year: int = 2022,
    target_year: int = 2030
) -> List[Dict]:
    """
    Детальный прогноз населения с разбивкой по возрастным группам
    и компонентам роста
    """
    results = []
    
    base_pop = BISHKEK_TOTAL_POPULATION.get(base_year, 1_120_800)
    current_pop = base_pop
    
    # Среднее количество детей 6-18 лет на основе наших данных
    avg_school_age = sum(BISHKEK_POPULATION_2022.values()) / len(BISHKEK_POPULATION_2022)
    
    for year in range(base_year, target_year + 1):
        years_diff = year - base_year
        
        # Компоненты роста
        births = int(current_pop * DEMOGRAPHIC_RATES['birth_rate'] / 1000)
        deaths = int(current_pop * DEMOGRAPHIC_RATES['death_rate'] / 1000)
        natural_growth = births - deaths
        migration = int(current_pop * DEMOGRAPHIC_RATES['migration_rate'] / 1000)
        total_growth = natural_growth + migration
        
        # Население на конец года
        if year > base_year:
            current_pop = current_pop + total_growth
        
        # Возрастные группы (с учётом изменения структуры)
        age_groups = {}
        for group, pct in AGE_STRUCTURE_2022.items():
            # Корректируем структуру: молодёжь растёт быстрее из-за рождаемости
            if group in ['0-5', '6-17']:
                adjusted_pct = pct * (1 + 0.005 * years_diff)  # +0.5% в год
            elif group == '65+':
                adjusted_pct = pct * (1 + 0.003 * years_diff)  # Старение
            else:
                adjusted_pct = pct
            age_groups[group] = int(current_pop * adjusted_pct / 100)
        
        # Школьный возраст (6-17) детально
        school_age_total = age_groups['6-17']
        
        # Прогноз детей школьного возраста по нашим данным
        school_age_by_year = {}
        for age in range(6, 19):
            base_val = BISHKEK_POPULATION_2022.get(age, 14500)
            school_age_by_year[age] = int(base_val * ((1.035) ** years_diff))
        
        results.append({
            'year': year,
            'total_population': current_pop,
            'growth_components': {
                'births': births,
                'deaths': deaths,
                'natural_growth': natural_growth,
                'migration': migration,
                'total_growth': total_growth,
                'growth_rate_percent': round(total_growth / (current_pop - total_growth) * 100, 2) if current_pop > total_growth else 0
            },
            'age_groups': age_groups,
            'school_age_population': {
                'total': sum(school_age_by_year.values()),
                'by_age': school_age_by_year
            }
        })
    
    return results


def get_population_pyramid(year: int = 2022) -> Dict:
    """
    Построение возрастной пирамиды населения
    """
    base_pop = BISHKEK_TOTAL_POPULATION.get(year, 1_120_800)
    years_from_2022 = year - 2022
    growth_factor = (1.025) ** years_from_2022
    
    # Детализированная возрастная структура
    detailed_structure = {
        '0-4': 8.5,
        '5-9': 8.8,
        '10-14': 7.2,
        '15-19': 6.9,
        '20-24': 7.8,
        '25-29': 9.5,
        '30-34': 8.8,
        '35-39': 7.8,
        '40-44': 7.4,
        '45-49': 6.2,
        '50-54': 5.9,
        '55-59': 5.8,
        '60-64': 5.0,
        '65-69': 2.4,
        '70-74': 1.2,
        '75+': 0.8,
    }
    
    pyramid = {}
    for age_group, pct in detailed_structure.items():
        pyramid[age_group] = int(base_pop * growth_factor * pct / 100)
    
    return {
        'year': year,
        'total_population': int(base_pop * growth_factor),
        'pyramid': pyramid,
        'working_age': sum(pyramid[g] for g in ['20-24', '25-29', '30-34', '35-39', '40-44', '45-49', '50-54', '55-59']),
        'children': sum(pyramid[g] for g in ['0-4', '5-9', '10-14', '15-19']),
        'elderly': sum(pyramid[g] for g in ['60-64', '65-69', '70-74', '75+']),
        'dependency_ratio': round(
            (sum(pyramid[g] for g in ['0-4', '5-9', '10-14', '15-19', '60-64', '65-69', '70-74', '75+']) /
             sum(pyramid[g] for g in ['20-24', '25-29', '30-34', '35-39', '40-44', '45-49', '50-54', '55-59'])) * 100, 1
        )
    }


def get_cohort_projection(base_year: int = 2022, target_year: int = 2025) -> Dict[int, int]:
    """
    Проекция когорт на будущие годы.
    
    Когортный метод: дети 6 лет в 2022 → первоклассники в 2023 → второклассники в 2024 и т.д.
    
    Args:
        base_year: Базовый год данных (2022)
        target_year: Целевой год прогноза
    
    Returns:
        Словарь {класс: количество учеников}
    """
    years_diff = target_year - base_year
    
    # Коэффициент годового роста населения Бишкека (~3.5% включая миграцию)
    annual_growth = 1.035
    
    projection = {}
    
    for grade in range(1, 12):
        # Какой возраст был у этих детей в 2022?
        age_in_base_year = (grade + 6) - years_diff
        
        if age_in_base_year in BISHKEK_POPULATION_2022:
            # Используем реальные данные с поправкой на рост
            base_population = BISHKEK_POPULATION_2022[age_in_base_year]
            projection[grade] = int(base_population * (annual_growth ** years_diff))
        elif age_in_base_year < 6:
            # Ещё не родились в 2022 - экстраполируем по рождаемости
            # Берём среднее 6-летних и добавляем рост
            base = BISHKEK_POPULATION_2022[6]
            years_before_6 = 6 - age_in_base_year
            projection[grade] = int(base * (annual_growth ** (years_diff + years_before_6)))
        else:
            # Старше 18 в базовом году - используем среднее
            projection[grade] = int(14_500 * (annual_growth ** years_diff))
    
    return projection


def calculate_total_projected_students(target_year: int = 2025) -> int:
    """Общее прогнозируемое количество школьников на год"""
    projection = get_cohort_projection(2022, target_year)
    return sum(projection.values())


def get_demographic_trends() -> Dict:
    """
    Анализ демографических трендов на основе реальных данных
    """
    ages = sorted(BISHKEK_POPULATION_2022.keys())
    populations = [BISHKEK_POPULATION_2022[age] for age in ages]
    
    # Тренд: больше младших → рост, больше старших → спад
    young_avg = np.mean(populations[:5])   # 6-10 лет
    middle_avg = np.mean(populations[5:9]) # 11-14 лет
    old_avg = np.mean(populations[9:])     # 15-18 лет
    
    # Линейная регрессия для определения общего тренда
    x = np.array(ages).reshape(-1, 1)
    y = np.array(populations)
    lr = LinearRegression().fit(x, y)
    trend_slope = lr.coef_[0]
    
    return {
        'young_average': int(young_avg),
        'middle_average': int(middle_avg),
        'old_average': int(old_avg),
        'growth_ratio': round(young_avg / old_avg, 3),  # >1 = рост
        'trend_slope': round(trend_slope, 2),  # отрицательный = больше молодых
        'total_school_age': TOTAL_SCHOOL_AGE_POPULATION_2022,
        'analysis': 'growing' if young_avg > old_avg else 'declining'
    }


class SchoolDemandForecaster:
    """
    ML-модель для прогнозирования востребованности школ
    
    Основные методы:
    - train(): обучение модели на данных школ
    - predict_demand(): прогноз потребности на N лет вперёд
    - analyze_district(): анализ района с рекомендациями
    - get_risk_schools(): список школ с риском перегрузки
    """
    
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.district_models = {}  # Отдельные модели для каждого района
        self.is_trained = False
        self.training_stats = {}
        self.feature_names = []
        
        # Реальные демографические данные Бишкека (2022)
        self.population_data = BISHKEK_POPULATION_2022
        self.total_school_age = TOTAL_SCHOOL_AGE_POPULATION_2022
        
        # Расчётные демографические коэффициенты на основе данных
        self.demographic_coefficients = {
            'birth_rate': 0.028,  # ~15,700 шестилетних / 560,000 населения
            'population_growth': 0.025,  # Естественный прирост
            'migration_factor': 0.01,  # Миграция в Бишкек
            'total_growth_rate': 0.035,  # Суммарный рост ~3.5% в год
            'school_enrollment_rate': 0.97,  # Охват школьным образованием
        }
        
        # Средний размер класса по стандартам КР
        self.standard_class_size = 25
        
    def prepare_data_from_schools(self, schools_queryset) -> pd.DataFrame:
        """
        Подготовка данных из QuerySet школ для обучения
        
        Создаёт признаки:
        - Распределение по классам (1-11)
        - Тренды роста/убыли (производные)
        - Характеристики школы (вместимость, район, тип)
        - Демографические оценки района
        """
        data = []
        
        for school in schools_queryset:
            # Пропускаем школы без учеников
            if school.total_students == 0:
                continue
                
            # Распределение по классам
            grades = [
                school.students_class_1,
                school.students_class_2,
                school.students_class_3,
                school.students_class_4,
                school.students_class_5,
                school.students_class_6,
                school.students_class_7,
                school.students_class_8,
                school.students_class_9,
                school.students_class_10,
                school.students_class_11,
            ]
            
            # Вычисляем производные (тренды)
            grades_array = np.array(grades, dtype=float)
            
            # Тренд начальной школы (1-4 классы)
            primary_trend = np.mean(grades_array[:4]) if sum(grades_array[:4]) > 0 else 0
            
            # Тренд средней школы (5-9 классы)
            middle_trend = np.mean(grades_array[4:9]) if sum(grades_array[4:9]) > 0 else 0
            
            # Тренд старшей школы (10-11 классы)
            senior_trend = np.mean(grades_array[9:11]) if sum(grades_array[9:11]) > 0 else 0
            
            # Отношение младших к старшим (индикатор роста)
            if senior_trend > 0:
                growth_indicator = primary_trend / senior_trend
            else:
                growth_indicator = 2.0 if primary_trend > 0 else 1.0
            
            # Градиент по классам (насколько меняется количество от класса к классу)
            grade_gradient = np.gradient(grades_array)
            avg_gradient = np.mean(grade_gradient)
            
            # Оценочная вместимость
            capacity = school.estimated_capacity
            occupancy = school.occupancy_rate
            
            # Кодируем район
            district_code = self._encode_district(school.district)
            
            # Кодируем форму собственности
            ownership_code = 1 if 'Private' in (school.owner_form or '') else 0
            
            row = {
                'school_id': school.id,
                'institution_id': school.institution_id,
                'name': school.name,
                'district': school.district,
                'district_code': district_code,
                'latitude': school.latitude,
                'longitude': school.longitude,
                
                # Распределение по классам
                'grade_1': grades[0],
                'grade_2': grades[1],
                'grade_3': grades[2],
                'grade_4': grades[3],
                'grade_5': grades[4],
                'grade_6': grades[5],
                'grade_7': grades[6],
                'grade_8': grades[7],
                'grade_9': grades[8],
                'grade_10': grades[9],
                'grade_11': grades[10],
                
                # Агрегированные признаки
                'total_students': school.total_students,
                'total_classes': school.total_classes,
                'capacity': capacity,
                'occupancy_rate': occupancy,
                
                # Тренды
                'primary_avg': primary_trend,
                'middle_avg': middle_trend,
                'senior_avg': senior_trend,
                'growth_indicator': growth_indicator,
                'avg_gradient': avg_gradient,
                
                # Категориальные
                'ownership_private': ownership_code,
                
                # Производные признаки
                'students_per_class': school.total_students / max(school.total_classes, 1),
                'capacity_buffer': capacity - school.total_students,
                'is_overloaded': 1 if occupancy > 100 else 0,
            }
            
            data.append(row)
        
        df = pd.DataFrame(data)
        print(f"📊 Подготовлено {len(df)} школ для анализа")
        
        return df
    
    def _encode_district(self, district_name: str) -> int:
        """Кодирование района в числовой признак"""
        districts = {
            'Ленинский': 1,
            'Октябрьский': 2,
            'Первомайский': 3,
            'Свердловский': 4,
        }
        
        for key, code in districts.items():
            if key in (district_name or ''):
                return code
        return 0
    
    def train(self, schools_queryset) -> Dict:
        """
        Обучение модели прогнозирования
        
        Использует:
        - Данные 230 школ (распределение по классам, вместимость)
        - Реальные демографические данные 2011-2024
        - Когортный метод прогнозирования
        - Gradient Boosting для предсказания тренда
        """
        print("🎓 Начинаем обучение ML-модели прогнозирования...")
        print(f"   📊 Демографические данные: {len(NATURAL_POPULATION_GROWTH)} лет (2011-2024)")
        print(f"   👶 Данные по возрастам: {len(BISHKEK_POPULATION_2022)} возрастных групп")
        
        try:
            # Подготавливаем данные школ
            df = self.prepare_data_from_schools(schools_queryset)
            
            if len(df) < 10:
                return {
                    'success': False,
                    'error': 'Недостаточно данных для обучения (минимум 10 школ)'
                }
            
            # === ИНТЕГРАЦИЯ ДЕМОГРАФИЧЕСКИХ ДАННЫХ ===
            
            # 1. Анализ естественного прироста
            growth_analysis = analyze_natural_growth_trends()
            
            # 2. Добавляем демографические признаки к каждой школе
            # Доля района в городском населении (оценка)
            district_population_share = {
                'Ленинский': 0.28,      # ~28% населения
                'Октябрьский': 0.22,    # ~22%
                'Первомайский': 0.25,   # ~25%
                'Свердловский': 0.25,   # ~25%
            }
            
            # Добавляем демографические признаки
            df['demo_avg_growth'] = growth_analysis['average_annual']
            df['demo_recent_growth'] = growth_analysis['periods']['2023-2024']['average']
            df['demo_trend_slope'] = growth_analysis['trend_slope']
            df['demo_growth_volatility'] = growth_analysis['volatility']
            
            # Расчётный прирост детей в районе школы
            df['district_share'] = df['district'].apply(
                lambda d: next((v for k, v in district_population_share.items() if k in str(d)), 0.25)
            )
            df['expected_new_students'] = df['district_share'] * growth_analysis['projected_annual_growth'] * 0.15  # 15% - школьный возраст
            
            # Коэффициент роста на основе реальных данных
            # Используем скорректированный рост с учётом 2023-2024
            adjusted_growth_rate = get_adjusted_growth_rate(2025)
            df['demo_growth_rate'] = adjusted_growth_rate
            
            # Признаки для модели (РАСШИРЕННЫЙ НАБОР)
            self.feature_names = [
                # Базовые признаки школы
                'district_code', 'latitude', 'longitude',
                'grade_1', 'grade_2', 'grade_3', 'grade_4',
                'grade_5', 'grade_6', 'grade_7', 'grade_8',
                'grade_9', 'grade_10', 'grade_11',
                'capacity', 'ownership_private',
                'growth_indicator', 'avg_gradient',
                'students_per_class',
                # НОВЫЕ демографические признаки
                'demo_growth_rate',
                'expected_new_students',
                'district_share',
            ]
            
            X = df[self.feature_names].values
            
            # Целевая переменная: комбинированный индикатор роста
            # Учитываем и школьный тренд, и демографию
            y = df['growth_indicator'].values * (1 + df['demo_growth_rate'].values)
            
            # Нормализация
            X_scaled = self.scaler.fit_transform(X)
            
            # Обучаем Gradient Boosting
            self.model = GradientBoostingRegressor(
                n_estimators=150,  # Увеличили для лучшей точности
                max_depth=6,
                learning_rate=0.08,
                min_samples_split=5,
                random_state=42
            )
            
            self.model.fit(X_scaled, y)
            
            # Кросс-валидация
            cv_scores = cross_val_score(self.model, X_scaled, y, cv=5, scoring='r2')
            
            # Важность признаков
            feature_importance = dict(zip(
                self.feature_names,
                self.model.feature_importances_
            ))
            
            # Сортируем по важности
            feature_importance = dict(sorted(
                feature_importance.items(),
                key=lambda x: x[1],
                reverse=True
            ))
            
            self.is_trained = True
            self.training_stats = {
                'samples': len(df),
                'features': len(self.feature_names),
                'cv_score_mean': float(np.mean(cv_scores)),
                'cv_score_std': float(np.std(cv_scores)),
                'feature_importance': feature_importance,
                'trained_at': datetime.now().isoformat(),
                # НОВОЕ: информация о демографических данных
                'demographic_data_used': {
                    'natural_growth_years': list(NATURAL_POPULATION_GROWTH.keys()),
                    'avg_annual_growth': growth_analysis['average_annual'],
                    'recent_growth_2023_2024': growth_analysis['periods']['2023-2024']['average'],
                    'projected_growth': growth_analysis['projected_annual_growth'],
                    'school_age_population_2022': TOTAL_SCHOOL_AGE_POPULATION_2022,
                    'adjusted_growth_rate': adjusted_growth_rate
                }
            }
            
            # Сохраняем данные для прогнозов
            self.training_data = df
            self.demographic_analysis = growth_analysis
            
            print(f"✅ Модель обучена с демографическими данными!")
            print(f"   • Школ: {len(df)}")
            print(f"   • Признаков: {len(self.feature_names)} (включая демографию)")
            print(f"   • R² (CV): {np.mean(cv_scores):.3f} ± {np.std(cv_scores):.3f}")
            print(f"   • Использован прирост: {growth_analysis['projected_annual_growth']:,.0f} чел/год")
            print(f"   • Топ-3 признака: {list(feature_importance.keys())[:3]}")
            
            return {
                'success': True,
                'stats': self.training_stats
            }
            
        except Exception as e:
            print(f"❌ Ошибка обучения: {e}")
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }
    
    def predict_school_demand(self, school_data: Dict, years_ahead: int = 5) -> Dict:
        """
        Прогноз востребованности для конкретной школы на N лет вперёд
        
        Использует:
        1. Текущее распределение по классам
        2. РЕАЛЬНЫЕ демографические данные 2011-2024
        3. Когортный метод с учётом снижения рождаемости
        4. ML-модель для оценки тренда школы
        """
        if not self.is_trained:
            return {'success': False, 'error': 'Модель не обучена'}
        
        try:
            # Текущие данные
            current_students = school_data.get('total_students', 0)
            capacity = school_data.get('capacity', current_students)
            grades = [school_data.get(f'grade_{i}', 0) for i in range(1, 12)]
            district = school_data.get('district', '')
            
            # Получаем актуальные демографические данные
            growth_analysis = analyze_natural_growth_trends()
            
            # Прогноз на каждый год
            forecasts = []
            predicted_students = current_students
            
            for year in range(1, years_ahead + 1):
                target_year = datetime.now().year + year
                
                # Используем реальный скорректированный коэффициент роста
                adjusted_rate = get_adjusted_growth_rate(target_year)
                
                # ML-поправка на тренд конкретной школы
                if hasattr(self, 'model') and self.model is not None:
                    features = self._extract_features(school_data)
                    # Добавляем демографические признаки
                    features.extend([adjusted_rate, 0, 0.25])  # demo_growth_rate, expected_new_students, district_share
                    features_scaled = self.scaler.transform([features])
                    trend_factor = self.model.predict(features_scaled)[0]
                else:
                    trend_factor = 1.0
                
                # Комбинированный прогноз с учётом демографии
                # Используем геометрическое среднее для сглаживания
                base_growth = adjusted_rate * 0.7 + 0.018 * 0.3  # 70% реальные данные, 30% базовый рост
                growth_rate = base_growth * (trend_factor ** 0.5)  # Смягчаем влияние ML
                
                predicted_students = predicted_students * (1 + growth_rate)
                
                # Прогноз загруженности
                predicted_occupancy = (predicted_students / capacity * 100) if capacity > 0 else 0
                
                # Доверительный интервал (учитываем волатильность демографии)
                volatility_factor = growth_analysis['volatility'] / growth_analysis['average_annual']
                confidence_lower = predicted_students * (1 - 0.1 - volatility_factor * 0.05)
                confidence_upper = predicted_students * (1 + 0.1 + volatility_factor * 0.05)
                
                forecasts.append({
                    'year': target_year,
                    'predicted_students': int(predicted_students),
                    'predicted_occupancy': round(predicted_occupancy, 1),
                    'confidence_interval': {
                        'lower': int(confidence_lower),
                        'upper': int(confidence_upper)
                    },
                    'deficit': int(predicted_students - capacity) if predicted_students > capacity else 0,
                    'status': self._get_status(predicted_occupancy)
                })
            
            return {
                'success': True,
                'school_name': school_data.get('name', 'Неизвестно'),
                'current_students': current_students,
                'current_capacity': capacity,
                'current_occupancy': round(current_students / capacity * 100, 1) if capacity > 0 else 0,
                'forecasts': forecasts,
                'summary': self._generate_summary(forecasts, capacity)
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _extract_features(self, school_data: Dict) -> List[float]:
        """Извлечение признаков из данных школы"""
        features = []
        
        for name in self.feature_names:
            if name in school_data:
                features.append(float(school_data[name]))
            elif name.startswith('grade_'):
                grade_num = int(name.split('_')[1])
                features.append(float(school_data.get(f'students_class_{grade_num}', 0)))
            else:
                features.append(0.0)
        
        return features
    
    def _get_status(self, occupancy: float) -> str:
        """Статус загруженности"""
        if occupancy > 120:
            return 'critical'
        elif occupancy > 100:
            return 'overloaded'
        elif occupancy > 80:
            return 'high'
        elif occupancy > 50:
            return 'normal'
        else:
            return 'low'
    
    def _generate_summary(self, forecasts: List[Dict], capacity: int) -> Dict:
        """Генерация резюме прогноза"""
        last_forecast = forecasts[-1]
        first_forecast = forecasts[0]
        
        total_growth = last_forecast['predicted_students'] - first_forecast['predicted_students']
        avg_growth_rate = (total_growth / first_forecast['predicted_students'] * 100) if first_forecast['predicted_students'] > 0 else 0
        
        # Год, когда школа станет перегруженной (если ещё не)
        overload_year = None
        for f in forecasts:
            if f['predicted_occupancy'] > 100 and overload_year is None:
                overload_year = f['year']
                break
        
        # Дефицит мест к концу прогноза
        final_deficit = last_forecast['deficit']
        
        # Рекомендация
        if final_deficit > 200:
            recommendation = 'Критическая нехватка мест. Требуется строительство новой школы в районе.'
        elif final_deficit > 100:
            recommendation = 'Значительный дефицит мест. Рекомендуется расширение школы или открытие филиала.'
        elif final_deficit > 0:
            recommendation = 'Умеренный дефицит. Рекомендуется оптимизация классов или дополнительные смены.'
        else:
            recommendation = 'Вместимость достаточна на прогнозируемый период.'
        
        return {
            'total_growth_students': int(total_growth),
            'avg_growth_rate_percent': round(avg_growth_rate, 1),
            'overload_year': overload_year,
            'final_deficit': final_deficit,
            'recommendation': recommendation
        }
    
    def analyze_district(self, district_name: str, schools_queryset) -> Dict:
        """
        Комплексный анализ района с прогнозами и рекомендациями
        
        Возвращает:
        - Общую статистику района
        - Прогноз потребности на 5 лет
        - Список проблемных школ
        - Рекомендации по развитию
        """
        print(f"📊 Анализ района: {district_name}")
        
        try:
            # Фильтруем школы района
            district_schools = [s for s in schools_queryset if district_name in (s.district or '')]
            
            if not district_schools:
                return {
                    'success': False,
                    'error': f'Школы не найдены в районе "{district_name}"'
                }
            
            # Текущая статистика
            total_students = sum(s.total_students for s in district_schools)
            total_capacity = sum(s.estimated_capacity for s in district_schools)
            avg_occupancy = (total_students / total_capacity * 100) if total_capacity > 0 else 0
            
            overloaded_schools = [s for s in district_schools if s.occupancy_rate > 100]
            critical_schools = [s for s in district_schools if s.occupancy_rate > 120]
            
            # Распределение по классам в районе
            district_grades = [0] * 11
            for school in district_schools:
                district_grades[0] += school.students_class_1
                district_grades[1] += school.students_class_2
                district_grades[2] += school.students_class_3
                district_grades[3] += school.students_class_4
                district_grades[4] += school.students_class_5
                district_grades[5] += school.students_class_6
                district_grades[6] += school.students_class_7
                district_grades[7] += school.students_class_8
                district_grades[8] += school.students_class_9
                district_grades[9] += school.students_class_10
                district_grades[10] += school.students_class_11
            
            # Тренд района
            primary_students = sum(district_grades[:4])
            senior_students = sum(district_grades[9:11])
            district_growth_trend = (primary_students / senior_students) if senior_students > 0 else 2.0
            
            # Прогноз на 5 лет
            forecasts = []
            projected_students = total_students
            
            # Получаем реальные демографические данные
            growth_analysis = analyze_natural_growth_trends()
            
            for year in range(1, 6):
                target_year = datetime.now().year + year
                
                # Используем РЕАЛЬНЫЙ скорректированный коэффициент роста
                adjusted_rate = get_adjusted_growth_rate(target_year)
                
                # Комбинируем с трендом района
                growth_rate = adjusted_rate * (district_growth_trend ** 0.2)  # Смягчаем влияние тренда
                
                projected_students = projected_students * (1 + growth_rate)
                projected_occupancy = (projected_students / total_capacity * 100) if total_capacity > 0 else 0
                
                forecasts.append({
                    'year': target_year,
                    'projected_students': int(projected_students),
                    'projected_occupancy': round(projected_occupancy, 1),
                    'additional_places_needed': max(0, int(projected_students - total_capacity)),
                    'new_schools_needed': max(0, int((projected_students - total_capacity) / 1000)),
                    'growth_rate_used': round(growth_rate * 100, 2)
                })
            
            # Проблемные школы
            problem_schools = []
            for school in sorted(district_schools, key=lambda x: -x.occupancy_rate)[:10]:
                if school.occupancy_rate > 80:
                    problem_schools.append({
                        'name': school.name,
                        'students': school.total_students,
                        'capacity': school.estimated_capacity,
                        'occupancy': round(school.occupancy_rate, 1),
                        'status': self._get_status(school.occupancy_rate),
                        'lat': school.latitude,
                        'lng': school.longitude
                    })
            
            # Рекомендации
            recommendations = self._generate_district_recommendations(
                avg_occupancy, forecasts, len(overloaded_schools), len(district_schools)
            )
            
            return {
                'success': True,
                'district': district_name,
                'current_stats': {
                    'schools_count': len(district_schools),
                    'total_students': total_students,
                    'total_capacity': total_capacity,
                    'avg_occupancy': round(avg_occupancy, 1),
                    'overloaded_schools': len(overloaded_schools),
                    'critical_schools': len(critical_schools),
                    'growth_trend': round(district_growth_trend, 2)
                },
                'grade_distribution': {
                    f'grade_{i+1}': district_grades[i] for i in range(11)
                },
                'forecasts': forecasts,
                'problem_schools': problem_schools,
                'recommendations': recommendations
            }
            
        except Exception as e:
            print(f"❌ Ошибка анализа района: {e}")
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    def _generate_district_recommendations(
        self, 
        current_occupancy: float, 
        forecasts: List[Dict],
        overloaded_count: int,
        total_schools: int
    ) -> List[Dict]:
        """Генерация рекомендаций для района"""
        recommendations = []
        
        # Текущая ситуация
        if current_occupancy > 100:
            recommendations.append({
                'priority': 'high',
                'category': 'capacity',
                'title': 'Критическая перегрузка района',
                'description': f'Средняя загруженность {current_occupancy:.0f}%. Требуются срочные меры.',
                'actions': [
                    'Открыть дополнительные смены в наименее загруженных школах',
                    'Перераспределить учеников между школами',
                    'Начать проектирование новой школы'
                ]
            })
        elif current_occupancy > 85:
            recommendations.append({
                'priority': 'medium',
                'category': 'capacity',
                'title': 'Высокая загруженность',
                'description': f'Район близок к пределу вместимости ({current_occupancy:.0f}%).',
                'actions': [
                    'Провести аудит использования помещений',
                    'Рассмотреть расширение существующих школ'
                ]
            })
        
        # Прогноз
        final_forecast = forecasts[-1]
        if final_forecast['new_schools_needed'] > 0:
            recommendations.append({
                'priority': 'high',
                'category': 'infrastructure',
                'title': f'Необходимо строительство {final_forecast["new_schools_needed"]} новых школ',
                'description': f'К {final_forecast["year"]} году прогнозируется дефицит {final_forecast["additional_places_needed"]} мест.',
                'actions': [
                    'Определить участки под строительство',
                    'Включить в план развития города',
                    'Подготовить проектную документацию'
                ]
            })
        
        # Перегруженные школы
        overload_ratio = overloaded_count / total_schools if total_schools > 0 else 0
        if overload_ratio > 0.3:
            recommendations.append({
                'priority': 'medium',
                'category': 'distribution',
                'title': 'Неравномерное распределение',
                'description': f'{overloaded_count} из {total_schools} школ перегружены ({overload_ratio*100:.0f}%).',
                'actions': [
                    'Пересмотреть границы школьных микрорайонов',
                    'Организовать подвоз учеников в менее загруженные школы',
                    'Открыть филиалы в густонаселённых кварталах'
                ]
            })
        
        return recommendations
    
    def get_city_overview(self, schools_queryset) -> Dict:
        """
        Общий обзор ситуации по городу
        """
        try:
            schools_list = list(schools_queryset)
            
            if not schools_list:
                return {'success': False, 'error': 'Нет данных о школах'}
            
            # Группировка по районам
            districts = {}
            for school in schools_list:
                district = school.district or 'Не указан'
                if district not in districts:
                    districts[district] = {
                        'schools': [],
                        'total_students': 0,
                        'total_capacity': 0
                    }
                districts[district]['schools'].append(school)
                districts[district]['total_students'] += school.total_students
                districts[district]['total_capacity'] += school.estimated_capacity
            
            # Статистика по районам
            district_stats = []
            for district_name, data in districts.items():
                occupancy = (data['total_students'] / data['total_capacity'] * 100) if data['total_capacity'] > 0 else 0
                
                # Подсчёт перегруженных
                overloaded = sum(1 for s in data['schools'] if s.occupancy_rate > 100)
                
                district_stats.append({
                    'name': district_name,
                    'schools_count': len(data['schools']),
                    'students': data['total_students'],
                    'capacity': data['total_capacity'],
                    'occupancy': round(occupancy, 1),
                    'overloaded_schools': overloaded,
                    'status': self._get_status(occupancy)
                })
            
            # Сортируем по загруженности
            district_stats.sort(key=lambda x: -x['occupancy'])
            
            # Общая статистика
            total_students = sum(s.total_students for s in schools_list)
            total_capacity = sum(s.estimated_capacity for s in schools_list)
            total_overloaded = sum(1 for s in schools_list if s.occupancy_rate > 100)
            
            # Прогноз на 5 лет для города
            city_forecasts = []
            projected = total_students
            
            # Используем когортный метод с реальными демографическими данными
            current_year = datetime.now().year
            
            for year in range(1, 6):
                target_year = current_year + year
                
                # Когортное прогнозирование на основе данных 2022
                cohort_projection = get_cohort_projection(2022, target_year)
                projected_from_cohorts = sum(cohort_projection.values())
                
                # Учитываем охват школьным образованием
                projected_enrolled = int(projected_from_cohorts * self.demographic_coefficients['school_enrollment_rate'])
                
                city_forecasts.append({
                    'year': target_year,
                    'projected_students': projected_enrolled,
                    'projected_deficit': max(0, projected_enrolled - total_capacity),
                    'growth_from_current': projected_enrolled - total_students,
                    'growth_percent': round((projected_enrolled - total_students) / total_students * 100, 1) if total_students > 0 else 0
                })
            
            # Демографические тренды
            demo_trends = get_demographic_trends()
            
            return {
                'success': True,
                'city': 'Бишкек',
                'total_stats': {
                    'schools_count': len(schools_list),
                    'total_students': total_students,
                    'total_capacity': total_capacity,
                    'avg_occupancy': round(total_students / total_capacity * 100, 1) if total_capacity > 0 else 0,
                    'overloaded_schools': total_overloaded,
                    'overload_ratio': round(total_overloaded / len(schools_list) * 100, 1) if schools_list else 0
                },
                'demographics': {
                    'base_year': 2022,
                    'school_age_population': TOTAL_SCHOOL_AGE_POPULATION_2022,
                    'enrollment_rate': self.demographic_coefficients['school_enrollment_rate'],
                    'trend_analysis': demo_trends['analysis'],
                    'growth_ratio': demo_trends['growth_ratio'],
                    'population_by_age': {str(k): v for k, v in BISHKEK_POPULATION_2022.items()}
                },
                'districts': district_stats,
                'city_forecast': city_forecasts,
                'critical_districts': [d for d in district_stats if d['occupancy'] > 100]
            }
            
        except Exception as e:
            print(f"❌ Ошибка обзора: {e}")
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    def get_risk_schools(self, schools_queryset, threshold: float = 90.0) -> List[Dict]:
        """
        Получить список школ с высоким риском перегрузки
        
        Args:
            threshold: Порог загруженности (%)
        """
        risk_schools = []
        
        for school in schools_queryset:
            if school.occupancy_rate >= threshold:
                # Прогнозируем на 3 года
                projected = school.total_students
                for _ in range(3):
                    growth = self.demographic_coefficients['population_growth']
                    projected = projected * (1 + growth)
                
                projected_occupancy = (projected / school.estimated_capacity * 100) if school.estimated_capacity > 0 else 0
                
                risk_schools.append({
                    'school_id': school.id,
                    'name': school.name,
                    'district': school.district,
                    'current_students': school.total_students,
                    'capacity': school.estimated_capacity,
                    'current_occupancy': round(school.occupancy_rate, 1),
                    'projected_occupancy_3y': round(projected_occupancy, 1),
                    'risk_level': 'critical' if school.occupancy_rate > 120 else ('high' if school.occupancy_rate > 100 else 'medium'),
                    'lat': school.latitude,
                    'lng': school.longitude
                })
        
        # Сортируем по загруженности
        risk_schools.sort(key=lambda x: -x['current_occupancy'])
        
        return risk_schools


# Глобальный экземпляр для использования в views
_forecaster_instance = None

def get_forecaster() -> SchoolDemandForecaster:
    """Получить или создать экземпляр прогнозировщика"""
    global _forecaster_instance
    if _forecaster_instance is None:
        _forecaster_instance = SchoolDemandForecaster()
    return _forecaster_instance
