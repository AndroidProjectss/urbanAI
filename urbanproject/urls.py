from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('building_optimizer.urls')), # Все API-эндпоинты идут через /api/
    path('', include('building_optimizer.urls')), # Главная страница и другие статические пути
]