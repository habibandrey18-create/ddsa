"""Service for cleaning sold-out products from Telegram channel"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import re

logger = logging.getLogger(__name__)


class CleanerService:
    """Service to check and clean sold-out products from channel"""

    def __init__(self, db, bot, http_client=None):
        self.db = db
        self.bot = bot
        self.http_client = http_client

        # Import HTTP client if not provided
        if not http_client:
            try:
                from src.services.http_client import HTTPClient

                self.http_client = HTTPClient()
            except ImportError:
                logger.warning(
                    "HTTPClient not available, cleaner will use basic checks"
                )

    async def check_if_sold_out(self, url: str) -> bool:
        """
        Проверяет, распродан ли товар по URL.

        Args:
            url: URL товара на Яндекс.Маркете

        Returns:
            True если товар распродан, False если в наличии
        """
        try:
            if not self.http_client:
                logger.warning("HTTPClient not available, cannot check sold out status")
                return False

            # Fetch page
            html = await self.http_client.fetch_text(url)
            if not html:
                logger.warning(f"Could not fetch URL for sold-out check: {url[:100]}")
                return False

            # Check for sold-out indicators (case-insensitive)
            sold_out_patterns = [
                r"нет в наличии",
                r"распродано",
                r"товар закончился",
                r"out of stock",
                r"нет на складе",
                r"временно недоступен",
                r"снят с продажи",
                r"закончился",
                r"нет в продаже",
                r"недоступен для заказа",
                r"status.*unavailable",
                r"availability.*false",
            ]

            html_lower = html.lower()

            for pattern in sold_out_patterns:
                if re.search(pattern, html_lower, re.IGNORECASE):
                    logger.info(f"Found sold-out indicator '{pattern}' for {url[:100]}")
                    return True

            # Additional check: look for "buy" button or availability status
            # If page has "Купить" button - товар в наличии
            if re.search(r"купить|добавить в корзину|в корзину", html_lower):
                return False

            # If no clear indicators, assume available
            return False

        except Exception as e:
            logger.exception(f"Error checking sold-out status for {url[:100]}: {e}")
            return False  # On error, assume available (don't delete)

    async def clean_sold_out_posts(
        self, hours: int = 48, delete_messages: bool = True, edit_caption: bool = False
    ) -> Dict[str, int]:
        """
        Проверяет и очищает распроданные товары из канала.

        Args:
            hours: Проверять посты за последние N часов
            delete_messages: Если True - удаляет сообщения, если False - редактирует
            edit_caption: Если True - редактирует caption добавляя "❌ SOLD OUT"

        Returns:
            Словарь со статистикой: {"checked": N, "sold_out": M, "deleted": K, "edited": L, "errors": E}
        """
        stats = {"checked": 0, "sold_out": 0, "deleted": 0, "edited": 0, "errors": 0}

        try:
            # Get recent posts with message_id
            posts = self.db.get_recent_posts_with_messages(hours=hours)

            logger.info(f"Checking {len(posts)} posts for sold-out status...")

            for post in posts:
                stats["checked"] += 1

                url = post["url"]
                message_id = post["message_id"]
                channel_id = post["channel_id"]
                title = post.get("title", "")

                # Check if sold out
                is_sold_out = await self.check_if_sold_out(url)

                if not is_sold_out:
                    continue

                stats["sold_out"] += 1
                logger.info(f"Found sold-out product: {title[:50]} ({url[:100]})")

                # Handle sold-out post
                try:
                    if delete_messages:
                        # Delete message
                        await self.bot.delete_message(
                            chat_id=channel_id, message_id=message_id
                        )
                        stats["deleted"] += 1
                        logger.info(
                            f"Deleted message {message_id} from channel {channel_id}"
                        )

                    elif edit_caption:
                        # Edit message caption
                        try:
                            # Get current message to preserve caption
                            message = await self.bot.get_chat(chat_id=channel_id)
                            # Try to get message (this might not work for channels)
                            # Fallback: just edit caption
                            new_caption = f"{title}\n\n❌ <b>РАСПРОДАНО</b>"

                            await self.bot.edit_message_caption(
                                chat_id=channel_id,
                                message_id=message_id,
                                caption=new_caption,
                                parse_mode="HTML",
                            )
                            stats["edited"] += 1
                            logger.info(
                                f"Edited message {message_id} in channel {channel_id}"
                            )
                        except Exception as edit_error:
                            # If edit fails, try delete as fallback
                            logger.warning(f"Edit failed, trying delete: {edit_error}")
                            try:
                                await self.bot.delete_message(
                                    chat_id=channel_id, message_id=message_id
                                )
                                stats["deleted"] += 1
                            except:
                                raise edit_error

                    # Small delay to avoid rate limiting
                    await asyncio.sleep(0.5)

                except Exception as e:
                    error_msg = str(e)

                    # Handle "Message not found" gracefully
                    if (
                        "message not found" in error_msg.lower()
                        or "message to delete not found" in error_msg.lower()
                    ):
                        logger.debug(
                            f"Message {message_id} already deleted (not found)"
                        )
                        # This is OK - admin might have deleted it manually
                        continue

                    stats["errors"] += 1
                    logger.warning(
                        f"Error handling sold-out post {message_id}: {error_msg[:200]}"
                    )

            logger.info(f"Sold-out cleaner completed: {stats}")
            return stats

        except Exception as e:
            logger.exception(f"Error in clean_sold_out_posts: {e}")
            return stats

    async def run_periodic_cleanup(
        self,
        interval_hours: int = 6,
        check_hours: int = 48,
        delete_messages: bool = True,
    ):
        """
        Запускает периодическую очистку распроданных товаров.

        Args:
            interval_hours: Интервал между проверками (в часах)
            check_hours: Проверять посты за последние N часов
            delete_messages: Удалять или редактировать сообщения
        """
        logger.info(f"Sold-out cleaner started: checking every {interval_hours} hours")

        while True:
            try:
                await asyncio.sleep(interval_hours * 3600)  # Convert to seconds

                logger.info("Running periodic sold-out cleanup...")
                stats = await self.clean_sold_out_posts(
                    hours=check_hours,
                    delete_messages=delete_messages,
                    edit_caption=not delete_messages,
                )

                logger.info(f"Cleanup stats: {stats}")

            except Exception as e:
                logger.exception(f"Error in periodic cleanup: {e}")
                await asyncio.sleep(3600)  # Wait 1 hour before retry













