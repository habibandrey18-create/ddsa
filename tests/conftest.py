"""
Конфигурация pytest для тестов
"""

import pytest
import sys
import os

# Добавляем корневую директорию проекта в путь
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Регистрируем маркер asyncio для pytest
pytest_plugins = ("pytest_asyncio",)


@pytest.fixture
def mock_db():
    """Мок для базы данных"""
    from unittest.mock import MagicMock

    db = MagicMock()
    db.get_cached_data.return_value = None
    db.set_cached_data = MagicMock()
    db.is_blacklisted.return_value = False
    db.exists_url.return_value = False
    db.add_post_to_history = MagicMock()
    db.update_publishing_state = MagicMock()
    db.add_to_error_queue = MagicMock()
    return db


@pytest.fixture
def mock_bot():
    """Мок для Telegram бота"""
    from unittest.mock import MagicMock, AsyncMock

    bot = MagicMock()
    bot.send_message = AsyncMock()
    bot.send_photo = AsyncMock()
    return bot


@pytest.fixture
def sample_card_url():
    """Пример валидного card-URL"""
    return "https://market.yandex.ru/card/product-name/123456"


@pytest.fixture
def sample_cc_url():
    """Пример валидного cc-URL"""
    return "https://market.yandex.ru/cc/ABC123"


@pytest.fixture
def sample_product_data():
    """Пример данных товара"""
    return {
        "title": "Test Product",
        "price": "1000 ₽",
        "url": "https://market.yandex.ru/card/test/123456",
        "description": "Test description",
        "image_bytes": None,
        "image_url": None,
        "flags": [],
    }
