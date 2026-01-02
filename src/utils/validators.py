# utils/validators.py
"""Валидаторы для проверки данных перед сохранением"""
import re
from urllib.parse import urlparse
from typing import Optional, Tuple


def validate_yandex_market_url(url: str) -> Tuple[bool, Optional[str]]:
    """
    Валидирует URL Яндекс.Маркета

    Returns:
        (is_valid, error_message)
    """
    if not url or not isinstance(url, str):
        return False, "URL должен быть непустой строкой"

    if len(url) > 2048:
        return False, "URL слишком длинный (максимум 2048 символов)"

    try:
        parsed = urlparse(url)

        # Проверка схемы
        if parsed.scheme not in ("http", "https"):
            return False, "URL должен использовать http или https"

        # Проверка домена
        if "market.yandex.ru" not in parsed.netloc:
            return False, "URL должен быть с домена market.yandex.ru"

        # Проверка пути
        valid_paths = ["/card/", "/product/", "/cc/"]
        if not any(path in parsed.path for path in valid_paths):
            return (
                False,
                f"URL должен содержать один из путей: {', '.join(valid_paths)}",
            )

        return True, None
    except Exception as e:
        return False, f"Ошибка парсинга URL: {str(e)}"


def validate_price(price: Optional[float]) -> Tuple[bool, Optional[str]]:
    """Валидирует цену товара"""
    if price is None:
        return False, "Цена не указана"

    if not isinstance(price, (int, float)):
        return False, "Цена должна быть числом"

    if price < 0:
        return False, "Цена не может быть отрицательной"

    if price > 100000000:  # 100 миллионов
        return False, "Цена слишком большая"

    return True, None


def validate_title(title: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Валидирует название товара"""
    if not title or not isinstance(title, str):
        return False, "Название должно быть непустой строкой"

    title = title.strip()

    if len(title) < 3:
        return False, "Название слишком короткое (минимум 3 символа)"

    if len(title) > 500:
        return False, "Название слишком длинное (максимум 500 символов)"

    # Проверка на подозрительные символы
    if re.search(r"[<>{}[\]\\|`~]", title):
        return False, "Название содержит недопустимые символы"

    return True, None


def validate_description(description: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Валидирует описание товара"""
    if not description:
        return True, None  # Описание опционально

    if not isinstance(description, str):
        return False, "Описание должно быть строкой"

    if len(description) > 5000:
        return False, "Описание слишком длинное (максимум 5000 символов)"

    return True, None













