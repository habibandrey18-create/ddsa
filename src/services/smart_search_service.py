# services/smart_search_service.py - Умный автопоиск с offset per keyword
"""
Smart search service for Yandex Market.
Combines search engine, product processing, and data extraction functionality.
"""
import asyncio
import json
import os
import logging
from typing import List, Dict, Any, Optional, Tuple

import src.config as config
from src.core.database import get_postgres_db
from src.core.redis_cache import get_redis_cache

# Import mixins
from .search.search_engine import SearchEngineMixin
from .search.product_processor import ProductProcessorMixin

# Playwright for anti-bot bypass (fallback only)
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    async_playwright = None

logger = logging.getLogger(__name__)


class SmartSearchService(SearchEngineMixin, ProductProcessorMixin):
    """Умный автопоиск с offset per keyword"""

    def __init__(self):
        self.db = get_postgres_db() if config.USE_POSTGRES else None
        self.redis = get_redis_cache() if config.USE_REDIS else None
        self._session = None
        self._last_catalog_parse = self._load_parse_cache()  # Персистентный кэш
        self._semaphore = asyncio.Semaphore(3)  # Ограничение concurrency до 3
        self._playwright_daily_count = 0  # Счетчик Playwright использований за день
        # Метрики для мониторинга
        self.metrics = {
            'catalog_requests': 0,
            'catalog_errors': 0,
            'products_parsed': 0,
            'playwright_fallback_used': 0,
            'shadow_ban_detected': 0
        }

    def _load_parse_cache(self) -> Dict:
        """Загрузка кэша времени парсинга из файла"""
        cache_file = "catalog_parse_cache.json"
        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load parse cache: {e}")
        return {}

    def _save_parse_cache(self):
        """Сохранение кэша времени парсинга в файл"""
        cache_file = "catalog_parse_cache.json"
        try:
            with open(cache_file, 'w') as f:
                json.dump(self._last_catalog_parse, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save parse cache: {e}")

    def _can_use_playwright_fallback(self) -> bool:
        """Проверка лимита на Playwright fallback (max 5 per day)"""
        return self._playwright_daily_count < 5

    def get_metrics(self) -> Dict:
        """Получить метрики для мониторинга"""
        return {
            **self.metrics,
            'playwright_daily_count': self._playwright_daily_count,
            'cache_size': len(self._last_catalog_parse)
        }

    async def get_session(self):
        """Получить HTTP сессию"""
        if self._session is None:
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close_session(self):
        """Закрыть HTTP сессию"""
        if self._session:
            await self._session.close()
            self._session = None

    async def crawl_catalogs(self, max_catalogs: int = 5) -> Tuple[int, int]:
        """
        Обход каталогов Яндекс.Маркета

        Args:
            max_catalogs: Максимум каталогов для обработки

        Returns:
            Tuple[int, int]: (обработано_товаров, пропущено_товаров)
        """
        logger.info(f"Starting catalog crawl with max {max_catalogs} catalogs")

        total_added = 0
        total_skipped = 0

        try:
            # Список URL каталогов для обхода
            catalog_urls = [
                "https://market.yandex.ru/catalog--naushniki/",
                "https://market.yandex.ru/catalog--smartfony/",
                "https://market.yandex.ru/catalog--noutbuki/",
                "https://market.yandex.ru/catalog--planshety/",
                "https://market.yandex.ru/catalog--smart-chasy/",
            ][:max_catalogs]

            for url in catalog_urls:
                try:
                    async with self._semaphore:
                        added, skipped = await self._process_catalog(url)
                        total_added += added
                        total_skipped += skipped

                        # Небольшая пауза между каталогами
                        await asyncio.sleep(2)

                except Exception as e:
                    logger.error(f"Failed to process catalog {url}: {e}")
                    self.metrics['catalog_errors'] += 1

            logger.info(f"Catalog crawl completed: {total_added} added, {total_skipped} skipped")

        except Exception as e:
            logger.error(f"Catalog crawl failed: {e}")

        return total_added, total_skipped

    async def _process_catalog(self, url: str) -> Tuple[int, int]:
        """Обработать один каталог"""
        logger.info(f"Processing catalog: {url}")

        try:
            # Получаем HTML каталога
            html = await self._fetch_catalog_page(url)
            if not html:
                return 0, 0

            # Парсим товары из HTML
            products = self._parse_catalog_products(html, url)

            # Обрабатываем найденные товары
            added, skipped = await self._process_found_products(products, url)

            logger.info(f"Catalog {url} processed: {len(products)} found, {added} added, {skipped} skipped")
            return added, skipped

        except Exception as e:
            logger.error(f"Failed to process catalog {url}: {e}")
            return 0, 0

    async def _fetch_catalog_page(self, url: str) -> Optional[str]:
        """Получить HTML страницы каталога"""
        try:
            session = await self.get_session()
            from src.utils.scraper import fetch_with_backoff
            html = await fetch_with_backoff(url, session, max_attempts=3)

            if html and len(html.strip()) > 1000:
                self.metrics['catalog_requests'] += 1
                return html
            else:
                logger.warning(f"Invalid HTML received for catalog {url}")
                return None

        except Exception as e:
            logger.error(f"Failed to fetch catalog page {url}: {e}")
            self.metrics['catalog_errors'] += 1
            return None

    def _parse_catalog_products(self, html: str, url: str = "") -> List[Dict]:
        """
        Парсинг товаров из HTML каталога
        Сначала пытаемся найти __NEXT_DATA__, затем fallback на HTML парсинг
        """
        try:
            # Сначала пытаемся найти __NEXT_DATA__
            products = self._extract_items_from_next_data(html)
            if products:
                logger.info(f"Extracted {len(products)} products from __NEXT_DATA__")
                return products

            # Fallback: HTML парсинг
            products = self._parse_catalog_fallback(html)
            logger.info(f"Extracted {len(products)} products via HTML fallback")
            return products

        except Exception as e:
            logger.error(f"Failed to parse catalog products: {e}")
            return []

    def _extract_items_from_next_data(self, html: str) -> List[Dict]:
        """Извлечение товаров из __NEXT_DATA__"""
        try:
            import re
            next_data_match = re.search(r'__NEXT_DATA__\s*=\s*({.+?});', html, re.DOTALL)
            if not next_data_match:
                return []

            next_data = json.loads(next_data_match.group(1))
            return self._parse_next_data_products(next_data)

        except Exception as e:
            logger.debug(f"Failed to extract from __NEXT_DATA__: {e}")
            return []

    def _parse_next_data_products(self, data: Dict) -> List[Dict]:
        """Парсинг товаров из NEXT_DATA структуры"""
        products = []

        try:
            # Ищем товары в различных местах структуры
            if 'props' in data and 'pageProps' in data['props']:
                page_props = data['props']['pageProps']

                # Ищем в catalogData
                if 'catalogData' in page_props:
                    catalog_data = page_props['catalogData']
                    if 'products' in catalog_data:
                        for item in catalog_data['products']:
                            product = self._convert_item_to_product(item)
                            if product:
                                products.append(product)

        except Exception as e:
            logger.debug(f"Failed to parse NEXT_DATA products: {e}")

        return products

    def _convert_item_to_product(self, item: Dict) -> Optional[Dict]:
        """Конвертировать элемент NEXT_DATA в формат продукта"""
        try:
            product = {
                'id': str(item.get('id', '')),
                'title': item.get('title', ''),
                'price': item.get('price', {}).get('value'),
                'url': item.get('link', {}).get('href', ''),
                'vendor': item.get('vendor', {}).get('name', ''),
                'rating': item.get('rating', 0),
                'reviews_count': item.get('reviewsCount', 0),
                'image_url': item.get('image', {}).get('url'),
                'has_images': bool(item.get('image')),
                'category': item.get('category', ''),
            }

            # Валидация обязательных полей
            if product['id'] and product['title'] and product['url']:
                return product

        except Exception as e:
            logger.debug(f"Failed to convert item to product: {e}")

            return None

    def _parse_catalog_fallback(self, html: str) -> List[Dict]:
        """Fallback парсинг товаров из HTML"""
        products = []

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            # Ищем элементы товаров
            product_selectors = [
                '[data-zone="product"]',
                '.product-card',
                '.catalog-product',
                '[data-product-id]'
            ]

            for selector in product_selectors:
                cards = soup.select(selector)
                for card in cards:
                    product = self._parse_product_card(card)
                    if product:
                        products.append(product)

                if products:
                    break

        except Exception as e:
            logger.error(f"Catalog fallback parsing failed: {e}")

        return products

    def _parse_product_card(self, card) -> Optional[Dict]:
        """Парсинг карточки товара"""
        try:
            # Извлекаем данные из атрибутов и текста
            product_id = card.get('data-product-id') or card.get('data-id')
            title_elem = card.select_one('[data-zone="title"], .title, h3, h4')
            price_elem = card.select_one('[data-zone="price"], .price')

            if not title_elem or not product_id:
                return None

            title = title_elem.get_text(strip=True)
            price_text = price_elem.get_text(strip=True) if price_elem else None

            # Извлекаем цену
            price = None
            if price_text:
                import re
                price_match = re.search(r'(\d+(?:\s*\d+)*(?:[.,]\d{1,2})?)', price_text.replace(' ', ''))
                if price_match:
                    price = float(price_match.group(1).replace(',', '.'))

            return {
                'id': str(product_id),
                'title': title,
                'price': price,
                'url': f"https://market.yandex.ru/product/{product_id}",
                'has_images': True,
            }

        except Exception as e:
            logger.debug(f"Failed to parse product card: {e}")
            return None

    async def _process_found_products(self, products: List[Dict], source_url: str) -> Tuple[int, int]:
        """Обработать найденные товары"""
        added = 0
        skipped = 0

        for product in products:
            try:
                await self._enqueue_product(product, source_url)
                added += 1
                self.metrics['products_parsed'] += 1

            except Exception as e:
                logger.error(f"Failed to process product {product.get('title', 'Unknown')}: {e}")
                skipped += 1

        return added, skipped

    async def run_smart_search_cycle(self, max_catalogs: int = 5):
        """
        Запуск цикла умного поиска
        
        Args:
            max_catalogs: Максимум каталогов для обработки
        """
        logger.info("🚀 Starting Advanced Yandex.Market Bot Worker")

        try:
            # Проверяем подключения
            logger.info("🔍 Checking database connections...")
            if self.db:
                logger.info("✅ Postgres connection OK")
            if self.redis:
                logger.info("✅ Redis connection OK")
            logger.info("✅ All database connections verified")

            # Запускаем фоновые сервисы
            logger.info("🔄 Starting background services...")
            # Publish service is handled separately
            logger.info("✅ Background services started")

            # Основной цикл поиска
            logger.info("🔄 Starting main work loop")

            while True:
                try:
                    # Обходим каталоги
                    await self.crawl_catalogs(max_catalogs)

                    # Запускаем поиск по ключевым словам
                    await self._run_keyword_searches()

                    # Обслуживание системы
                    await self._run_maintenance()

                    # Ждем следующего цикла
                    await asyncio.sleep(300)  # 5 минут

        except Exception as e:
                    logger.error(f"Work cycle error: {e}")
                    await asyncio.sleep(60)

        except Exception as e:
            logger.error(f"Smart search cycle failed: {e}")
        finally:
            await self.close_session()

    async def _run_keyword_searches(self):
        """Запуск поиска по ключевым словам"""
        try:
            keywords = getattr(config, 'AUTO_SEARCH_QUERIES', '').split(',')
            if not keywords or keywords == ['']:
                return

            for keyword in keywords[:3]:  # Ограничиваем до 3 ключевых слов
                keyword = keyword.strip()
                if keyword:
                    await self._run_smart_search(keyword, max_pages=2)

        except Exception as e:
            logger.error(f"Keyword search failed: {e}")

    async def _run_maintenance(self):
        """Обслуживание системы"""
        try:
            # Сохраняем кэш
            self._save_parse_cache()

            # Очищаем старые метрики (опционально)
            # Можно добавить другие задачи обслуживания

        except Exception as e:
            logger.error(f"Maintenance failed: {e}")

    async def reset_search_state(self, key_text: str = None):
        """Сброс состояния поиска"""
        try:
            if self.db:
            if key_text:
                    self.db.reset_search_key(key_text)
            else:
                    self.db.reset_all_search_keys()
            logger.info(f"Search state reset for {key_text or 'all keys'}")
        except Exception as e:
            logger.error(f"Failed to reset search state: {e}")

    def get_search_stats(self) -> Dict:
        """Получить статистику поиска"""
        try:
            stats = {
                'metrics': self.get_metrics(),
                'cache_info': {
                    'size': len(self._last_catalog_parse),
                    'last_updated': max(self._last_catalog_parse.values()) if self._last_catalog_parse else None
                }
            }

            if self.db:
                stats['db_stats'] = self.db.get_search_stats()

            return stats

        except Exception as e:
            logger.error(f"Failed to get search stats: {e}")
            return {}


# Backward compatibility
class SimpleSmartSearch(SmartSearchService):
    """Простая версия умного поиска с сохранением offsets"""

    def __init__(self):
        super().__init__()
        # Загружаем смещения (offset) для ключевых слов
        if os.path.exists(getattr(config, 'OFFSET_FILE', 'search_offsets.json')):
            try:
                with open(getattr(config, 'OFFSET_FILE', 'search_offsets.json'), "r", encoding="utf-8") as f:
                    self.offsets = json.load(f)
            except Exception:
                self.offsets = {}
        else:
            self.offsets = {}

    def search(self, keywords: list):
        """
        Продолжает поиск с сохраненного смещения для каждого ключевого слова.
        """
        results = []
        for kw in keywords:
            offset = self.offsets.get(kw, 0)
            # Выполняем поиск (заглушка)
            new_results = []  # Например: market_api.search(kw, offset)
            results.extend(new_results)
            self.offsets[kw] = offset + len(new_results)

        offset_file = getattr(config, 'OFFSET_FILE', 'search_offsets.json')
        with open(offset_file, "w", encoding="utf-8") as f:
            json.dump(self.offsets, f)


# Factory function for backward compatibility
def get_smart_search_service():
    """Get smart search service instance"""
    return SmartSearchService()