#!/usr/bin/env python
"""
Скрипт для запуска Django сервера с автоматической настройкой
"""
import os
import sys
import subprocess
from pathlib import Path

def run_command(command, description=""):
    """Выполнить команду с выводом результата"""
    print(f"🔧 {description}")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        if result.stdout:
            print(f"✅ {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка: {e}")
        if e.stderr:
            print(f"Детали ошибки: {e.stderr}")
        return False

def setup_project():
    """Настройка проекта"""
    print("🚀 Настройка проекта Building Optimizer MVP")
    print("=" * 50)
    
    # Проверяем наличие виртуального окружения
    if not os.path.exists('venv') and not os.path.exists('.venv'):
        print("📦 Создание виртуального окружения...")
        if not run_command("python -m venv venv", "Создание venv"):
            print("❌ Не удалось создать виртуальное окружение")
            return False
    
    # Активация виртуального окружения и установка зависимостей
    if os.name == 'nt':  # Windows
        venv_activate = "venv\\Scripts\\activate"
        pip_cmd = "venv\\Scripts\\pip"
        python_cmd = "venv\\Scripts\\python"
    else:  # Unix/Linux/MacOS
        venv_activate = "source venv/bin/activate"
        pip_cmd = "venv/bin/pip"
        python_cmd = "venv/bin/python"
    
    # Установка зависимостей
    print("📚 Установка зависимостей...")
    if not run_command(f"{pip_cmd} install -r requirements.txt", "Установка пакетов"):
        print("❌ Не удалось установить зависимости")
        return False
    
    # Создание директорий
    os.makedirs('building_optimizer/management/commands', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    # Миграции базы данных
    print("🗄️ Настройка базы данных...")
    if not run_command(f"{python_cmd} manage.py makemigrations", "Создание миграций"):
        return False
    
    if not run_command(f"{python_cmd} manage.py migrate", "Применение миграций"):
        return False
    
    # Создание примерных данных
    print("📊 Создание примерных данных...")
    run_command(f"{python_cmd} manage.py populate_sample_data", "Заполнение данными")
    
    # Создание суперпользователя (опционально)
    print("\n👤 Создание администратора (опционально)")
    create_admin = input("Создать учетную запись администратора? (y/n): ")
    if create_admin.lower() == 'y':
        run_command(f"{python_cmd} manage.py createsuperuser", "Создание суперпользователя")
    
    return True

def main():
    """Главная функция"""
    if not setup_project():
        print("❌ Ошибка настройки проекта")
        sys.exit(1)
    
    print("\n🎉 Проект успешно настроен!")
    print("=" * 50)
    print("📋 Инструкции:")
    print("1. Активируйте виртуальное окружение:")
    if os.name == 'nt':
        print("   venv\\Scripts\\activate")
    else:
        print("   source venv/bin/activate")
    
    print("2. Запустите сервер:")
    print("   python manage.py runserver")
    print("3. Откройте браузер: http://127.0.0.1:8000/")
    print("4. Админ-панель: http://127.0.0.1:8000/admin/")
    print("\n🔧 Особенности MVP:")
    print("- Тепловая карта с плотностью населения")
    print("- ИИ-рекомендации через Gemini API")
    print("- Интерактивная карта OpenStreetMap")
    print("- Поддержка разных типов зданий")
    print("- Адаптивный дизайн")
    
    # Предложение запустить сервер
    run_now = input("\n🚀 Запустить сервер сейчас? (y/n): ")
    if run_now.lower() == 'y':
        if os.name == 'nt':
            python_cmd = "venv\\Scripts\\python"
        else:
            python_cmd = "venv/bin/python"
        
        print("🌐 Запуск сервера...")
        try:
            subprocess.run(f"{python_cmd} manage.py runserver", shell=True)
        except KeyboardInterrupt:
            print("\n👋 Сервер остановлен")

if __name__ == "__main__":
    main()