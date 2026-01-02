"""
Distributed Rate Limiter using Redis
=====================================

Thread-safe, multi-instance rate limiting using Redis atomic operations.
Prevents IP bans from Yandex Market by enforcing strict rate limits.

Author: Senior Backend Engineer
Date: 2026-01-01
"""

import asyncio
import logging
import time
from typing import Optional
import redis
import config
from redis_cache import get_redis_cache

logger = logging.getLogger(__name__)


class DistributedRateLimiter:
    """
    Distributed rate limiter using Redis sorted sets.
    
    Features:
    - Atomic sliding window
    - Shared across all bot instances
    - Prevents thundering herd
    - Automatic cleanup
    """
    
    def __init__(
        self,
        redis_client: Optional[redis.Redis],
        key: str,
        limit: int,
        window_seconds: int
    ):
        """
        Initialize distributed rate limiter.
        
        Args:
            redis_client: Redis client instance (or None for testing)
            key: Unique key for this rate limiter (e.g., "yandex_api")
            limit: Max requests allowed in window
            window_seconds: Time window in seconds
        """
        self.redis = redis_client
        self.key = f"ratelimit:{key}"
        self.limit = limit
        self.window = window_seconds
        self._local_fallback = []  # Fallback if Redis unavailable
        
        logger.info(
            f"DistributedRateLimiter initialized: {key} "
            f"(limit={limit}/{window_seconds}s)"
        )
    
    async def acquire(self) -> bool:
        """
        Acquire permission to make a request.
        Blocks until permission granted (respects rate limit).
        
        Returns:
            True if acquired, False if rate limiter disabled
        """
        if not self.redis:
            # Fallback to local rate limiting (not distributed)
            return await self._acquire_local()
        
        try:
            return await self._acquire_redis()
        except Exception as e:
            logger.error(f"Redis rate limiter failed, using local fallback: {e}")
            return await self._acquire_local()
    
    async def _acquire_redis(self) -> bool:
        """Atomic Redis-based rate limiting."""
        now = time.time()
        window_start = now - self.window
        
        # Atomic sliding window using pipeline
        pipe = self.redis.pipeline()
        
        # Remove old entries
        pipe.zremrangebyscore(self.key, '-inf', window_start)
        
        # Count current requests in window
        pipe.zcard(self.key)
        
        # Execute pipeline
        results = pipe.execute()
        current_count = results[1]
        
        if current_count >= self.limit:
            # Rate limit exceeded - wait for oldest request to expire
            oldest = self.redis.zrange(self.key, 0, 0, withscores=True)
            if oldest:
                oldest_time = oldest[0][1]
                wait_time = self.window - (now - oldest_time) + 0.1  # 100ms buffer
                
                if wait_time > 0:
                    logger.warning(
                        f"Rate limit hit for {self.key}: "
                        f"{current_count}/{self.limit}, waiting {wait_time:.1f}s"
                    )
                    await asyncio.sleep(wait_time)
                    # Retry after waiting
                    return await self._acquire_redis()
        
        # Add current request
        self.redis.zadd(self.key, {str(now): now})
        
        # Set TTL on key
        self.redis.expire(self.key, self.window + 60)  # Extra 60s buffer
        
        logger.debug(f"Rate limit acquired: {current_count + 1}/{self.limit}")
        return True
    
    async def _acquire_local(self) -> bool:
        """Local fallback rate limiting (not distributed)."""
        now = time.time()
        window_start = now - self.window
        
        # Clean old entries
        self._local_fallback = [t for t in self._local_fallback if t > window_start]
        
        if len(self._local_fallback) >= self.limit:
            # Wait
            oldest = min(self._local_fallback)
            wait_time = self.window - (now - oldest) + 0.1
            
            if wait_time > 0:
                logger.warning(
                    f"Local rate limit hit: {len(self._local_fallback)}/{self.limit}, "
                    f"waiting {wait_time:.1f}s"
                )
                await asyncio.sleep(wait_time)
                return await self._acquire_local()
        
        # Add current request
        self._local_fallback.append(now)
        return True
    
    def get_stats(self) -> dict:
        """Get rate limiter statistics."""
        if not self.redis:
            return {
                'type': 'local_fallback',
                'current_count': len(self._local_fallback),
                'limit': self.limit,
                'window_seconds': self.window
            }
        
        try:
            now = time.time()
            window_start = now - self.window
            
            # Clean and count
            self.redis.zremrangebyscore(self.key, '-inf', window_start)
            current_count = self.redis.zcard(self.key)
            
            return {
                'type': 'redis_distributed',
                'current_count': current_count,
                'limit': self.limit,
                'window_seconds': self.window,
                'remaining': max(0, self.limit - current_count)
            }
        except Exception as e:
            logger.error(f"Failed to get rate limiter stats: {e}")
            return {'error': str(e)}


# Global rate limiters for different services
_yandex_api_limiter: Optional[DistributedRateLimiter] = None
_yandex_catalog_limiter: Optional[DistributedRateLimiter] = None
_telegram_api_limiter: Optional[DistributedRateLimiter] = None


def get_yandex_api_limiter() -> DistributedRateLimiter:
    """Get rate limiter for Yandex Market API calls."""
    global _yandex_api_limiter
    if _yandex_api_limiter is None:
        redis_client = None
        try:
            redis_cache = get_redis_cache()
            redis_client = redis_cache.client if redis_cache else None
        except:
            pass
        
        _yandex_api_limiter = DistributedRateLimiter(
            redis_client=redis_client,
            key="yandex_api",
            limit=config.API_RATE_LIMIT,  # 10 requests
            window_seconds=config.API_RATE_WINDOW  # per 60 seconds
        )
    return _yandex_api_limiter


def get_yandex_catalog_limiter() -> DistributedRateLimiter:
    """Get rate limiter for Yandex Market catalog scraping."""
    global _yandex_catalog_limiter
    if _yandex_catalog_limiter is None:
        redis_client = None
        try:
            redis_cache = get_redis_cache()
            redis_client = redis_cache.client if redis_cache else None
        except:
            pass
        
        _yandex_catalog_limiter = DistributedRateLimiter(
            redis_client=redis_client,
            key="yandex_catalog",
            limit=5,  # Very conservative for scraping
            window_seconds=60
        )
    return _yandex_catalog_limiter


def get_telegram_api_limiter() -> DistributedRateLimiter:
    """Get rate limiter for Telegram Bot API calls."""
    global _telegram_api_limiter
    if _telegram_api_limiter is None:
        redis_client = None
        try:
            redis_cache = get_redis_cache()
            redis_client = redis_cache.client if redis_cache else None
        except:
            pass
        
        _telegram_api_limiter = DistributedRateLimiter(
            redis_client=redis_client,
            key="telegram_api",
            limit=30,  # Telegram limit is 30/second per bot
            window_seconds=1
        )
    return _telegram_api_limiter


# Example usage:
"""
from services.distributed_rate_limiter import get_yandex_api_limiter

async def fetch_product():
    limiter = get_yandex_api_limiter()
    
    # Acquire rate limit slot (blocks if limit exceeded)
    await limiter.acquire()
    
    # Make request
    response = await http_client.get("https://market.yandex.ru/...")
    
    # No need to release - automatic with sliding window
"""

