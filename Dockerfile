# UrbanAI - Dockerfile для хакатона
# Django 4.2 + Python 3.11

FROM python:3.11-slim

# Переменные окружения
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=urbanproject.settings

# Рабочая директория
WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копируем и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir gunicorn

# Копируем проект
COPY . .

# Создаем директорию для статики
RUN mkdir -p /app/staticfiles

# Собираем статику
RUN python manage.py collectstatic --noinput

# Права на entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Порт
EXPOSE 8001

# Запуск
ENTRYPOINT ["/entrypoint.sh"]
