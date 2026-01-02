# Новая Архитектура Yandex.Market Bot

## Обзор

Продвинутая архитектура бота для парсинга и публикации товаров Yandex.Market с использованием Postgres + Redis для высокой производительности и надёжности.

## Архитектура

### Хранилище
- **Postgres**: Основное хранилище товаров, истории цен, метрик, настроек
- **Redis**: Быстрая очередь публикации, дедупликация, sliding windows, кэш

### Сервисы (Workers)
1. **Smart Search** - Умный автопоиск с offset per keyword
2. **Validator** - Валидация и фильтрация товаров
3. **Content Service** - Генерация контента с ротацией шаблонов
4. **Publish Service** - Буфер отложенной публикации
5. **Metrics Service** - Сбор и анализ метрик CTR

### Особенности
- ✅ **Умный автопоиск** - offset per keyword для избежания дублирования
- ✅ **Анти-пустые посты** - многоуровневая валидация
- ✅ **Ротация контента** - шаблоны + CTA для разнообразия
- ✅ **Фильтры качества** - цена/скидка/рейтинг/отзывы
- ✅ **Price alerts** - уведомления о снижении цен
- ✅ **Brand limits** - sliding window ограничения брендов
- ✅ **Publish buffer** - Redis очередь с rate limiting
- ✅ **CTR метрики** - отслеживание эффективности

## Установка

### 1. Зависимости

```bash
pip install -r requirements.txt
```

### 2. Базы данных

#### Postgres
```sql
-- Создание базы данных
CREATE DATABASE yandex_market_bot;

-- Создание пользователя
CREATE USER bot_user WITH PASSWORD 'your_password';

-- Предоставление прав
GRANT ALL PRIVILEGES ON DATABASE yandex_market_bot TO bot_user;
```

#### Redis
```bash
# Установка Redis (Ubuntu/Debian)
sudo apt update && sudo apt install redis-server

# Запуск
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

### 3. Конфигурация

Обновите `.env` файл:

```ini
# Новая архитектура
USE_POSTGRES=true
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=yandex_market_bot
POSTGRES_USER=bot_user
POSTGRES_PASSWORD=your_password

USE_REDIS=true
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# Фильтры качества
QUALITY_MIN_PRICE=100
QUALITY_MIN_DISCOUNT=10
QUALITY_MIN_RATING=4.2
QUALITY_MIN_REVIEWS=50

# Лимиты брендов
BRAND_WINDOW_SIZE=50
BRAND_MAX_PER_WINDOW=1

# Буфер публикации
PUBLISH_INTERVAL=60
PUBLISH_BATCH_SIZE=1

# AI сервисы
GROQ_API_KEY=your_groq_key
```

### 4. Инициализация

```bash
# Тестирование архитектуры
python test_new_architecture.py

# Если все тесты пройдены, запуск бота
python main_worker.py
```

## Компоненты

### 1. Smart Search Service (`services/smart_search_service.py`)

**Функции:**
- Автопоиск товаров по ключевым словам
- Offset per keyword для продолжения поиска
- Дедупликация через Redis
- Сохранение в Postgres

**Использование:**
```python
from services.smart_search_service import get_smart_search_service

search = get_smart_search_service()
result = await search.run_smart_search_cycle(keywords=["наушники", "гаджеты"])
```

### 2. Product Validator (`services/validator_service.py`)

**Проверки:**
- Наличие изображений
- Корректность цены
- Достаточная длина описания
- Доступность товара
- Фильтры качества
- Белый/чёрный список брендов
- Sliding window лимиты

**Использование:**
```python
from services.validator_service import get_product_validator

validator = get_product_validator()
is_valid, errors = await validator.validate_product(product)
```

### 3. Content Service (`services/content_service.py`)

**Особенности:**
- 5+ шаблонов постов
- Ротация CTA (10+ вариантов)
- Весовая система выбора
- Поддержка разных категорий товаров

**Шаблоны:**
- General (общие товары)
- Discount (скидки)
- Rating (высокий рейтинг)
- New (новинки)

### 4. Publish Service (`services/publish_service.py`)

**Функции:**
- Redis очередь публикаций
- Rate limiting (интервал между постами)
- Приоритетная очередь
- Sliding window лимиты брендов

**Очередь:**
- Score = timestamp - priority (меньше = выше приоритет)
- Автоматическая очистка старых элементов

### 5. Metrics Service (`services/metrics_service.py`)

**Метрики:**
- CTR по постам
- CTR по брендам
- CTR по шаблонам
- Конверсии (опционально)

**Отчёты:**
- Ежедневные отчёты производительности
- A/B тестирование шаблонов
- Экспорт в CSV

## API Endpoints

### Метрики
```
GET /metrics/report?days=7          # Отчёт о производительности
GET /metrics/click/{post_id}        # Отслеживание кликов
POST /metrics/impression/{post_id}  # Отслеживание показов
```

### Управление
```
POST /admin/search/manual            # Ручной запуск поиска
GET /admin/queue/stats              # Статистика очереди
POST /admin/publish/force           # Принудительная публикация
```

## Мониторинг

### Логи
```
INFO: Поиск завершён: найдено 25 товаров
INFO: Опубликовано: 3 поста, CTR: 2.4%
WARNING: Товар не прошёл валидацию: низкая цена
ERROR: Ошибка подключения к Redis
```

### Метрики Prometheus (опционально)
- `yandex_market_products_found_total`
- `yandex_market_posts_published_total`
- `yandex_market_ctr_percentage`
- `yandex_market_queue_size`

## Производительность

### Базы данных
- **Postgres**: 1000+ RPM на чтение, 500+ RPM на запись
- **Redis**: 50000+ RPM, sub-millisecond latency

### Поиск
- 50+ ключевых слов за цикл
- 20-50 товаров на страницу
- 30-60 минут между циклами

### Публикация
- 1 пост в минуту (rate limit)
- Batch processing (1-5 постов за раз)
- Priority queue для важных товаров

## Безопасность

### Rate Limiting
- Redis-based rate limiting
- Circuit breaker pattern
- Graceful degradation

### Валидация
- Input sanitization
- SQL injection prevention
- XSS protection в контенте

## Расширение

### Добавление новых шаблонов
```python
content_service.add_custom_template(
    "custom_1",
    "🎉 {title} — только {price} ₽!",
    category="promo",
    weight=2
)
```

### Добавление новых CTA
```python
content_service.add_custom_cta(
    "custom_cta",
    "Срочно в корзину!",
    category="urgent",
    emoji="🔥",
    weight=3
)
```

### Кастомные фильтры качества
```python
# В config.py добавить:
CUSTOM_MIN_WEIGHT=0.5  # кг
CUSTOM_MAX_DELIVERY_DAYS=7
```

## Troubleshooting

### Проблемы с Postgres
```bash
# Проверить подключение
psql -h localhost -U bot_user -d yandex_market_bot

# Проверить логи
tail -f /var/log/postgresql/postgresql-*.log
```

### Проблемы с Redis
```bash
# Проверить статус
redis-cli ping

# Проверить память
redis-cli info memory

# Очистить очередь (тестирование)
redis-cli del publish_buffer
```

### Отладка поиска
```bash
# Ручной поиск
python test_new_architecture.py search

# Проверка валидатора
python test_new_architecture.py validator
```

## Production Deployment

### Docker Compose
```yaml
version: '3.8'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: yandex_market_bot
      POSTGRES_USER: bot_user
      POSTGRES_PASSWORD: your_password

  redis:
    image: redis:7-alpine

  bot:
    build: .
    depends_on:
      - postgres
      - redis
    environment:
      - USE_POSTGRES=true
      - USE_REDIS=true
```

### Systemd Service
```ini
[Unit]
Description=Yandex Market Bot
After=network.target postgresql.service redis-server.service

[Service]
Type=simple
User=botuser
WorkingDirectory=/path/to/bot
ExecStart=/path/to/venv/bin/python main_worker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Roadmap

### Краткосрочные цели (1-2 недели)
- [ ] Интеграция с Telegram Bot API
- [ ] Web dashboard для мониторинга
- [ ] A/B тестирование шаблонов
- [ ] Автоматическая ротация ключевых слов

### Долгосрочные цели (1-3 месяца)
- [ ] ML модель для предсказания CTR
- [ ] Интеграция с внешними affiliate сетями
- [ ] Мульти-платформенная публикация
- [ ] Advanced analytics dashboard

---

## Контакты

Для вопросов и предложений: создайте issue в репозитории или напишите в Telegram.