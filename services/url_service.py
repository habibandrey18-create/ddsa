"""
URL Service - работа с URL товаров Яндекс.Маркета
Разделение уровней: нормализация, разбор card/cc, извлечение cc
"""

import logging
import re
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)


class UrlService:
    """
    Сервис для работы с URL товаров
    """

    @staticmethod
    def parse_url(url: str) -> Dict[str, Any]:
        """
        Разбирает URL и определяет его тип

        Args:
            url: URL товара

        Returns:
            Словарь с информацией:
            {
                "type": "cc" | "card" | "product" | "unknown",
                "is_cc": bool,
                "is_card": bool,
                "cc_code": Optional[str],
                "normalized_card_url": Optional[str],
                "parsed": ParseResult
            }
        """
        parsed = urlparse(url)
        path = parsed.path

        result = {
            "type": "unknown",
            "is_cc": False,
            "is_card": False,
            "cc_code": None,
            "normalized_card_url": None,
            "parsed": parsed,
        }

        # Проверка на cc/...
        if path.startswith("/cc/"):
            result["type"] = "cc"
            result["is_cc"] = True
            # Извлекаем CC код
            cc_match = re.search(r"/cc/([A-Za-z0-9_-]+)", path)
            if cc_match:
                result["cc_code"] = cc_match.group(1)
            return result

        # Проверка на card/...
        if "/card/" in path:
            result["type"] = "card"
            result["is_card"] = True
            result["normalized_card_url"] = UrlService._normalize_card_url(url)
            return result

        # Проверка на product/...
        if "/product/" in path:
            result["type"] = "product"
            result["is_card"] = True
            result["normalized_card_url"] = UrlService._normalize_card_url(url)
            return result

        return result

    @staticmethod
    def _normalize_card_url(url: str) -> str:
        """
        Нормализует card-URL до базового формата

        Args:
            url: Исходный URL

        Returns:
            Нормализованный URL
        """
        parsed = urlparse(url)

        # Удаляем все параметры, кроме тех, что могут быть частью product_id
        clean_path = parsed.path

        # Удаляем /cc/ часть, если она есть
        clean_path = re.sub(r"/cc/[A-Za-z0-9_-]+", "", clean_path)

        # Удаляем хвосты типа ,ccCiA...
        clean_path = re.sub(r",cc[A-Za-z0-9_-]+", "", clean_path)

        # Собираем URL без query и fragment
        normalized = f"{parsed.scheme}://{parsed.netloc}{clean_path}"

        # Дополнительная очистка от повторяющихся слешей
        normalized = re.sub(r"(?<!:)/{2,}", "/", normalized)

        return normalized

    @staticmethod
    def extract_cc_code(url: str) -> Optional[str]:
        """
        Извлекает CC код из URL

        Args:
            url: URL товара

        Returns:
            CC код или None
        """
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)

        # 1. Ищем в параметрах cc=
        if "cc" in query_params and query_params["cc"]:
            code = query_params["cc"][0]
            logger.debug(f"Found CC code in URL params: {code}")
            return code.split(",")[0]  # Обрезаем по первую запятую

        # 2. Ищем в пути /cc/<код>
        path_match = re.search(r"/cc/([A-Za-z0-9_-]+)", parsed.path)
        if path_match:
            code = path_match.group(1)
            logger.debug(f"Found CC code in URL path: {code}")
            return code.split(",")[0]  # Обрезаем по первую запятую

        # 3. Ищем в хвосте ,ccCiA...
        tail_match = re.search(r",cc([A-Za-z0-9_-]+)", url)
        if tail_match:
            code = tail_match.group(1)
            logger.debug(f"Found CC code in URL tail: {code}")
            return code.split(",")[0]  # Обрезаем по первую запятую

        return None

    @staticmethod
    def build_cc_link(cc_code: str) -> str:
        """
        Строит партнёрскую cc-ссылку из кода

        Args:
            cc_code: CC код

        Returns:
            Партнёрская ссылка
        """
        return f"https://market.yandex.ru/cc/{cc_code}"

    @staticmethod
    def should_use_direct_cc(url: str) -> Tuple[bool, Optional[str]]:
        """
        Проверяет, нужно ли использовать cc-ссылку напрямую

        Args:
            url: URL товара

        Returns:
            Tuple (should_use, cc_link)
        """
        parsed = UrlService.parse_url(url)

        if parsed["is_cc"] and parsed["cc_code"]:
            return True, UrlService.build_cc_link(parsed["cc_code"])

        # Проверяем наличие CC в параметрах
        cc_code = UrlService.extract_cc_code(url)
        if cc_code:
            return True, UrlService.build_cc_link(cc_code)

        return False, None

    @staticmethod
    def generate_qr_code(text: str) -> Optional[bytes]:
        """
        Генерирует QR-код для текста

        Args:
            text: Текст для кодирования в QR-код

        Returns:
            Bytes изображения QR-кода или None при ошибке
        """
        try:
            import qrcode
            from io import BytesIO

            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(text)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            return buffer.getvalue()
        except ImportError:
            logger.warning("qrcode library not installed, QR code generation disabled")
            return None
        except Exception as e:
            logger.error(f"Error generating QR code: {e}")
            return None

    @staticmethod
    def shorten_url(url: str, max_length: int = 60) -> str:
        """
        Сокращает URL до указанной длины

        Args:
            url: URL для сокращения
            max_length: Максимальная длина

        Returns:
            Сокращённый URL
        """
        if len(url) <= max_length:
            return url

        # Обрезаем середину URL, оставляя начало и конец
        if max_length < 20:
            return url[:max_length]

        start_len = max_length // 2 - 3
        end_len = max_length // 2 - 3
        return f"{url[:start_len]}...{url[-end_len:]}"


# Свободные функции для совместимости
def generate_qr_code(text: str) -> Optional[bytes]:
    """Свободная функция для генерации QR-кода"""
    return UrlService.generate_qr_code(text)


def shorten_url(url: str, max_length: int = 60) -> str:
    """Свободная функция для сокращения URL"""
    return UrlService.shorten_url(url, max_length)


def add_affiliate_params(url: str, clid: str = None, vid: str = None) -> str:
    """
    Добавляет партнерские параметры Yandex Market к URL.

    Args:
        url: Исходный URL товара
        clid: Partner CLID (из config.AFFILIATE_CLID)
        vid: Partner VID (из config.AFFILIATE_VID)

    Returns:
        URL с добавленными параметрами clid и vid
    """
    if not url:
        return url

    # Импортируем config только при необходимости
    try:
        import config

        clid = clid or getattr(config, "AFFILIATE_CLID", None)
        vid = vid or getattr(config, "AFFILIATE_VID", None)
    except:
        pass

    # Если параметры не указаны - возвращаем оригинальный URL
    if not clid and not vid:
        return url

    # Парсим URL
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)

    # Добавляем партнерские параметры
    if clid:
        query_params["clid"] = [clid]
    if vid:
        query_params["vid"] = [vid]

    # Формируем новую query строку
    from urllib.parse import urlencode

    new_query = urlencode(query_params, doseq=True)

    # Собираем новый URL
    new_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if new_query:
        new_url += f"?{new_query}"
    if parsed.fragment:
        new_url += f"#{parsed.fragment}"

    logger.debug(f"Added affiliate params to URL: clid={clid}, vid={vid}")
    return new_url
