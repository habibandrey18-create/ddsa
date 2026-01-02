# utils/context_pool.py
"""
Browser Context Pool - Reuse Playwright contexts for better performance
Reduces browser startup overhead by reusing contexts
"""
import asyncio
import logging
import time
from typing import Optional, Dict, Any
from pathlib import Path
from collections import deque

logger = logging.getLogger(__name__)

# Context pool configuration
MAX_POOL_SIZE = 3  # Maximum contexts in pool
CONTEXT_TTL = 300  # Context lifetime in seconds (5 minutes)
CONTEXT_MAX_USES = 10  # Maximum uses per context before recycling


class ContextPool:
    """
    Pool of reusable Playwright browser contexts.
    Reduces browser startup overhead by reusing contexts.
    """
    
    def __init__(self, max_size: int = MAX_POOL_SIZE, ttl: int = CONTEXT_TTL):
        """
        Initialize context pool.
        
        Args:
            max_size: Maximum number of contexts in pool
            ttl: Time-to-live for contexts in seconds
        """
        self.max_size = max_size
        self.ttl = ttl
        self._pool: deque = deque(maxlen=max_size)
        self._lock = asyncio.Lock()
        self._context_metadata: Dict[Any, Dict[str, Any]] = {}
    
    async def acquire(
        self,
        browser,
        storage_state_path: Optional[str] = None,
        **context_options
    ):
        """
        Acquire a context from pool or create new one.
        Thread-safe operation with proper locking.
        
        Args:
            browser: Playwright browser instance
            storage_state_path: Optional storage state path
            **context_options: Additional context options (UA, viewport, etc.)
            
        Returns:
            Browser context with UA rotation and settings applied
        """
        async with self._lock:
            # #region agent edit - при подключении через CDP используем существующие контексты
            # Проверяем, подключен ли браузер через CDP (у него есть метод contexts)
            try:
                # Проверяем, есть ли у браузера метод contexts (это означает, что он подключен через CDP)
                if hasattr(browser, 'contexts'):
                    existing_contexts = browser.contexts
                    logger.info(f"🔗 Found {len(existing_contexts)} existing browser contexts via CDP")                    if existing_contexts:
                        # Используем первый существующий контекст (обычно это основной контекст браузера)
                        context = existing_contexts[0]
                        pages_count = len(context.pages) if hasattr(context, 'pages') else 0
                        logger.info(f"✅ Using existing browser context (has {pages_count} pages)")                        return context
                    else:
                        logger.info("⚠️ No existing contexts found via CDP, will create new context")
            except Exception as e:
                logger.debug(f"Could not use existing CDP contexts: {e}, will use pool or create new")            # #endregion
            
            # Try to reuse existing context from pool
            while self._pool:
                context, metadata = self._pool.popleft()
                
                # Check if context is still valid
                if self._is_context_valid(context, metadata):
                    metadata['uses'] = metadata.get('uses', 0) + 1
                    metadata['last_used'] = time.time()
                    logger.debug(f"♻️ Reusing context from pool (uses: {metadata['uses']})")
                    
                    # Verify UA is still set (should be, but double-check)
                    try:
                        context_ua = await context.evaluate("() => navigator.userAgent")
                        logger.debug(f"🔍 Reused context UA: {context_ua[:50]}...")
                    except Exception:
                        pass  # Verification is optional
                    
                    return context
                else:
                    # Context expired, close it
                    try:
                        await context.close()
                    except Exception:
                        pass
                    self._context_metadata.pop(context, None)
            
            # Create new context with provided options (UA rotation ensured by caller)
            logger.debug("🆕 Creating new context")
            
            # Ensure UA and viewport are in options (safety check)
            if 'user_agent' not in context_options:
                import random
                from config.link_generation_config import USER_AGENTS
                context_options['user_agent'] = random.choice(USER_AGENTS)
                logger.debug(f"🔄 Auto-selected UA: {context_options['user_agent'][:50]}...")
            
            if 'viewport' not in context_options:
                import random
                from config.link_generation_config import VIEWPORTS
                context_options['viewport'] = random.choice(VIEWPORTS)
                logger.debug(f"🔄 Auto-selected viewport: {context_options['viewport']}")
            
            # Убеждаемся, что storage_state_path не пустая строка
            # Playwright интерпретирует пустую строку как путь к файлу, что приводит к FileNotFoundError
            actual_storage_state = storage_state_path if storage_state_path and storage_state_path.strip() else None            
            context = await browser.new_context(
                storage_state=actual_storage_state,
                **context_options
            )
            
            # Verify UA was set correctly
            try:
                context_ua = await context.evaluate("() => navigator.userAgent")
                expected_ua = context_options.get('user_agent', '')
                if expected_ua and expected_ua in context_ua:
                    logger.debug(f"✅ UA verified: {context_ua[:50]}...")
                else:
                    logger.warning(f"⚠️ UA mismatch: expected {expected_ua[:50]}..., got {context_ua[:50]}...")
            except Exception as e:
                logger.debug(f"Could not verify UA: {e}")
            
            self._context_metadata[context] = {
                'created_at': time.time(),
                'last_used': time.time(),
                'uses': 1,
                'storage_state_path': storage_state_path,
                'user_agent': context_options.get('user_agent', ''),
                'viewport': context_options.get('viewport', {})
            }
            
            return context
    
    async def release(self, context, reuse: bool = True):
        """
        Release context back to pool or close it.
        
        Args:
            context: Browser context to release
            reuse: Whether to reuse this context (if valid)
        """
        async with self._lock:
            metadata = self._context_metadata.get(context)
            
            if not metadata:
                # Not tracked, just close
                try:
                    await context.close()
                except Exception:
                    pass
                return
            
            # Check if should reuse
            if reuse and self._is_context_valid(context, metadata):
                if metadata['uses'] < CONTEXT_MAX_USES:
                    self._pool.append((context, metadata))
                    logger.debug(f"♻️ Context returned to pool (uses: {metadata['uses']})")
                    return
            
            # Close context (expired or too many uses)
            try:
                await context.close()
            except Exception:
                pass
            self._context_metadata.pop(context, None)
            logger.debug("🗑️ Context closed (expired or max uses reached)")
    
    def _is_context_valid(self, context, metadata: Dict[str, Any]) -> bool:
        """Check if context is still valid for reuse."""
        try:
            # Check if context is closed
            if context.browser is None:
                return False
            
            # Check TTL
            age = time.time() - metadata.get('created_at', 0)
            if age > self.ttl:
                return False
            
            # Check max uses
            if metadata.get('uses', 0) >= CONTEXT_MAX_USES:
                return False
            
            return True
        except Exception:
            return False
    
    async def cleanup(self):
        """Clean up all contexts in pool."""
        async with self._lock:
            while self._pool:
                context, _ = self._pool.popleft()
                try:
                    await context.close()
                except Exception:
                    pass
            self._context_metadata.clear()
            logger.info("🧹 Context pool cleaned up")


# Global context pool instance
_context_pool: Optional[ContextPool] = None


def get_context_pool() -> ContextPool:
    """Get or create global context pool instance."""
    global _context_pool
    if _context_pool is None:
        _context_pool = ContextPool()
    return _context_pool

