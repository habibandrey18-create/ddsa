"""
Unit тесты для PostService
"""

import pytest
import os
from unittest.mock import AsyncMock, patch, MagicMock
from services.post_service import create_link_only_post, send_post_to_channel


class TestCreateLinkOnlyPost:
    """Тесты для create_link_only_post"""

    @pytest.mark.asyncio
    async def test_create_link_only_post(self):
        """Тест 35: Создание link-only поста"""
        url = "https://market.yandex.ru/cc/ABC123"
        result = await create_link_only_post(url, None, "test_correlation")

        assert result["title"] == "Товар Яндекс.Маркета"
        assert result["price"] == "Цена уточняется"
        assert result["url"] == url
        assert result["ref_link"] == url
        assert result["has_ref"] is True
        assert "link_only" in result["flags"]
        assert "cc_url_direct" in result["flags"]
        assert "scrape_failed" in result["flags"]


class TestSendPostToChannel:
    """Тесты для send_post_to_channel"""

    @pytest.mark.asyncio
    async def test_send_post_photo_success(self):
        """Тест 31: Успешная отправка поста с фото"""
        mock_bot = MagicMock()
        mock_message = MagicMock()
        mock_message.message_id = 12345
        mock_bot.send_photo = AsyncMock(return_value=mock_message)

        data = {
            "title": "Test Product",
            "price": "1000 ₽",
            "url": "https://market.yandex.ru/card/test/123456",
        }

        # Создаём временный файл для фото
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            photo_path = tmp.name

        try:
            with patch(
                "services.post_service.generate_post_caption",
                return_value="Test caption",
            ):
                success, message_id = await send_post_to_channel(
                    mock_bot, data, photo_path=photo_path, retry_count=1
                )

                assert success is True
                assert message_id == 12345
                mock_bot.send_photo.assert_called_once()
        finally:
            if os.path.exists(photo_path):
                os.remove(photo_path)

    @pytest.mark.asyncio
    async def test_send_post_text_success(self):
        """Тест 32: Успешная отправка текстового поста"""
        mock_bot = MagicMock()
        mock_message = MagicMock()
        mock_message.message_id = 67890
        mock_bot.send_message = AsyncMock(return_value=mock_message)

        data = {
            "title": "Test Product",
            "price": "1000 ₽",
            "url": "https://market.yandex.ru/card/test/123456",
        }

        with patch(
            "services.post_service.generate_post_caption", return_value="Test caption"
        ):
            success, message_id = await send_post_to_channel(
                mock_bot, data, photo_path=None, retry_count=1
            )

            assert success is True
            assert message_id == 67890
            mock_bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_post_retry_success(self):
        """Тест 33: Первая попытка падает, вторая успешна"""
        mock_bot = MagicMock()
        mock_message = MagicMock()
        mock_message.message_id = 11111
        mock_bot.send_message = AsyncMock(
            side_effect=[Exception("First attempt failed"), mock_message]
        )

        data = {
            "title": "Test Product",
            "price": "1000 ₽",
            "url": "https://market.yandex.ru/card/test/123456",
        }

        with patch(
            "services.post_service.generate_post_caption", return_value="Test caption"
        ):
            success, message_id = await send_post_to_channel(
                mock_bot, data, photo_path=None, retry_count=3
            )

            assert success is True
            assert message_id == 11111
            assert mock_bot.send_message.call_count == 2

    @pytest.mark.asyncio
    async def test_send_post_all_retries_fail(self):
        """Тест 34: Все попытки отправки падают"""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock(side_effect=Exception("All attempts failed"))
        mock_bot.send_message_to_chat = AsyncMock()  # Для уведомления об ошибке

        data = {
            "title": "Test Product",
            "price": "1000 ₽",
            "url": "https://market.yandex.ru/card/test/123456",
        }

        with patch(
            "services.post_service.generate_post_caption", return_value="Test caption"
        ):
            success, message_id = await send_post_to_channel(
                mock_bot, data, photo_path=None, retry_count=2, chat_id=12345
            )

            assert success is False
            assert message_id is None
            assert mock_bot.send_message.call_count == 2
