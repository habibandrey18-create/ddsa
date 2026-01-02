# Настройка продакшена для Yandex.Market бота

## 🚀 Запуск в продакшене

### 1. Подготовка переменных окружения

Создайте `.env` файл на основе этого шаблона:

```bash
# Yandex Market Bot Configuration - PRODUCTION MODE
# Bot settings
BOT_TOKEN=your_production_bot_token_here
CHANNEL_ID=@your_production_channel
ADMIN_ID=your_admin_telegram_id

# Environment - PRODUCTION
ENVIRONMENT=prod
DEBUG_MODE=false

# Database - PRODUCTION
USE_POSTGRES=true
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=ymarket
POSTGRES_USER=bot
POSTGRES_PASSWORD=your_secure_password_here

USE_REDIS=true
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# API settings
USE_OFFICIAL_API=false
YANDEX_OAUTH_TOKEN=your_yandex_oauth_token_here

# Proxy settings (для продакшена с SOCKS5 прокси)
PROXY_LIST_STR=socks5://TV4GO0:1Z7dhD8iey@109.248.15.182:5501,socks5://TV4GO0:1Z7dhD8iey@109.248.15.188:5501,socks5://TV4GO0:1Z7dhD8iey@109.248.15.207:5501,socks5://TV4GO0:1Z7dhD8iey@109.248.15.209:5501,socks5://TV4GO0:1Z7dhD8iey@109.248.15.220:5501,socks5://TV4GO0:1Z7dhD8iey@109.248.15.223:5501

# Rate limiting - более агрессивное для продакшена
API_RATE_LIMIT=5
API_RATE_WINDOW=60

# Auto search - включено для продакшена
AUTO_SEARCH_ENABLED=true
AUTO_SEARCH_QUERIES=laptop,smartphone,headphones,tablet,washing machine,refrigerator
AUTO_SEARCH_MAX_PER_QUERY=3

# Auto main page - включено для продакшена
AUTO_MAIN_PAGE_ENABLED=true
AUTO_MAIN_PAGE_MAX=5

# Night mode - для продакшена
NIGHT_START=23
NIGHT_END=8

# Quality filters - более строгие для продакшена
QUALITY_MIN_PRICE=500
QUALITY_MIN_DISCOUNT=15
QUALITY_MIN_RATING=4.0
QUALITY_MIN_REVIEWS=100

# Brand limits - для продакшена
BRAND_WINDOW_SIZE=100
BRAND_MAX_PER_WINDOW=2

# Publishing settings - для продакшена
PUBLISH_INTERVAL=120
PUBLISH_BATCH_SIZE=1
POST_INTERVAL=7200  # 2 часа между постами в продакшене

# Logging
LOG_LEVEL=WARNING
```

### 2. Запуск с Docker Compose

```bash
# Запуск всех сервисов
docker-compose up -d

# Проверка статуса
docker-compose ps

# Просмотр логов
docker-compose logs -f bot
```

### 3. Проверка работоспособности

```bash
# Проверка Redis
docker-compose exec redis redis-cli ping

# Проверка PostgreSQL
docker-compose exec postgres pg_isready -U bot

# Проверка логов бота
docker-compose logs bot | tail -50
```

### 4. Мониторинг метрик

Бот автоматически собирает метрики:

- **Успешность парсинга** - процент успешных запросов
- **CAPTCHA detection** - количество обнаруженных CAPTCHA
- **HTTP 429 errors** - количество rate limit ошибок
- **Proxy quality** - качество работы прокси
- **Queue size** - размер очереди публикаций

### 5. Алерты и автоматические действия

Бот автоматически реагирует на проблемы:

- **Низкая успешность парсинга** → автоматическая пауза shadow-ban
- **Высокий CAPTCHA rate** → пауза + тестирование прокси
- **HTTP 429 rate** → увеличение задержек между запросами
- **Низкое качество прокси** → автоматическое тестирование пула

### 6. Резервное копирование

```bash
# Бэкап базы данных
docker-compose exec postgres pg_dump -U bot ymarket > backup_$(date +%Y%m%d_%H%M%S).sql

# Бэкап Redis (RDB файл)
docker-compose exec redis redis-cli save
docker cp $(docker-compose ps -q redis):/data/dump.rdb ./redis_backup_$(date +%Y%m%d_%H%M%S).rdb
```

### 7. Масштабирование

Для высокой нагрузки:

```bash
# Запуск нескольких инстансов бота
docker-compose up -d --scale bot=3

# Балансировка нагрузки через Redis очередь
# Все инстансы будут использовать общую очередь
```

### 8. Мониторинг производительности

Ключевые метрики для отслеживания:

- **Parsing success rate**: > 80%
- **Posts per hour**: 10-20 в продакшене
- **Queue size**: < 100 элементов
- **Proxy success rate**: > 70%
- **Affiliate CTR**: > 1%

### 9. Обновление

```bash
# Остановка
docker-compose down

# Обновление кода
git pull

# Пересборка
docker-compose build --no-cache

# Запуск
docker-compose up -d
```

## 🔧 Troubleshooting

### Redis не запускается
```bash
# Проверить порт
netstat -tlnp | grep 6379

# Проверить логи Redis
docker-compose logs redis
```

### Бот не может подключиться к Redis/PostgreSQL
```bash
# Проверить переменные окружения
docker-compose exec bot env | grep -E "(REDIS|POSTGRES)"

# Проверить подключение
docker-compose exec bot python -c "import redis; r = redis.Redis('redis', 6379); print(r.ping())"
```

### Высокий rate CAPTCHA
- Проверить прокси качество
- Увеличить задержки между запросами
- Проверить user-agent ротацию

### Низкая успешность парсинга
- Проверить работу Playwright fallback
- Проверить качество прокси
- Возможно shadow-ban - проверить логи алертов
