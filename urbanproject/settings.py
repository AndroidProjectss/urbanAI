import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-your-secret-key-here')

DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 'yes')

# Разрешенные хосты из env или дефолтные
_raw_allowed_hosts = [h.strip() for h in os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',') if h.strip()]
ALLOWED_HOSTS = list(dict.fromkeys(_raw_allowed_hosts + ['127.0.0.1', 'localhost']))

# CSRF trusted origins для production
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:8001',
    'http://127.0.0.1:8001',
]
# Добавляем из ALLOWED_HOSTS
for host in ALLOWED_HOSTS:
    if host and host not in ('localhost', '127.0.0.1'):
        CSRF_TRUSTED_ORIGINS.append(f'http://{host}')
        CSRF_TRUSTED_ORIGINS.append(f'https://{host}')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'building_optimizer',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'urbanproject.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'urbanproject.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []

# API Keys
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'AIzaSyATqR3WHOm852h3N6BR7KKLeUo3zUhVYXc')
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY', '')

# CORS settings
CORS_ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8001",
    "http://127.0.0.1:8001",
]

# Добавляем разрешенные хосты в CORS
for host in ALLOWED_HOSTS:
    if host and host not in ('localhost', '127.0.0.1'):
        CORS_ALLOWED_ORIGINS.append(f'http://{host}')
        CORS_ALLOWED_ORIGINS.append(f'https://{host}')
        CORS_ALLOWED_ORIGINS.append(f'http://{host}:8001')

# Разрешаем все для разработки (можно отключить в production)
CORS_ALLOW_ALL_ORIGINS = DEBUG

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Security settings for production
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_CONTENT_TYPE_NOSNIFF = True