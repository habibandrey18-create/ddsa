# redis_cache.py - Redis implementation for queues and cache
import json
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
import redis
import src.config as config

logger = logging.getLogger(__name__)

class RedisCache:
    """Redis cache and queue implementation"""

    def __init__(self):
        if not config.USE_REDIS:
            raise ValueError("Redis is not enabled in config")

        self.client = redis.Redis(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            db=config.REDIS_DB,
            password=config.REDIS_PASSWORD,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True
        )

        # Test connection
        try:
            self.client.ping()
            logger.info("Redis connection established")
        except redis.ConnectionError as e:
            logger.error(f"Redis connection failed: {e}")
            raise

    # Методы для буфера публикации
    def enqueue_publish_item(self, item: Dict, priority: int = 100) -> bool:
        """Добавить товар в очередь публикации с приоритетом"""
        try:
            # Используем timestamp с приоритетом для сортировки
            # Чем меньше score, тем выше приоритет
            score = time.time() - priority
            item_json = json.dumps(item, ensure_ascii=False)
            self.client.zadd("publish_buffer", {item_json: score})
            logger.debug(f"Enqueued item for publishing: {item.get('title', 'Unknown')}")
            return True
        except Exception as e:
            logger.error(f"Failed to enqueue publish item: {e}")
            return False

    def dequeue_publish_items(self, count: int = 1) -> List[Dict]:
        """Извлечь товары из очереди публикации"""
        try:
            # Получаем items с наименьшими score (высший приоритет)
            items_with_scores = self.client.zrangebyscore(
                "publish_buffer",
                "-inf",
                "+inf",
                start=0,
                num=count,
                withscores=True
            )

            items = []
            for item_json, score in items_with_scores:
                try:
                    item = json.loads(item_json)
                    items.append(item)
                    # Удаляем из очереди
                    self.client.zrem("publish_buffer", item_json)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode publish item: {e}")
                    # Удаляем поврежденный item
                    self.client.zrem("publish_buffer", item_json)

            if items:
                logger.debug(f"Dequeued {len(items)} items for publishing")

            return items
        except Exception as e:
            logger.error(f"Failed to dequeue publish items: {e}")
            return []

    def get_publish_queue_size(self) -> int:
        """Получить размер очереди публикации"""
        try:
            return self.client.zcard("publish_buffer")
        except Exception as e:
            logger.error(f"Failed to get publish queue size: {e}")
            return 0

    def peek_publish_queue(self, count: int = 5) -> List[Dict]:
        """Посмотреть на следующие items в очереди без извлечения"""
        try:
            items_with_scores = self.client.zrangebyscore(
                "publish_buffer",
                "-inf",
                "+inf",
                start=0,
                num=count,
                withscores=True
            )

            items = []
            for item_json, score in items_with_scores:
                try:
                    item = json.loads(item_json)
                    item['_priority_score'] = score
                    items.append(item)
                except json.JSONDecodeError:
                    pass

            return items
        except Exception as e:
            logger.error(f"Failed to peek publish queue: {e}")
            return []

    # Методы для sliding window брендов
    def can_publish_brand(self, brand: str, window_size: int = None, max_per_window: int = None) -> bool:
        """Проверить, можно ли публиковать бренд (sliding window)"""
        if window_size is None:
            window_size = config.BRAND_WINDOW_SIZE
        if max_per_window is None:
            max_per_window = config.BRAND_MAX_PER_WINDOW

        try:
            recent_brands = self.client.lrange("recent:brands", 0, window_size - 1)
            brand_count = recent_brands.count(brand)
            return brand_count < max_per_window
        except Exception as e:
            logger.error(f"Failed to check brand publish limit: {e}")
            return True  # В случае ошибки разрешаем публикацию

    def record_brand_publish(self, brand: str, window_size: int = None):
        """Записать публикацию бренда в sliding window"""
        if window_size is None:
            window_size = config.BRAND_WINDOW_SIZE

        try:
            # Добавляем в начало списка
            self.client.lpush("recent:brands", brand)
            # Ограничиваем размер списка
            self.client.ltrim("recent:brands", 0, window_size - 1)
            logger.debug(f"Recorded brand publish: {brand}")
        except Exception as e:
            logger.error(f"Failed to record brand publish: {e}")

    def get_recent_brands(self, count: int = 20) -> List[str]:
        """Получить недавние опубликованные бренды"""
        try:
            return self.client.lrange("recent:brands", 0, count - 1)
        except Exception as e:
            logger.error(f"Failed to get recent brands: {e}")
            return []

    def get_brand_publish_stats(self, brand: str, window_size: int = None) -> Dict:
        """Получить статистику публикаций бренда"""
        if window_size is None:
            window_size = config.BRAND_WINDOW_SIZE

        try:
            recent_brands = self.client.lrange("recent:brands", 0, window_size - 1)
            brand_count = recent_brands.count(brand)
            total_count = len(recent_brands)

            return {
                'brand': brand,
                'count_in_window': brand_count,
                'window_size': window_size,
                'max_allowed': config.BRAND_MAX_PER_WINDOW,
                'can_publish': brand_count < config.BRAND_MAX_PER_WINDOW
            }
        except Exception as e:
            logger.error(f"Failed to get brand publish stats: {e}")
            return {
                'brand': brand,
                'count_in_window': 0,
                'window_size': window_size or config.BRAND_WINDOW_SIZE,
                'max_allowed': config.BRAND_MAX_PER_WINDOW,
                'can_publish': True
            }

    # Методы для кэша товаров
    def cache_product(self, product_id: str, product_data: Dict, ttl_seconds: int = 3600):
        """Кэшировать данные товара"""
        try:
            key = f"product:{product_id}"
            data_json = json.dumps(product_data, ensure_ascii=False)
            self.client.setex(key, ttl_seconds, data_json)
            logger.debug(f"Cached product: {product_id}")
        except Exception as e:
            logger.error(f"Failed to cache product {product_id}: {e}")

    def get_cached_product(self, product_id: str) -> Optional[Dict]:
        """Получить кэшированные данные товара"""
        try:
            key = f"product:{product_id}"
            data_json = self.client.get(key)
            if data_json:
                return json.loads(data_json)
        except Exception as e:
            logger.error(f"Failed to get cached product {product_id}: {e}")
        return None

    def invalidate_product_cache(self, product_id: str):
        """Удалить товар из кэша"""
        try:
            key = f"product:{product_id}"
            self.client.delete(key)
            logger.debug(f"Invalidated cache for product: {product_id}")
        except Exception as e:
            logger.error(f"Failed to invalidate cache for product {product_id}: {e}")

    # Методы для дедупликации
    def is_product_seen_recently(self, product_key: str, ttl_seconds: int = 86400) -> bool:
        """Проверить, видели ли мы этот товар недавно"""
        try:
            key = f"seen:{product_key}"
            exists = self.client.exists(key)
            if not exists:
                # Устанавливаем TTL для будущих проверок
                self.client.setex(key, ttl_seconds, "1")
            return exists
        except Exception as e:
            logger.error(f"Failed to check product seen status: {e}")
            return False

    def mark_product_seen(self, product_key: str, ttl_seconds: int = 86400):
        """Пометить товар как увиденный"""
        try:
            key = f"seen:{product_key}"
            self.client.setex(key, ttl_seconds, "1")
            logger.debug(f"Marked product as seen: {product_key}")
        except Exception as e:
            logger.error(f"Failed to mark product as seen: {e}")

    # Методы для rate limiting
    def check_rate_limit(self, key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
        """Проверить rate limit"""
        try:
            # Используем sorted set для sliding window
            now = time.time()
            window_start = now - window_seconds

            # Удаляем старые записи
            self.client.zremrangebyscore(f"ratelimit:{key}", "-inf", window_start)

            # Получаем количество запросов в окне
            current_count = self.client.zcard(f"ratelimit:{key}")

            allowed = current_count < limit

            if allowed:
                # Добавляем новую запись
                self.client.zadd(f"ratelimit:{key}", {str(now): now})
                # Устанавливаем TTL на весь ключ
                self.client.expire(f"ratelimit:{key}", window_seconds)

            return allowed, limit - current_count - 1 if not allowed else limit - current_count
        except Exception as e:
            logger.error(f"Failed to check rate limit for {key}: {e}")
            return True, 999  # В случае ошибки разрешаем

    # Методы для статистики и мониторинга
    def increment_counter(self, key: str, amount: int = 1):
        """Увеличить счетчик"""
        try:
            self.client.incrby(key, amount)
        except Exception as e:
            logger.error(f"Failed to increment counter {key}: {e}")

    def get_counter(self, key: str) -> int:
        """Получить значение счетчика"""
        try:
            value = self.client.get(key)
            return int(value) if value else 0
        except Exception as e:
            logger.error(f"Failed to get counter {key}: {e}")
            return 0

    def set_counter(self, key: str, value: int):
        """Установить значение счетчика"""
        try:
            self.client.set(key, str(value))
        except Exception as e:
            logger.error(f"Failed to set counter {key}: {e}")

    # Методы для очередей заданий (для фоновых задач)
    def enqueue_job(self, queue_name: str, job_data: Dict) -> bool:
        """Добавить задание в очередь"""
        try:
            job_json = json.dumps(job_data, ensure_ascii=False)
            self.client.lpush(f"queue:{queue_name}", job_json)
            logger.debug(f"Enqueued job to {queue_name}: {job_data.get('type', 'unknown')}")
            return True
        except Exception as e:
            logger.error(f"Failed to enqueue job to {queue_name}: {e}")
            return False

    def dequeue_job(self, queue_name: str) -> Optional[Dict]:
        """Извлечь задание из очереди"""
        try:
            job_json = self.client.rpop(f"queue:{queue_name}")
            if job_json:
                job_data = json.loads(job_json)
                logger.debug(f"Dequeued job from {queue_name}: {job_data.get('type', 'unknown')}")
                return job_data
        except Exception as e:
            logger.error(f"Failed to dequeue job from {queue_name}: {e}")
        return None

    def get_queue_size(self, queue_name: str) -> int:
        """Получить размер очереди заданий"""
        try:
            return self.client.llen(f"queue:{queue_name}")
        except Exception as e:
            logger.error(f"Failed to get queue size for {queue_name}: {e}")
            return 0

    # Методы для очистки и обслуживания
    def clear_publish_buffer(self):
        """Очистить буфер публикации (для тестирования)"""
        try:
            self.client.delete("publish_buffer")
            logger.info("Cleared publish buffer")
        except Exception as e:
            logger.error(f"Failed to clear publish buffer: {e}")

    def clear_brand_window(self):
        """Очистить sliding window брендов (для тестирования)"""
        try:
            self.client.delete("recent:brands")
            logger.info("Cleared brand window")
        except Exception as e:
            logger.error(f"Failed to clear brand window: {e}")

    def get_stats(self) -> Dict:
        """Получить статистику Redis"""
        try:
            info = self.client.info()
            return {
                'connected_clients': info.get('connected_clients', 0),
                'used_memory_human': info.get('used_memory_human', '0B'),
                'total_connections_received': info.get('total_connections_received', 0),
                'publish_buffer_size': self.get_publish_queue_size(),
                'brand_window_size': self.client.llen("recent:brands"),
            }
        except Exception as e:
            logger.error(f"Failed to get Redis stats: {e}")
            return {}

    def health_check(self) -> bool:
        """Проверка здоровья Redis"""
        try:
            return self.client.ping()
        except Exception:
            return False

# Глобальный экземпляр
_redis_cache = None

def get_redis_cache() -> RedisCache:
    """Get global Redis cache instance"""
    global _redis_cache
    if _redis_cache is None and config.USE_REDIS:
        _redis_cache = RedisCache()
    return _redis_cache
