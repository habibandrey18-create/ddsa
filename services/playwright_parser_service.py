"""
Playwright Parser Service - Fallback парсинг каталогов через headless browser
Используется ТОЛЬКО когда обычный HTTP парсинг вернул < 5 товаров или сработал shadow-ban detector
"""

import json
import asyncio
import logging
from typing import List, Dict, Optional, Any
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "Accept-Language": "ru-RU,ru;q=0.9",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class PlaywrightParserService:
    """Сервис для парсинга каталогов через Playwright (fallback)"""

    def __init__(self):
        self._playwright = None
        self._browser = None

    async def _ensure_playwright(self):
        """Инициализировать Playwright если еще не инициализирован"""
        # Playwright не нужно предварительно инициализировать,
        # async_playwright() контекстный менеджер
        pass

    async def parse_catalog(self, url: str) -> List[Dict[str, Any]]:
        """
        Парсинг каталога через Playwright (fallback метод)

        Args:
            url: URL каталога Yandex.Market

        Returns:
            Список товаров в формате:
            [{
                "market_id": str,
                "title": str,
                "price": int,
                "rating": float,
                "reviews": int,
                "url": str
            }]
        """
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                    ]
                )

                context = await browser.new_context(
                    user_agent=USER_AGENT,
                    locale="ru-RU",
                    extra_http_headers=HEADERS,
                    viewport={"width": 1366, "height": 768},
                )

                page = await context.new_page()

                logger.info(f"Playwright: loading {url}")
                response = await page.goto(url, wait_until="networkidle", timeout=60000)

                # Проверяем на CAPTCHA или другие анти-бот меры
                captcha_detected = await self._check_for_captcha(page)
                if captcha_detected:
                    from services.monitoring_service import record_captcha_detected
                    record_captcha_detected(url)
                    logger.warning(f"CAPTCHA detected for catalog {url}")
                    await browser.close()
                    return []

                # Небольшая "человеческая" пауза
                await page.wait_for_timeout(3000)

                html = await page.content()
                await browser.close()

                return self._parse_next_data(html)

        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return []
        except Exception as e:
            logger.error(f"Playwright fallback failed for {url}: {e}")
            return []

    def _parse_next_data(self, html: str) -> List[Dict[str, Any]]:
        """
        Парсинг __NEXT_DATA__ из HTML (ГЛАВНОЕ)

        Args:
            html: HTML содержимое страницы

        Returns:
            Список товаров
        """
        try:
            soup = BeautifulSoup(html, "lxml")

            script = soup.find("script", id="__NEXT_DATA__")
            if not script:
                logger.warning("❌ __NEXT_DATA__ not found")
                return []

            data = json.loads(script.string)

            # ⚠️ путь может меняться, но этот сейчас рабочий
            try:
                items = (
                    data["props"]["pageProps"]
                    ["initialState"]["search"]["results"]["items"]
                )
            except KeyError:
                logger.warning("❌ Items path not found in JSON")
                return []

            products = []

            for item in items:
                try:
                    market_id = str(item.get("id", ""))
                    if not market_id:
                        continue

                    title = item.get("titles", {}).get("raw") or item.get("title", "")
                    if not title:
                        continue

                    prices = item.get("prices", {})
                    price = prices.get("value")
                    if not price:
                        continue

                    products.append({
                        "market_id": market_id,
                        "title": title,
                        "price": int(price),
                        "rating": item.get("rating"),
                        "reviews": item.get("reviewsCount", 0),
                        "url": f"https://market.yandex.ru/product/{item['id']}",
                        "vendor": item.get("vendor"),
                        "discount_percent": item.get("discount", 0),
                        "source": "playwright_fallback"
                    })
                except KeyError as e:
                    logger.debug(f"Failed to parse item: {e}")
                    continue

            logger.info(f"✅ Parsed {len(products)} products from __NEXT_DATA__")
            return products

        except Exception as e:
            logger.error(f"Failed to parse __NEXT_DATA__: {e}")
            return []

    async def parse_single_product(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Парсинг отдельного товара через Playwright (fallback для SPA)

        Args:
            url: URL товара Yandex.Market

        Returns:
            Данные товара или None
        """
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                    ]
                )

                context = await browser.new_context(
                    user_agent=USER_AGENT,
                    locale="ru-RU",
                    extra_http_headers=HEADERS,
                    viewport={"width": 1366, "height": 768},
                )

                page = await context.new_page()

                logger.info(f"Playwright: loading single product {url}")
                response = await page.goto(url, wait_until="networkidle", timeout=60000)

                # Проверяем на CAPTCHA или другие анти-бот меры
                captcha_detected = await self._check_for_captcha(page)
                if captcha_detected:
                    from services.monitoring_service import record_captcha_detected
                    record_captcha_detected(url)
                    logger.warning(f"CAPTCHA detected for single product {url}")
                    await browser.close()
                    return None

                # Небольшая "человеческая" пауза
                await page.wait_for_timeout(3000)

                html = await page.content()
                await browser.close()

                return self._parse_single_product_data(html, url)

        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return None
        except Exception as e:
            logger.error(f"Playwright single product parsing failed for {url}: {e}")
            return None

    def _parse_single_product_data(self, html: str, url: str) -> Optional[Dict[str, Any]]:
        """
        Парсинг данных отдельного товара из HTML (использует __NEXT_DATA__)

        Args:
            html: HTML содержимое страницы
            url: URL товара

        Returns:
            Данные товара или None
        """
        try:
            from bs4 import BeautifulSoup
            import json

            soup = BeautifulSoup(html, "lxml")

            # Сначала пробуем __NEXT_DATA__
            script = soup.find("script", id="__NEXT_DATA__")
            if script:
                try:
                    data = json.loads(script.string)

                    # Пытаемся найти данные товара в различных путях JSON
                    product_data = None

                    # Путь 1: props.pageProps.product
                    try:
                        product_data = data["props"]["pageProps"]["product"]
                    except KeyError:
                        pass

                    # Путь 2: props.pageProps.initialState
                    if not product_data:
                        try:
                            initial_state = data["props"]["pageProps"]["initialState"]
                            # Ищем товар в различных разделах
                            for section in ["product", "card", "item"]:
                                if section in initial_state:
                                    product_data = initial_state[section]
                                    break
                        except KeyError:
                            pass

                    if product_data:
                        # Извлекаем данные товара
                        title = product_data.get("title") or product_data.get("name")
                        price_info = product_data.get("price", {})
                        price = price_info.get("value") if isinstance(price_info, dict) else price_info

                        if title and price:
                            return {
                                "title": title,
                                "price": f"{int(price):,} ₽".replace(",", " "),
                                "url": url,
                                "rating": product_data.get("rating"),
                                "reviews": product_data.get("reviewsCount", 0),
                                "vendor": product_data.get("vendor"),
                                "image_url": None,  # Будет заполнено позже если нужно
                                "_debug": "playwright_single_product"
                            }
                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    logger.debug(f"Failed to parse product from __NEXT_DATA__: {e}")

            # Fallback: обычный HTML парсинг
            title = None
            price = None

            # Ищем title
            h1 = soup.find("h1")
            if h1:
                title = h1.get_text(strip=True)

            # Ищем цену
            price_elem = soup.find(attrs={"data-auto": "snippet-price-current"})
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                # Извлекаем числовое значение
                import re
                price_match = re.search(r"(\d[\d\s]*)(?:₽|руб)", price_text.replace(" ", ""))
                if price_match:
                    price_num = int(price_match.group(1).replace(" ", ""))
                    price = f"{price_num:,} ₽".replace(",", " ")

            if title and price:
                return {
                    "title": title,
                    "price": price,
                    "url": url,
                    "image_url": None,
                    "_debug": "playwright_html_fallback"
                }

            return None

        except Exception as e:
            logger.error(f"Failed to parse single product data: {e}")
            return None

    async def _check_for_captcha(self, page) -> bool:
        """
        Проверяет наличие CAPTCHA на странице

        Args:
            page: Playwright page object

        Returns:
            True если CAPTCHA обнаружена
        """
        try:
            # Ищем различные индикаторы CAPTCHA
            captcha_selectors = [
                "[class*='captcha']",
                "[class*='Captcha']",
                "[id*='captcha']",
                "[id*='Captcha']",
                "text=/капча/i",
                "text=/captcha/i",
                "text=/проверка/i",
                "text=/робот/i"
            ]

            for selector in captcha_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        return True
                except:
                    pass

            # Проверяем статус код ответа (если доступен)
            try:
                response = page.request.last_response()
                if response and response.status == 429:
                    logger.warning("HTTP 429 (Too Many Requests) detected")
                    return True
            except:
                pass

            return False
        except Exception as e:
            logger.debug(f"Error checking for CAPTCHA: {e}")
            return False

    async def close(self):
        """Закрыть Playwright (no-op, используем context manager)"""
        pass


# Глобальный экземпляр
_playwright_parser = None


def get_playwright_parser() -> PlaywrightParserService:
    """Get global Playwright parser instance"""
    global _playwright_parser
    if _playwright_parser is None:
        _playwright_parser = PlaywrightParserService()
    return _playwright_parser

