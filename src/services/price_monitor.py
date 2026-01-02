# services/price_monitor.py
"""Сервис для мониторинга падения цен на товары"""
import asyncio
import logging
import re
from typing import List, Dict, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

from src.utils.scraper import scrape_yandex_market


def extract_price_number(price_str: str) -> Optional[float]:
    """
    Извлекает числовое значение цены из строки.

    Args:
        price_str: Строка с ценой (например, "3 166 ₽" или "Цена уточняется")

    Returns:
        Числовое значение цены или None если не удалось извлечь
    """
    if not price_str or price_str == "Цена уточняется":
        return None

    # Убираем все символы кроме цифр, точек и запятых
    cleaned = re.sub(r"[^\d.,]", "", price_str.replace("\u00a0", " "))
    cleaned = cleaned.replace(" ", "").replace(",", ".")

    try:
        price_num = float(cleaned)
        return price_num if price_num > 0 else None
    except (ValueError, TypeError):
        return None


class PriceMonitorService:
    """Сервис для мониторинга падения цен"""

    def __init__(self, db):
        """
        Инициализация сервиса мониторинга цен.

        Args:
            db: Экземпляр Database
        """
        self.db = db
        self.price_drop_threshold = 0.15  # 15% падение цены

    async def check_price_drops(self, limit: int = 50) -> List[Dict[str, any]]:
        """
        Проверяет последние товары из истории на падение цены.

        Args:
            limit: Количество товаров для проверки (по умолчанию 50)

        Returns:
            Список товаров с упавшей ценой, готовых к повторной публикации
        """
        logger.info(f"🔍 Начинаем проверку цен для {limit} товаров...")

        # Получаем последние товары из истории
        with self.db.connection:
            rows = self.db.cursor.execute(
                """
                SELECT id, url, title, last_price 
                FROM history 
                ORDER BY date_added DESC 
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        if not rows:
            logger.info("📭 История пуста, нечего проверять")
            return []

        price_drops = []
        checked_count = 0
        error_count = 0

        for row in rows:
            url = row["url"]
            history_id = row["id"]
            title = row.get("title", "")
            old_price = row.get("last_price")

            # Пропускаем если нет старой цены (товар еще не проверялся)
            if old_price is None:
                logger.debug(f"⏭ Пропускаем {url[:80]}... (нет старой цены)")
                continue

            try:
                # Мягкая задержка: 1 товар в 10 секунд
                if checked_count > 0:
                    await asyncio.sleep(10)

                # Скрапим текущую цену
                logger.debug(f"🔍 Проверяем цену для {url[:80]}...")
                product_data = await scrape_yandex_market(url)

                if not product_data:
                    logger.warning(f"⚠️ Не удалось получить данные для {url[:80]}...")
                    error_count += 1
                    continue

                current_price_str = product_data.get("price", "")
                current_price = extract_price_number(current_price_str)

                if current_price is None:
                    logger.debug(
                        f"⏭ Не удалось извлечь цену для {url[:80]}... (цена: {current_price_str})"
                    )
                    checked_count += 1
                    # Обновляем last_price даже если не удалось извлечь (чтобы не проверять снова)
                    self._update_last_price(history_id, old_price)
                    continue

                checked_count += 1

                # Проверяем падение цены (>15%)
                price_drop_ratio = (old_price - current_price) / old_price

                if price_drop_ratio >= self.price_drop_threshold:
                    # Значительное падение цены!
                    logger.info(
                        f"📉 Обнаружено падение цены для {url[:80]}...: "
                        f"{old_price:.2f} ₽ → {current_price:.2f} ₽ "
                        f"({price_drop_ratio*100:.1f}% падение)"
                    )

                    price_drops.append(
                        {
                            "url": url,
                            "title": title or product_data.get("title", "Товар"),
                            "old_price": old_price,
                            "current_price": current_price,
                            "price_drop_percent": price_drop_ratio * 100,
                            "history_id": history_id,
                        }
                    )

                # Обновляем last_price в БД
                self._update_last_price(history_id, current_price)

            except Exception as e:
                logger.exception(f"❌ Ошибка при проверке цены для {url[:80]}...: {e}")
                error_count += 1
                continue

        logger.info(
            f"✅ Проверка завершена: проверено {checked_count}, "
            f"найдено падений {len(price_drops)}, ошибок {error_count}"
        )

        return price_drops

    def _update_last_price(self, history_id: int, price: float) -> None:
        """
        Обновляет last_price в истории.

        Args:
            history_id: ID записи в истории
            price: Новая цена
        """
        try:
            with self.db.connection:
                self.db.cursor.execute(
                    "UPDATE history SET last_price = ? WHERE id = ?",
                    (price, history_id),
                )
        except Exception as e:
            logger.warning(
                f"⚠️ Ошибка обновления last_price для history_id={history_id}: {e}"
            )

    async def process_price_drops(self, price_drops: List[Dict[str, any]]) -> int:
        """
        Обрабатывает найденные падения цен: добавляет товары в очередь с тегом.

        Args:
            price_drops: Список товаров с упавшей ценой

        Returns:
            Количество товаров, добавленных в очередь
        """
        if not price_drops:
            return 0

        added_count = 0

        for drop in price_drops:
            url = drop["url"]
            title = drop["title"]
            old_price = drop["old_price"]
            current_price = drop["current_price"]
            drop_percent = drop["price_drop_percent"]

            # Проверяем, не добавлен ли уже в очередь
            if self.db.exists_url_in_queue(url, check_normalized=True):
                logger.debug(f"⏭ Товар {url[:80]}... уже в очереди, пропускаем")
                continue

            # Добавляем в очередь с высоким приоритетом
            queue_id = self.db.add_to_queue(
                url, priority=10
            )  # Высокий приоритет для падений цен

            if queue_id:
                added_count += 1
                # Store price drop info for later use in caption generation
                # Import here to avoid circular dependency
                try:
                    import bot

                    bot.store_price_drop_info(
                        url,
                        {
                            "old_price": old_price,
                            "current_price": current_price,
                            "price_drop_percent": drop_percent,
                        },
                    )
                except ImportError:
                    logger.warning(
                        "⚠️ Could not import bot module to store price drop info"
                    )

                logger.info(
                    f"✅ Добавлен в очередь (приоритет 10): {title[:50]}... "
                    f"({old_price:.0f} ₽ → {current_price:.0f} ₽, -{drop_percent:.1f}%)"
                )
            else:
                logger.warning(f"⚠️ Не удалось добавить в очередь: {url[:80]}...")

        return added_count


async def check_price_drops(db, limit: int = 50) -> List[Dict[str, any]]:
    """
    Удобная функция для проверки падения цен.

    Args:
        db: Экземпляр Database
        limit: Количество товаров для проверки

    Returns:
        Список товаров с упавшей ценой
    """
    monitor = PriceMonitorService(db)
    return await monitor.check_price_drops(limit=limit)
