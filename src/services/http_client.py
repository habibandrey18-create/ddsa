# services/http_client.py
"""Централизованный HTTP клиент с connection pooling и rate limiting"""
import asyncio
import logging
import random
import time
from typing import Optional, Dict, List
from collections import deque
import aiohttp
from aiohttp import ClientSession, ClientTimeout, ClientProxyConnectionError
import src.config as config
from src.services.session_manager import get_session_manager

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter для ограничения частоты запросов"""

    def __init__(self, max_requests: int, time_window: int):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = deque()

    async def acquire(self):
        """Ждет, пока можно будет сделать запрос"""
        now = time.time()
        # Удаляем старые запросы
        while self.requests and self.requests[0] < now - self.time_window:
            self.requests.popleft()

        # Если достигнут лимит, ждем
        if len(self.requests) >= self.max_requests:
            wait_time = self.time_window - (now - self.requests[0])
            if wait_time > 0:
                logger.debug(f"Rate limit reached, waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                # Повторно очищаем после ожидания
                now = time.time()
                while self.requests and self.requests[0] < now - self.time_window:
                    self.requests.popleft()

        self.requests.append(time.time())


class HTTPClient:
    """Централизованный HTTP клиент с connection pooling"""

    _instance: Optional["HTTPClient"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Prevent multiple initialization
        if hasattr(self, '_initialized') and self._initialized:
            return

        # Defer session creation until needed (lazy initialization)
        self._session = None
        self.rate_limiter = RateLimiter(max_requests=10, time_window=60)
        # Load proxy list from config
        self.proxy_list: List[str] = getattr(config, "PROXY_LIST", [])
        self._initialized = True

        if self.proxy_list:
            logger.info(
                f"HTTPClient initialized with {len(self.proxy_list)} proxy(ies) for rotation"
            )
        else:
            logger.info(
                "HTTPClient initialized with connection pooling (no proxies configured)"
            )

    @property
    def session(self):
        """Lazy initialization of aiohttp ClientSession"""
        if self._session is None:
            timeout = ClientTimeout(total=30, connect=10)
            connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
            self._session = ClientSession(
                timeout=timeout,
                connector=connector,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
            )
            # Регистрируем сессию в менеджере для автоматического закрытия
            session_manager = get_session_manager()
            session_manager.register_session(self._session)
            logger.debug("HTTPClient session created and registered")
        return self._session

    def _get_random_proxy(self) -> Optional[str]:
        """Возвращает случайный прокси из списка или None если список пуст"""
        if not self.proxy_list:
            return None
        return random.choice(self.proxy_list)

    async def get(
        self, url: str, headers: Optional[Dict] = None, max_retries: int = 3
    ) -> Optional[aiohttp.ClientResponse]:
        """Выполняет GET запрос с rate limiting и retry

        ВАЖНО: Ответ должен быть прочитан внутри async with блока или использовать метод fetch_text()
        """
        await self.rate_limiter.acquire()

        last_error = None
        for attempt in range(max_retries):
            try:
                request_headers = dict(self.session.headers)
                if headers:
                    request_headers.update(headers)

                # Создаем запрос без async with, чтобы соединение не закрывалось сразу
                resp = await self.session.get(url, headers=request_headers)

                if resp.status == 200:
                    # Возвращаем ответ, но вызывающий код должен прочитать данные до закрытия
                    return resp
                elif resp.status == 429:  # Too Many Requests
                    resp.close()
                    wait_time = 2**attempt
                    logger.warning(
                        f"Rate limited (429), waiting {wait_time}s before retry {attempt + 1}/{max_retries}"
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    resp.close()
                    logger.error(f"HTTP {resp.status} for {url[:100]}")
                    return None
            except asyncio.TimeoutError:
                last_error = "Timeout"
                if attempt < max_retries - 1:
                    wait_time = 2**attempt
                    logger.warning(
                        f"Timeout, retrying in {wait_time}s ({attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
            except aiohttp.ClientError as e:
                last_error = str(e)
                if attempt < max_retries - 1:
                    wait_time = 2**attempt
                    logger.warning(
                        f"Network error: {e}, retrying in {wait_time}s ({attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
            except Exception as e:
                last_error = str(e)
                logger.error(f"Unexpected error fetching {url[:100]}: {e}")
                break

        logger.error(
            f"Failed to fetch {url[:100]} after {max_retries} attempts. Last error: {last_error}"
        )
        return None

    async def fetch_text(
        self, url: str, headers: Optional[Dict] = None, max_retries: int = 3
    ) -> Optional[str]:
        """Выполняет GET запрос и возвращает текст ответа с поддержкой ротации прокси"""
        await self.rate_limiter.acquire()

        last_error = None
        used_proxies = (
            set()
        )  # Отслеживаем использованные прокси для избежания повторного использования при ошибке

        for attempt in range(max_retries):
            proxy = self._get_random_proxy()
            # Если прокси уже использовался и не сработал, попробуем другой
            if (
                proxy
                and proxy in used_proxies
                and len(used_proxies) < len(self.proxy_list)
            ):
                available_proxies = [
                    p for p in self.proxy_list if p not in used_proxies
                ]
                if available_proxies:
                    proxy = random.choice(available_proxies)

            try:
                request_headers = dict(self.session.headers)
                if headers:
                    request_headers.update(headers)

                # FIXED: Added explicit timeout for proxy requests (prevents hangs)
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                async with self.session.get(
                    url, headers=request_headers, proxy=proxy, timeout=timeout
                ) as resp:
                    if resp.status == 200:
                        # Читаем данные внутри async with блока
                        text = await resp.text()
                        if proxy:
                            logger.debug(f"Successfully fetched {url[:100]} via proxy")
                        return text
                    elif resp.status == 429:  # Too Many Requests
                        wait_time = 2**attempt
                        logger.warning(
                            f"Rate limited (429), waiting {wait_time}s before retry {attempt + 1}/{max_retries}"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"HTTP {resp.status} for {url[:100]}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2**attempt)
                            continue
                        return None
            except ClientProxyConnectionError as e:
                last_error = f"Proxy connection error: {e}"
                if proxy:
                    used_proxies.add(proxy)
                    logger.warning(
                        f"Proxy {proxy[:50]}... failed, trying different proxy"
                    )
                # Если есть еще прокси, попробуем сразу с другим
                if self.proxy_list and len(used_proxies) < len(self.proxy_list):
                    continue  # Попробуем сразу с другим прокси
                elif attempt < max_retries - 1:
                    wait_time = 2**attempt
                    logger.warning(
                        f"All proxies failed or no more proxies, retrying in {wait_time}s ({attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
            except asyncio.TimeoutError:
                last_error = "Timeout"
                if proxy:
                    used_proxies.add(proxy)
                if attempt < max_retries - 1:
                    wait_time = 2**attempt
                    logger.warning(
                        f"Timeout, retrying in {wait_time}s ({attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
            except aiohttp.ClientError as e:
                last_error = str(e)
                if proxy:
                    used_proxies.add(proxy)
                if attempt < max_retries - 1:
                    wait_time = 2**attempt
                    logger.warning(
                        f"Network error: {e}, retrying in {wait_time}s ({attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
            except Exception as e:
                last_error = str(e)
                logger.error(f"Unexpected error fetching {url[:100]}: {e}")
                break

        logger.error(
            f"Failed to fetch {url[:100]} after {max_retries} attempts. Last error: {last_error}"
        )
        return None

    async def fetch_json(
        self, url: str, headers: Optional[Dict] = None, max_retries: int = 3
    ) -> Optional[Dict]:
        """Выполняет GET запрос и возвращает JSON ответ с поддержкой ротации прокси"""
        await self.rate_limiter.acquire()

        last_error = None
        used_proxies = (
            set()
        )  # Отслеживаем использованные прокси для избежания повторного использования при ошибке

        for attempt in range(max_retries):
            proxy = self._get_random_proxy()
            # Если прокси уже использовался и не сработал, попробуем другой
            if (
                proxy
                and proxy in used_proxies
                and len(used_proxies) < len(self.proxy_list)
            ):
                available_proxies = [
                    p for p in self.proxy_list if p not in used_proxies
                ]
                if available_proxies:
                    proxy = random.choice(available_proxies)

            try:
                request_headers = dict(self.session.headers)
                if headers:
                    request_headers.update(headers)

                # FIXED: Added explicit timeout for JSON requests (prevents hangs)
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                async with self.session.get(
                    url, headers=request_headers, proxy=proxy, timeout=timeout
                ) as resp:
                    if resp.status == 200:
                        # Читаем JSON данные внутри async with блока
                        data = await resp.json()
                        if proxy:
                            logger.debug(
                                f"Successfully fetched JSON from {url[:100]} via proxy"
                            )
                        return data
                    elif resp.status == 429:  # Too Many Requests
                        wait_time = 2**attempt
                        logger.warning(
                            f"Rate limited (429), waiting {wait_time}s before retry {attempt + 1}/{max_retries}"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"HTTP {resp.status} for {url[:100]}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2**attempt)
                            continue
                        return None
            except ClientProxyConnectionError as e:
                last_error = f"Proxy connection error: {e}"
                if proxy:
                    used_proxies.add(proxy)
                    logger.warning(
                        f"Proxy {proxy[:50]}... failed, trying different proxy"
                    )
                # Если есть еще прокси, попробуем сразу с другим
                if self.proxy_list and len(used_proxies) < len(self.proxy_list):
                    continue  # Попробуем сразу с другим прокси
                elif attempt < max_retries - 1:
                    wait_time = 2**attempt
                    logger.warning(
                        f"All proxies failed or no more proxies, retrying in {wait_time}s ({attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
            except asyncio.TimeoutError:
                last_error = "Timeout"
                if proxy:
                    used_proxies.add(proxy)
                if attempt < max_retries - 1:
                    wait_time = 2**attempt
                    logger.warning(
                        f"Timeout, retrying in {wait_time}s ({attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
            except aiohttp.ClientError as e:
                last_error = str(e)
                if proxy:
                    used_proxies.add(proxy)
                if attempt < max_retries - 1:
                    wait_time = 2**attempt
                    logger.warning(
                        f"Network error: {e}, retrying in {wait_time}s ({attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
            except Exception as e:
                last_error = str(e)
                logger.error(f"Unexpected error fetching {url[:100]}: {e}")
                break

        logger.error(
            f"Failed to fetch {url[:100]} after {max_retries} attempts. Last error: {last_error}"
        )
        return None

    async def close(self):
        """
        Закрывает HTTP сессию.
        FIXED: Added graceful cleanup to prevent connection leaks.
        """
        if self._session and not self._session.closed:
            # Удаляем из менеджера перед закрытием
            session_manager = get_session_manager()
            session_manager.unregister_session(self._session)
            await self._session.close()
            # Wait for connections to close gracefully
            await asyncio.sleep(0.25)
            logger.info("HTTPClient session closed")
            self._session = None
    
    async def __aenter__(self):
        """Context manager support"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager support - auto close"""
        await self.close()


# Singleton instance
_http_client: Optional[HTTPClient] = None


def get_http_client() -> HTTPClient:
    """Получить глобальный экземпляр HTTPClient"""
    global _http_client
    if _http_client is None:
        _http_client = HTTPClient()
    return _http_client
