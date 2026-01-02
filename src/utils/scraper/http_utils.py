# utils/scraper/http_utils.py
"""
HTTP utilities for web scraping.
Handles fetching, rate limiting, and proxy management.
"""
import asyncio
import logging
import random
import time
from typing import Dict, Optional, Tuple

import aiohttp

import src.config as config
from src.utils.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)

# Initialize rate limiter with defaults if config values are missing
try:
    rate_limit = getattr(config, "API_RATE_LIMIT", 10)
    rate_window = getattr(config, "API_RATE_WINDOW", 60)
except AttributeError:
    rate_limit = 10
    rate_window = 60

rate_limiter = get_rate_limiter(rate_limit, rate_window)

USER_AGENT = "MarketiTochkaBot/1.0 (+https://vpulse.lol)"
REQUEST_TIMEOUT = 15


async def fetch_with_backoff(
    url: str,
    session: aiohttp.ClientSession,
    max_attempts: int = 3,
    headers: Optional[Dict[str, str]] = None,
    use_proxy: bool = True
) -> Optional[str]:
    """Запрашивает URL с exponential backoff при ошибках и правильным error handling"""
    from src.services.proxy_service import get_proxy_for_request

    proxy = None
    if use_proxy:
        proxy = get_proxy_for_request()

    for attempt in range(max_attempts):
        try:
            await rate_limiter.acquire()  # Rate limiting

            start_time = time.time()
            async with session.get(
                url,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                proxy=proxy.get('http') if proxy else None
            ) as resp:
                response_time = time.time() - start_time

                # Сообщаем результат прокси сервису
                if proxy and hasattr(proxy, 'get'):
                    from src.services.proxy_service import get_proxy_service
                    proxy_service = get_proxy_service()
                    # Находим соответствующий ProxyInfo объект
                    proxy_url = proxy.get('http')
                    if proxy_url:
                        # Извлекаем host:port из proxy URL
                        import re
                        match = re.search(r'@([^:]+):(\d+)', proxy_url)
                        if match:
                            host, port = match.groups()
                            # Ищем прокси в списке сервиса
                            for p in proxy_service.proxies:
                                if p.host == host and p.port == int(port):
                                    proxy_service.report_proxy_result(p, resp.status == 200, response_time)
                                    break

                text = await resp.text(errors="ignore")
                if resp.status == 200:
                    return text
                elif resp.status == 429:
                    logger.warning(f"HTTP 429 (Too Many Requests) for {url} - possible rate limit")
                    # При 429 меняем прокси и ждем дольше
                    if use_proxy and proxy:
                        proxy = get_proxy_for_request()  # Получаем новый прокси
                else:
                    logger.warning(f"Status {resp.status} for {url}")
        except Exception as e:
            logger.warning(f"Fetch attempt {attempt + 1} failed for {url}: {e}")
            # Сообщаем о неудаче прокси сервису
            if proxy and hasattr(proxy, 'get'):
                from src.services.proxy_service import get_proxy_service
                proxy_service = get_proxy_service()
                proxy_url = proxy.get('http')
                if proxy_url:
                    import re
                    match = re.search(r'@([^:]+):(\d+)', proxy_url)
                    if match:
                        host, port = match.groups()
                        for p in proxy_service.proxies:
                            if p.host == host and p.port == int(port):
                                proxy_service.report_proxy_result(p, False, 0)
                                break

        if attempt < max_attempts - 1:  # Не спать после последней попытки
            delay = (2 ** attempt) + random.random()  # Exponential + jitter
            # При 429 увеличиваем задержку
            if 'resp' in locals() and resp.status == 429:
                delay *= 3  # Увеличиваем задержку в 3 раза
            await asyncio.sleep(delay)

    logger.warning(f"fetch_with_backoff failed after {max_attempts} attempts for {url}")
    return None


async def fetch_text(
    session: aiohttp.ClientSession,
    url: str,
    headers: Dict[str, str]
) -> Tuple[Optional[str], Optional[int]]:
    """Fetch text content from URL."""
    try:
        await rate_limiter.acquire()  # Rate limiting
        async with session.get(url, headers=headers, timeout=REQUEST_TIMEOUT) as resp:
            return await resp.text(errors="ignore"), resp.status
    except Exception as e:
        logger.debug("fetch_text error %s -> %s", url, e)
        return None, None


async def fetch_bytes(
    session: aiohttp.ClientSession,
    url: str,
    headers: Dict[str, str]
) -> Optional[bytes]:
    """Fetch binary content from URL."""
    try:
        await rate_limiter.acquire()  # Rate limiting
        async with session.get(url, headers=headers, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status == 200:
                return await resp.read()
            return None
    except Exception as e:
        logger.debug("fetch_bytes error %s -> %s", url, e)
        return None


async def resolve_final_url(url: str, max_redirects: int = 10) -> Optional[str]:
    """
    Разрешает финальный URL после редиректов для cc/... ссылок
    Обрабатывает ya.cc редиректы до получения card-URL
    """
    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }

    try:
        async with aiohttp.ClientSession() as session:
            for redirect_count in range(max_redirects):
                logger.debug(f"Resolving redirect {redirect_count + 1}/{max_redirects}: {url}")

                try:
                    await rate_limiter.acquire()
                    async with session.get(
                        url,
                        headers=headers,
                        timeout=REQUEST_TIMEOUT,
                        allow_redirects=False
                    ) as resp:

                        # Check if this is a redirect
                        if resp.status in (301, 302, 303, 307, 308):
                            location = resp.headers.get('Location')
                            if location:
                                # Handle relative URLs
                                if location.startswith('/'):
                                    from urllib.parse import urljoin
                                    location = urljoin(url, location)

                                url = location
                                logger.debug(f"Following redirect to: {url}")
                                continue
                            else:
                                logger.warning(f"Redirect {resp.status} without Location header")
                                return None
                        elif resp.status == 200:
                            # This is the final URL
                            logger.debug(f"Final URL resolved: {url}")
                            return url
                        else:
                            logger.warning(f"Unexpected status {resp.status} for {url}")
                            return None

                except asyncio.TimeoutError:
                    logger.warning(f"Timeout resolving {url}")
                    return None
                except Exception as e:
                    logger.warning(f"Error resolving {url}: {e}")
                    return None

            logger.warning(f"Too many redirects ({max_redirects}) for {url}")
            return None

    except Exception as e:
        logger.error(f"Failed to resolve final URL for {url}: {e}")
        return None


async def fetch_via_api(product_url: str):
    """Fetch product data via API if available."""
    # This is a placeholder for API-based fetching
    # Implementation would depend on specific API requirements
    logger.info(f"API fetch not implemented for {product_url}")
    return None
