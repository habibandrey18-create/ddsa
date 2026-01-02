"""
AI Result Validator - строгая валидация результатов от ChatGPT
"""

import logging
import re
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ValidatedResult:
    """Валидированный результат от AI"""

    product_url: str
    ref_link: Optional[str]
    price: Optional[float]
    title: str
    is_valid: bool
    flags: list[str]
    source: str = "ai"  # ai, parser, cache


@dataclass
class InvalidResult:
    """Невалидный результат с причиной"""

    reason: str
    original_result: Dict[str, Any]


class AiResultValidator:
    """
    Валидатор результатов от AiEnrichmentService
    """

    @staticmethod
    def _clean_text(text: str, max_length: int = 200) -> str:
        """
        Очистка текста от emoji, управляющих символов и HTML

        Args:
            text: Исходный текст
            max_length: Максимальная длина

        Returns:
            Очищенный текст
        """
        if not text:
            return ""

        # Удаляем HTML теги
        text = re.sub(r"<[^>]+>", "", text)

        # Удаляем emoji и управляющие символы
        # Оставляем только печатные символы, пробелы, знаки препинания
        text = re.sub(
            r'[^\w\s\-.,!?()\[\]{}:;"\'/\\@#$%^&*+=|<>~`]', "", text, flags=re.UNICODE
        )

        # Удаляем множественные пробелы
        text = re.sub(r"\s+", " ", text).strip()

        # Обрезаем до max_length
        if len(text) > max_length:
            text = text[:max_length].rsplit(" ", 1)[0]  # Обрезаем по последнему слову

        return text

    @staticmethod
    def _validate_ref_link(
        ref_link: Optional[str], raw_context: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Валидация ref_link

        Args:
            ref_link: Ссылка для валидации
            raw_context: Сырые данные для проверки наличия ссылки

        Returns:
            Tuple (is_valid, error_message)
        """
        if not ref_link:
            return True, None  # None - это валидно (нет ссылки)

        # Проверка формата
        if not ref_link.startswith("https://market.yandex.ru/cc/"):
            return False, f"Invalid ref_link format: {ref_link[:50]}"

        # Проверка на хвосты
        if "/cc/," in ref_link or ref_link.count("/cc/") > 1:
            return False, f"Invalid ref_link with tail: {ref_link[:50]}"

        # Извлекаем CC код
        cc_match = re.search(r"/cc/([A-Za-z0-9_-]+)", ref_link)
        if not cc_match:
            return False, f"CC code not found in ref_link: {ref_link[:50]}"

        cc_code = cc_match.group(1)

        # Проверка, что код встречается в исходных данных
        url = raw_context.get("url", "")
        final_url = raw_context.get("final_url", url)
        raw_html = raw_context.get("raw_html", "")

        # Ищем CC код в исходных данных
        found_in_url = cc_code in url or cc_code in final_url
        found_in_html = cc_code in raw_html[:5000] if raw_html else False

        if not found_in_url and not found_in_html:
            logger.warning(
                f"CC code {cc_code} not found in raw context, marking as suspicious"
            )
            return False, f"CC code {cc_code} not found in raw context"

        return True, None

    @staticmethod
    def _validate_product_url(
        product_url: str, raw_context: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Валидация product_url

        Args:
            product_url: URL для валидации
            raw_context: Сырые данные для проверки

        Returns:
            Tuple (is_valid, error_message)
        """
        if not product_url:
            return False, "product_url is empty"

        # Проверка формата
        if not product_url.startswith("https://market.yandex.ru/card/"):
            return False, f"Invalid product_url format: {product_url[:50]}"

        # Проверка, что URL встречается в исходных данных
        url = raw_context.get("url", "")
        final_url = raw_context.get("final_url", url)
        raw_html = raw_context.get("raw_html", "")

        # Извлекаем базовый путь для сравнения
        product_path = product_url.split("?")[0].split("#")[0]
        final_path = final_url.split("?")[0].split("#")[0] if final_url else ""

        # Проверяем, что product_url похож на исходный
        found_in_url = product_path in url or product_path in final_url
        found_in_html = product_path in raw_html[:5000] if raw_html else False

        if not found_in_url and not found_in_html:
            # Мягкая проверка - проверяем хотя бы домен и структуру
            if "/card/" not in url and "/card/" not in final_url:
                logger.warning(f"product_url {product_path} not found in raw context")
                # Не считаем это критичной ошибкой, но логируем

        return True, None

    @staticmethod
    def _validate_price(price: Any) -> Tuple[bool, Optional[float], Optional[str]]:
        """
        Валидация цены

        Args:
            price: Цена (может быть str, int, float, None)

        Returns:
            Tuple (is_valid, price_value, error_message)
        """
        if price is None:
            return True, None, None  # None - это валидно (нет цены)

        # Преобразуем в число
        try:
            if isinstance(price, str):
                # Удаляем все нецифровые символы кроме точки и запятой
                price_clean = re.sub(r"[^\d.,]", "", price)
                price_clean = price_clean.replace(",", ".")
                price_value = float(price_clean)
            elif isinstance(price, (int, float)):
                price_value = float(price)
            else:
                return False, None, f"Invalid price type: {type(price)}"

            # Проверка: должна быть > 0 и целое число
            if price_value <= 0:
                return False, None, f"Price must be > 0, got {price_value}"

            # Проверка на целое число
            if price_value != int(price_value):
                return False, None, f"Price must be integer, got {price_value}"

            return True, int(price_value), None

        except (ValueError, TypeError) as e:
            return False, None, f"Failed to parse price: {e}"

    def validate(
        self, ai_result: Dict[str, Any], raw_context: Dict[str, Any]
    ) -> Tuple[bool, Optional[ValidatedResult], Optional[InvalidResult]]:
        """
        Валидация результата от AI

        Args:
            ai_result: Результат от AiEnrichmentService
            raw_context: Сырые данные (url, final_url, raw_html и т.д.)

        Returns:
            Tuple (is_valid, ValidatedResult, InvalidResult)
        """
        if not ai_result:
            return False, None, InvalidResult("AI result is empty", {})

        # Проверка обязательных полей
        required_fields = ["product_url", "ref_link", "price", "title", "is_valid"]
        missing_fields = [f for f in required_fields if f not in ai_result]
        if missing_fields:
            return (
                False,
                None,
                InvalidResult(f"Missing fields: {missing_fields}", ai_result),
            )

        # Если AI сам сказал что невалидно - возвращаем Invalid
        if not ai_result.get("is_valid", False):
            reason = ai_result.get("notes", "AI marked as invalid")
            return False, None, InvalidResult(reason, ai_result)

        # Валидация product_url
        product_url = ai_result.get("product_url", "")
        is_valid_url, url_error = self._validate_product_url(product_url, raw_context)
        if not is_valid_url:
            return (
                False,
                None,
                InvalidResult(f"Invalid product_url: {url_error}", ai_result),
            )

        # Валидация ref_link
        ref_link = ai_result.get("ref_link")
        is_valid_ref, ref_error = self._validate_ref_link(ref_link, raw_context)
        if not is_valid_ref:
            return (
                False,
                None,
                InvalidResult(f"Invalid ref_link: {ref_error}", ai_result),
            )

        # Валидация price
        price = ai_result.get("price")
        is_valid_price, price_value, price_error = self._validate_price(price)
        if not is_valid_price:
            return (
                False,
                None,
                InvalidResult(f"Invalid price: {price_error}", ai_result),
            )

        # Очистка title
        title = self._clean_text(ai_result.get("title", ""), max_length=200)
        if not title:
            return (
                False,
                None,
                InvalidResult("Title is empty after cleaning", ai_result),
            )

        # Формируем валидированный результат
        flags = ["ai_ok"]
        if ref_link:
            flags.append("has_ref")
        if price_value:
            flags.append("has_price")

        validated = ValidatedResult(
            product_url=product_url,
            ref_link=ref_link,
            price=price_value,
            title=title,
            is_valid=True,
            flags=flags,
            source="ai",
        )

        return True, validated, None
