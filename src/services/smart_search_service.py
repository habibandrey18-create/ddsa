# services/smart_search_service.py - Умный автопоиск с offset per keyword
import asyncio
import json
import os
import logging
import random
import re
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse, quote_plus
import aiohttp
import src.config as config
from src.utils.scraper import scrape_product_data, fetch_with_backoff
from src.core.database import get_postgres_db
from src.core.redis_cache import get_redis_cache

# Playwright for anti-bot bypass (fallback only)
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    async_playwright = None

logger = logging.getLogger(__name__)


class SimpleSmartSearch:
    """Простая версия умного поиска с сохранением offsets"""

    def __init__(self):
        # Загружаем смещения (offset) для ключевых слов
        if os.path.exists(config.OFFSET_FILE):
            with open(config.OFFSET_FILE, "r", encoding="utf-8") as f:
                self.offsets = json.load(f)
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
        with open(config.OFFSET_FILE, "w", encoding="utf-8") as f:
            json.dump(self.offsets, f)
        return results

class SmartSearchService:
    """Сервис умного автопоиска по каталогам (основной источник)"""

    # Каталоги и бренды - основной источник товаров
    # UPDATED: Using referral_products URLs as main source
    CATALOG_URLS = [
        # Главная страница referral products (основной источник)
        "https://market.yandex.ru/page/referral_products?generalContext=t%3DcprPage%3Bcpk%3Dreferral_products%3B&rs=eJwzEv7EKMDBKLDwEKsEg8bqk6waq46wAgA7hQYe",
        # Категория продукты (hid=91307)
        "https://market.yandex.ru/search?generalContext=t%3DcprPage%3Bcpk%3Dreferral_products%3B&searchContext=referral_products_ctx&rs=eJwzEv7EKMDBKLDwEKsEg8bqk6waq46wAgA7hQYe&clicked-on-nav-tree=1&page-key=referral_products&hid=91307",
        # Товары для дома (hid=90666)
        "https://market.yandex.ru/search?generalContext=t%3DcprPage%3Bcpk%3Dreferral_products%3B&searchContext=referral_products_ctx&rs=eJwzEv7EKMDBKLDwEKsEg8bqk6waq46wAgA7hQYe&clicked-on-nav-tree=1&page-key=referral_products&hid=90666",
        # Дополнительные источники для разнообразия
        "https://market.yandex.ru/catalog--naushniki/",
        "https://market.yandex.ru/catalog--smartfony/",
    ]

    # Playwright settings for anti-bot bypass
    PLAYWRIGHT_HEADERS = {
        "Accept-Language": "ru-RU,ru;q=0.9",
    }
    PLAYWRIGHT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

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
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={
                    "User-Agent": config.USER_AGENT or "Mozilla/5.0 (compatible; MarketBot/1.0)",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                    "Accept-Encoding": "gzip, deflate, br",
                }
            )
        return self._session

    async def close_session(self):
        """
        Закрыть HTTP сессию и сохранить кэш.
        FIXED: Added proper session cleanup to prevent connection leaks.
        """
        if self._session and not self._session.closed:
            await self._session.close()
            # Wait for connections to close gracefully
            await asyncio.sleep(0.25)
            self._session = None
            logger.info("SmartSearchService HTTP session closed")

        # Сохраняем кэш при shutdown
        self._save_parse_cache()

    async def crawl_catalogs(self, max_catalogs: int = 5) -> Tuple[int, int]:
        """
        Парсинг каталогов и брендов (основной источник товаров)

        Args:
            max_catalogs: Максимальное количество каталогов для обработки

        Returns:
            Tuple[int, int]: (added_products, skipped_products)
        """
        added = 0
        skipped = 0

        try:
            # Выбираем случайные каталоги для разнообразия
            selected_catalogs = random.sample(self.CATALOG_URLS, min(max_catalogs, len(self.CATALOG_URLS)))

            for catalog_url in selected_catalogs:
                try:
                    # Проверяем кэш времени последнего парсинга (минимум 30 минут)
                    import time
                    cache_key = catalog_url
                    now = time.time()
                    last_parse = self._last_catalog_parse.get(cache_key, 0)

                    if now - last_parse < 1800:  # 30 minutes
                        logger.debug(f"Skipping {catalog_url}, parsed recently")
                        continue

                    logger.info(f"Processing catalog: {catalog_url}")

                    # Проверяем shadow-ban паузу перед парсингом каталога
                    from src.services.shadow_ban_service import get_shadow_ban_service
                    shadow_ban_service = get_shadow_ban_service()
                    if not shadow_ban_service.can_continue_parsing():
                        logger.warning(f"Shadow-ban pause active, skipping catalog: {catalog_url}")
                        continue

                    # Получаем HTML страницы каталога
                    self.metrics['catalog_requests'] += 1
                    html = await self._fetch_catalog_page(catalog_url)
                    if not html:
                        self.metrics['catalog_errors'] += 1
                        logger.warning(f"Failed to fetch catalog: {catalog_url}")
                        continue

                    # Парсим товары (ограничиваем до 50 на каталог для оптимизации)
                    products = await self._parse_catalog_products(html, catalog_url)
                    
                    # Проверяем shadow-ban после парсинга (отключаем для referral_products)
                    if 'referral_products' not in catalog_url:
                        shadow_banned = shadow_ban_service.is_shadow_banned(len(products), len(html))
                        if shadow_banned:
                            shadow_ban_service.record_shadow_ban(
                                catalog_url=catalog_url,
                                products_count=len(products),
                                html_size=len(html)
                            )
                            self.metrics['shadow_ban_detected'] += 1
                            logger.warning(f"Shadow-ban detected for {catalog_url}, pausing")
                            continue  # Пропускаем этот каталог
                    
                    logger.info(f"Parsed {len(products)} products from {catalog_url.split('/')[-2]}")

                    # Обрабатываем найденные товары
                    catalog_added, catalog_skipped = await self._process_found_products(products, catalog_url)
                    added += catalog_added
                    skipped += catalog_skipped

                    # Обновляем кэш времени парсинга
                    import time
                    self._last_catalog_parse[cache_key] = time.time()

                    # КРИТИЧНАЯ ПАУЗА: имитация человеческого поведения
                    await asyncio.sleep(random.uniform(3.5, 7.5))

                except Exception as e:
                    logger.error(f"Error processing catalog {catalog_url}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error in crawl_catalogs: {e}")

        return added, skipped

    async def _process_found_products(self, products: List[Dict], source_url: str) -> Tuple[int, int]:
        """Обработка найденных товаров с валидацией и atomic dedup"""
        added = skipped = 0

        for p in products[:50]:  # Safety cap
            try:
                # Валидация продукта
                ok, reasons = await self._validate_product_for_queue(p)
                if not ok:
                    logger.info(f"Skip {p.get('market_id', 'unknown')} reasons={reasons}")
                    skipped += 1
                    continue

                # Atomic dedup check (race condition safe)
                market_id = p.get('market_id')
                if not market_id or not await self._mark_product_seen(market_id):
                    logger.info(f"Already seen or invalid: {market_id}")
                    skipped += 1
                    continue

                # Добавляем в очередь
                await self._enqueue_product(p, source_url)
                added += 1
                logger.debug(f"Enqueued {market_id}")

            except Exception as e:
                logger.warning(f"Error processing product {p.get('market_id', 'unknown')}: {e}")
                skipped += 1

        return added, skipped

    async def _mark_product_seen(self, market_id: str) -> bool:
        """Atomic проверка и маркировка товара как увиденного (race condition safe)"""
        if self.db and hasattr(self.db, 'mark_seen'):
            # Используем atomic операцию в БД
            return self.db.mark_seen(market_id)
        elif self.redis:
            # Используем Redis SET для дедупликации
            key = f"seen_products:{market_id}"
            return bool(self.redis.set(key, "1", ex=604800, nx=True))  # 7 дней, only if not exists
        else:
            # Fallback в памяти (не надежно при перезапуске)
            return True  # Всегда считаем новым

    async def _validate_product_for_queue(self, product: Dict) -> Tuple[bool, List[str]]:
        """Валидация продукта перед добавлением в очередь"""
        from src.services.post_service import is_product_valid
        return is_product_valid(product)

    async def _enqueue_product(self, product: Dict, source_url: str):
        """Добавление продукта в очередь публикации с ERID логированием"""
        try:
            from src.services.publish_service import get_publish_service
            from src.services.affiliate_service import get_affiliate_link

            # Генерируем affiliate ссылку с ERID
            from src.utils.correlation_id import get_correlation_id
            correlation_id = get_correlation_id() or "unknown"
            affiliate_url, erid = get_affiliate_link(product.get('url', ''), correlation_id=correlation_id)

            # Логируем ERID для отладки
            market_id = product.get('market_id')
            logger.info(f"Product {market_id} -> ERID {erid}, affiliate: {affiliate_url[:50]}...")

            publish_item = {
                'market_id': market_id,
                'title': product.get('title', ''),
                'url': affiliate_url,  # Affiliate ссылка с ERID
                'price': product.get('price'),
                'old_price': product.get('old_price'),
                'discount_percent': product.get('discount_percent', 0),
                'vendor': product.get('vendor'),
                'rating': product.get('rating'),
                'reviews_count': product.get('reviews_count', 0),
                'has_images': product.get('has_images', True),
                'source': 'catalog_search',
                'priority': 100,
                'erid': erid  # Сохраняем ERID для логов
            }

            publish_service = get_publish_service()
            success = publish_service.enqueue_product(publish_item)

            if success:
                logger.info(f"Successfully enqueued {market_id}")
            else:
                logger.warning(f"Failed to enqueue {market_id}")

        except Exception as e:
            market_id = product.get('market_id', 'unknown')
            logger.error(f"Failed to enqueue product {market_id}: {e}")

    async def _parse_catalog_products(self, html: str, url: str = "") -> List[Dict]:
        """Парсинг товаров из __NEXT_DATA__ в HTML каталога с упрощенной логикой"""
        # Проверка размера HTML для оптимизации
        if len(html) > 5_000_000:  # 5MB limit
            logger.warning(f"HTML too large ({len(html)} bytes), skipping parsing")
            return []

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')

            # Пытаемся __NEXT_DATA__ сначала
            next_data_script = soup.find('script', id='__NEXT_DATA__')
            if next_data_script:
                try:
                    data = json.loads(next_data_script.string)
                    items = self._extract_items_from_next_data(data)

                    products = []
                    for item in items:
                        if product := self._convert_item_to_product(item):
                            products.append(product)

                    if products:
                        logger.debug(f"Parsed {len(products)} products from __NEXT_DATA__")
                        return products

                except (json.JSONDecodeError, KeyError) as e:
                    logger.debug(f"__NEXT_DATA__ parsing failed: {e}")

            # Fallback к CSS парсингу
            logger.debug("Falling back to CSS parsing")
            return self._parse_catalog_fallback(html)

        except Exception as e:
            logger.error(f"Critical parsing error: {e}")
            return []

    def _extract_items_from_next_data(self, data: Dict) -> List[Dict]:
        """Извлечение товаров из структуры __NEXT_DATA__"""
        items = []

        try:
            # Путь: props.pageProps.initialState.search.results.items
            props = data.get('props', {})
            page_props = props.get('pageProps', {})
            initial_state = page_props.get('initialState', {})
            search = initial_state.get('search', {})
            results = search.get('results', {})
            items = results.get('items', [])

        except Exception as e:
            logger.warning(f"Failed to extract items from __NEXT_DATA__: {e}")

        return items

    def _convert_item_to_product(self, item: Dict) -> Optional[Dict]:
        """Преобразование item из __NEXT_DATA__ в формат продукта"""
        try:
            market_id = str(item.get('id', ''))
            if not market_id:
                return None

            slug = item.get('slug', '')
            title = item.get('title', '')

            # Цены
            prices = item.get('prices', {})
            price = prices.get('value')
            old_price = prices.get('oldValue')

            if not price or not isinstance(price, (int, float)):
                return None

            # Формируем URL
            if slug and market_id:
                url = f"https://market.yandex.ru/product--{slug}/{market_id}"
            else:
                return None

            return {
                'market_id': market_id,
                'title': title,
                'price': int(price),
                'old_price': int(old_price) if old_price else None,
                'rating': item.get('rating'),
                'reviews_count': item.get('reviewsCount', 0),
                'vendor': item.get('brand'),
                'url': url,
                'discount_percent': item.get('discount', 0),
                'has_images': True,
                'source': 'catalog'
            }

        except Exception as e:
            logger.warning(f"Error converting item to product: {e}")
            return None

    def _parse_catalog_fallback(self, html: str) -> List[Dict]:
        """Fallback парсинг с помощью CSS селекторов"""
        products = []

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')

            # Ищем карточки товаров
            product_cards = soup.find_all('article', attrs={'data-auto': 'snippet'})

            if getattr(config, 'DEBUG_MODE', False):
                logger.info(f"Found {len(product_cards)} product cards with CSS fallback")

            for card in product_cards[:20]:  # Ограничиваем до 20 товаров
                try:
                    product = self._parse_product_card(card)
                    if product:
                        products.append(product)
                except Exception as e:
                    logger.warning(f"Failed to parse product card: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error in CSS fallback parsing: {e}")

        return products

    def _parse_product_card(self, card) -> Optional[Dict]:
        """Парсинг отдельной карточки товара"""
        try:
            # Извлекаем market_id из data-product-id или ссылки
            market_id = card.get('data-product-id')
            if not market_id:
                link = card.find('a', href=True)
                if link:
                    href = link['href']
                    # Извлекаем ID из URL типа /product--slug/id
                    match = re.search(r'/(\d+)/?$', href)
                    if match:
                        market_id = match.group(1)

            if not market_id:
                return None

            # Название
            title_elem = card.find('h3') or card.find(attrs={'data-auto': 'snippet-title'})
            title = title_elem.get_text().strip() if title_elem else 'Без названия'

            # Цена
            price_elem = card.find(attrs={'data-auto': 'snippet-price-current'})
            price = 0
            if price_elem:
                price_text = re.sub(r'[^\d]', '', price_elem.get_text())
                price = int(price_text) if price_text.isdigit() else 0

            # Старая цена
            old_price_elem = card.find(attrs={'data-auto': 'snippet-price-old'})
            old_price = None
            if old_price_elem:
                old_price_text = re.sub(r'[^\d]', '', old_price_elem.get_text())
                old_price = int(old_price_text) if old_price_text.isdigit() else None

            # Рейтинг
            rating_elem = card.find(attrs={'data-auto': 'rating'})
            rating = None
            if rating_elem:
                rating_text = rating_elem.get_text().strip()
                try:
                    rating = float(rating_text)
                except ValueError:
                    pass

            # Отзывы
            reviews_elem = card.find(attrs={'data-auto': 'reviews'})
            reviews_count = 0
            if reviews_elem:
                reviews_text = re.sub(r'[^\d]', '', reviews_elem.get_text())
                reviews_count = int(reviews_text) if reviews_text.isdigit() else 0

            # Бренд
            vendor_elem = card.find(attrs={'data-auto': 'snippet-vendor'})
            vendor = vendor_elem.get_text().strip() if vendor_elem else None

            # URL
            link_elem = card.find('a', href=True)
            url = f"https://market.yandex.ru{link_elem['href']}" if link_elem else ''

            return {
                'market_id': str(market_id),
                'title': title,
                'price': price,
                'old_price': old_price,
                'rating': rating,
                'reviews_count': reviews_count,
                'vendor': vendor,
                'url': url,
                'discount_percent': 0,
                'has_images': True,
                'source': 'catalog_fallback'
            }

        except Exception as e:
            logger.warning(f"Error parsing product card: {e}")
            return None

    async def _fetch_catalog_page(self, url: str) -> Optional[str]:
        """
        Получить HTML страницы каталога с оптимизированными headers и semaphore.
        FIXED: Added distributed rate limiting to prevent IP bans.
        """
        async with self._semaphore:  # Ограничение concurrency
            try:
                # FIXED: Apply rate limiting before request
                from src.services.distributed_rate_limiter import get_yandex_catalog_limiter
                limiter = get_yandex_catalog_limiter()
                await limiter.acquire()
                
                session = await self.get_session()
                html = await fetch_with_backoff(url, session, max_attempts=3, headers=self.PLAYWRIGHT_HEADERS)

                if not html:
                    logger.warning(f"HTTP fetch failed for {url}")
                    return None

                if getattr(config, 'DEBUG_MODE', False):
                    logger.debug(f"Fetched {len(html)} chars from {url}")

                return html

            except Exception as e:
                logger.error(f"Error fetching {url}: {e}")
                return None

    async def _run_smart_search(self, key_text: str, start_page: int = 1, max_pages: int = 10) -> Tuple[int, int]:
        """
        Выполнить умный поиск по ключевому слову

        Args:
            key_text: Ключевое слово для поиска
            start_page: Стартовая страница
            max_pages: Максимум страниц для обработки

        Returns:
            Tuple (added, skipped)
        """
        added = 0
        skipped = 0

        logger.info(f"Starting smart search for '{key_text}' from page {start_page}")

        try:
            # Обрабатываем несколько страниц
            for page_num in range(start_page, start_page + max_pages):
                page_added, page_skipped = await self._process_search_page(key_text, page_num)
                added += page_added
                skipped += page_skipped

                # Обновляем состояние поиска
                if self.db:
                    self.db.update_search_key(key_text, last_page=page_num)

                # Небольшая пауза между страницами
                await asyncio.sleep(random.uniform(1, 3))

                # Если на странице не найдено товаров, возможно конец поиска
                if page_added == 0 and page_num > start_page + 1:
                    logger.info(f"No products found on page {page_num} for '{key_text}', stopping search")
                    break

            logger.info(f"Smart search for '{key_text}' completed: added={added}, skipped={skipped}")
            return added, skipped

        except Exception as e:
            logger.error(f"Failed smart search for '{key_text}': {e}")
            return 0, 0

    async def _process_search_page(self, key_text: str, page_num: int) -> Tuple[int, int]:
        """
        Обработать одну страницу поиска

        Args:
            key_text: Ключевое слово
            page_num: Номер страницы

        Returns:
            Tuple[int, int]: (added_products, skipped_products)
        """
        try:
            # Формируем URL страницы поиска
            search_url = self._build_search_url(key_text, page_num)

            # Используем fetch_with_backoff для надежных запросов
            from src.utils.scraper import fetch_with_backoff
            session = await self.get_session()
            html = await fetch_with_backoff(search_url, session, max_attempts=3)

            if not html:
                logger.warning(f"Failed to fetch search page {page_num} for '{key_text}' after retries")
                return 0, 0

            # Проверяем что HTML не пустой
            if len(html.strip()) < 100:
                logger.warning(f"HTML too short ({len(html)} chars) for page {page_num}")
                return 0, 0

            products = self._extract_products_from_search(html, search_url)

            if getattr(config, 'DEBUG_MODE', False):
                logger.info(f"Downloaded HTML: {len(html)} chars, parsed products: {len(products)}")

            added = 0
            skipped = 0

            for product in products:
                try:
                    # Проверяем дедупликацию
                    product_key = self._generate_product_key(product)
                    if self.redis and self.redis.is_product_seen_recently(product_key):
                        skipped += 1
                        continue

                    # Сохраняем товар в базу
                    await self._save_product_to_database(product)

                    # Помечаем как увиденный
                    if self.redis:
                        self.redis.mark_product_seen(product_key)

                    # Добавляем в очередь публикации
                    await self._enqueue_for_publishing(product)

                    added += 1

                except Exception as e:
                    logger.error(f"Failed to process product {product.get('title', 'Unknown')}: {e}")
                    skipped += 1

                if getattr(config, 'DEBUG_MODE', False):
                    logger.info(f"Processed page {page_num} for '{key_text}': found={len(products)}, added={added}, skipped={skipped}")
                else:
                    logger.debug(f"Processed page {page_num} for '{key_text}': found={len(products)}, added={added}, skipped={skipped}")
                return added, skipped

        except Exception as e:
            logger.error(f"Failed to process search page {page_num} for '{key_text}': {e}")
            return 0, 0

    def _build_search_url(self, key_text: str, page_num: int) -> str:
        """Построить URL страницы поиска"""
        base_url = "https://market.yandex.ru/search"

        # Убираем двойное кодирование - используем обычный UTF-8
        params = {
            "text": key_text,  # Не кодируем, aiohttp сделает это правильно
        }

        # Упрощаем для тестирования - убираем дополнительные параметры
        # которые могут вызывать 400 ошибку
        # if page_num == 1:
        #     params.update({
        #         "delivery-interval": "1",  # Доставка в день заказа
        #         "onstock": "1",  # В наличии
        #     })

        query_string = urlencode(params, doseq=True)
        final_url = f"{base_url}?{query_string}"

        if getattr(config, 'DEBUG_MODE', False):
            logger.info(f"Generated search URL: {final_url}")
        else:
            logger.debug(f"Generated search URL: {final_url}")

        return final_url

    def _extract_products_from_search(self, html: str, url: str = "") -> List[Dict]:
        """
        Извлечь товары из HTML страницы поиска
        
        Args:
            html: HTML содержимое страницы
            url: URL страницы (для логирования shadow-ban)
        """
        products = []

        try:
            if getattr(config, 'DEBUG_MODE', False):
                logger.info(f"HTML length: {len(html)} chars")

            # Используем BeautifulSoup для парсинга современной структуры Yandex.Market
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, 'lxml')
            except ImportError:
                logger.warning("BeautifulSoup not available, falling back to regex")
                return self._extract_products_fallback(html)

            # Ищем элементы с data-zone-name="productSnippet"
            product_snippets = soup.find_all(attrs={'data-zone-name': 'productSnippet'})

            if getattr(config, 'DEBUG_MODE', False):
                logger.info(f"Found {len(product_snippets)} productSnippet elements")

            for snippet in product_snippets:
                try:
                    product_data = self._parse_product_snippet(snippet)
                    if product_data:
                        products.append(product_data)
                except Exception as e:
                    logger.warning(f"Failed to parse product snippet: {e}")

            # 2. Пробуем JSON-LD структурированные данные
            if len(products) < 10:
                json_products = self._extract_products_from_json_ld(soup)
                if json_products:
                    products.extend(json_products)
                    if getattr(config, 'DEBUG_MODE', False):
                        logger.info(f"Added {len(json_products)} products from JSON-LD")

            # 3. Пробуем window.__STATE__ (дополнительный источник)
            if len(products) < 10:
                state_products = self._parse_window_state(html)
                if state_products:
                    products.extend(state_products)
                    if getattr(config, 'DEBUG_MODE', False):
                        logger.info(f"Added {len(state_products)} products from window.__STATE__")

            # 4. Fallback на CSS селекторы
            if len(products) < 10:
                if getattr(config, 'DEBUG_MODE', False):
                    logger.info("Few products found, using CSS fallback")
                fallback_products = self._extract_products_fallback(html)
                products.extend(fallback_products)

            # КРИТИЧНАЯ ПРОВЕРКА: детектор shadow-ban с auto-pause
            from src.services.shadow_ban_service import get_shadow_ban_service
            shadow_ban_service = get_shadow_ban_service()
            
            # Проверяем, можно ли продолжать (не активна ли пауза)
            if not shadow_ban_service.can_continue_parsing():
                logger.warning("Shadow-ban pause active, skipping parsing")
                return []
            
            shadow_banned = shadow_ban_service.is_shadow_banned(len(products), len(html))
            too_few_products = len(products) < 5

            if shadow_banned:
                # Записываем shadow-ban и устанавливаем паузу
                shadow_ban_service.record_shadow_ban(
                    catalog_url=url or "unknown",
                    products_count=len(products),
                    html_size=len(html)
                )
                self.metrics['shadow_ban_detected'] += 1
                logger.warning("Shadow-ban detected, pausing parsing for several hours")
                return []  # Прекращаем парсинг, пауза установлена
            
            if too_few_products:
                # Мало товаров - Playwright fallback обрабатывается на уровне crawl_catalogs
                logger.warning(f"Only {len(products)} products found, Playwright fallback needed")
                return []

            if getattr(config, 'DEBUG_MODE', False):
                logger.info(f"Extracted {len(products)} products total")

        except Exception as e:
            logger.error(f"Failed to extract products from search HTML: {e}")
            return []

        return products

    def _parse_product_snippet(self, snippet) -> Optional[Dict]:
        """Парсинг одного productSnippet элемента"""
        import re
        try:
            # Извлекаем данные из data-zone-data атрибута (JSON)
            zone_data = snippet.get('data-zone-data')
            if zone_data:
                import json
                data = json.loads(zone_data)

                # Структура данных может быть разной, адаптируемся
                product_info = data.get('product', data)

                return {
                    'id': str(product_info.get('id', product_info.get('marketId', 'unknown'))),
                    'market_id': str(product_info.get('id', product_info.get('marketId', 'unknown'))),
                    'title': product_info.get('title', product_info.get('name', 'Без названия')),
                    'price': product_info.get('price', product_info.get('offer', {}).get('price', 0)),
                    'url': product_info.get('url', product_info.get('link', '')),
                    'vendor': product_info.get('vendor', product_info.get('brand', 'Unknown')),
                    'rating': product_info.get('rating', 0),
                    'reviews_count': product_info.get('reviewsCount', 0),
                    'has_images': bool(product_info.get('images', [])),
                    'discount_percent': product_info.get('discount', 0)
                }

            # Fallback: парсим HTML структуру
            title_elem = snippet.find(['h3', 'h4'], class_=re.compile(r'.*title.*', re.I))
            title = title_elem.get_text().strip() if title_elem else 'Без названия'

            price_elem = snippet.find(attrs={'data-auto': 'price-value'})
            price = 0
            if price_elem:
                price_text = price_elem.get_text().strip()
                # Извлекаем цифры из цены
                import re
                price_match = re.search(r'(\d[\d\s]*)(?:\s*₽)?', price_text.replace(' ', ''))
                if price_match:
                    price = int(price_match.group(1).replace(' ', ''))

            url_elem = snippet.find('a', href=True)
            url = url_elem['href'] if url_elem else ''

            return {
                'id': f'parsed_{hash(title) % 10000}',
                'market_id': f'parsed_{hash(title) % 10000}',
                'title': title,
                'price': price,
                'url': url if url.startswith('http') else f'https://market.yandex.ru{url}',
                'vendor': 'Unknown',
                'rating': 0,
                'reviews_count': 0,
                'has_images': False,
                'discount_percent': 0
            }

        except Exception as e:
            logger.warning(f"Failed to parse product snippet: {e}")
            return None

    def _extract_products_from_json_ld(self, soup) -> List[Dict]:
        """Извлечение товаров из JSON-LD структурированных данных"""
        products = []

        try:
            json_scripts = soup.find_all('script', type='application/ld+json')

            for script in json_scripts:
                try:
                    import json
                    data = json.loads(script.string)

                    if isinstance(data, dict) and data.get('@type') == 'Product':
                        # Это страница товара, а не поиска
                        continue
                    elif isinstance(data, list):
                        # Массив товаров
                        for item in data:
                            if isinstance(item, dict) and item.get('@type') == 'Product':
                                product = {
                                    'id': f'jsonld_{hash(item.get("name", "")) % 10000}',
                                    'market_id': f'jsonld_{hash(item.get("name", "")) % 10000}',
                                    'title': item.get('name', 'Без названия'),
                                    'price': 0,  # JSON-LD может не содержать цены
                                    'url': item.get('url', ''),
                                    'vendor': 'Unknown',
                                    'rating': item.get('aggregateRating', {}).get('ratingValue', 0),
                                    'reviews_count': item.get('aggregateRating', {}).get('reviewCount', 0),
                                    'has_images': bool(item.get('image')),
                                    'discount_percent': 0
                                }
                                products.append(product)

                except (json.JSONDecodeError, AttributeError):
                    continue

        except Exception as e:
            logger.warning(f"Failed to extract products from JSON-LD: {e}")

        return products

    def _extract_products_fallback(self, html: str) -> List[Dict]:
        """Fallback парсер на основе регулярных выражений"""
        products = []

        try:
            # Простой поиск по заголовкам товаров
            title_pattern = r'<h3[^>]*class="[^"]*title[^"]*"[^>]*>([^<]*)</h3>'
            titles = re.findall(title_pattern, html, re.IGNORECASE)

            # В ПРОДАКШЕНЕ mock товары ЗАПРЕЩЕНЫ!
            # Они могут привести к публикации несуществующих товаров
            if not titles:
                logger.warning("No real products found in HTML fallback - possible shadow-ban or parsing error")
                # НЕ создаем mock товары в продакшене

            # Если нашли заголовки, создаем товары
            for i, title in enumerate(titles[:10]):
                products.append({
                    'id': f'extracted_{i}',
                    'market_id': f'extracted_{i}',
                    'title': title.strip(),
                    'price': 1000,
                    'url': f'https://market.yandex.ru/search?title={title.strip()}',
                    'vendor': 'Unknown',
                    'rating': 4.0,
                    'reviews_count': 10,
                    'has_images': False,
                    'discount_percent': 0
                })

        except Exception as e:
            logger.error(f"Fallback extraction failed: {e}")

        return products

    def _parse_product_block(self, product_id: str, html_block: str) -> Optional[Dict]:
        """Распарсить блок товара"""
        try:
            product_data = {
                'id': product_id,
                'market_id': product_id,
            }

            # Извлекаем название
            title_match = re.search(r'<h3[^>]*>([^<]*)</h3>', html_block, re.IGNORECASE)
            if title_match:
                product_data['title'] = title_match.group(1).strip()

            # Извлекаем URL
            url_match = re.search(r'href="([^"]*?product[^"]*?)"', html_block)
            if url_match:
                product_data['url'] = f"https://market.yandex.ru{url_match.group(1)}"

            # Извлекаем цену
            price_match = re.search(r'(\d[\d\s]*?)₽', html_block)
            if price_match:
                price_str = price_match.group(1).replace(' ', '')
                try:
                    product_data['price'] = float(price_str)
                except ValueError:
                    pass

            # Извлекаем старую цену и скидку
            old_price_match = re.search(r'<s[^>]*>(\d[\d\s]*?)₽</s>', html_block)
            if old_price_match:
                old_price_str = old_price_match.group(1).replace(' ', '')
                try:
                    product_data['old_price'] = float(old_price_str)
                    if 'price' in product_data and product_data['old_price'] > product_data['price']:
                        discount = (product_data['old_price'] - product_data['price']) / product_data['old_price'] * 100
                        product_data['discount_percent'] = round(discount, 1)
                except ValueError:
                    pass

            # Извлекаем рейтинг
            rating_match = re.search(r'rating[^>]*>(\d\.\d)', html_block)
            if rating_match:
                try:
                    product_data['rating'] = float(rating_match.group(1))
                except ValueError:
                    pass

            # Извлекаем количество отзывов
            reviews_match = re.search(r'(\d+)\s*отзыв', html_block)
            if reviews_match:
                try:
                    product_data['reviews_count'] = int(reviews_match.group(1))
                except ValueError:
                    pass

            # Извлекаем бренд/производителя
            vendor_match = re.search(r'<span[^>]*class="[^"]*brand[^"]*"[^>]*>([^<]*)</span>', html_block, re.IGNORECASE)
            if vendor_match:
                product_data['vendor'] = vendor_match.group(1).strip()

            # Извлекаем offerid из URL
            if 'url' in product_data:
                parsed_url = urlparse(product_data['url'])
                query_params = parse_qs(parsed_url.query)
                if 'offerid' in query_params:
                    product_data['offerid'] = query_params['offerid'][0]

            # Проверяем наличие картинок
            if '<img' in html_block:
                product_data['has_images'] = True
            else:
                product_data['has_images'] = False

            return product_data

        except Exception as e:
            logger.error(f"Failed to parse product block {product_id}: {e}")
            return None

    def _generate_product_key(self, product: Dict) -> str:
        """
        FIXED: Now uses utils.product_key.generate_product_key (single source of truth).
        This prevents deduplication failures from inconsistent key generation.
        
        Previously had different normalization logic than database.py → same product
        got different keys → deduplication failed!
        """
        from src.utils.product_key import generate_product_key
        
        return generate_product_key(
            title=product.get('title', ''),
            vendor=product.get('vendor', ''),
            offerid=product.get('offerid', ''),
            url=product.get('url', ''),
            market_id=product.get('market_id') or product.get('id', '')
        )

    async def _save_product_to_database(self, product: Dict):
        """Сохранить товар в базу данных"""
        try:
            # Проверяем доступность базы данных
            if not self.db:
                logger.debug("Database not available, skipping product save")
                return
            # Преобразуем данные для сохранения
            db_product = {
                'id': product['market_id'],
                'url': product.get('url', ''),
                'title': product.get('title', ''),
                'vendor': product.get('vendor'),
                'offerid': product.get('offerid'),
                'price': product.get('price'),
                'old_price': product.get('old_price'),
                'discount_percent': product.get('discount_percent'),
                'rating': product.get('rating'),
                'reviews_count': product.get('reviews_count'),
                'availability': True,  # По умолчанию считаем доступным
                'images': [],  # Пока пустой массив
                'specs': {},
                'marketing_description': None,
            }

            self.db.save_product(db_product)

            # Сохраняем историю цен если есть цена
            if product.get('price'):
                self.db.save_price_history(
                    product['market_id'],
                    product['price'],
                    product.get('old_price'),
                    product.get('discount_percent')
                )

        except Exception as e:
            logger.error(f"Failed to save product {product.get('title', 'Unknown')}: {e}")
            raise

    async def _enqueue_for_publishing(self, product: Dict):
        """Добавить товар в очередь публикации с дедупликацией"""
        try:
            market_id = product.get('market_id')
            if not market_id:
                logger.warning("Cannot enqueue product without market_id")
                return

            # Дедупликация: проверяем, не видели ли мы этот товар недавно
            if self.redis:
                if self.redis.is_product_seen_recently(market_id, ttl_seconds=86400):  # 24 часа
                    logger.debug(f"Skipping duplicate product (seen recently): {market_id}")
                    return

                # Помечаем товар как увиденный
                self.redis.mark_product_seen(market_id, ttl_seconds=86400)

            # Определяем приоритет
            priority = 100  # Обычный приоритет

            # Проверяем на price alert (только если есть база данных)
            if self.db and product.get('price') and product.get('old_price'):
                min_price_30 = self.db.get_min_price_last_days(product['market_id'], days=30)
                if min_price_30 and product['price'] <= min_price_30 * 0.9:  # Цена на 10% ниже минимума за 30 дней
                    priority = 200  # Высокий приоритет для price alerts
                    logger.info(f"Price alert triggered for {product.get('title', 'Unknown')}: current={product['price']}, min_30={min_price_30}")

            if self.redis:
                # Добавляем дополнительные данные для публикации
                publish_item = {
                    'market_id': product['market_id'],
                    'title': product.get('title', ''),
                    'url': product.get('url', ''),
                    'price': product.get('price'),
                    'old_price': product.get('old_price'),
                    'discount_percent': product.get('discount_percent'),
                    'vendor': product.get('vendor'),
                    'rating': product.get('rating'),
                    'reviews_count': product.get('reviews_count'),
                    'has_images': product.get('has_images', False),
                    'source': 'smart_search',
                    'search_key': None,  # Можно добавить позже
                    'priority': priority,
                    'created_at': None,  # Redis сам добавит timestamp
                }

                self.redis.enqueue_publish_item(publish_item, priority)
                logger.debug(f"Enqueued product for publishing: {product.get('title', 'Unknown')} (priority={priority})")

        except Exception as e:
            logger.error(f"Failed to enqueue product for publishing: {e}")

    async def run_smart_search_cycle(self, max_catalogs: int = 5):
        """
        Запустить цикл поиска по каталогам (основной источник товаров)

        Args:
            max_catalogs: Максимум каталогов для обработки
        """
        logger.info(f"Starting catalog search cycle (max {max_catalogs} catalogs)")

        # Используем каталоги вместо ключевых слов
        total_added, total_skipped = await self.crawl_catalogs(max_catalogs)

        logger.info(f"Smart search cycle completed: total_added={total_added}, total_skipped={total_skipped}")

        return {
            'total_added': total_added,
            'total_skipped': total_skipped,
            'catalogs_processed': max_catalogs
        }

    async def reset_search_state(self, key_text: str = None):
        """Сбросить состояние поиска (для тестирования или перезапуска)"""
        try:
            if not self.db:
                logger.warning("Database not available, cannot reset search state")
                return

            if key_text:
                # Сбрасываем конкретное ключевое слово
                self.db.update_search_key(key_text, last_page=0, last_offset=0)
                logger.info(f"Reset search state for '{key_text}'")
            else:
                # TODO: Сбросить все если нужно
                logger.warning("Reset all search states not implemented yet")
        except Exception as e:
            logger.error(f"Failed to reset search state: {e}")

    async def get_search_stats(self) -> Dict:
        """Получить статистику поиска"""
        try:
            # TODO: Добавить статистику из базы данных
            if self.redis:
                return {
                    'publish_queue_size': self.redis.get_publish_queue_size(),
                    'redis_health': self.redis.health_check(),
                }
            else:
                return {'redis_disabled': True}
        except Exception as e:
            logger.error(f"Failed to get search stats: {e}")
            return {}

    def _parse_window_state(self, html: str) -> List[Dict]:
        """Парсинг товаров из window.__STATE__"""
        products = []

        try:
            # Ищем window.__STATE__ в HTML
            import re
            state_match = re.search(r'window\.__STATE__\s*=\s*({.+?});', html, re.DOTALL)
            if not state_match:
                return products

            import json
            state_data = json.loads(state_match.group(1))

            # Ищем товары в разных возможных местах
            search_data = state_data.get('search', {})
            results = search_data.get('results', {})
            items = results.get('items', [])

            for item in items:
                try:
                    product = self._convert_item_to_product(item)
                    if product:
                        products.append(product)
                except Exception as e:
                    logger.warning(f"Failed to convert window.__STATE__ item: {e}")

        except Exception as e:
            logger.warning(f"Failed to parse window.__STATE__: {e}")

        return products

    def _is_shadow_banned(self, products_count: int, html_size: int) -> bool:
        """
        Детектор shadow-ban от Yandex (использует ShadowBanService)
        """
        from src.services.shadow_ban_service import get_shadow_ban_service
        service = get_shadow_ban_service()
        return service.is_shadow_banned(products_count, html_size)

    async def _fetch_market_catalog_playwright(self, url: str) -> List[Dict]:
        """
        Playwright fallback для обхода анти-бот защиты Yandex.
        Использовать ТОЛЬКО когда обычный HTTP не работает.
        """
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("Playwright not available, skipping browser fallback")
            return []

        try:
            logger.info(f"Using Playwright fallback for: {url}")

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,  # В проде True для экономии ресурсов
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                    ]
                )

                context = await browser.new_context(
                    user_agent=self.PLAYWRIGHT_USER_AGENT,
                    locale="ru-RU",
                    extra_http_headers=self.PLAYWRIGHT_HEADERS,
                    viewport={"width": 1366, "height": 768},
                )

                page = await context.new_page()

                # FIXED: Reduced timeout from 60s to 15s (aggressive for production)
                # networkidle → domcontentloaded (faster, good enough for parsing)
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)

                # "Человеческая" пауза (reduced from 3s to 2s)
                await page.wait_for_timeout(2000)

                # Получаем HTML
                html = await page.content()
                await browser.close()

            # Парсим __NEXT_DATA__ из полученного HTML
            return self._parse_next_data_products(html)

        except Exception as e:
            logger.error(f"Playwright fallback failed for {url}: {e}")
            return []

    def _parse_next_data_products(self, html: str) -> List[Dict]:
        """Парсер __NEXT_DATA__ из HTML (улучшенная версия)"""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')

            script = soup.find("script", id="__NEXT_DATA__")
            if not script:
                logger.warning("__NEXT_DATA__ script not found")
                return []

            data = json.loads(script.string)

            # Путь к товарам (может меняться, но этот сейчас рабочий)
            try:
                items = (
                    data["props"]["pageProps"]
                    ["initialState"]["search"]["results"]["items"]
                )
            except KeyError:
                logger.warning("Items path not found in __NEXT_DATA__")
                return []

            products = []
            for item in items:
                try:
                    # Адаптируем под реальную структуру данных Yandex
                    market_id = str(item.get("id", ""))
                    if not market_id:
                        continue

                    # Разные варианты получения данных
                    title = item.get("titles", {}).get("raw") or item.get("title", "")
                    if not title:
                        continue

                    prices = item.get("prices", {})
                    price = prices.get("value")
                    if not price:
                        continue

                    product = {
                        'market_id': market_id,
                        'title': title,
                        'price': int(price),
                        'old_price': prices.get("oldValue"),
                        'rating': item.get('rating'),
                        'reviews_count': item.get('reviewsCount', 0),
                        'vendor': item.get('vendor'),
                        'url': f"https://market.yandex.ru/product--{item.get('slug', '')}/{market_id}",
                        'discount_percent': item.get('discount', 0),
                        'has_images': True,
                        'source': 'playwright_fallback'
                    }
                    products.append(product)

                except Exception as e:
                    logger.warning(f"Failed to parse Playwright item: {e}")
                    continue

            logger.info(f"Playwright parsed {len(products)} products from __NEXT_DATA__")
            return products

        except Exception as e:
            logger.error(f"Failed to parse __NEXT_DATA__: {e}")
            return []


# Глобальный экземпляр
_smart_search_service = None

def get_smart_search_service():
    """Get global smart search service instance"""
    global _smart_search_service
    if _smart_search_service is None:
        _smart_search_service = SmartSearchService()
    return _smart_search_service
