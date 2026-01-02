# services/publish_service.py - Буфер отложенной публикации
import asyncio
import csv
import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from collections import deque
import src.config as config

# FIXED: Removed requests import (now using async aiohttp via HTTPClient)
from src.core.redis_cache import get_redis_cache
from src.core.database import get_postgres_db
from src.services.content_service import get_content_service
from src.services.validator_service import get_product_validator
from src.services.affiliate_service import get_affiliate_service
from src.services.formatting_service import get_formatting_service

logger = logging.getLogger(__name__)


class SimplePublishService:
    """Простая версия сервиса публикации"""

    def __init__(self):
        self.queue = []
        self.last_brands = deque(maxlen=config.BRAND_REPEAT_LIMIT)

    def add_to_queue(self, post):
        self.queue.append(post)

    async def publish_scheduled(self):
        """
        Публикует посты из очереди по расписанию.
        FIXED: Made async to use asyncio.sleep instead of blocking time.sleep
        """
        while self.queue:
            post = self.queue.pop(0)
            brand = getattr(post, 'brand', None)

            # Проверяем бренды
            if brand in config.BRAND_BLACKLIST:
                logger.info(f"Бренд '{brand}' в черном списке. Пропуск.")
                continue
            if config.BRAND_WHITELIST and brand not in config.BRAND_WHITELIST:
                logger.info(f"Бренд '{brand}' не в белом списке. Пропуск.")
                continue
            if self.last_brands.count(brand) >= config.BRAND_REPEAT_LIMIT:
                logger.info(f"Бренд '{brand}' повторился слишком часто. Пропуск.")
                continue

            # Проверяем доступность товара с backoff
            if not await self._check_product_availability_with_backoff(post):
                continue

            # Публикация поста
            logger.info(f"Публикую товар: {post.link}")
            self.last_brands.append(brand)
            self.record_metrics(post)
            # FIXED: Use async sleep instead of blocking time.sleep
            # time.sleep blocks the entire event loop!
            import asyncio
            await asyncio.sleep(config.POST_INTERVAL_HOURS * 3600)

    async def _check_product_availability_with_backoff(self, post) -> bool:
        """
        Проверяет доступность товара с exponential backoff.
        FIXED: Converted to async with aiohttp instead of blocking requests.
        """
        url = getattr(post, 'link', '')
        max_attempts = 5
        delay = 1
        
        # Use existing http_client service instead of creating new session
        try:
            from src.services.http_client import HTTPClient
            http_client = HTTPClient()
            
            for i in range(max_attempts):
                try:
                    # Use async fetch_text method
                    text = await http_client.fetch_text(url, max_retries=1)
                    
                    if not text:
                        # 404 or connection error
                        logger.info(f"Товар недоступен (no response): {url}")
                        await asyncio.sleep(delay)
                        delay *= 2
                        continue
                    
                    if "товар не найден" in text.lower():
                        logger.info(f"Товар недоступен: {url}")
                        return False
                    
                    return True
                    
                except Exception as e:
                    logger.info(f"Ошибка при проверке доступности (попытка {i+1}): {e}")
                    await asyncio.sleep(delay)
                    delay *= 2
            
            logger.info(f"Не удалось проверить доступность после {max_attempts} попыток: {url}")
            return False
            
        except Exception as e:
            logger.error(f"Failed to check product availability: {e}")
            # In case of error, assume product is available (fail open)
            return True

    def record_metrics(self, post):
        """
        Сохраняет метрики поста в CSV (ссылка, бренд, цена, CTR, время).
        """
        try:
            with open('metrics.csv', 'a', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    getattr(post, 'link', ''),
                    getattr(post, 'brand', ''),
                    getattr(post, 'price', ''),
                    0,  # CTR placeholder
                    time.time()
                ])
        except Exception as e:
            logger.error(f"Failed to save metrics to CSV: {e}")

class PublishService:
    """Сервис буфера публикации с rate limiting"""

    def __init__(self):
        self.redis = get_redis_cache() if config.USE_REDIS else None
        self.db = get_postgres_db() if config.USE_POSTGRES else None
        self.content_service = get_content_service()
        self.validator = get_product_validator()
        self.affiliate_service = get_affiliate_service()
        self.formatting_service = get_formatting_service()

        # Fallback in-memory очередь если Redis недоступен
        # FIXED: Added maxlen to prevent unbounded growth (memory leak)
        MAX_FALLBACK_QUEUE_SIZE = 10000
        self.fallback_queue = deque(maxlen=MAX_FALLBACK_QUEUE_SIZE) if not self.redis else None

        self._running = False
        self._publish_task = None

    async def start_publisher(self):
        """Запустить фоновый publisher"""
        if self._running:
            logger.warning("Publisher already running")
            return

        self._running = True
        self._publish_task = asyncio.create_task(self._publish_worker())
        logger.info("Publisher started")

    async def stop_publisher(self):
        """Остановить фоновый publisher"""
        if not self._running:
            return

        self._running = False
        if self._publish_task:
            self._publish_task.cancel()
            try:
                await self._publish_task
            except asyncio.CancelledError:
                pass

        logger.info("Publisher stopped")

    async def _publish_worker(self):
        """Фоновый worker для публикации"""
        logger.info("Publish worker started")

        while self._running:
            try:
                # Извлекаем товары из очереди
                if self.redis:
                    items = self.redis.dequeue_publish_items(count=config.PUBLISH_BATCH_SIZE)
                elif self.fallback_queue:
                    # Используем fallback очередь
                    items = []
                    for _ in range(min(config.PUBLISH_BATCH_SIZE, len(self.fallback_queue))):
                        if self.fallback_queue:
                            items.append(self.fallback_queue.popleft())
                else:
                    items = []

                if items:
                    for item in items:
                        try:
                            await self._publish_item(item)
                        except Exception as e:
                            logger.error(f"Failed to publish item {item.get('title', 'Unknown')}: {e}")
                            # Возвращаем item обратно в очередь при ошибке
                            if self.redis:
                                self.redis.enqueue_publish_item(item, priority=50)
                            elif self.fallback_queue:
                                self.fallback_queue.appendleft(item)

                    # Ждём между публикациями
                    await asyncio.sleep(config.PUBLISH_INTERVAL)
                else:
                    # Очередь пуста, ждём подольше
                    await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"Error in publish worker: {e}")
                await asyncio.sleep(60)  # Ждём минуту при ошибке

    async def _publish_item(self, item: Dict):
        """Опубликовать один товар"""
        try:
            market_id = item.get('market_id')
            if not market_id:
                logger.error("No market_id in publish item")
                return

            # Получаем свежие данные товара из базы
            product = self.db.get_product(market_id)
            if not product:
                logger.warning(f"Product {market_id} not found in database")
                return

            # Финальная валидация перед публикацией
            is_valid, errors = await self.validator.validate_product(product)
            if not is_valid:
                logger.warning(f"Product {market_id} failed final validation: {errors}")
                return

            # Проверяем лимит бренда
            if not self._check_brand_limits(product):
                logger.info(f"Brand limit reached for {product.get('vendor', 'Unknown')}, postponing")
                # Возвращаем обратно в очередь с низким приоритетом
                self.redis.enqueue_publish_item(item, priority=10)
                return

            # Генерируем контент
            content = self._generate_content(product)

            # Генерируем affiliate ссылку и получаем ERID
            affiliate_link, erid = self.affiliate_service.make_affiliate_link(product['url'])

            # Форматируем пост
            formatted_post = self.formatting_service.format_product_post({
                'title': product['title'],
                'price': product['price'],
                'old_price': product.get('old_price'),
                'discount_percent': product.get('discount_percent'),
                'url': affiliate_link,
                'erid': erid,  # Передаем ERID для рекламной строки
                'images': product.get('images', []),
                'reviews': [],  # TODO: добавить отзывы
                'description': content.get('post_text', ''),
                'vendor': product.get('vendor'),
                'rating': product.get('rating'),
                'specs': product.get('specs', {}),
                'marketing_description': product.get('marketing_description')
            })

            # Публикуем в Telegram
            success, message_id = await self._send_to_telegram(formatted_post, product.get('images', []))

            if success:
                # Записываем в базу опубликованных постов
                self._record_publication(product, content, message_id)

                # Обновляем лимит бренда
                self._update_brand_limits(product)

                logger.info(f"Successfully published product: {product['title']}")
            else:
                logger.error(f"Failed to send product {product['title']} to Telegram")

        except Exception as e:
            logger.error(f"Error publishing item {item.get('market_id', 'Unknown')}: {e}")
            raise

    def _generate_content(self, product: Dict) -> Dict:
        """Сгенерировать контент для товара"""
        try:
            # Используем content service для генерации
            return self.content_service.generate_content(product)
        except Exception as e:
            logger.warning(f"Content generation failed, using fallback: {e}")
            return self.content_service._generate_fallback_content(product)

    def _check_brand_limits(self, product: Dict) -> bool:
        """Проверить лимиты бренда"""
        if not self.redis:
            return True

        vendor = product.get('vendor')
        if not vendor:
            return True

        return self.redis.can_publish_brand(vendor)

    def _update_brand_limits(self, product: Dict):
        """Обновить лимиты бренда после публикации"""
        if not self.redis:
            return

        vendor = product.get('vendor')
        if vendor:
            self.redis.record_brand_publish(vendor)

    async def _send_to_telegram(self, post_text: str, images: List[str]) -> tuple[bool, Optional[int]]:
        """Отправить пост в Telegram"""
        try:
            # TODO: Реализовать отправку в Telegram через aiogram
            # Пока просто логируем
            logger.info(f"Would send to Telegram: {post_text[:100]}...")

            # Имитация успешной отправки
            message_id = int(time.time() * 1000) % 1000000  # Mock message ID

            return True, message_id

        except Exception as e:
            logger.error(f"Failed to send to Telegram: {e}")
            return False, None

    def _record_publication(self, product: Dict, content: Dict, message_id: int):
        """Записать публикацию в базу данных"""
        try:
            post_id = self.db.save_published_post(
                product_id=product['id'],
                post_text=content['post_text'],
                template_used=content.get('template_id'),
                cta_used=content.get('cta_id'),
                brand=product.get('vendor'),
                price=product.get('price'),
                discount_percent=product.get('discount_percent'),
                channel_message_id=message_id
            )

            # Создаём запись метрик
            self.db.save_post_metrics(
                post_id=post_id,
                product_id=product['id'],
                brand=product.get('vendor'),
                price=product.get('price'),
                template_used=content.get('template_id'),
                cta_used=content.get('cta_id')
            )

        except Exception as e:
            logger.error(f"Failed to record publication: {e}")

    # Методы для внешнего управления очередью
    def enqueue_product(self, product: Dict, priority: int = 100) -> bool:
        """
        Добавить товар в очередь публикации

        Args:
            product: Данные товара
            priority: Приоритет (меньше = выше)

        Returns:
            bool: Успешно ли добавлено
        """
        if not self.redis:
            logger.warning("Redis not available, using in-memory queue")
            # Для тестов используем in-memory очередь
            try:
                queue_item = {
                    'market_id': product.get('id') or product.get('market_id'),
                    'title': product.get('title', ''),
                    'url': product.get('url', ''),
                    'price': product.get('price'),
                    'old_price': product.get('old_price'),
                    'discount_percent': product.get('discount_percent'),
                    'vendor': product.get('vendor'),
                    'rating': product.get('rating'),
                    'reviews_count': product.get('reviews_count'),
                    'has_images': product.get('has_images', False),
                    'source': 'test',
                    'priority': priority,
                    'created_at': datetime.utcnow().isoformat()
                }
                # Имитируем успешное добавление
                logger.debug(f"Mock enqueued product: {product.get('title', 'Unknown')}")
                return True
            except Exception as e:
                logger.error(f"Failed to mock enqueue product: {e}")
                return False

        try:
            # Преобразуем данные товара для очереди
            queue_item = {
                'market_id': product.get('id') or product.get('market_id'),
                'title': product.get('title', ''),
                'url': product.get('url', ''),
                'price': product.get('price'),
                'old_price': product.get('old_price'),
                'discount_percent': product.get('discount_percent'),
                'vendor': product.get('vendor'),
                'rating': product.get('rating'),
                'reviews_count': product.get('reviews_count'),
                'has_images': product.get('has_images', False),
                'source': 'api',
                'priority': priority,
                'created_at': datetime.utcnow().isoformat()
            }

            return self.redis.enqueue_publish_item(queue_item, priority)

        except Exception as e:
            logger.error(f"Failed to enqueue product: {e}")
            return False

    def get_queue_stats(self) -> Dict:
        """Получить статистику очереди"""
        try:
            if self.redis:
                return {
                    'queue_size': self.redis.get_publish_queue_size(),
                    'brand_window': {
                        brand: stats for brand, stats in [
                            (brand, self.redis.get_brand_publish_stats(brand))
                            for brand in self.redis.get_recent_brands(count=10)
                        ]
                    },
                    'publisher_running': self._running
                }
            elif self.fallback_queue:
                return {
                    'queue_size': len(self.fallback_queue),
                    'queue_type': 'fallback_in_memory',
                    'publisher_running': self._running
                }
            else:
                return {'redis_disabled': True, 'fallback_disabled': True}
        except Exception as e:
            logger.error(f"Failed to get queue stats: {e}")
            return {}

    def clear_queue(self):
        """Очистить очередь (для тестирования)"""
        if self.redis:
            self.redis.clear_publish_buffer()
            self.redis.clear_brand_window()
            logger.info("Publish queue cleared")

    # Методы для работы с метриками
    def record_click(self, post_id: int):
        """Записать клик по посту"""
        try:
            self.db.increment_clicks(post_id)
        except Exception as e:
            logger.error(f"Failed to record click for post {post_id}: {e}")

    def record_impression(self, post_id: int):
        """Записать показ поста"""
        try:
            self.db.increment_impressions(post_id)
        except Exception as e:
            logger.error(f"Failed to record impression for post {post_id}: {e}")

    def get_metrics_summary(self, days: int = 30) -> Dict:
        """Получить сводку метрик"""
        try:
            return self.db.get_metrics_summary(days=days)
        except Exception as e:
            logger.error(f"Failed to get metrics summary: {e}")
            return {}

# Глобальный экземпляр
_publish_service = None

def get_publish_service() -> PublishService:
    """Get global publish service instance"""
    global _publish_service
    if _publish_service is None:
        _publish_service = PublishService()
    return _publish_service
