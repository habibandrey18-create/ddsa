#!/bin/bash
# Скрипт для быстрой настройки и запуска инфраструктуры

set -e

echo "🚀 Setting up Yandex.Market Bot infrastructure..."

# Проверка Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose is not installed. Please install docker-compose first."
    exit 1
fi

# Копируем .env.example в .env если .env не существует
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "📝 Copying .env.example to .env..."
        cp .env.example .env
        echo "⚠️  Please edit .env and set your BOT_TOKEN and other settings"
    else
        echo "❌ .env.example not found. Please create .env file manually."
        exit 1
    fi
fi

# Запускаем docker-compose
echo "🐳 Starting Docker containers..."
docker-compose up -d

# Ждем пока Postgres будет готов
echo "⏳ Waiting for Postgres to be ready..."
sleep 5

# Запускаем миграции
echo "📊 Running database migrations..."
docker-compose exec bot python scripts/run_migrations.py || {
    echo "⚠️  Migrations failed or bot container not ready. Running manually..."
    python scripts/run_migrations.py || true
}

echo "✅ Setup complete!"
echo ""
echo "📋 Useful commands:"
echo "  docker-compose logs -f bot    # View bot logs"
echo "  docker-compose ps             # Check container status"
echo "  docker-compose down           # Stop containers"
echo "  docker-compose restart bot    # Restart bot only"

