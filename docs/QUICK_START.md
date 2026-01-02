# Быстрый старт - Yandex.Market Bot

## 1. Поднятие инфраструктуры (Postgres + Redis + бот)

### Docker Compose (рекомендуется)

```bash
# 1. Скопируйте .env.example в .env и заполните настройки
cp .env.example .env
# Отредактируйте .env, установите BOT_TOKEN и другие настройки

# 2. Запустите инфраструктуру
docker-compose up -d

# 3. Запустите миграции БД
docker-compose exec bot python scripts/run_migrations.py
```

### Ручной запуск (без Docker)

```bash
# 1. Установите Postgres и Redis
# 2. Создайте БД
createdb ymarket
# 3. Запустите миграции
python scripts/run_migrations.py
# 4. Запустите бота
python main.py
```

## 2. Ручной прогон каталога

```bash
# Ручной поиск товаров
python main.py search наушники

# Проверка логов
tail -n 200 logs/bot.log | grep -E "parsed products|added to queue|erid"
```

## 3. Проверка affiliate/ERID ссылок

1. Проверьте формат ссылок в логах: должны быть `https://market.yandex.ru/cc/<code>`
2. В посте должен быть ERID: `erid: <ERID>` (совпадает со ссылкой)
3. Кликните по 2-3 тестовым ссылкам и проверьте их в партнерской панели

## 4. Мониторинг и алерты

### Prometheus метрики

Метрики доступны на `http://localhost:9100/metrics` (если PROMETHEUS_ENABLED=true)

Основные метрики:
- `ymarket_products_found_total` - найдено товаров
- `ymarket_products_published_total` - опубликовано товаров
- `ymarket_products_rejected_total` - отклонено товаров
- `ymarket_search_errors_total` - ошибки поиска
- `ymarket_publish_errors_total` - ошибки публикации
- `ymarket_clicks_total` - клики по ссылкам

### Пример prometheus.yml

```yaml
scrape_configs:
  - job_name: 'ymarket_bot'
    static_configs:
      - targets: ['bot-host:9100']
```

### Алерты (пример)

```yaml
groups:
  - name: ymarket_alerts
    rules:
      - alert: HighRejectionRate
        expr: rate(ymarket_products_rejected_total[1h]) > 50
        annotations:
          summary: "High product rejection rate"
      
      - alert: PublishWorkerDown
        expr: up{job="ymarket_bot"} == 0
        annotations:
          summary: "Publish worker is down"
      
      - alert: ShadowBanDetected
        expr: increase(ymarket_shadow_ban_detected_total[1h]) > 0
        annotations:
          summary: "Shadow ban detected"
```

## 5. Анти-бот / парсинг

### Playwright fallback

Playwright используется автоматически когда:
- Обычный HTTP парсинг вернул < 5 товаров
- Сработал shadow-ban detector
- Возвращается 400/403 ошибка

Настройки в `.env`:
- `USE_PLAYWRIGHT_FALLBACK=true` (по умолчанию включено)
- Playwright запускается автоматически при необходимости

## 6. Обучение на кликах

Сервис учится на основе:
- Категории товаров
- Брендов
- Ценовых диапазонов
- Типов постов

Стратегия выбора:
- 70% — топ-категории
- 20% — тест новых
- 10% — эксперименты

Автоматическая очистка:
- Бренды с кликами < 0.3 → в blacklist
- Категории без кликов → реже
- Типы постов с нулем → отключаем

## 7. Runbook - если что-то поломалось

### Парсер вернул 0 товаров

1. Проверьте логи: `tail -n 200 logs/bot.log | grep "shadow-ban"`
2. Если shadow-ban → включите Playwright fallback
3. Если нет shadow-ban → проверьте прокси/headers

### Publish queue растет

```bash
# Проверьте размер очереди
redis-cli LLEN publish_queue

# Проверьте rejections.csv
tail -n 50 rejections.csv
```

### ERID/affiliate не совпадают

```bash
# Найдите все erid в логах
grep "erid" logs/bot.log | tail -n 50

# Сравните со ссылками в постах
```

## 8. Полезные команды

```bash
# Статус бота
python main.py status

# Принудительная публикация
python main.py publish

# Ручной поиск
python main.py search наушники

# Логи Docker
docker-compose logs -f bot

# Перезапуск бота
docker-compose restart bot

# Остановка всех контейнеров
docker-compose down
```

## 9. Health check

```bash
# HTTP health (если есть endpoint)
curl -sS http://localhost:8000/health

# Prometheus метрики
curl -sS http://localhost:9100/metrics

# Проверка БД
docker-compose exec postgres psql -U bot -d ymarket -c "SELECT COUNT(*) FROM products;"
```

