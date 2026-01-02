"""
Partner Link Service - обертка над YandexMarketLinkGen для получения партнерских ссылок
Использует normalize_market_url для правильной обработки card-URL и cc-URL
"""

import logging
import re
from typing import Optional, Dict, Any
from urllib.parse import urlparse, parse_qs, urlunparse
from dataclasses import dataclass

from utils.yandex_market_link_gen import YandexMarketLinkGen
from services.url_service import UrlService
from utils.url_normalizer import MarketUrlInfo

logger = logging.getLogger(__name__)


@dataclass
class PartnerLinkInfo:
    """Информация о партнёрской ссылке"""

    ref_link: Optional[str]
    product_url: str
    has_ref: bool
    source: str  # "from_input" | "from_scraper" | "extracted" | "generated" | "none"
    flags: list[str]


class PartnerLinkService:
    """
    Сервис для получения партнерских ссылок через YandexMarketLinkGen
    """

    def __init__(self):
        """Инициализация сервиса с настройками по умолчанию"""
        self._gen = YandexMarketLinkGen(
            headless=True,  # Браузер работает в фоне (headless режим)
            timeout=180,  # Увеличено до 180 секунд для извлечения ссылки из "Поделиться - Копировать ссылку"
            max_retries=3,
            debug=False,  # Отключен debug для работы в фоне
        )

    def _extract_cc_code_from_url(self, url: str) -> Optional[str]:
        """
        Извлечь CC код из URL параметров или хвоста

        Ищет:
        1. Параметр cc=<код> в URL
        2. Хвост вида ,ccCiA... в конце URL

        Args:
            url: URL для разбора

        Returns:
            CC код или None
        """
        if not url:
            return None

        # 1. Ищем параметр cc= в URL
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        if "cc" in query_params:
            cc_code = query_params["cc"][0]
            # Обрезаем по первую запятую если есть
            if "," in cc_code:
                cc_code = cc_code.split(",")[0]
            if cc_code:
                logger.info(f"Found CC code in URL params: {cc_code}")
                return cc_code

        # 2. Ищем хвост вида ,ccCiA... в конце URL
        # Ищем паттерн ,cc[A-Za-z0-9]+ в конце пути или параметров
        tail_match = re.search(r",cc([A-Za-z0-9_-]+)", url)
        if tail_match:
            cc_code = tail_match.group(1)
            # Обрезаем по первую запятую если есть
            if "," in cc_code:
                cc_code = cc_code.split(",")[0]
            if cc_code:
                logger.info(f"Found CC code in URL tail: {cc_code}")
                return cc_code

        return None

    def _normalize_card_url(self, url: str) -> str:
        """
        Нормализовать card URL - убрать лишние параметры, оставить только базовый URL

        Args:
            url: Исходный URL

        Returns:
            Нормализованный card URL
        """
        if not url:
            return url

        # Если это уже /cc/ ссылка, возвращаем как есть
        if "/cc/" in url:
            return url.split("?")[0].split("#")[0]

        # Парсим URL
        parsed = urlparse(url)

        # Оставляем только базовый путь без параметров
        # Например: https://market.yandex.ru/card/product-name/123456
        normalized = urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path.split("?")[0].split("#")[0],
                "",
                "",
                "",
            )
        )

        return normalized

    def _validate_cc_link(self, link: Optional[str]) -> Optional[str]:
        """
        МАКСИМАЛЬНО УЛУЧШЕННАЯ валидация CC ссылки: проверка формата, домена и качества кода.

        Args:
            link: Ссылка для валидации

        Returns:
            Валидированная ссылка или None
        """
        if not link:
            return None

        # #region agent edit - МАКСИМАЛЬНО УЛУЧШЕННАЯ ВАЛИДАЦИЯ
        # Нормализация ссылки (убираем лишние пробелы)
        link = link.strip()

        # Проверка формата: должна быть https://market.yandex.ru/cc/...
        if not link.startswith("https://market.yandex.ru/cc/"):
            # Пробуем исправить ссылку (если есть http:// или без протокола)
            if link.startswith("http://market.yandex.ru/cc/"):
                link = link.replace("http://", "https://")
            elif link.startswith("market.yandex.ru/cc/"):
                link = "https://" + link
            elif "/cc/" in link:
                # Пытаемся извлечь код из ссылки
                match = re.search(r"/cc/([A-Za-z0-9_-]+)", link)
                if match:
                    code = match.group(1)
                    link = f"https://market.yandex.ru/cc/{code}"
                else:
                    logger.warning(f"Invalid CC link format: {link}")
                    return None
            else:
                logger.warning(f"Invalid CC link format: {link}")
                return None

        # Проверка на обфусцированный JavaScript код (например, _0x49088e)
        if "_0x" in link or link.count("_0x") > 0:
            logger.warning(f"Invalid CC link (obfuscated JS code): {link}")
            return None

        # Проверка на хвосты вида ,ccCiA... (не должно быть запятой после /cc/)
        if "/cc/," in link or link.count("/cc/") > 1:
            logger.warning(f"Invalid CC link with tail: {link}")
            return None

        # Проверка на httpsmarket... (без двоеточия и слешей)
        if "httpsmarket" in link.lower() or "httpmarket" in link.lower():
            logger.warning(f"Invalid CC link format (malformed protocol): {link}")
            return None

        # Извлекаем код после /cc/ и проверяем его качество
        parts = link.split("/cc/")
        if len(parts) == 2:
            code = (
                parts[1].split("?")[0].split("#")[0].split(",")[0].split("&")[0].strip()
            )

            # Проверка на пустой код
            if not code:
                logger.warning(f"Invalid CC code (empty): {link}")
                return None

            # #region agent edit - ПРОВЕРКА НА ЗАРЕЗЕРВИРОВАННЫЕ СЛОВА
            # Проверка на зарезервированные слова и домены
            invalid_codes = [
                "https",
                "http",
                "www",
                "market",
                "yandex",
                "ru",
                "com",
                "org",
                "net",
                "special",
                "originals",
                "card",
                "product",
                "catalog",
                "search",
                "shop",
                "seller",
                "offer",
                "price",
                "review",
                "rating",
                "image",
                "photo",
                "video",
                "javascript",
                "void",
                "null",
                "undefined",
                "true",
                "false",
                "function",
                "object",
                "array",
                "string",
                "number",
                "boolean",
                "date",
                "time",
                "partner",
                "passport",
                "auth",
                "login",
                "register",
                "account",
                "profile",
                "settings",
                "help",
                "support",
                "about",
                "contact",
                "terms",
                "privacy",
                "cookie",
                "policy",
                "legal",
                "faq",
                "blog",
                "news",
                "press",
                "careers",
            ]
            if code.lower() in invalid_codes:
                logger.warning(f"Invalid CC code (reserved word): {code}")
                return None
            # #endregion

            # Проверка на запятые в коде
            if "," in code:
                logger.warning(f"Invalid CC code with comma: {code}")
                return None

            # Проверка длины кода (обычно CC коды от 5 до 20 символов)
            if len(code) < 5:
                logger.warning(f"Invalid CC code (too short): {code}")
                return None

            if len(code) > 30:
                logger.warning(f"Invalid CC code (too long): {code}")
                return None

            # Проверка на чисто числовой код (обычно это не CC коды)
            if code.isdigit():
                logger.warning(f"Invalid CC code (numeric only): {code}")
                return None

            # Проверка на код, который выглядит как хеш (слишком длинный и случайный)
            if len(code) > 20 and all(c in "0123456789abcdefABCDEF" for c in code):
                logger.warning(f"Invalid CC code (looks like hash): {code}")
                return None

            # Формируем чистую ссылку без параметров
            clean_link = f"https://market.yandex.ru/cc/{code}"
            return clean_link
        else:
            logger.warning(f"Invalid CC link structure: {link}")
            return None
        # #endregion

    async def get_cc_link(
        self, url: str, reuse_state_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Получить CC ссылку для товара

        Args:
            url: URL товара на Яндекс.Маркете
            reuse_state_path: Путь к файлу состояния браузера для переиспользования

        Returns:
            CC ссылка или None в случае ошибки
        """
        try:
            result = await self._gen.generate(
                url=url, job_id=None, reuse_state_path=reuse_state_path
            )
            # Валидируем результат
            validated = self._validate_cc_link(result)
            if not validated and result:
                logger.warning(f"Generated link failed validation: {result}")
            return validated
        except Exception as e:
            logger.warning(f"Partner link generation failed for {url}, using original URL: {e}")
            return None

    async def get_partner_link(
        self, url: str, use_browser: bool = True
    ) -> Dict[str, Any]:
        """
        Получить партнерскую ссылку для товара (совместимость с существующим кодом)

        Args:
            url: URL товара на Яндекс.Маркете
            use_browser: Использовать ли браузер для генерации ссылки

        Returns:
            Словарь с результатом:
            {
                "ref_link": str | None,
                "flags": list[str],
                "url": str
            }
        """
        flags = []
        ref_link = None

        if use_browser:
            try:
                ref_link = await self.get_cc_link(url)
            except Exception as e:
                logger.warning(f"Partner link generation failed for {url}, using original URL: {e}")
                flags.append("partner_link_failed")

        if ref_link:
            flags.append("ok")
        else:
            flags.append("ref_not_found")

        return {"ref_link": ref_link, "flags": flags, "url": url}

    async def get_product_with_partner_link(
        self,
        url: str,
        use_browser: bool = True,
        raw_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Получить информацию о товаре с партнерской ссылкой

        Args:
            url: URL товара на Яндекс.Маркете
            use_browser: Использовать ли браузер для генерации ссылки
            raw_data: Опциональные сырые данные для AI обогащения

        Returns:
            Словарь с результатом:
            {
                "url": str,
                "ref_link": str | None,
                "product_url": str,
                "has_ref": bool,
                "flags": list[str],
                "note": str
            }
        """
        flags = []
        ref_link = None
        has_ref = False
        product_url = self._normalize_card_url(url)

        # Пробуем AI обогащение если есть сырые данные
        ai_result = None
        if raw_data:
            try:
                from services.ai_enrichment_service import get_ai_enrichment_service

                ai_service = get_ai_enrichment_service()
                if ai_service.enabled:
                    ai_result = await ai_service.enrich_product_safe(raw_data)
                    if ai_result and ai_result.get("is_valid"):
                        if ai_result.get("product_url"):
                            product_url = ai_result["product_url"]
                        if ai_result.get("ref_link"):
                            ref_link = ai_result["ref_link"]
                            has_ref = True
                            flags.append("ok")
                            flags.append("from_ai")
                            logger.info(
                                f"Using AI enrichment result: ref_link={'found' if ref_link else 'not found'}"
                            )
            except Exception as e:
                logger.debug(f"AI enrichment failed in PartnerLinkService: {e}")

        # Fallback: если AI не дал результат, используем текущую логику
        if not ai_result or not ai_result.get("is_valid"):
            # Сначала пытаемся извлечь CC код из исходного URL
            cc_code = self._extract_cc_code_from_url(url)
            if cc_code:
                ref_link = f"https://market.yandex.ru/cc/{cc_code}"
                has_ref = True
                flags.append("ok")
                flags.append("from_url")
                logger.info(f"Using CC code from URL: {cc_code}")
            else:
                # Если не нашли в URL, пытаемся через браузер
                if use_browser:
                    try:
                        ref_link = await self.get_cc_link(url)
                        if ref_link:
                            has_ref = True
                            flags.append("ok")
                            flags.append("from_browser")
                    except Exception as e:
                        logger.warning(
                            f"Partner link generation failed for {url}, using original URL: {e}",
                        )
                        flags.append("partner_link_failed")

        if not has_ref:
            flags.append("ref_not_found")
            note = "Партнёрская ссылка не найдена"
        else:
            note = "Партнёрская ссылка найдена"

        return {
            "url": url,
            "ref_link": ref_link if has_ref else None,
            "product_url": product_url,
            "has_ref": has_ref,
            "flags": flags,
            "note": note,
        }

    async def ensure_partner_link(
        self,
        url: str,
        url_info: MarketUrlInfo,
        existing_data: Optional[Dict[str, Any]] = None,
    ) -> PartnerLinkInfo:
        """
        Централизованная логика получения/принятия партнёрской ссылки.
        Использует MarketUrlInfo для правильной обработки card-URL и cc-URL.

        Бизнес-логика:
        - Если входной URL - cc-URL: использует cc_from_url напрямую, не генерирует новый
        - Если входной URL - card-URL: может получить/сгенерировать cc через партнёрский сервис
        - Всегда использует ровно тот cc, который вернул Маркет/партнёрка, без модификаций

        Args:
            url: Исходный URL
            url_info: Информация о URL (от normalize_market_url)
            existing_data: Опциональные данные от скрапера

        Returns:
            PartnerLinkInfo с информацией о партнёрской ссылке
        """  # Если это cc-ссылка - используем её напрямую (запрещено генерировать новую)
        # ВАЖНО: Проверяем, что исходный URL действительно начинается с /cc/, а не просто содержит параметр cc=
        # Параметр cc= в card-URL не означает, что это cc-ссылка - это просто параметр
        is_real_cc_url = "/cc/" in url and url_info.cc_from_url
        if is_real_cc_url:
            ref_link = url_info.get_partner_link()
            return PartnerLinkInfo(
                ref_link=ref_link,
                product_url=url_info.card_url
                or url,  # card_url для скрапа, но в посте используем исходную cc
                has_ref=True,
                source="from_input",
                flags=url_info.flags + ["cc_url_direct"],
            )

        # Если в данных уже есть ref_link - используем её (от скрапера/партнёрки)
        if existing_data and existing_data.get("ref_link"):
            ref_link = existing_data["ref_link"]
            if ref_link and "/cc/" in ref_link:
                return PartnerLinkInfo(
                    ref_link=ref_link,
                    product_url=existing_data.get(
                        "product_url", url_info.card_url or url
                    ),
                    has_ref=True,
                    source="from_scraper",
                    flags=existing_data.get("flags", []),
                )

        # Если это card-URL - пытаемся получить/сгенерировать cc через партнёрский сервис
        # (но только если это не cc-URL, иначе бы уже вернулись выше)
        if url_info.card_url:
            try:
                # Пытаемся сгенерировать партнёрскую ссылку                ref_link = await self.get_cc_link(url_info.card_url)                if ref_link:
                return PartnerLinkInfo(
                    ref_link=ref_link,
                    product_url=url_info.card_url,
                    has_ref=True,
                    source="generated",
                    flags=["cc_generated"],
                )
            except Exception as e:
                logger.warning(
                    f"Partner link generation failed for {url_info.card_url}, using original URL: {e}"
                )
        # Если в existing_data есть has_ref=False - значит партнёрка не найдена
        if existing_data and existing_data.get("has_ref") is False:
            return PartnerLinkInfo(
                ref_link=None,
                product_url=url_info.card_url or url,
                has_ref=False,
                source="none",
                flags=existing_data.get("flags", []) + ["no_partner_link"],
            )

        # Fallback: нет партнёрской ссылки
        return PartnerLinkInfo(
            ref_link=None,
            product_url=url_info.card_url or url,
            has_ref=False,
            source="none",
            flags=["no_partner_link"],
        )


# Свободные функции для совместимости
async def ensure_partner_link(
    url: str, url_info: MarketUrlInfo, existing_data: Optional[Dict[str, Any]] = None
) -> PartnerLinkInfo:
    """
    Свободная функция для ensure_partner_link.
    Использует MarketUrlInfo для правильной обработки card-URL и cc-URL.

    Args:
        url: Исходный URL
        url_info: Информация о URL (от normalize_market_url)
        existing_data: Опциональные данные от скрапера

    Returns:
        PartnerLinkInfo с информацией о партнёрской ссылке
    """
    service = PartnerLinkService()
    return await service.ensure_partner_link(url, url_info, existing_data)


async def get_product_with_partner_link(
    url: str, use_browser: bool = True, raw_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Получить информацию о товаре с партнерской ссылкой (свободная функция)

    Args:
        url: URL товара на Яндекс.Маркете
        use_browser: Использовать ли браузер для генерации ссылки
        raw_data: Опциональные сырые данные для AI обогащения

    Returns:
        Словарь с результатом:
        {
            "url": str,
            "ref_link": str | None,
            "product_url": str,
            "has_ref": bool,
            "flags": list[str],
            "note": str
        }
    """
    service = PartnerLinkService()
    return await service.get_product_with_partner_link(
        url, use_browser=use_browser, raw_data=raw_data
    )
