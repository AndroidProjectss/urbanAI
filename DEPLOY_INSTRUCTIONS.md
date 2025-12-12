# 🚀 Инструкция по деплою UrbanAI на VPS

## Требования
- Ubuntu 22.04
- Docker и Docker Compose установлены
- Доступ по SSH с правами sudo

---

## 📦 Шаг 1: Создание пользователя для хакатона

```bash
# Подключаемся к серверу
ssh root@your-server-ip

# Создаем пользователя hackathon
sudo adduser hackathon

# Добавляем в группу docker (чтобы мог запускать контейнеры)
sudo usermod -aG docker hackathon

# Добавляем в группу sudo (опционально, для удобства)
sudo usermod -aG sudo hackathon

# Переключаемся на пользователя
su - hackathon
```

---

## 📂 Шаг 2: Загрузка проекта на сервер

### Вариант A: Через Git
```bash
# На сервере под пользователем hackathon
cd ~
git clone https://github.com/your-repo/urbanAI.git
cd urbanAI
```

### Вариант B: Через SCP (с локальной машины)
```bash
# На ЛОКАЛЬНОЙ машине (Windows PowerShell)
scp -r C:\Users\Lenovo\projects\urbanAI hackathon@your-server-ip:~/

# Или через rsync (если есть WSL)
rsync -avz --exclude '__pycache__' --exclude '.git' --exclude 'venv' \
    /mnt/c/Users/Lenovo/projects/urbanAI/ hackathon@your-server-ip:~/urbanAI/
```

### Вариант C: Через архив
```bash
# На ЛОКАЛЬНОЙ машине - создаем архив (PowerShell)
cd C:\Users\Lenovo\projects
Compress-Archive -Path urbanAI -DestinationPath urbanAI.zip

# Отправляем на сервер
scp urbanAI.zip hackathon@your-server-ip:~/

# На СЕРВЕРЕ - распаковываем
cd ~
unzip urbanAI.zip
cd urbanAI
```

---

## ⚙️ Шаг 3: Настройка окружения

```bash
# На сервере в папке проекта
cd ~/urbanAI

# Создаем .env файл
cp .env.example .env

# Редактируем .env
nano .env
```

**Заполните .env:**
```env
SECRET_KEY=сгенерируйте-длинный-случайный-ключ-минимум-50-символов
ALLOWED_HOSTS=localhost,127.0.0.1,your-domain.com,your-server-ip
DEBUG=False
GEMINI_API_KEY=ваш-ключ-gemini-api
```

**Сгенерировать SECRET_KEY можно так:**
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

---

## 🐳 Шаг 4: Запуск Docker контейнера

```bash
# Убедитесь что вы в папке проекта
cd ~/urbanAI

# Собираем и запускаем
docker-compose up -d --build

# Проверяем статус
docker-compose ps

# Смотрим логи
docker-compose logs -f
```

**Проект будет доступен на порту 8001:**
```
http://your-server-ip:8001/
```

---

## 🔧 Шаг 5: Настройка Nginx (опционально)

Если хотите красивый домен без порта:

```bash
# Под пользователем root или sudo
sudo nano /etc/nginx/sites-available/urbanai
```

**Конфигурация Nginx:**
```nginx
server {
    listen 80;
    server_name urbanai.your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 120s;
    }

    location /static/ {
        alias /home/hackathon/urbanAI/staticfiles/;
    }
}
```

```bash
# Активируем сайт
sudo ln -s /etc/nginx/sites-available/urbanai /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 🔥 Полезные команды

```bash
# Перезапуск контейнера
docker-compose restart

# Остановка
docker-compose down

# Пересборка после изменений
docker-compose up -d --build

# Логи в реальном времени
docker-compose logs -f urbanai

# Зайти внутрь контейнера
docker-compose exec urbanai bash

# Выполнить Django команду
docker-compose exec urbanai python manage.py migrate
docker-compose exec urbanai python manage.py createsuperuser

# Проверить статус
docker-compose ps
docker stats urbanai_hackathon
```

---

## 🧹 После хакатона: Полная очистка

```bash
# 1. Останавливаем и удаляем контейнеры
cd ~/urbanAI
docker-compose down -v  # -v удаляет volumes

# 2. Удаляем образы
docker rmi urbanai_urbanai
docker image prune -a  # Удалить все неиспользуемые образы

# 3. Выходим из пользователя
exit

# 4. Под root - удаляем пользователя и его файлы
sudo deluser --remove-home hackathon

# 5. Удаляем конфиг nginx (если создавали)
sudo rm /etc/nginx/sites-enabled/urbanai
sudo rm /etc/nginx/sites-available/urbanai
sudo systemctl reload nginx

# 6. Очистка Docker
docker system prune -a --volumes
```

---

## 🐛 Troubleshooting

### Порт занят
```bash
# Проверить что занимает порт 8001
sudo lsof -i :8001
sudo netstat -tulpn | grep 8001

# Если что-то занимает - убить
sudo kill -9 PID
```

### Проблемы с правами Docker
```bash
# Убедитесь что пользователь в группе docker
groups hackathon

# Если нет - добавьте и перелогиньтесь
sudo usermod -aG docker hackathon
# Выйти и зайти заново
```

### Контейнер не стартует
```bash
# Смотрим логи
docker-compose logs urbanai

# Пробуем запустить без демона
docker-compose up
```

### База данных не сохраняется
```bash
# Проверяем volumes
docker volume ls
docker volume inspect urbanai_urbanai_db
```

---

## 📊 Проверка работы

1. Откройте `http://your-server-ip:8001/` - должна загрузиться карта
2. Проверьте API: `http://your-server-ip:8001/api/enhanced-heatmap/`
3. Проверьте логи: `docker-compose logs -f`

---

## 📝 Структура файлов на сервере

```
/home/hackathon/
└── urbanAI/
    ├── Dockerfile
    ├── docker-compose.yml
    ├── entrypoint.sh
    ├── .env                  # Ваши настройки (не в git!)
    ├── .env.example
    ├── requirements.txt
    ├── manage.py
    ├── urbanproject/
    │   └── settings.py
    ├── building_optimizer/
    │   └── ...
    └── staticfiles/          # Собранная статика
```

---

**🎉 Готово! Проект запущен на порту 8001 и не мешает существующему проекту на порту 8000.**
