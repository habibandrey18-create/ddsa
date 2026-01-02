# utils/xhr_cache.py
"""
XHR Cache - Cache successful XHR requests for fast reproduction
Reduces need for full browser automation by reusing captured XHR
Thread-safe in-memory cache with disk persistence
"""
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any
from hashlib import md5

from config.link_generation_config import DEBUG_DIR, XHR_CACHE_TTL, XHR_CACHE_MAX_SIZE

logger = logging.getLogger(__name__)

# Cache configuration
XHR_CACHE_FILE = DEBUG_DIR / "xhr_cache.json"


class XHRCache:
    """
    Thread-safe cache for successful XHR requests.
    Stores XHR info keyed by URL pattern for fast lookup.
    """

    def __init__(self, cache_file: Path = XHR_CACHE_FILE, ttl: int = XHR_CACHE_TTL):
        """
        Initialize XHR cache.

        Args:
            cache_file: Path to cache file
            ttl: Time-to-live for cache entries in seconds
        """
        self.cache_file = cache_file
        self.ttl = ttl
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._load_cache()

    def _load_cache(self):
        """Load cache from disk."""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Filter expired entries
                    now = time.time()
                    self._cache = {
                        k: v
                        for k, v in data.items()
                        if now - v.get("cached_at", 0) < self.ttl
                    }
                    logger.info(f"📦 Loaded {len(self._cache)} valid XHR cache entries")
        except Exception as e:
            logger.warning(f"⚠️ Failed to load XHR cache: {e}")
            self._cache = {}

    def _save_cache(self):
        """Save cache to disk."""
        try:
            # Limit cache size
            if len(self._cache) > XHR_CACHE_MAX_SIZE:
                # Remove oldest entries
                sorted_items = sorted(
                    self._cache.items(), key=lambda x: x[1].get("cached_at", 0)
                )
                self._cache = dict(sorted_items[-XHR_CACHE_MAX_SIZE:])

            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"⚠️ Failed to save XHR cache: {e}")

    def _get_cache_key(self, url: str) -> str:
        """Generate cache key from URL."""
        # Use domain + path pattern (ignore query params for matching)
        from urllib.parse import urlparse

        parsed = urlparse(url)
        key_str = f"{parsed.netloc}{parsed.path}"
        return md5(key_str.encode()).hexdigest()[:16]

    async def get(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Get cached XHR info for URL (thread-safe).

        Args:
            url: Product URL

        Returns:
            Cached XHR info or None
        """
        async with self._lock:
            cache_key = self._get_cache_key(url)
            entry = self._cache.get(cache_key)

            if not entry:
                return None

            # Check if expired
            if time.time() - entry.get("cached_at", 0) > self.ttl:
                self._cache.pop(cache_key, None)
                return None

            logger.debug(f"📦 Cache hit for URL: {url[:100]}")
            return entry.get("xhr_info")

    async def put(self, url: str, xhr_info: Dict[str, Any]):
        """
        Cache XHR info for URL (thread-safe).

        Args:
            url: Product URL
            xhr_info: XHR information to cache
        """
        async with self._lock:
            cache_key = self._get_cache_key(url)
            self._cache[cache_key] = {
                "xhr_info": xhr_info,
                "cached_at": time.time(),
                "url": url,
            }
            # Save to disk asynchronously (don't block)
            asyncio.create_task(asyncio.to_thread(self._save_cache))
            logger.debug(f"💾 Cached XHR for URL: {url[:100]}")

    def clear(self):
        """Clear all cache entries."""
        self._cache.clear()
        try:
            if self.cache_file.exists():
                self.cache_file.unlink()
        except Exception:
            pass
        logger.info("🧹 XHR cache cleared")


# Global cache instance
_xhr_cache: Optional[XHRCache] = None


def get_xhr_cache() -> XHRCache:
    """Get or create global XHR cache instance."""
    global _xhr_cache
    if _xhr_cache is None:
        _xhr_cache = XHRCache()
    return _xhr_cache
