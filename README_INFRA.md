# Инфраструктура Yandex.Market Bot

## Обзор

Реализована полная инфраструктура для продакшн-развертывания бота с Docker, Postgres, Redis, мониторингом и умными алгоритмами.

## Компоненты

### 1. Docker Infrastructure

- **docker-compose.yml** - Оркестрация Postgres + Redis + Bot
- **Dockerfile** - Образ бота с Playwright и всеми зависимостями
- **.env.example** - Шаблон конфигурации

### 2. База данных

- **Postgres 15** - Основная БД
- **SQL миграции** (`migrations/001_initial_schema.sql`) - Схема таблиц:
  - `products` - Товары (dedup)
  - `metrics` - Метрики affiliate ссылок
  - `post_performance` - Производительность постов
  - `category_performance` - Статистика по категориям
  - `brand_performance` - Статистика по брендам
  - `shadow_ban_log` - Логи shadow-ban детектора

### 3. Сервисы

#### Playwright Parser Service (`services/playwright_parser_service.py`)
- Fallback парсинг каталогов через headless browser
- Используется только когда HTTP парсинг вернул < 5 товаров
- Парсит `__NEXT_DATA__` из HTML

#### Prometheus Metrics Service (`services/prometheus_metrics_service.py`)
- Экспорт метрик для мониторинга
- Метрики: products_found, products_published, products_rejected, clicks
- HTTP endpoint: `http://localhost:9100/metrics`

#### Click Learning Service (`services/click_learning_service.py`)
- Обучение на кликах
- Анализ эффективности по категориям/брендам/ценам
- Стратегия: 70% топ-категории, 20% новые, 10% эксперименты

## Быстрый старт

```bash
# 1. Клонировать репозиторий и перейти в директорию
cd "Yandex.Market bot"

# 2. Скопировать .env.example в .env и заполнить настройки
cp .env.example .env
# Отредактируйте .env, установите BOT_TOKEN

# 3. Запустить инфраструктуру
docker-compose up -d

# 4. Запустить миграции
docker-compose exec bot python scripts/run_migrations.py

# 5. Проверить логи
docker-compose logs -f bot
```

## Конфигурация

### Обязательные переменные в .env:

```env
BOT_TOKEN=your_telegram_bot_token
CHANNEL_ID=@your_channel
DATABASE_URL=postgresql://bot:secret@postgres:5432/ymarket
REDIS_URL=redis://redis:6379/0
```

### Опциональные переменные:

```env
# Prometheus
PROMETHEUS_ENABLED=true
PROMETHEUS_PORT=9100

# Learning
LEARNING_MIN_POSTS=5
LEARNING_MIN_CLICKS_BLACKLIST=0.3
```

## Мониторинг

### Prometheus метрики

Метрики доступны на `http://localhost:9100/metrics`

Основные метрики:
- `ymarket_products_found_total` - найдено товаров
- `ymarket_products_published_total` - опубликовано товаров
- `ymarket_products_rejected_total` - отклонено товаров
- `ymarket_clicks_total` - клики по ссылкам

### Алерты (пример prometheus.yml)

```yaml
groups:
  - name: ymarket_alerts
    rules:
      - alert: HighRejectionRate
        expr: rate(ymarket_products_rejected_total[1h]) > 50
        annotations:
          summary: "High product rejection rate"
      
      - alert: ShadowBanDetected
        expr: increase(ymarket_shadow_ban_detected_total[1h]) > 0
        annotations:
          summary: "Shadow ban detected"
```

## Проверка affiliate/ERID ссылок

1. Проверьте формат ссылок: `https://market.yandex.ru/cc/<code>`
2. В посте должен быть ERID: `erid: <ERID>`
3. Кликните по тестовым ссылкам и проверьте в партнерской панели

## Обучение на кликах

Сервис учится на основе:
- Категории товаров
- Брендов
- Ценовых диапазонов
- Типов постов

Стратегия:
- 70% — топ-категории
- 20% — тест новых
- 10% — эксперименты

Автоматическая очистка:
- Бренды с кликами < 0.3 → blacklist
- Категории без кликов → реже
- Типы постов с нулем → отключаем

## Runbook

### Парсер вернул 0 товаров

1. Проверьте логи: `docker-compose logs bot | grep "shadow-ban"`
2. Если shadow-ban → Playwright fallback включится автоматически
3. Проверьте прокси/headers в .env

### Publish queue растет

```bash
# Проверьте размер очереди в Redis
docker-compose exec redis redis-cli LLEN publish_queue
```

### Проверка БД

```bash
# Подключиться к Postgres
docker-compose exec postgres psql -U bot -d ymarket

# Проверить количество товаров
SELECT COUNT(*) FROM products;

# Проверить метрики
SELECT * FROM metrics ORDER BY created_at DESC LIMIT 10;
```

## Полезные команды

```bash
# Статус контейнеров
docker-compose ps

# Логи бота
docker-compose logs -f bot

# Перезапуск бота
docker-compose restart bot

# Остановка всех контейнеров
docker-compose down

# Остановка с удалением volumes
docker-compose down -v
```

## Документация

- `docs/QUICK_START.md` - Быстрый старт
- `migrations/001_initial_schema.sql` - SQL схема
- `scripts/run_migrations.py` - Скрипт миграций
- `scripts/docker_setup.sh` - Скрипт настройки

## Лицензия

MIT

