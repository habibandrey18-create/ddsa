"""
URL Normalizer - централизованная нормализация URL Яндекс.Маркета
Разделяет card-URL и cc-URL, обрабатывает resolve_final_url один раз
"""

import logging
import re
from typing import Dict, Any, Optional, Tuple, List
from urllib.parse import urlparse, parse_qs
import asyncio

logger = logging.getLogger(__name__)


class MarketUrlInfo:
    """Информация о нормализованном URL"""

    def __init__(
        self,
        original_url: str,
        card_url: Optional[str],
        cc_from_url: Optional[str],
        flags: List[str],
        resolved_url: Optional[str] = None,
    ):
        self.original_url = original_url
        self.card_url = card_url  # Чистый card-URL для скрапа
        self.cc_from_url = cc_from_url  # CC код из исходного URL (если был)
        self.flags = flags  # Флаги: from_cc_link, ref_not_found, etc.
        self.resolved_url = resolved_url  # Результат resolve_final_url (если вызывался)

    @property
    def is_cc_url(self) -> bool:
        """Проверка, является ли исходный URL cc-ссылкой"""
        return self.cc_from_url is not None

    @property
    def has_partner_link(self) -> bool:
        """Проверка, есть ли партнёрская ссылка в исходном URL"""
        return self.cc_from_url is not None

    def get_partner_link(self) -> Optional[str]:
        """Возвращает партнёрскую ссылку, если она была в исходном URL"""
        if self.cc_from_url:
            return f"https://market.yandex.ru/cc/{self.cc_from_url}"
        return None


async def normalize_market_url(
    url: str, resolve_redirects: bool = True
) -> MarketUrlInfo:
    """
    Нормализует URL Яндекс.Маркета, разделяя card-URL и cc-URL.
    Вызывает resolve_final_url один раз при необходимости.

    Бизнес-логика:
    - Если входной URL уже содержит /cc/ код → возвращает его как cc_from_url,
      не генерирует новый, помечает флагом from_cc_link
    - Если входной URL - card-URL → возвращает его как card_url для скрапа
    - Если входной URL - cc-URL → вызывает resolve_final_url один раз для получения
      card-URL для скрапа, но сохраняет исходный cc-код

    Args:
        url: Исходный URL
        resolve_redirects: Вызывать ли resolve_final_url для cc-URL

    Returns:
        MarketUrlInfo с нормализованными данными
    """
    original_url = url.strip()
    flags: List[str] = []

    # Шаг 1: Извлечение CC кода из исходного URL
    cc_code = _extract_cc_code_from_url(original_url)
    if cc_code:
        flags.append("from_cc_link")
        logger.info(
            "normalize_market_url: detected cc/ code in input URL: %s (code=%s)",
            original_url[:100],
            cc_code,
        )

    # Шаг 2: Определение типа URL и извлечение card-URL
    parsed = urlparse(original_url)
    path = parsed.path
    card_url: Optional[str] = None
    resolved_url: Optional[str] = None

    # Если это cc-URL
    if path.startswith("/cc/") or cc_code:
        # Для скрапа нужно получить card-URL через редирект
        if resolve_redirects:
            try:
                from utils.scraper import resolve_final_url

                resolved_url = await resolve_final_url(original_url)

                # resolve_final_url теперь сам обрабатывает ya.cc редиректы
                if resolved_url and (
                    "/card/" in resolved_url or "/product/" in resolved_url
                ):
                    card_url = _normalize_card_url(resolved_url)
                    logger.info(
                        "normalize_market_url: resolved cc/ to card/ URL: %s -> %s",
                        original_url[:100],
                        card_url[:100],
                    )
                elif resolved_url and "ya.cc" in resolved_url:
                    # Если все еще ya.cc после всех редиректов, попробуем использовать Playwright
                    logger.warning(
                        "normalize_market_url: ya.cc not resolved to card/, trying Playwright fallback"
                    )
                    try:
                        from playwright.async_api import async_playwright

                        async with async_playwright() as p:
                            browser = await p.chromium.launch(headless=True)
                            page = await browser.new_page()
                            await page.goto(
                                resolved_url, wait_until="networkidle", timeout=30000
                            )
                            final_url = page.url
                            await browser.close()

                            if "/card/" in final_url or "/product/" in final_url:
                                card_url = _normalize_card_url(final_url)
                                logger.info(
                                    "normalize_market_url: resolved ya.cc via Playwright: %s -> %s",
                                    resolved_url[:100],
                                    card_url[:100],
                                )
                            else:
                                raise Exception("Playwright also returned non-card URL")
                    except Exception as playwright_error:
                        logger.warning(
                            "normalize_market_url: Playwright fallback failed: %s, returning None for scrape_service",
                            str(playwright_error)[:200],
                        )
                        card_url = None  # Вернем None, чтобы scrape_service попытался разрешить
                        flags.append("cc_resolve_failed")
                else:
                    # Не удалось получить card-URL, вернем None чтобы scrape_service попытался разрешить
                    logger.warning(
                        "normalize_market_url: could not resolve cc/ to card/, returning None for scrape_service to handle"
                    )
                    card_url = (
                        None  # Вернем None, чтобы scrape_service попытался разрешить
                    )
                    flags.append("cc_resolve_failed")
            except Exception as e:
                logger.warning(
                    "normalize_market_url: error resolving cc/ URL: %s", str(e)[:200]
                )
                card_url = None  # Вернем None, чтобы scrape_service попытался разрешить
                flags.append("cc_resolve_error")
        else:
            # Не разрешаем редиректы, вернем None
            card_url = None
    else:
        # Это card-URL или product-URL
        if "/card/" in path or "/product/" in path:
            card_url = _normalize_card_url(original_url)
        else:
            # Неизвестный тип URL, используем как есть
            card_url = original_url
            flags.append("unknown_url_type")

    return MarketUrlInfo(
        original_url=original_url,
        card_url=card_url,
        cc_from_url=cc_code,
        flags=flags,
        resolved_url=resolved_url,
    )


def _extract_cc_code_from_url(url: str) -> Optional[str]:
    """
    Извлекает CC код из URL различными способами.

    ВАЖНО: Параметр cc= в card-URL не означает, что это cc-ссылка.
    Параметр cc= используется для передачи cc-кода в card-URL, но сам URL остаётся card-URL.
    Только URL, начинающийся с /cc/, считается cc-ссылкой.

    Args:
        url: URL для анализа

    Returns:
        CC код или None (только если URL начинается с /cc/)
    """
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    # 1. Ищем в пути /cc/<код> - это единственный способ определить cc-ссылку
    path_match = re.search(r"/cc/([A-Za-z0-9_-]+)", parsed.path)
    if path_match:
        code = path_match.group(1)
        logger.debug("Found CC code in URL path: %s", code)
        return code.split(",")[0]  # Обрезаем по первую запятую

    # 2. НЕ извлекаем cc-код из параметра cc= в query string, если URL начинается с /card/
    # Параметр cc= в card-URL не означает, что это cc-ссылка - это просто параметр
    # Например: https://market.yandex.ru/card/...?cc=XXX - это card-URL с параметром, а не cc-ссылка
    # 3. Ищем в хвосте ,ccCiA... (только если URL начинается с /cc/)
    if "/cc/" in url:
        tail_match = re.search(r",cc([A-Za-z0-9_-]+)", url)
        if tail_match:
            code = tail_match.group(1)
            logger.debug("Found CC code in URL tail: %s", code)
            return code.split(",")[0]

    return None


def _normalize_card_url(url: str) -> str:
    """
    Нормализует card-URL до базового формата.
    Удаляет лишние параметры и хвосты.

    Args:
        url: Исходный URL

    Returns:
        Нормализованный URL
    """
    parsed = urlparse(url)
    clean_path = parsed.path

    # Удаляем /cc/ часть, если она есть
    clean_path = re.sub(r"/cc/[A-Za-z0-9_-]+", "", clean_path)

    # Удаляем хвосты типа ,ccCiA...
    clean_path = re.sub(r",cc[A-Za-z0-9_-]+", "", clean_path)

    # Собираем URL без query и fragment (для скрапа нужен чистый card-URL)
    normalized = f"{parsed.scheme}://{parsed.netloc}{clean_path}"

    # Дополнительная очистка от повторяющихся слешей
    normalized = re.sub(r"(?<!:)/{2,}", "/", normalized)

    return normalized
