"""
Scrape Service - безопасный скрап с ретраями и типизированными ошибками
"""

import asyncio
import logging
from typing import Dict, Any, Optional
import aiohttp

from utils.scraper import scrape_yandex_market
import database

logger = logging.getLogger(__name__)


class ScrapeError(Exception):
    """Базовый класс для ошибок скрапа"""

    pass


class ScrapeTimeoutError(ScrapeError):
    """Таймаут при скрапе"""

    pass


class ScrapeNetworkError(ScrapeError):
    """Сетевая ошибка при скрапе"""

    pass


class ScrapeParseError(ScrapeError):
    """Ошибка парсинга данных"""

    pass


async def safe_scrape_with_retry(
    url: str,
    max_attempts: int = 3,
    correlation_id: Optional[str] = None,
    use_cache: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Безопасный скрап с ретраями и типизированными ошибками.
    Автоматически использует Playwright fallback при невыдаче данных.

    Args:
        url: URL для скрапа
        max_attempts: Максимальное количество попыток
        correlation_id: ID для корреляции логов
        use_cache: Использовать ли кэш

    Returns:
        Данные товара или None при ошибке
    """
    correlation_id = correlation_id or "unknown"

    # Проверяем кэш
    if use_cache:
        db = database.Database()
        cached = db.get_cached_data(url, max_age_hours=24)
        if cached:
            logger.info(
                "safe_scrape_with_retry: using cached data for %s (correlation_id=%s)",
                url,
                correlation_id,
            )
            return cached

    # Скрапим с ретраями и автоматическим fallback на Playwright
    last_error = None
    error_type = None
    used_playwright = False

    for attempt in range(max_attempts):
        try:
            # Сначала пытаемся получить данные через HTTP
            data = await scrape_yandex_market(url)
            if data and data.get("title"):
                # Записываем успешный парсинг
                from services.monitoring_service import record_parsing_attempt
                record_parsing_attempt(url, success=True)

                # Сохраняем в кэш
                if use_cache:
                    db = database.Database()
                    db.set_cached_data(url, data)
                if used_playwright:
                    logger.info(
                        "safe_scrape_with_retry: Playwright fallback succeeded for %s (correlation_id=%s)",
                        url,
                        correlation_id,
                    )
                return data
            else:
                # Записываем неудачный парсинг
                from services.monitoring_service import record_parsing_attempt
                record_parsing_attempt(url, success=False)

                # Данные получены, но некорректные - возможно SPA или бан
                error_type = "parse_error"
                last_error = ValueError("Scraped data is invalid or missing title - trying Playwright fallback")

                # Пытаемся через Playwright fallback
                logger.info(
                    "safe_scrape_with_retry: HTTP parsing failed, trying Playwright fallback for %s (correlation_id=%s)",
                    url,
                    correlation_id,
                )
                try:
                    from services.playwright_parser_service import get_playwright_parser

                    playwright_parser = get_playwright_parser()
                    # Пытаемся получить данные через Playwright для отдельного товара
                    playwright_data = await playwright_parser.parse_single_product(url)
                    if playwright_data and playwright_data.get("title"):
                        used_playwright = True
                        # Сохраняем в кэш
                        if use_cache:
                            db = database.Database()
                            db.set_cached_data(url, playwright_data)
                        return playwright_data
                    else:
                        logger.warning(
                            "safe_scrape_with_retry: Playwright returned no valid data for %s (correlation_id=%s)",
                            url,
                            correlation_id,
                        )
                except Exception as playwright_error:
                    logger.warning(
                        "safe_scrape_with_retry: Playwright fallback failed for %s (correlation_id=%s): %s",
                        url,
                        correlation_id,
                        str(playwright_error)[:200],
                    )

        except asyncio.TimeoutError as e:
            last_error = e
            error_type = "timeout"
            logger.warning(
                "safe_scrape_with_retry: timeout on attempt %d/%d for %s (correlation_id=%s)",
                attempt + 1,
                max_attempts,
                url,
                correlation_id,
            )

        except aiohttp.ClientError as e:
            last_error = e
            error_type = "network_error"
            logger.warning(
                "safe_scrape_with_retry: network error on attempt %d/%d for %s (correlation_id=%s): %s",
                attempt + 1,
                max_attempts,
                url,
                correlation_id,
                str(e)[:200],
            )

        except Exception as e:
            last_error = e
            error_type = "unknown_error"
            logger.warning(
                "safe_scrape_with_retry: error on attempt %d/%d for %s (correlation_id=%s): %s",
                attempt + 1,
                max_attempts,
                url,
                correlation_id,
                str(e)[:200],
            )

        # Exponential backoff перед следующей попыткой
        if attempt < max_attempts - 1:
            wait_time = 2**attempt
            await asyncio.sleep(wait_time)

    # Все попытки исчерпаны
    logger.warning(
        "safe_scrape_with_retry: failed after %d attempts for %s (correlation_id=%s, error_type=%s, error=%s)",
        max_attempts,
        url,
        correlation_id,
        error_type,
        str(last_error)[:200] if last_error else "unknown",
    )

    return None


async def get_product_data(
    url: str,
    url_info,  # MarketUrlInfo или Dict[str, Any] для обратной совместимости
    retry_count: int = 3,
    correlation_id: Optional[str] = None,
    use_cache: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Получение данных товара с учётом типа URL

    Args:
        url: Исходный URL
        url_info: Информация о URL (MarketUrlInfo от normalize_market_url или Dict от UrlService.parse_url)
        retry_count: Количество попыток
        correlation_id: ID для корреляции логов
        use_cache: Использовать ли кэш

    Returns:
        Данные товара или None
    """
    correlation_id = correlation_id or "unknown"

    # Поддержка как MarketUrlInfo, так и Dict для обратной совместимости
    from utils.url_normalizer import MarketUrlInfo

    # Определяем URL для скрапа
    if isinstance(url_info, MarketUrlInfo):
        scrape_url = url_info.card_url or url
        is_cc = url_info.is_cc_url
    else:
        # Обратная совместимость со словарем
        scrape_url = url_info.get("normalized_card_url") or url
        is_cc = url_info.get("is_cc", False)

    # Если это cc-ссылка, пытаемся получить card-URL через редирект
    if (
        is_cc
    ):  # Сначала проверяем, есть ли уже card_url в url_info (от normalize_market_url)
        # Но только если это действительно card-URL, а не cc-ссылка или None
        if (
            isinstance(url_info, MarketUrlInfo)
            and url_info.card_url
            and "/cc/" not in url_info.card_url
        ):
            scrape_url = url_info.card_url
            logger.info(
                "get_product_data: using card_url from url_info: %s (correlation_id=%s)",
                scrape_url,
                correlation_id,
            )
        else:
            # Если card_url нет или это cc-ссылка, пытаемся разрешить через редирект
            try:
                from utils.scraper import resolve_final_url

                resolved_url = await resolve_final_url(url)
                # Если resolve_final_url вернул ya.cc, пытаемся разрешить через Playwright
                if resolved_url and "ya.cc" in resolved_url:
                    logger.info(
                        "get_product_data: resolve_final_url returned ya.cc, trying Playwright: %s (correlation_id=%s)",
                        resolved_url,
                        correlation_id,
                    )
                    try:
                        from playwright.async_api import async_playwright
                        import asyncio

                        async with async_playwright() as p:
                            browser = await p.chromium.launch(headless=True)
                            page = await browser.new_page()
                            # Используем load вместо networkidle, так как ya.cc может использовать JavaScript для редиректа
                            await page.goto(
                                resolved_url, wait_until="load", timeout=30000
                            )
                            # Ждем дополнительное время для выполнения JavaScript редиректов
                            await asyncio.sleep(2)
                            # Проверяем, произошел ли редирект
                            final_url = page.url
                            # Если все еще ya.cc, ждем еще и проверяем снова
                            if "ya.cc" in final_url:
                                await asyncio.sleep(3)
                                final_url = page.url
                            await browser.close()
                            if "/card/" in final_url or "/product/" in final_url:
                                resolved_url = final_url
                                logger.info(
                                    "get_product_data: resolved ya.cc via Playwright: %s -> %s (correlation_id=%s)",
                                    resolved_url[:100],
                                    final_url[:100],
                                    correlation_id,
                                )
                            else:
                                logger.warning(
                                    "get_product_data: Playwright also returned non-card URL: %s (correlation_id=%s)",
                                    final_url[:100],
                                    correlation_id,
                                )
                    except Exception as playwright_error:
                        logger.warning(
                            "get_product_data: Playwright fallback failed: %s (correlation_id=%s)",
                            str(playwright_error)[:200],
                            correlation_id,
                        )

                if resolved_url and (
                    "/card/" in resolved_url or "/product/" in resolved_url
                ):
                    scrape_url = resolved_url
                    logger.info(
                        "get_product_data: resolved cc/ to card/ URL: %s -> %s (correlation_id=%s)",
                        url,
                        scrape_url,
                        correlation_id,
                    )
                else:
                    logger.error(
                        "get_product_data: CRITICAL - could not resolve cc/ URL to card/, cannot scrape (correlation_id=%s)",
                        correlation_id,
                    )
                    # Не пытаемся скрапить cc-ссылку напрямую - это не работает
                    return None
            except Exception as e:
                logger.error(
                    "get_product_data: error resolving cc/ URL: %s (correlation_id=%s)",
                    e,
                    correlation_id,
                )
                return None  # Скрапим
    result = await safe_scrape_with_retry(
        scrape_url,
        max_attempts=retry_count,
        correlation_id=correlation_id,
        use_cache=use_cache,
    )
    return result
