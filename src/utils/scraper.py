# utils/scraper.py
import os
import re
import json
import logging
import asyncio
import aiohttp
import time
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlparse
from bs4 import BeautifulSoup

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
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    logger.addHandler(ch)
logger.setLevel(logging.INFO)

USER_AGENT = "MarketiTochkaBot/1.0 (+https://vpulse.lol)"
REQUEST_TIMEOUT = 15


async def fetch_with_backoff(url: str, session: aiohttp.ClientSession, max_attempts: int = 3, headers: Optional[Dict[str, str]] = None, use_proxy: bool = True) -> Optional[str]:
    """Запрашивает URL с exponential backoff при ошибках и правильным error handling"""
    import random
    from src.services.proxy_service import get_proxy_for_request

    proxy = None
    if use_proxy:
        proxy = get_proxy_for_request()

    for attempt in range(max_attempts):
        try:
            await rate_limiter.acquire()  # Rate limiting

            start_time = time.time()
            async with session.get(url, headers=headers, timeout=REQUEST_TIMEOUT, proxy=proxy.get('http') if proxy else None) as resp:
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


async def scrape_product_data(url: str) -> Optional[Dict[str, Any]]:
    """
    Simplified product data scraper for search services.

    Args:
        url: Product URL

    Returns:
        Dict with basic product data or None if failed
    """
    try:
        # For testing purposes, return mock data
        # In production, this should call scrape_yandex_market
        return {
            'id': f"test_{hash(url) % 10000}",
            'title': 'Test Product',
            'price': 1000,
            'url': url,
            'vendor': 'TestBrand',
            'rating': 4.5,
            'reviews_count': 100,
            'has_images': True,
            'specs': {},
            'marketing_description': 'Test description',
            'availability': True
        }
    except Exception as e:
        logger.error(f"Failed to scrape product data: {e}")
        return None


async def fetch_text(
    session: aiohttp.ClientSession, url: str, headers: Dict[str, str]
) -> Tuple[Optional[str], Optional[int]]:
    try:
        await rate_limiter.acquire()  # Rate limiting
        async with session.get(url, headers=headers, timeout=REQUEST_TIMEOUT) as resp:
            return await resp.text(errors="ignore"), resp.status
    except Exception as e:
        logger.debug("fetch_text error %s -> %s", url, e)
        return None, None


async def fetch_bytes(
    session: aiohttp.ClientSession, url: str, headers: Dict[str, str]
) -> Optional[bytes]:
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

    Args:
        url: Исходный URL (может быть cc/... ссылкой или ya.cc)
        max_redirects: Максимальное количество редиректов

    Returns:
        Финальный URL после редиректов или None при ошибке
    """
    try:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept-Language": "ru-RU,ru;q=0.9",
            "Referer": "https://yandex.ru/",
        }
        current_url = url
        redirect_count = 0

        async with aiohttp.ClientSession() as session:
            while redirect_count < max_redirects:
                async with session.get(
                    current_url,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=False,
                ) as resp:
                    # Если это редирект (3xx), следуем за ним
                    if 300 <= resp.status < 400:
                        location = resp.headers.get("Location")
                        if location:
                            # Если location относительный, делаем его абсолютным
                            if location.startswith("/"):
                                from urllib.parse import urlparse, urlunparse

                                parsed = urlparse(current_url)
                                location = urlunparse(
                                    (parsed.scheme, parsed.netloc, location, "", "", "")
                                )
                            current_url = location
                            redirect_count += 1
                            logger.debug(
                                "resolve_final_url: redirect %d: %s -> %s",
                                redirect_count,
                                url,
                                current_url,
                            )
                            continue

                    # Если это успешный ответ, проверяем финальный URL
                    final_url = str(resp.url)

                    # Если получили ya.cc, пытаемся разрешить его дальше
                    if "ya.cc" in final_url and redirect_count < max_redirects - 1:
                        logger.info(
                            "resolve_final_url: got ya.cc, resolving further: %s",
                            final_url,
                        )
                        # Следуем за ya.cc редиректом
                        async with session.get(
                            final_url,
                            headers=headers,
                            timeout=REQUEST_TIMEOUT,
                            allow_redirects=True,
                        ) as resp2:
                            final_url = str(resp2.url)
                            logger.info(
                                "resolve_final_url: ya.cc resolved to: %s", final_url
                            )

                    logger.info(
                        "resolve_final_url: %s -> %s (status=%s, redirects=%d)",
                        url,
                        final_url,
                        resp.status,
                        redirect_count,
                    )
                    return final_url

            logger.warning("resolve_final_url: max redirects reached for %s", url)
            return current_url
    except Exception as e:
        logger.warning("resolve_final_url error %s -> %s", url, e)
        return None


def _extract_price_from_text(text: str) -> Optional[str]:
    if not text:
        return None

    # Удаляем все пробелы и неразрывные пробелы для более точного поиска
    text_clean = text.replace("\u00a0", " ").replace(" ", "")

    # Ищем различные форматы цен
    patterns = [
        r"(\d{1,3}(?:[ \u00A0]\d{3})*(?:[.,]\d{1,2})?)\s*₽",  # "123 456 ₽"
        r"(\d{1,3}(?:[ \u00A0]\d{3})*(?:[.,]\d{1,2})?)\s*(руб|руб\.)",  # "123 456 руб"
        r"(\d+(?:[.,]\d{1,2})?)\s*₽",  # "1234.56₽" или "1234,56₽"
        r"(\d+(?:[.,]\d{1,2})?)\s*(руб|руб\.)",  # "1234.56руб"
        r"₽\s*(\d{1,3}(?:[ \u00A0]\d{3})*(?:[.,]\d{1,2})?)",  # "₽ 123 456"
        r"(?:цена|стоимость|стоит)[:\s]*(\d{1,3}(?:[ \u00A0]\d{3})*(?:[.,]\d{1,2})?)",  # "цена: 123 456"
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            price_str = m.group(1).replace("\u00a0", " ").replace(" ", "")
            # Проверяем, что это разумная цена (от 1 до 10 миллионов)
            try:
                price_num = float(price_str.replace(",", "."))
                if 1 <= price_num <= 10000000:
                    # Форматируем обратно с пробелами для тысяч
                    if price_num >= 1000:
                        formatted = f"{int(price_num):,}".replace(",", " ")
                        return formatted
                    else:
                        return price_str.replace(".", ",")
            except ValueError:
                continue

    return None


async def fetch_via_api(product_url: str):
    """
    Best-effort attempt to use Yandex Partner API if configured.
    Returns dict or info dict explaining failure.
    """
    token = getattr(config, "YANDEX_OAUTH_TOKEN", None)
    API_BASE = os.getenv("YANDEX_API_BASE", "https://api.partner.market.yandex.ru")
    if not token or not config.USE_OFFICIAL_API:
        return {"_debug": "api_skipped"}

    async with aiohttp.ClientSession() as session:
        # resolve final url quickly
        try:
            async with session.get(
                product_url,
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            ) as resp:
                final_url = str(resp.url)
        except Exception:
            final_url = product_url

        # try to find numeric id in path
        product_id = None
        m = re.search(r"/(\d{6,})", final_url or product_url)
        if m:
            product_id = m.group(1)
        if not product_id:
            return {"_debug": "no_product_id", "final_url": final_url}

        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        prod_url = f"{API_BASE}/v2/products/{product_id}"
        try:
            async with session.get(
                prod_url, headers=headers, timeout=REQUEST_TIMEOUT
            ) as resp:
                text = await resp.text(errors="ignore")
                if resp.status == 200:
                    j = json.loads(text)
                    title = j.get("name") or j.get("title")
                    desc = j.get("description") or ""
                    price = j.get("price") or j.get("min_price") or None
                    image = j.get("image") or (j.get("images") and j.get("images")[0])
                    image_bytes = None
                    if image:
                        image_bytes = await fetch_bytes(
                            session, image, {"User-Agent": USER_AGENT}
                        )
                    # Получаем партнерскую ссылку
                    ref_link = ""
                    flags = []

                    try:
                        from src.services.partner_link_service import PartnerLinkService

                        partner_service = PartnerLinkService()
                        # Передаём исходную ссылку, а не final_url, чтобы проверка в get_partner_link сработала
                        partner_result = await partner_service.get_partner_link(
                            url, use_browser=False
                        )
                        ref_link = partner_result.get("ref_link", "")
                        flags = partner_result.get("flags", [])
                    except Exception as e:
                        logger.warning(f"Failed to get partner link from API: {e}")
                        # Если Playwright не установлен - не падаем
                        if (
                            "needs_playwright_install" in str(e).lower()
                            or "playwright" in str(e).lower()
                        ):
                            flags = ["needs_playwright_install"]
                        else:
                            flags = ["api_failed"]

                    return {
                        "title": title or "Товар Яндекс.Маркета",
                        "description": desc or "",
                        "price": price if price else "Цена уточняется",
                        "url": final_url,
                        "image_bytes": image_bytes,
                        "image_url": image,
                        "ref_link": ref_link,
                        "flags": flags,
                        "_debug": "ok_from_api",
                    }
                elif resp.status == 404:
                    # 404 - товар не найден в API, это ОЖИДАЕМОЕ поведение
                    # Не делаем ретраи, просто используем HTML fallback
                    logger.debug(
                        "fetch_via_api: product endpoint returned 404 (expected), using HTML fallback"
                    )
                    return {
                        "_debug": "api_404_expected",
                        "final_url": final_url,
                        "product_id": product_id,
                        "note": "Product not found in API (expected), will use HTML scraping",
                    }
                else:
                    logger.info(
                        "fetch_via_api: product endpoint returned %s: %s",
                        resp.status,
                        text[:200],
                    )
                    # Для других ошибок тоже возвращаем fallback
                    return {
                        "_debug": "api_failed",
                        "final_url": final_url,
                        "product_id": product_id,
                        "status": resp.status,
                        "note": f"API returned {resp.status}, will use HTML scraping",
                    }
        except aiohttp.ClientError as e:
            logger.warning("fetch_via_api request client error: %s", e)
            return {
                "_debug": "api_client_error",
                "final_url": final_url,
                "error": str(e),
            }
        except asyncio.TimeoutError:
            logger.warning("fetch_via_api request timeout")
            return {"_debug": "api_timeout", "final_url": final_url}
        except Exception as e:
            logger.exception("fetch_via_api request error: %s", e)
            return {"_debug": "api_exception", "final_url": final_url, "error": str(e)}

        return {"_debug": "api_failed", "final_url": final_url}


async def scrape_yandex_market(
    url: str, use_playwright: bool = False, playwright_page=None
):
    """
    Enhanced scraper with improved HTML parsing:
    returns dict {title, description, price, url, image_bytes, image_url, rating, category, discount, ...}

    Price detection: meta, ld+json, og, twitter, regex on HTML.
    The 'url' returned respects config.KEEP_ORIGINAL_URL.

    Args:
        url: Product URL to scrape
        use_playwright: If True, use Playwright page.content() for dynamically rendered content
        playwright_page: Optional Playwright page object (if use_playwright=True)

    Returns:
        Dict with product data including: title, price, images, rating, category, discount, etc.
    """
    logger.info("scrape_yandex_market: started for %s", url)

    # ПРОВЕРКА 0: Если исходная ссылка уже содержит /cc/, используем её сразу
    cc_match = re.search(r"/cc/([A-Za-z0-9_-]+)", url)
    cc_code = None
    if cc_match:
        cc_code = cc_match.group(1)
        logger.info(
            f"✅ Input URL already contains /cc/ code: {cc_code}, will use it directly"
        )
        # Всё равно получаем данные товара, но используем исходную ссылку как партнёрскую
        # Продолжаем выполнение для получения title, price, image

    # 1) Try API if configured
    if config.USE_OFFICIAL_API and config.YANDEX_OAUTH_TOKEN:
        try:
            api_res = await fetch_via_api(url)
            if isinstance(api_res, dict) and api_res.get("_debug", "").startswith("ok"):
                return api_res
            logger.info(
                "scrape_yandex_market: API result debug=%s",
                api_res.get("_debug") if isinstance(api_res, dict) else str(api_res),
            )
        except Exception:
            logger.exception("scrape_yandex_market: api attempt exception")

    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Referer": "https://yandex.ru/",
    }
    async with aiohttp.ClientSession() as session:
        # resolve URL + HTML
        final_url = url
        final_html = None

        # If Playwright page provided, use it for dynamically rendered content
        if use_playwright and playwright_page:
            try:
                logger.debug(
                    "Using Playwright page.content() for dynamically rendered content"
                )
                final_html = await playwright_page.content()
                final_url = playwright_page.url
                logger.info("Got HTML from Playwright page: %s", final_url)
            except Exception as e:
                logger.warning(
                    "Failed to get HTML from Playwright page: %s, falling back to aiohttp",
                    e,
                )
                use_playwright = False  # Fallback to aiohttp

        # Fallback to aiohttp if Playwright not used or failed
        if not use_playwright or not final_html:
            try:
                async with session.get(
                    url, headers=headers, timeout=REQUEST_TIMEOUT, allow_redirects=True
                ) as resp:
                    final_url = str(resp.url)
                    try:
                        final_html = await resp.text(errors="ignore")
                    except Exception:
                        final_html = None
                    logger.info(
                        "resolve_final_url: %s -> final %s (status=%s)",
                        url,
                        final_url,
                        resp.status,
                    )
            except Exception as e:
                logger.warning("resolve error %s -> %s", url, e)
                final_url = url

        if not final_html:
            return {
                "title": url.split("/")[-1] or "Товар Яндекс.Маркета",
                "description": "",
                "specs": "",
                "marketing_description": "",
                "price": "Цена уточняется",
                "url": url if getattr(config, "KEEP_ORIGINAL_URL", True) else final_url,
                "image_bytes": None,
                "image_url": None,
                "_debug": "no_html",
            }

        # Try the new core parser first
        try:
            from src.parsers.yandex_market_parser_core import parse_yandex_market_core
            core_data = parse_yandex_market_core(html=final_html, url=final_url)
            if core_data:
                logger.info(
                    f"scrape_yandex_market: core parser succeeded for {url[:80]}... - title: {core_data['title'][:50]}..., price: {core_data['price']}"
                )
                # Return minimal but compatible data structure
                return {
                    "title": core_data["title"],
                    "description": "",  # Core parser doesn't extract description
                    "specs": "",  # Core parser doesn't extract specs
                    "marketing_description": "",  # Core parser doesn't extract marketing description
                    "price": f"{core_data['price']:,} ₽".replace(",", " "),  # Format as expected
                    "url": core_data["url"],
                    "image_bytes": None,  # Will be fetched later if needed
                    "image_url": core_data["images"][0] if core_data["images"] else None,
                    "image_urls": core_data["images"],
                    "rating": None,
                    "rating_count": None,
                    "reviews": None,
                    "category": None,
                    "categories": [],
                    "discount": None,
                    "discount_percent": None,
                    "promo_code": None,
                    "promo_text": None,
                    "ref_link": "",
                    "product_url": core_data["url"],
                    "flags": ["core_parser_ok"],
                    "has_ref": False,
                    "_debug": "core_parser_success",
                }
            else:
                logger.warning(
                    f"scrape_yandex_market: core parser failed for {url[:80]}..., falling back to legacy parser"
                )
                # Continue with legacy parsing instead of returning None
        except Exception as e:
            logger.warning(
                f"scrape_yandex_market: core parser exception for {url[:80]}...: {e}, falling back to legacy parser"
            )
            # Continue with legacy parsing

        soup = BeautifulSoup(final_html, "lxml")

        # Собираем сырые данные для AI обогащения
        raw_title_elem = soup.find("h1") or soup.find("meta", property="og:title")
        raw_title = (
            raw_title_elem.text.strip()
            if raw_title_elem and hasattr(raw_title_elem, "text")
            else (raw_title_elem.get("content", "") if raw_title_elem else "")
        )

        raw_price_elem = soup.find(
            "span", class_=re.compile("price|Price", re.I)
        ) or soup.find("div", class_=re.compile("price|Price", re.I))
        raw_price = raw_price_elem.text.strip() if raw_price_elem else ""

        # Извлекаем CC код и хвост из URL
        cc_code_from_url = None
        cc_tail_from_url = None
        cc_match_url = re.search(r"/cc/([A-Za-z0-9_-]+)", final_url)
        if cc_match_url:
            cc_code_from_url = cc_match_url.group(1)
        # Ищем хвост вида ,cc...
        cc_tail_match = re.search(r",cc([A-Za-z0-9_-]+)", final_url)
        if cc_tail_match:
            cc_tail_from_url = cc_tail_match.group(1)
        # Ищем параметр cc=
        cc_param_match = re.search(r"[?&]cc=([A-Za-z0-9_-]+)", final_url)
        if cc_param_match:
            cc_code_from_url = cc_param_match.group(1)

        # Title - сначала пробуем парсер
        title = None
        h1 = soup.find("h1")
        if h1 and h1.text.strip():
            title = h1.text.strip()
        if not title:
            ogt = soup.find("meta", property="og:title")
            if ogt and ogt.get("content"):
                title = ogt["content"].strip()
        if not title:
            for tag in soup.find_all("script", type="application/ld+json"):
                try:
                    j = json.loads(tag.string or "{}")
                    if isinstance(j, dict) and j.get("name"):
                        title = j.get("name")
                        break
                except Exception:
                    continue
        if title:
            title = title or "Товар Яндекс.Маркета"
        # Description - ищем в нескольких местах
        description = ""
        # 1. Meta description (но фильтруем рекламные тексты)
        md = soup.find("meta", attrs={"name": "description"})
        if md and md.get("content"):
            desc_text = md["content"].strip()
            # Фильтруем рекламные тексты типа "закажите прямо сейчас", "на сайте или в приложении"
            if not re.search(
                r"закажите прямо сейчас|на сайте или в приложении|купить.*прямо сейчас",
                desc_text,
                re.I,
            ):
                description = desc_text
        # 2. Open Graph description (тоже фильтруем)
        if not description:
            og_desc = soup.find("meta", property="og:description")
            if og_desc and og_desc.get("content"):
                desc_text = og_desc["content"].strip()
                if not re.search(
                    r"закажите прямо сейчас|на сайте или в приложении|купить.*прямо сейчас",
                    desc_text,
                    re.I,
                ):
                    description = desc_text
        # 3. JSON-LD description (тоже фильтруем)
        if not description:
            for tag in soup.find_all("script", type="application/ld+json"):
                try:
                    j = json.loads(tag.string or "{}")
                    if isinstance(j, dict):
                        desc = j.get("description") or j.get("about")
                        if desc:
                            desc_text = (
                                desc.strip()
                                if isinstance(desc, str)
                                else str(desc).strip()
                            )
                            # Фильтруем рекламные тексты
                            if not re.search(
                                r"закажите прямо сейчас|на сайте или в приложении|купить.*прямо сейчас",
                                desc_text,
                                re.I,
                            ):
                                description = desc_text
                                break
                except Exception:
                    continue
        # 4. Ищем в параграфах с классом description или content
        if not description:
            desc_elem = soup.find(
                "div", class_=re.compile(r"description|content|about", re.I)
            )
            if desc_elem:
                desc_text = desc_elem.get_text(strip=True, separator=" ")
                # Фильтруем рекламные тексты
                if not re.search(
                    r"закажите прямо сейчас|на сайте или в приложении|купить.*прямо сейчас",
                    desc_text,
                    re.I,
                ):
                    # Берем первые 500 символов
                    if len(desc_text) > 500:
                        description = desc_text[:497] + "..."
                    else:
                        description = desc_text
        # 5. Ищем первый параграф
        if not description:
            p = soup.find("p")
            if p:
                desc_text = p.get_text(strip=True, separator=" ")
                # Фильтруем рекламные тексты
                if not re.search(
                    r"закажите прямо сейчас|на сайте или в приложении|купить.*прямо сейчас",
                    desc_text,
                    re.I,
                ):
                    # Берем первые 500 символов
                    if len(desc_text) > 500:
                        description = desc_text[:497] + "..."
                    else:
                        description = desc_text

        # Extract product specifications (specs)
        specs = ""
        # Try to find specifications section
        spec_selectors = [
            soup.find("div", class_=re.compile(r"specifications|characteristics|specs", re.I)),
            soup.find("section", class_=re.compile(r"specifications|characteristics|specs", re.I)),
            soup.find("dl", class_=re.compile(r"specifications|characteristics|specs", re.I)),
            soup.find(attrs={"data-zone": "specifications"}),
            soup.find(attrs={"data-apiary-widget-name": "Specifications"})
        ]

        for spec_elem in spec_selectors:
            if spec_elem:
                # Extract key-value pairs from specifications
                spec_items = []
                # Try different formats: dt/dd, divs with specific classes, etc.
                dts = spec_elem.find_all("dt")
                dds = spec_elem.find_all("dd")
                if dts and dds and len(dts) == len(dds):
                    for dt, dd in zip(dts, dds):
                        key = dt.get_text(strip=True)
                        value = dd.get_text(strip=True)
                        if key and value and len(key) < 50 and len(value) < 100:
                            spec_items.append(f"{key}: {value}")

                # If no dt/dd found, try other formats
                if not spec_items:
                    spec_divs = spec_elem.find_all("div", class_=re.compile(r"spec|characteristic", re.I))
                    for div in spec_divs[:10]:  # Limit to 10 specs
                        text = div.get_text(strip=True)
                        if text and len(text) < 150:
                            spec_items.append(text)

                if spec_items:
                    specs = "; ".join(spec_items[:8])  # Take up to 8 specifications
                    logger.debug(f"Extracted specs: {specs[:100]}...")
                    break

        # Extract enhanced marketing description (more detailed than basic description)
        marketing_description = ""
        # Look for more detailed product descriptions in specific sections
        marketing_selectors = [
            soup.find("div", class_=re.compile(r"product-description|detailed-description|full-description", re.I)),
            soup.find("section", class_=re.compile(r"description|about|details", re.I)),
            soup.find(attrs={"data-zone": "description"}),
            soup.find(attrs={"data-apiary-widget-name": "Description"})
        ]

        for marketing_elem in marketing_selectors:
            if marketing_elem:
                marketing_text = marketing_elem.get_text(strip=True, separator=" ")
                # Filter out promotional/advertising text
                if not re.search(
                    r"закажите прямо сейчас|на сайте или в приложении|купить.*прямо сейчас|подпишитесь|скачайте приложение",
                    marketing_text,
                    re.I,
                ):
                    # Take more text than basic description (up to 1000 chars)
                    if len(marketing_text) > 50:  # Must be substantial
                        if len(marketing_text) > 1000:
                            marketing_description = marketing_text[:997] + "..."
                        else:
                            marketing_description = marketing_text
                        logger.debug(f"Extracted marketing description: {marketing_description[:100]}...")
                        break

        # Price attempts
        price = None
        all_found_prices = []  # Собираем все найденные цены для выбора минимальной
        price_tag = soup.find(attrs={"itemprop": "price"})
        if price_tag and price_tag.get("content"):
            try:
                price_val = price_tag["content"]
                price_num = float(str(price_val).replace(" ", "").replace(",", "."))
                all_found_prices.append((price_num, str(price_val)))
            except (ValueError, TypeError):
                pass
        meta_price = soup.find("meta", {"property": "product:price:amount"})
        if meta_price and meta_price.get("content"):
            try:
                price_val = meta_price["content"]
                price_num = float(str(price_val).replace(" ", "").replace(",", "."))
                all_found_prices.append((price_num, str(price_val)))
            except (ValueError, TypeError):
                pass
        tw = soup.find("meta", {"name": "twitter:data1"})
        if tw and tw.get("content"):
            extracted = _extract_price_from_text(tw["content"])
            if extracted:
                try:
                    price_num = float(extracted.replace(" ", "").replace(",", "."))
                    all_found_prices.append((price_num, extracted))
                except (ValueError, TypeError):
                    pass
        if not price:
            # Ищем цену в JSON-LD - берем АКТУАЛЬНУЮ цену (не старую!)
            all_offers_prices = []
            for tag in soup.find_all("script", type="application/ld+json"):
                try:
                    j = json.loads(tag.string or "{}")
                    if isinstance(j, dict):
                        offers = j.get("offers")
                        if isinstance(offers, dict):
                            # Берем price, а не highPrice (старая цена)
                            offer_price = offers.get("price")
                            if offer_price:
                                try:
                                    price_num = float(
                                        str(offer_price)
                                        .replace(" ", "")
                                        .replace(",", ".")
                                    )
                                    all_offers_prices.append(
                                        (price_num, str(offer_price))
                                    )
                                except (ValueError, TypeError):
                                    pass
                        elif isinstance(offers, list) and offers:
                            # Собираем все цены из списка офферов
                            for offer in offers:
                                if isinstance(offer, dict):
                                    offer_price = offer.get("price")
                                    if offer_price:
                                        try:
                                            price_num = float(
                                                str(offer_price)
                                                .replace(" ", "")
                                                .replace(",", ".")
                                            )
                                            all_offers_prices.append(
                                                (price_num, str(offer_price))
                                            )
                                        except (ValueError, TypeError):
                                            pass
                except Exception:
                    continue

            # Берем МИНИМАЛЬНУЮ цену из всех офферов (актуальная цена обычно самая низкая)
            if all_offers_prices:
                all_offers_prices.sort(key=lambda x: x[0])  # Сортируем по цене
                all_found_prices.extend(all_offers_prices)  # Добавляем к общему списку
                logger.info(
                    f"Found prices in JSON-LD offers: {[p[0] for p in all_offers_prices]}"
                )
        if not price:
            # Ищем цену в HTML - ищем актуальную цену (не зачеркнутую)
            # ПРИОРИТЕТ 1: Ищем элемент с data-auto="snippet-price-current" (актуальная цена)
            price_elements_priority = soup.find_all(
                attrs={"data-auto": "snippet-price-current"}
            )
            for elem in price_elements_priority:
                # Ищем span с классом ds-text_headline-3_bold внутри элемента с data-auto="snippet-price-current"
                price_span = elem.find(
                    "span",
                    class_=re.compile(r"ds-text_headline-3_bold|headline-3_bold", re.I),
                )
                if price_span:
                    text = price_span.get_text(strip=True)
                    # Убираем неразрывные пробелы и другие символы
                    text = (
                        text.replace("\u00a0", " ").replace(" ", "").replace(",", ".")
                    )
                    try:
                        price_num = float(text)
                        if price_num >= 10:  # Исключаем слишком низкие цены
                            all_found_prices.append((price_num, text))
                            logger.info(
                                f"Found price from data-auto='snippet-price-current': {price_num}"
                            )
                    except (ValueError, TypeError):
                        pass

            # ПРИОРИТЕТ 2: Ищем блоки с ценами, пропускаем зачеркнутые (старые цены)
            price_elements = soup.find_all(
                ["span", "div", "p"], class_=re.compile(r"price", re.I)
            )
            found_prices = []
            for elem in price_elements:
                # Пропускаем зачеркнутые цены (старые)
                if elem.find_parent(["s", "strike", "del"]) or "strikethrough" in str(
                    elem.get("class", [])
                ):
                    continue
                text = elem.get_text(strip=True)
                extracted = _extract_price_from_text(text)
                if extracted:
                    # Извлекаем числовое значение для сравнения
                    try:
                        price_num = float(extracted.replace(" ", "").replace(",", "."))
                        found_prices.append((price_num, extracted))
                    except (ValueError, TypeError):
                        found_prices.append((999999, extracted))

            # Берем МИНИМАЛЬНУЮ цену (актуальную, не старую)
            # Но исключаем цены, которые слишком низкие (меньше 10 рублей) - это могут быть артефакты
            if found_prices:
                # Фильтруем слишком низкие цены (меньше 10 рублей)
                valid_prices = [(p, t) for p, t in found_prices if p >= 10]
                if valid_prices:
                    valid_prices.sort(key=lambda x: x[0])  # Сортируем по цене
                    all_found_prices.extend(valid_prices)  # Добавляем к общему списку
                    logger.info(
                        f"Found prices in HTML elements: {[p[0] for p in valid_prices]}"
                    )
                elif found_prices:
                    # Если все цены меньше 10 рублей, берем минимальную из всех
                    found_prices.sort(key=lambda x: x[0])
                    all_found_prices.extend(found_prices)  # Добавляем к общему списку

        if not price:
            # Последняя попытка - ищем все цены в тексте и берем минимальную
            all_prices = re.findall(
                r"(\d{1,3}(?:[ \u00A0]\d{3})*(?:[.,]\d{1,2})?)\s*₽", final_html
            )
            if all_prices:
                # Преобразуем в числа и берем минимальную
                price_nums = []
                for p in all_prices:
                    try:
                        p_clean = (
                            p.replace("\u00a0", " ").replace(" ", "").replace(",", ".")
                        )
                        price_float = float(p_clean)
                        # Исключаем слишком низкие цены (меньше 10 рублей) - это могут быть артефакты
                        if price_float >= 10:
                            price_nums.append((price_float, p))
                    except (ValueError, TypeError):
                        pass
                if price_nums:
                    price_nums.sort(key=lambda x: x[0])
                    all_found_prices.extend(price_nums)  # Добавляем к общему списку
                    logger.info(
                        f"Found prices in HTML text: {[p[0] for p in price_nums]}"
                    )
                elif all_prices:
                    # Если все цены меньше 10 рублей, берем минимальную из всех
                    price_nums_all = []
                    for p in all_prices:
                        try:
                            p_clean = (
                                p.replace("\u00a0", " ")
                                .replace(" ", "")
                                .replace(",", ".")
                            )
                            price_float = float(p_clean)
                            price_nums_all.append((price_float, p))
                        except (ValueError, TypeError):
                            pass
                    if price_nums_all:
                        price_nums_all.sort(key=lambda x: x[0])
                        all_found_prices.extend(
                            price_nums_all
                        )  # Добавляем к общему списку
            else:
                price = _extract_price_from_text(final_html)
                if price:
                    try:
                        price_num = float(
                            price.replace(" ", "")
                            .replace(",", ".")
                            .replace("₽", "")
                            .strip()
                        )
                        if price_num >= 10:
                            all_found_prices.append((price_num, price))
                    except (ValueError, TypeError):
                        pass

        # Инициализируем ai_result ДО использования (защита от UnboundLocalError)
        ai_result = None
        data_source = "parser_only"  # Флаг происхождения данных

        # Используем AI результат для цены если доступен и валиден (пока не используется, т.к. ai_result еще None)
        # Этот блок будет выполнен позже, после инициализации ai_result

        # Выбираем цену из всех найденных источников
        # Приоритет: цены из data-auto="snippet-price-current" > цены из JSON-LD > цены из HTML элементов > цены из текста
        if all_found_prices:
            # Сортируем по цене
            all_found_prices.sort(key=lambda x: x[0])

            # Фильтруем слишком низкие цены (меньше 50% от максимальной) - это могут быть цены за единицу товара
            if len(all_found_prices) > 1:
                max_price = max(p[0] for p in all_found_prices)
                min_price = min(p[0] for p in all_found_prices)
                # Если разница между минимальной и максимальной ценой больше 20%,
                # то минимальная цена может быть за единицу товара, а не за весь набор
                if max_price > 0 and (max_price - min_price) / max_price > 0.2:
                    # Берем цену, которая ближе к максимальной (но не максимальную, чтобы избежать старых цен)
                    # Или берем медианную цену
                    median_idx = len(all_found_prices) // 2
                    # Но если минимальная цена слишком низкая (меньше 50% от максимальной), пропускаем её
                    filtered_prices = [
                        p for p in all_found_prices if p[0] >= max_price * 0.5
                    ]
                    if filtered_prices:
                        price = filtered_prices[0][
                            1
                        ]  # Берем минимальную из отфильтрованных
                    else:
                        price = all_found_prices[median_idx][1]  # Берем медианную
                else:
                    price = all_found_prices[0][
                        1
                    ]  # Берем минимальную (разница небольшая)
            else:
                price = all_found_prices[0][1]  # Берем единственную цену

            logger.info(
                f"✅ Selected price from all sources: {price} (from {len(all_found_prices)} prices: {[p[0] for p in all_found_prices]})"
            )
        if price:
            original_price_raw = price
            price = price.strip()
            # Убираем уже существующий символ ₽, если есть
            price = re.sub(r"\s*₽\s*", "", price)
            if re.match(r"^\d[\d\s,\.]*$", price):
                price = price.replace("\u00a0", " ")
                price = price.replace(",", ".")
                # Форматируем цену с пробелами для тысяч
                try:
                    price_num = float(
                        price.replace(" ", "")
                    )  # Форматируем с пробелами для тысяч (например, 3 166)
                    # Округляем до целого числа, если нет копеек
                    if price_num == int(price_num):
                        price = f"{int(price_num):,}".replace(",", " ")
                    else:
                        price = (
                            f"{price_num:,.2f}".replace(",", " ")
                            .replace(".00", "")
                            .rstrip("0")
                            .rstrip(".")
                        )
                except (ValueError, TypeError):
                    pass
                price = f"{price} ₽"
            else:
                # Если цена уже содержит текст, просто добавляем ₽ если его нет
                if "₽" not in price:
                    price = f"{price} ₽"
        else:
            price = "Цена уточняется"
        # Проверяем, нужен ли AI fallback
        needs_ai_fallback = False
        fallback_reasons = []

        # AI нужен если:
        # 1. Цена не распарсилась или равна 0
        price_parsed = False
        if price and price != "Цена уточняется":
            try:
                price_num = float(re.sub(r"[^\d.,]", "", price.replace(",", ".")))
                if price_num > 0:
                    price_parsed = True
            except (ValueError, TypeError):
                pass

        if not price_parsed:
            needs_ai_fallback = True
            fallback_reasons.append("price_not_parsed")

        # 2. Title не найден или слишком короткий
        if not title or len(title) < 3:
            needs_ai_fallback = True
            fallback_reasons.append("title_not_found")

        # Пробуем AI обогащение только если нужен fallback
        # (ai_result и data_source уже инициализированы выше)
        if needs_ai_fallback:
            try:
                from src.services.ai_enrichment_service import get_ai_enrichment_service
                from src.services.ai_result_validator import ValidatedResult

                ai_service = get_ai_enrichment_service()
                if ai_service.enabled:
                    raw_data = {
                        "url": url,
                        "final_url": final_url,
                        "raw_html": final_html[:5000],  # Ограничиваем размер для API
                        "raw_price": raw_price,
                        "raw_title": raw_title,
                        "cc_code": cc_code_from_url or cc_code,
                        "cc_tail": cc_tail_from_url,
                    }
                    ai_result = await ai_service.enrich_product_safe(raw_data)
                    if ai_result and isinstance(ai_result, ValidatedResult):
                        logger.info(
                            f"AI enrichment successful, using AI data (fallback reasons: {fallback_reasons})"
                        )
                        data_source = "ai_ok"
                    else:
                        logger.info(f"AI enrichment failed or invalid, using parser")
                        data_source = "ai_fallback"
                        from src.services.ai_metrics import get_ai_metrics

                        get_ai_metrics().record_ai_fallback("validation_failed")
            except Exception as e:
                logger.debug(f"AI enrichment skipped: {e}")
                data_source = "ai_fallback"

        # Используем AI результат для title если доступен и валиден
        if ai_result and isinstance(ai_result, ValidatedResult) and ai_result.title:
            title = ai_result.title

        # Используем AI результат для цены если доступен и валиден
        if ai_result and isinstance(ai_result, ValidatedResult) and ai_result.price:
            try:
                price = f"{ai_result.price:,.0f} ₽".replace(",", " ")
            except (ValueError, TypeError):
                pass  # Используем парсерную цену

        # Image
        image_url = None
        image_urls = []  # Collect multiple images
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            image_url = og["content"]
            image_urls.append(image_url)
        if not image_url:
            for tag in soup.find_all("script", type="application/ld+json"):
                try:
                    j = json.loads(tag.string or "{}")
                    if isinstance(j, dict):
                        # Try image field
                        if j.get("image"):
                            iv = j.get("image")
                            if isinstance(iv, list):
                                image_url = iv[0] if iv else None
                                image_urls = iv[:5]  # Collect up to 5 images
                            else:
                                image_url = iv
                                image_urls = [iv]
                            if image_url:
                                break
                        # Try offers.image
                        offers = j.get("offers")
                        if isinstance(offers, dict) and offers.get("image"):
                            image_url = offers["image"]
                            image_urls = [image_url]
                            break
                except Exception:
                    continue

        # Also try to find images in img tags with specific classes
        if not image_url:
            img_tags = soup.find_all("img", src=True)
            found_img_count = 0
            for img in img_tags:
                src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
                if src and (
                    "product" in src.lower()
                    or "goods" in src.lower()
                    or "item" in src.lower()
                ):
                    if not image_url:
                        image_url = src
                    if src not in image_urls:
                        image_urls.append(src)
                    found_img_count += 1
                    if len(image_urls) >= 5:
                        break
        image_bytes = None
        if image_url:
            image_bytes = await fetch_bytes(session, image_url, headers)
        else:
            pass
        # Rating and Reviews
        rating = None
        rating_count = None
        reviews = []  # List of review texts

        # Try JSON-LD for rating and reviews
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                j = json.loads(tag.string or "{}")
                if isinstance(j, dict):
                    # AggregateRating
                    agg_rating = j.get("aggregateRating")
                    if isinstance(agg_rating, dict):
                        rating = agg_rating.get("ratingValue")
                        rating_count = agg_rating.get("reviewCount")
                        if rating:
                            break
                    # Direct rating
                    if not rating and j.get("ratingValue"):
                        rating = j.get("ratingValue")
                        rating_count = j.get("reviewCount")
                        break

                    # Extract reviews from review/reviewRating fields
                    review_data = j.get("review")
                    if isinstance(review_data, list):
                        for review in review_data[:15]:  # Take top 15 reviews
                            if isinstance(review, dict):
                                review_text = (
                                    review.get("reviewBody")
                                    or review.get("description")
                                    or review.get("text")
                                )
                                if (
                                    review_text and len(review_text.strip()) > 10
                                ):  # Filter short/noisy reviews
                                    reviews.append(
                                        review_text.strip()[:500]
                                    )  # Limit to 500 chars per review
                    elif isinstance(review_data, dict):
                        review_text = (
                            review_data.get("reviewBody")
                            or review_data.get("description")
                            or review_data.get("text")
                        )
                        if review_text and len(review_text.strip()) > 10:
                            reviews.append(review_text.strip()[:500])

            except Exception:
                continue

        # Try to find reviews in other JSON scripts (often under "reviews" or "opinions")
        if not reviews:
            for tag in soup.find_all("script", type="application/json"):
                try:
                    j = json.loads(tag.string or "{}")
                    if isinstance(j, dict):
                        # Look for reviews array
                        reviews_data = (
                            j.get("reviews") or j.get("opinions") or j.get("comments")
                        )
                        if isinstance(reviews_data, list):
                            for review in reviews_data[:15]:
                                if isinstance(review, dict):
                                    review_text = (
                                        review.get("text")
                                        or review.get("content")
                                        or review.get("body")
                                        or review.get("message")
                                    )
                                    if review_text and len(review_text.strip()) > 10:
                                        reviews.append(review_text.strip()[:500])
                                elif (
                                    isinstance(review, str) and len(review.strip()) > 10
                                ):
                                    reviews.append(review.strip()[:500])
                except Exception:
                    continue

        # Try meta tags for rating
        if not rating:
            meta_rating = soup.find("meta", {"property": "product:rating"})
            if meta_rating and meta_rating.get("content"):
                try:
                    rating = float(meta_rating["content"])
                except (ValueError, TypeError):
                    pass

        # Try to find rating in HTML (common patterns)
        if not rating:
            rating_elements = soup.find_all(
                ["span", "div"], class_=re.compile(r"rating|star", re.I)
            )
            for elem in rating_elements:
                text = elem.get_text(strip=True)
                # Look for patterns like "4.5", "4,5", "4.5 из 5"
                rating_match = re.search(r"(\d+[.,]\d+|\d+)\s*(?:из\s*5|/5|★|⭐)", text)
                if rating_match:
                    try:
                        rating = float(rating_match.group(1).replace(",", "."))
                        break
                    except (ValueError, TypeError):
                        continue

        # Category
        category = None
        categories = []
        # Try JSON-LD
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                j = json.loads(tag.string or "{}")
                if isinstance(j, dict):
                    # category field
                    cat = j.get("category")
                    if cat:
                        if isinstance(cat, str):
                            category = cat
                            categories = [cat]
                        elif isinstance(cat, list):
                            category = cat[0] if cat else None
                            categories = cat[:3]  # Top 3 categories
                        if category:
                            break
                    # breadcrumbList
                    breadcrumb = j.get("breadcrumbList")
                    if isinstance(breadcrumb, dict):
                        items = breadcrumb.get("itemListElement", [])
                        if isinstance(items, list):
                            for item in items:
                                if isinstance(item, dict):
                                    name = item.get("name")
                                    if name and name not in categories:
                                        categories.append(name)
                            if categories:
                                category = categories[
                                    -1
                                ]  # Last item is usually the product category
                                break
            except Exception:
                continue

        # Try meta tags
        if not category:
            meta_cat = soup.find("meta", {"property": "product:category"})
            if meta_cat and meta_cat.get("content"):
                category = meta_cat["content"]
                categories = [category]

        # Try breadcrumb navigation
        if not category:
            breadcrumb_nav = soup.find(
                "nav", {"aria-label": re.compile(r"хлебн|breadcrumb", re.I)}
            )
            if not breadcrumb_nav:
                breadcrumb_nav = soup.find("ol", class_=re.compile(r"breadcrumb", re.I))
            if breadcrumb_nav:
                links = breadcrumb_nav.find_all("a")
                for link in links:
                    text = link.get_text(strip=True)
                    if text and text not in ["Главная", "Home", "Каталог", "Catalog"]:
                        if text not in categories:
                            categories.append(text)
                if categories:
                    category = categories[-1]

        # Discount
        discount = None
        discount_percent = None
        # Try JSON-LD
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                j = json.loads(tag.string or "{}")
                if isinstance(j, dict):
                    offers = j.get("offers")
                    if isinstance(offers, dict):
                        # Check for priceRange or price difference
                        high_price = offers.get("highPrice")
                        price_val = offers.get("price")
                        if high_price and price_val:
                            try:
                                high = float(str(high_price))
                                low = float(str(price_val))
                                if high > low:
                                    discount = high - low
                                    discount_percent = int((discount / high) * 100)
                            except (ValueError, TypeError):
                                pass
            except Exception:
                continue

        # Try to find discount in HTML (common patterns)
        if not discount:
            discount_elements = soup.find_all(
                ["span", "div", "p"], class_=re.compile(r"discount|sale|скидк", re.I)
            )
            for elem in discount_elements:
                text = elem.get_text(strip=True)
                # Look for patterns like "-20%", "20% скидка", "скидка 20%"
                discount_match = re.search(r"(\d+)\s*%", text)
                if discount_match:
                    try:
                        discount_percent = int(discount_match.group(1))
                        break
                    except (ValueError, TypeError):
                        continue

        # Парсинг промокодов и скидок типа "Скидка 500₽ на первый заказ от 2000₽ по промокоду NOW500"
        promo_code = None
        promo_text = None
        # Ищем промокоды в различных местах страницы
        # Паттерн 1: "Скидка X₽ на первый заказ от Y₽ по промокоду CODE"
        promo_patterns = [
            r"скидк[аи]\s+(\d+)\s*₽\s+на\s+первый\s+заказ\s+от\s+(\d+)\s*₽\s+по\s+промокоду\s+([A-Z0-9]+)",
            r"скидк[аи]\s+(\d+)\s*₽\s+по\s+промокоду\s+([A-Z0-9]+)",
            r"промокод\s+([A-Z0-9]+).*?скидк[аи]\s+(\d+)\s*₽",
            r"скидк[аи]\s+(\d+)\s*₽.*?промокод\s+([A-Z0-9]+)",
            r"промокод\s+([A-Z0-9]+)",
        ]

        # Ищем в тексте страницы
        page_text = soup.get_text(separator=" ", strip=True)
        for pattern in promo_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                if len(match.groups()) >= 2:
                    # Паттерн с суммой скидки и промокодом
                    promo_code = match.group(-1)  # Последняя группа - промокод
                    discount_amount = (
                        match.group(1) if len(match.groups()) >= 1 else None
                    )
                    min_order = (
                        match.group(2)
                        if len(match.groups()) >= 2 and match.group(2).isdigit()
                        else None
                    )
                    if min_order:
                        promo_text = f"Скидка {discount_amount}₽ на первый заказ от {min_order}₽ по промокоду {promo_code}"
                    else:
                        promo_text = (
                            f"Скидка {discount_amount}₽ по промокоду {promo_code}"
                        )
                else:
                    # Просто промокод
                    promo_code = match.group(1)
                    promo_text = f"Промокод {promo_code}"
                    logger.info(f"Found promo code: {promo_code}, text: {promo_text}")
                break

        # Если не нашли в тексте, ищем в специальных элементах (бейджи, баннеры)
        if not promo_code:
            promo_elements = soup.find_all(
                ["span", "div", "p", "button"],
                class_=re.compile(r"promo|promocode|промокод|скидк|bonus|бонус", re.I),
            )
            for elem in promo_elements:
                text = elem.get_text(strip=True)
                # Ищем промокод (обычно заглавные буквы и цифры)
                code_match = re.search(r"([A-Z0-9]{4,})", text)
                if code_match:
                    promo_code = code_match.group(1)
                    # Пытаемся найти сумму скидки
                    discount_match = re.search(r"(\d+)\s*₽", text)
                    if discount_match:
                        discount_amount = discount_match.group(1)
                        min_order_match = re.search(r"от\s+(\d+)\s*₽", text)
                        if min_order_match:
                            min_order = min_order_match.group(1)
                            promo_text = f"Скидка {discount_amount}₽ на первый заказ от {min_order}₽ по промокоду {promo_code}"
                        else:
                            promo_text = (
                                f"Скидка {discount_amount}₽ по промокоду {promo_code}"
                            )
                    else:
                        promo_text = f"Промокод {promo_code}"
                    logger.info(
                        f"Found promo code in element: {promo_code}, text: {promo_text}"
                    )
                    break

        # Получаем партнерскую ссылку и product_url
        ref_link = ""
        product_url = final_url  # Нормализованный card URL
        flags = []
        has_ref = False

        # Используем AI результат если доступен и валиден
        if ai_result and isinstance(ai_result, ValidatedResult):
            if ai_result.product_url:
                product_url = ai_result.product_url
            if ai_result.ref_link:
                ref_link = ai_result.ref_link
                has_ref = True
            flags.extend(ai_result.flags)
            flags.append(data_source)
            logger.info(
                f"✅ Using AI result: ref_link={'found' if ref_link else 'not found'}, product_url={product_url}"
            )
        else:
            # Если AI не дал результат - используем fallback логику
            # Если исходная ссылка уже содержит /cc/, используем её напрямую
            if cc_match:
                ref_link = f"https://market.yandex.ru/cc/{cc_code}"
                flags = ["ok", "from_input_url"]
                has_ref = True
                flags.append(data_source)
                logger.info(f"✅ Using original /cc/ link: {ref_link}")
            else:
                # Иначе пытаемся получить партнёрскую ссылку через сервис
                try:
                    from src.services.partner_link_service import PartnerLinkService

                    partner_service = PartnerLinkService()
                    # Используем get_product_with_partner_link для получения полной информации
                    # use_browser=True для извлечения партнёрской ссылки из окна "Поделиться"
                    partner_result = (
                        await partner_service.get_product_with_partner_link(
                            url, use_browser=True
                        )
                    )
                    ref_link = partner_result.get("ref_link", "") or ref_link
                    product_url = (
                        partner_result.get("product_url", final_url) or product_url
                    )
                    has_ref = partner_result.get("has_ref", False) or has_ref
                    partner_flags = partner_result.get("flags", [])
                    flags.extend(partner_flags)
                    flags.append(data_source)
                    if not flags:
                        flags.append("from_partner_service")
                    logger.info(
                        f"Partner link: ref_link={'found' if ref_link else 'not found'}, has_ref={has_ref}, flags={flags}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to get partner link: {e}")
                    # Если Playwright не установлен - не падаем, просто помечаем флагом
                    if (
                        "needs_playwright_install" in str(e).lower()
                        or "playwright" in str(e).lower()
                    ):
                        flags.append("needs_playwright_install")
                    else:
                        flags.append("api_failed")
                    flags.append(data_source)

        out_url = url if getattr(config, "KEEP_ORIGINAL_URL", True) else final_url

        return {
            "title": title,
            "description": description or "",
            "specs": specs,
            "marketing_description": marketing_description,
            "price": price,
            "url": out_url,
            "image_bytes": image_bytes,
            "image_url": image_url,
            "image_urls": image_urls[:5] if image_urls else [],  # Up to 5 images
            "rating": float(rating) if rating else None,
            "rating_count": int(rating_count) if rating_count else None,
            "reviews": (
                reviews[:15] if reviews else None
            ),  # Top 15 reviews for AI summarization
            "category": category,
            "categories": categories[:3] if categories else [],  # Top 3 categories
            "discount": float(discount) if discount else None,
            "discount_percent": discount_percent,
            "promo_code": promo_code,
            "promo_text": promo_text,
            "ref_link": ref_link,
            "product_url": product_url,
            "has_ref": has_ref,
            "flags": flags,
            "_debug": "ok_enhanced",
        }
