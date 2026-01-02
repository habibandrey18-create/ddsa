"""
Integration тесты для process_and_publish
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Импортируем после добавления пути
import bot


class TestProcessAndPublish:
    """Тесты для process_and_publish"""

    @pytest.mark.asyncio
    async def test_process_and_publish_card_success(self):
        """Тест 23: Успешная публикация card-URL"""
        url = "https://market.yandex.ru/card/product/123456"
        mock_data = {
            "title": "Test Product",
            "price": "1000 ₽",
            "url": url,
            "image_bytes": None,
        }

        mock_bot = MagicMock()
        mock_message = MagicMock()
        mock_message.message_id = 12345
        mock_bot.send_message = AsyncMock(return_value=mock_message)

        with patch("bot.bot", mock_bot):
            with patch("bot.is_valid_yandex_market_url", return_value=True):
                with patch("bot.validate_product_url", return_value=(True, "")):
                    with patch("bot.db") as mock_db:
                        mock_db.is_blacklisted.return_value = False
                        mock_db.exists_url.return_value = False
                        mock_db.add_post_to_history = MagicMock()
                        mock_db.update_publishing_state = MagicMock()

                        with patch(
                            "bot.get_product_data", new_callable=AsyncMock
                        ) as mock_get_data:
                            mock_get_data.return_value = mock_data

                            with patch(
                                "bot.ensure_partner_link", new_callable=AsyncMock
                            ) as mock_partner:
                                from services.partner_link_service import (
                                    PartnerLinkInfo,
                                )

                                mock_partner.return_value = PartnerLinkInfo(
                                    ref_link=None,
                                    product_url=url,
                                    has_ref=False,
                                    source="none",
                                    flags=[],
                                )

                                with patch(
                                    "bot.validate_product_data", return_value=(True, "")
                                ):
                                    with patch(
                                        "bot.should_skip_product",
                                        return_value=(False, ""),
                                    ):
                                        with patch(
                                            "bot.send_post_to_channel",
                                            new_callable=AsyncMock,
                                        ) as mock_send:
                                            mock_send.return_value = (True, 12345)

                                            with patch(
                                                "bot.generate_post_caption",
                                                return_value="Test caption",
                                            ):
                                                success, message_id = (
                                                    await bot.process_and_publish(
                                                        url, chat_id=None, retry_count=1
                                                    )
                                                )

                                                assert success is True
                                                assert message_id == 12345

    @pytest.mark.asyncio
    async def test_process_and_publish_cc_success(self):
        """Тест 24: Успешная публикация cc-URL"""
        url = "https://market.yandex.ru/cc/ABC123"
        mock_data = {
            "title": "Test Product",
            "price": "1000 ₽",
            "url": url,
            "image_bytes": None,
        }
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()

        with patch("bot.bot", mock_bot):
            with patch("bot.is_valid_yandex_market_url", return_value=True):
                with patch("bot.validate_product_url", return_value=(True, "")):
                    with patch("bot.db") as mock_db:
                        mock_db.is_blacklisted.return_value = False
                        mock_db.exists_url.return_value = False
                        mock_db.add_post_to_history = MagicMock()

                        with patch(
                            "bot.get_product_data", new_callable=AsyncMock
                        ) as mock_get_data:
                            mock_get_data.return_value = mock_data

                            with patch(
                                "bot.ensure_partner_link", new_callable=AsyncMock
                            ) as mock_partner:
                                from services.partner_link_service import (
                                    PartnerLinkInfo,
                                )

                                mock_partner.return_value = PartnerLinkInfo(
                                    ref_link=url,
                                    product_url=url,
                                    has_ref=True,
                                    source="from_input",
                                    flags=["cc_url_direct"],
                                )

                                with patch(
                                    "bot.validate_product_data", return_value=(True, "")
                                ):
                                    with patch(
                                        "bot.should_skip_product",
                                        return_value=(False, ""),
                                    ):
                                        with patch(
                                            "bot.send_post_to_channel",
                                            new_callable=AsyncMock,
                                        ) as mock_send:
                                            mock_send.return_value = (True, 67890)

                                            with patch(
                                                "bot.generate_post_caption",
                                                return_value="Test caption",
                                            ):
                                                success, message_id = (
                                                    await bot.process_and_publish(
                                                        url, chat_id=None, retry_count=1
                                                    )
                                                )

                                                assert success is True
                                                assert message_id == 67890

    @pytest.mark.asyncio
    async def test_process_and_publish_card_scrape_fails(self):
        """Тест 25: Скрап card-URL падает после всех ретраев"""
        url = "https://market.yandex.ru/card/product/123456"
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()

        with patch("bot.bot", mock_bot):
            with patch("bot.is_valid_yandex_market_url", return_value=True):
                with patch("bot.validate_product_url", return_value=(True, "")):
                    with patch("bot.db") as mock_db:
                        mock_db.is_blacklisted.return_value = False
                        mock_db.exists_url.return_value = False

                        with patch(
                            "bot.get_product_data", new_callable=AsyncMock
                        ) as mock_get_data:
                            mock_get_data.return_value = None  # Скрап падает

                            success, message_id = await bot.process_and_publish(
                                url, chat_id=12345, retry_count=1
                            )

                            assert success is False
                            assert message_id is None
                            # Должно быть отправлено сообщение об ошибке
                            mock_bot.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_process_and_publish_cc_scrape_fails(self):
        """Тест 26: Скрап cc-URL падает, создаётся link-only пост"""
        url = "https://market.yandex.ru/cc/ABC123"
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()

        with patch("bot.bot", mock_bot):
            with patch("bot.is_valid_yandex_market_url", return_value=True):
                with patch("bot.validate_product_url", return_value=(True, "")):
                    with patch("bot.db") as mock_db:
                        mock_db.is_blacklisted.return_value = False
                        mock_db.exists_url.return_value = False
                        mock_db.add_post_to_history = MagicMock()

                        with patch(
                            "bot.get_product_data", new_callable=AsyncMock
                        ) as mock_get_data:
                            mock_get_data.return_value = None  # Скрап падает

                            with patch(
                                "bot.ensure_partner_link", new_callable=AsyncMock
                            ) as mock_partner:
                                from services.partner_link_service import (
                                    PartnerLinkInfo,
                                )

                                mock_partner.return_value = PartnerLinkInfo(
                                    ref_link=url,
                                    product_url=url,
                                    has_ref=True,
                                    source="from_input",
                                    flags=["cc_url_direct"],
                                )

                                with patch(
                                    "bot.validate_product_data", return_value=(True, "")
                                ):
                                    with patch(
                                        "bot.should_skip_product",
                                        return_value=(False, ""),
                                    ):
                                        with patch(
                                            "bot.send_post_to_channel",
                                            new_callable=AsyncMock,
                                        ) as mock_send:
                                            mock_send.return_value = (True, 99999)

                                            with patch(
                                                "bot.generate_post_caption",
                                                return_value="Test caption",
                                            ):
                                                success, message_id = (
                                                    await bot.process_and_publish(
                                                        url, chat_id=None, retry_count=1
                                                    )
                                                )

                                                # Должен создать link-only пост и успешно отправить
                                                assert success is True
                                                assert message_id == 99999

    @pytest.mark.asyncio
    async def test_process_and_publish_invalid_url(self):
        """Тест 27: Передан невалидный URL"""
        url = "https://invalid-url.com"
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()

        with patch("bot.bot", mock_bot):
            with patch("bot.is_valid_yandex_market_url", return_value=False):
                success, message_id = await bot.process_and_publish(
                    url, chat_id=12345, retry_count=1
                )

                assert success is False
                assert message_id is None
                mock_bot.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_process_and_publish_blacklisted(self):
        """Тест 28: URL в чёрном списке"""
        url = "https://market.yandex.ru/card/product/123456"
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()

        with patch("bot.bot", mock_bot):
            with patch("bot.is_valid_yandex_market_url", return_value=True):
                with patch("bot.validate_product_url", return_value=(True, "")):
                    with patch("bot.db") as mock_db:
                        mock_db.is_blacklisted.return_value = True

                        success, message_id = await bot.process_and_publish(
                            url, chat_id=12345, retry_count=1
                        )

                        assert success is False
                        assert message_id is None
                        mock_bot.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_process_and_publish_duplicate(self):
        """Тест 29: URL уже опубликован"""
        url = "https://market.yandex.ru/card/product/123456"
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()

        with patch("bot.bot", mock_bot):
            with patch("bot.is_valid_yandex_market_url", return_value=True):
                with patch("bot.validate_product_url", return_value=(True, "")):
                    with patch("bot.db") as mock_db:
                        mock_db.is_blacklisted.return_value = False
                        mock_db.exists_url.return_value = True  # Уже опубликован

                        success, message_id = await bot.process_and_publish(
                            url, chat_id=12345, retry_count=1
                        )

                        assert success is False
                        assert message_id is None
                        mock_bot.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_process_and_publish_validation_fails(self):
        """Тест 30: Данные не прошли валидацию"""
        url = "https://market.yandex.ru/card/product/123456"
        mock_data = {
            "title": "",  # Пустой title - не пройдёт валидацию
            "price": "",
            "url": url,
        }
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()

        with patch("bot.bot", mock_bot):
            with patch("bot.is_valid_yandex_market_url", return_value=True):
                with patch("bot.validate_product_url", return_value=(True, "")):
                    with patch("bot.db") as mock_db:
                        mock_db.is_blacklisted.return_value = False
                        mock_db.exists_url.return_value = False

                        with patch(
                            "bot.get_product_data", new_callable=AsyncMock
                        ) as mock_get_data:
                            mock_get_data.return_value = mock_data

                            with patch(
                                "bot.ensure_partner_link", new_callable=AsyncMock
                            ) as mock_partner:
                                from services.partner_link_service import (
                                    PartnerLinkInfo,
                                )

                                mock_partner.return_value = PartnerLinkInfo(
                                    ref_link=None,
                                    product_url=url,
                                    has_ref=False,
                                    source="none",
                                    flags=[],
                                )

                                with patch(
                                    "bot.validate_product_data",
                                    return_value=(False, "Нет названия товара"),
                                ):
                                    success, message_id = await bot.process_and_publish(
                                        url, chat_id=12345, retry_count=1
                                    )

                                    assert success is False
                                    assert message_id is None
                                    mock_bot.send_message.assert_called()
