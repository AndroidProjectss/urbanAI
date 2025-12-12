#!/bin/bash

set -e

echo "=== UrbanAI Docker Entrypoint ==="

# Применяем миграции
echo "📦 Applying database migrations..."
python manage.py migrate --noinput

# Загружаем данные школ (если таблица пустая)
echo "🏫 Loading school data..."
python manage.py load_schools || echo "⚠️ Schools already loaded or command not found"

echo "🚀 Starting Gunicorn on port 8001..."
exec gunicorn urbanproject.wsgi:application \
    --bind 0.0.0.0:8001 \
    --workers 3 \
    --threads 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    --capture-output \
    --log-level info
