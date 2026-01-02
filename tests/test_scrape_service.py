"""
Unit тесты для ScrapeService
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from services.scrape_service import (
    safe_scrape_with_retry,
    get_product_data,
    ScrapeTimeoutError,
    ScrapeNetworkError,
)


class TestSafeScrapeWithRetry:
    """Тесты для safe_scrape_with_retry"""

    @pytest.mark.asyncio
    async def test_safe_scrape_success(self):
        """Тест 10: Успешный скрап валидного URL"""
        mock_data = {
            "title": "Test Product",
            "price": "1000 ₽",
            "url": "https://market.yandex.ru/card/test/123456",
        }

        with patch(
            "services.scrape_service.scrape_yandex_market", new_callable=AsyncMock
        ) as mock_scrape:
            mock_scrape.return_value = mock_data

            with patch("services.scrape_service.database.Database") as mock_db:
                mock_db_instance = MagicMock()
                mock_db_instance.get_cached_data.return_value = None
                mock_db_instance.set_cached_data = MagicMock()
                mock_db.return_value = mock_db_instance

                result = await safe_scrape_with_retry(
                    "https://market.yandex.ru/card/test/123456"
                )

                assert result == mock_data
                assert result["title"] == "Test Product"

    @pytest.mark.asyncio
    async def test_safe_scrape_api_404(self):
        """Тест 11: API возвращает 404"""
        with patch(
            "services.scrape_service.scrape_yandex_market", new_callable=AsyncMock
        ) as mock_scrape:
            # Симулируем ошибку 404
            mock_scrape.side_effect = Exception("api404 expected")

            with patch("services.scrape_service.database.Database") as mock_db:
                mock_db_instance = MagicMock()
                mock_db_instance.get_cached_data.return_value = None
                mock_db.return_value = mock_db_instance

                result = await safe_scrape_with_retry(
                    "https://market.yandex.ru/card/test/123456", max_attempts=2
                )

                assert result is None
                mock_scrape.assert_called()

    @pytest.mark.asyncio
    async def test_safe_scrape_timeout(self):
        """Тест 12: Таймаут при скрапе"""
        with patch(
            "services.scrape_service.scrape_yandex_market", new_callable=AsyncMock
        ) as mock_scrape:
            mock_scrape.side_effect = asyncio.TimeoutError("Request timeout")

            with patch("services.scrape_service.database.Database") as mock_db:
                mock_db_instance = MagicMock()
                mock_db_instance.get_cached_data.return_value = None
                mock_db.return_value = mock_db_instance

                result = await safe_scrape_with_retry(
                    "https://market.yandex.ru/card/test/123456", max_attempts=2
                )

                assert result is None

    @pytest.mark.asyncio
    async def test_safe_scrape_empty_response(self):
        """Тест 13: Пустой ответ от сервера"""
        with patch(
            "services.scrape_service.scrape_yandex_market", new_callable=AsyncMock
        ) as mock_scrape:
            # Возвращаем данные без title
            mock_scrape.return_value = {"url": "https://market.yandex.ru/card/test"}

            with patch("services.scrape_service.database.Database") as mock_db:
                mock_db_instance = MagicMock()
                mock_db_instance.get_cached_data.return_value = None
                mock_db.return_value = mock_db_instance

                result = await safe_scrape_with_retry(
                    "https://market.yandex.ru/card/test/123456", max_attempts=2
                )

                # Должен вернуть None, так как нет title
                assert result is None

    @pytest.mark.asyncio
    async def test_safe_scrape_invalid_json(self):
        """Тест 14: Невалидный JSON в ответе API"""
        with patch(
            "services.scrape_service.scrape_yandex_market", new_callable=AsyncMock
        ) as mock_scrape:
            import json

            mock_scrape.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)

            with patch("services.scrape_service.database.Database") as mock_db:
                mock_db_instance = MagicMock()
                mock_db_instance.get_cached_data.return_value = None
                mock_db.return_value = mock_db_instance

                result = await safe_scrape_with_retry(
                    "https://market.yandex.ru/card/test/123456", max_attempts=2
                )

                assert result is None

    @pytest.mark.asyncio
    async def test_safe_scrape_retry_logic(self):
        """Тест 15: Первая попытка падает, вторая успешна"""
        mock_data = {
            "title": "Test Product",
            "price": "1000 ₽",
            "url": "https://market.yandex.ru/card/test/123456",
        }

        with patch(
            "services.scrape_service.scrape_yandex_market", new_callable=AsyncMock
        ) as mock_scrape:
            # Первая попытка падает, вторая успешна
            mock_scrape.side_effect = [Exception("First attempt failed"), mock_data]

            with patch("services.scrape_service.database.Database") as mock_db:
                mock_db_instance = MagicMock()
                mock_db_instance.get_cached_data.return_value = None
                mock_db_instance.set_cached_data = MagicMock()
                mock_db.return_value = mock_db_instance

                result = await safe_scrape_with_retry(
                    "https://market.yandex.ru/card/test/123456", max_attempts=3
                )

                assert result == mock_data
                assert mock_scrape.call_count == 2

    @pytest.mark.asyncio
    async def test_safe_scrape_cache_hit(self):
        """Тест 16: Данные есть в кэше"""
        cached_data = {
            "title": "Cached Product",
            "price": "2000 ₽",
            "url": "https://market.yandex.ru/card/test/123456",
        }

        with patch("services.scrape_service.database.Database") as mock_db:
            mock_db_instance = MagicMock()
            mock_db_instance.get_cached_data.return_value = cached_data
            mock_db.return_value = mock_db_instance

            with patch(
                "services.scrape_service.scrape_yandex_market", new_callable=AsyncMock
            ) as mock_scrape:
                result = await safe_scrape_with_retry(
                    "https://market.yandex.ru/card/test/123456"
                )

                assert result == cached_data
                # Скрапер не должен вызываться, если данные в кэше
                mock_scrape.assert_not_called()


class TestGetProductData:
    """Тесты для get_product_data"""

    @pytest.mark.asyncio
    async def test_get_product_data_cc_url_resolve(self):
        """Тест 21: cc-URL успешно резолвится в card-URL"""
        url = "https://market.yandex.ru/cc/ABC123"
        url_info = {"is_cc": True, "cc_code": "ABC123", "normalized_card_url": None}

        resolved_url = "https://market.yandex.ru/card/product/123456"
        mock_data = {"title": "Test Product", "price": "1000 ₽", "url": resolved_url}

        with patch(
            "services.scrape_service.resolve_final_url", new_callable=AsyncMock
        ) as mock_resolve:
            mock_resolve.return_value = resolved_url

            with patch(
                "services.scrape_service.safe_scrape_with_retry", new_callable=AsyncMock
            ) as mock_scrape:
                mock_scrape.return_value = mock_data

                result = await get_product_data(
                    url, url_info, retry_count=3, correlation_id="test"
                )

                assert result == mock_data
                mock_resolve.assert_called_once_with(url)
                mock_scrape.assert_called_once_with(resolved_url, 3, "test", True)

    @pytest.mark.asyncio
    async def test_get_product_data_cc_url_no_resolve(self):
        """Тест 22: cc-URL не резолвится, скрап падает"""
        url = "https://market.yandex.ru/cc/ABC123"
        url_info = {"is_cc": True, "cc_code": "ABC123", "normalized_card_url": None}

        with patch(
            "services.scrape_service.resolve_final_url", new_callable=AsyncMock
        ) as mock_resolve:
            mock_resolve.return_value = None  # Не удалось резолвить

            with patch(
                "services.scrape_service.safe_scrape_with_retry", new_callable=AsyncMock
            ) as mock_scrape:
                mock_scrape.return_value = None  # Скрап тоже падает

                result = await get_product_data(
                    url, url_info, retry_count=3, correlation_id="test"
                )

                assert result is None
                # Должен попытаться скрапить исходный URL
                mock_scrape.assert_called()
