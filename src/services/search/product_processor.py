# services/search/product_processor.py
"""
Product processing functionality for smart search service.
Handles product validation, deduplication, and queuing.
"""
import logging
from typing import Dict, List, Tuple

import src.config as config

logger = logging.getLogger(__name__)


class ProductProcessorMixin:
    """Mixin class for product processing functionality."""

    async def _validate_product_for_queue(self, product: Dict) -> Tuple[bool, List[str]]:
        """
        Валидировать товар перед добавлением в очередь

        Args:
            product: Данные товара

        Returns:
            Tuple[bool, List[str]]: (should_queue, reasons)
        """
        reasons = []

        # Проверяем обязательные поля
        if not product.get('title'):
            reasons.append("no_title")
            return False, reasons

        if not product.get('url'):
            reasons.append("no_url")
            return False, reasons

        # Проверяем качество товара
        rating = product.get('rating', 0)
        reviews = product.get('reviews_count', 0)
        price = product.get('price')

        # Фильтры качества
        min_price = getattr(config, 'QUALITY_MIN_PRICE', 0)
        min_rating = getattr(config, 'QUALITY_MIN_RATING', 0)
        min_reviews = getattr(config, 'QUALITY_MIN_REVIEWS', 0)

        if price and price < min_price:
            reasons.append(f"price_too_low_{price}")
            return False, reasons

        if rating < min_rating:
            reasons.append(f"rating_too_low_{rating}")
            return False, reasons

        if reviews < min_reviews:
            reasons.append(f"reviews_too_few_{reviews}")
            return False, reasons

        # Проверяем наличие изображений
        if not product.get('has_images', True):
            reasons.append("no_images")
            return False, reasons

        return True, []

    async def _enqueue_product(self, product: Dict, source_url: str):
        """
        Добавить товар в очередь публикации

        Args:
            product: Данные товара
            source_url: URL источника
        """
        try:
            # Валидируем товар
            should_queue, reasons = await self._validate_product_for_queue(product)

            if not should_queue:
                logger.debug(f"Product rejected: {product.get('title', 'Unknown')}, reasons: {reasons}")
                return

            # Добавляем метаданные
            product['source_url'] = source_url
            product['queued_at'] = __import__('time').time()
            product['validation_reasons'] = reasons

            # Отправляем в очередь
            await self._enqueue_for_publishing(product)

            logger.info(f"Product queued: {product.get('title', 'Unknown')}")

        except Exception as e:
            logger.error(f"Failed to enqueue product {product.get('title', 'Unknown')}: {e}")

    async def _save_product_to_database(self, product: Dict):
        """
        Сохранить товар в базу данных

        Args:
            product: Данные товара
        """
        try:
            if not self.db:
                logger.warning("Database not available, skipping save")
                return

            # Подготавливаем данные для сохранения
            db_product = {
                'market_id': product.get('id'),
                'title': product.get('title', ''),
                'description': product.get('description', ''),
                'price': product.get('price'),
                'url': product.get('url', ''),
                'vendor': product.get('vendor', ''),
                'rating': product.get('rating'),
                'reviews_count': product.get('reviews_count', 0),
                'image_url': product.get('image_url'),
                'specs': product.get('specs', {}),
                'category': product.get('category', ''),
                'source_url': product.get('source_url', ''),
                'raw_data': product
            }

            # Сохраняем в базу
            await self.db.save_product(db_product)

            logger.debug(f"Product saved to database: {product.get('title', 'Unknown')}")

        except Exception as e:
            logger.error(f"Failed to save product to database: {e}")
            raise

    async def _enqueue_for_publishing(self, product: Dict):
        """
        Добавить товар в очередь публикации

        Args:
            product: Данные товара
        """
        try:
            if not self.redis:
                logger.warning("Redis not available, skipping queue")
                return

            # Сериализуем продукт
            import json
            product_json = json.dumps(product, ensure_ascii=False, default=str)

            # Добавляем в очередь
            await self.redis.add_to_publish_queue(product_json)

            logger.debug(f"Product added to publish queue: {product.get('title', 'Unknown')}")

        except Exception as e:
            logger.error(f"Failed to enqueue product for publishing: {e}")
            raise

    def _generate_product_key(self, product: Dict) -> str:
        """
        Сгенерировать уникальный ключ для товара

        Args:
            product: Данные товара

        Returns:
            str: Уникальный ключ
        """
        # Используем market_id если есть, иначе комбинацию title + url
        market_id = product.get('id') or product.get('market_id')
        if market_id:
            return f"market_{market_id}"

        # Fallback: title + url hash
        title = product.get('title', '').strip()
        url = product.get('url', '').strip()

        import hashlib
        key_data = f"{title}|{url}".encode('utf-8')
        return hashlib.md5(key_data).hexdigest()[:16]
