# services/search/search_engine.py
"""
Search engine functionality for smart search service.
Handles search URL building and search page processing.
"""
import asyncio
import logging
import random
from typing import Tuple
from urllib.parse import urlencode

import src.config as config
from src.utils.scraper import fetch_with_backoff

logger = logging.getLogger(__name__)


class SearchEngineMixin:
    """Mixin class for search engine functionality."""

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
