"""
AI Cache - кэширование результатов AI обогащения
"""

import logging
import hashlib
import json
import time
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AiCache:
    """
    Кэш для результатов AI обогащения
    Кэширует по product_id или final_url на 24 часа
    """

    def __init__(self, cache_ttl_hours: int = 24):
        """
        Инициализация кэша

        Args:
            cache_ttl_hours: Время жизни кэша в часах
        """
        self.cache_ttl_hours = cache_ttl_hours
        self._cache: Dict[str, Dict[str, Any]] = {}

    def _generate_key(self, url: str, product_id: Optional[str] = None) -> str:
        """
        Генерация ключа кэша

        Args:
            url: URL товара
            product_id: Опциональный product_id

        Returns:
            Ключ кэша
        """
        if product_id:
            return f"product_id:{product_id}"

        # Используем нормализованный URL как ключ
        normalized = url.split("?")[0].split("#")[0]
        return f"url:{hashlib.md5(normalized.encode()).hexdigest()}"

    def get(
        self, url: str, product_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Получить результат из кэша

        Args:
            url: URL товара
            product_id: Опциональный product_id

        Returns:
            Кэшированный результат или None
        """
        key = self._generate_key(url, product_id)

        if key not in self._cache:
            return None

        cached = self._cache[key]

        # Проверка TTL
        cached_time = cached.get("cached_at", 0)
        if time.time() - cached_time > self.cache_ttl_hours * 3600:
            # Кэш истек
            del self._cache[key]
            logger.debug(f"Cache expired for {key}")
            return None

        logger.debug(f"Cache hit for {key}")
        return cached.get("result")

    def set(
        self, url: str, result: Dict[str, Any], product_id: Optional[str] = None
    ) -> None:
        """
        Сохранить результат в кэш

        Args:
            url: URL товара
            result: Результат для кэширования
            product_id: Опциональный product_id
        """
        key = self._generate_key(url, product_id)

        self._cache[key] = {"result": result, "cached_at": time.time(), "url": url}

        logger.debug(f"Cached result for {key}")

    def clear_expired(self) -> int:
        """
        Очистить истекшие записи из кэша

        Returns:
            Количество удаленных записей
        """
        now = time.time()
        expired_keys = [
            key
            for key, cached in self._cache.items()
            if now - cached.get("cached_at", 0) > self.cache_ttl_hours * 3600
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.debug(f"Cleared {len(expired_keys)} expired cache entries")

        return len(expired_keys)

    def get_stats(self) -> Dict[str, Any]:
        """
        Получить статистику кэша

        Returns:
            Словарь со статистикой
        """
        now = time.time()
        total = len(self._cache)
        expired = sum(
            1
            for cached in self._cache.values()
            if now - cached.get("cached_at", 0) > self.cache_ttl_hours * 3600
        )

        return {"total": total, "active": total - expired, "expired": expired}


# Глобальный экземпляр кэша
_ai_cache: Optional[AiCache] = None


def get_ai_cache() -> AiCache:
    """
    Получить глобальный экземпляр кэша

    Returns:
        Экземпляр AiCache
    """
    global _ai_cache
    if _ai_cache is None:
        _ai_cache = AiCache()
    return _ai_cache
