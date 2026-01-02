# services/utils.py
"""Общие утилиты для сервисов"""
import re
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
from typing import Optional


def extract_price_from_string(price_str: str) -> float:
    """Извлекает числовое значение цены из строки"""
    if not price_str or price_str == "Цена уточняется":
        return 0.0
    numbers = re.sub(r"[^\d.,]", "", price_str.replace("\u00a0", "").replace(" ", ""))
    numbers = numbers.replace(",", ".")
    try:
        return float(numbers)
    except ValueError:
        return 0.0


def is_valid_yandex_market_url(url: str) -> bool:
    """Проверяет, является ли URL валидной ссылкой на Яндекс.Маркет"""
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url.strip())
        domain = parsed.netloc.lower()
        valid_domains = ["market.yandex.ru", "market.yandex.com", "yandex.ru"]
        if not any(domain.endswith(d) for d in valid_domains):
            return False
        if not parsed.path or len(parsed.path) < 3:
            return False
        return True
    except Exception:
        return False


def convert_to_referral_link(url: str, ref_code: str = "") -> str:
    """Обрабатывает реферальные ссылки

    ВАЖНО:
    - Если ссылка уже короткая (cc/XXXXX), она сохраняется как есть!
    - Если ссылка длинная, добавляем реферальные параметры, но НЕ генерируем случайные cc/XXXXX
    - Случайные cc/XXXXX не работают - нужны реальные из партнерской программы
    """
    try:
        # Если уже короткая ссылка (cc/XXXXX), возвращаем её как есть
        # Это важно - сохраняем оригинальные реферальные ссылки!
        if "/cc/" in url:
            # Убираем все параметры, оставляем только чистую ссылку cc/XXXXX
            base_url = url.split("?")[0]
            return base_url

        # Если ссылка длинная, НЕ генерируем случайную cc/XXXXX
        # Вместо этого добавляем реферальные параметры к длинной ссылке
        # Случайные cc/XXXXX не работают - нужны реальные из партнерской программы

        # Если есть REF_CODE в формате cc/XXXXX, можно использовать его,
        # но лучше оставить длинную ссылку с параметрами
        # Возвращаем исходную ссылку - она будет обработана в add_ref_and_utm
        return url
    except Exception:
        return url


def add_ref_and_utm(
    url: str,
    ref_code: str = "",
    utm_source: str = "telegram",
    utm_medium: str = "bot",
    utm_campaign: str = "marketi_tochka",
) -> str:
    """Обрабатывает URL - сохраняет оригинальные короткие ссылки или добавляет параметры

    ВАЖНО: Каждый товар должен иметь свою уникальную короткую ссылку cc/XXXXX
    Не используем один REF_CODE для всех - каждая ссылка уникальна!
    """
    try:
        # Если уже короткая ссылка - сохраняем её как есть (это уникальная ссылка для товара!)
        if "/cc/" in url:
            return convert_to_referral_link(url, ref_code)

        # Если ссылка длинная - оставляем длинной с реферальными параметрами
        # НЕ используем один REF_CODE для всех товаров - каждая ссылка должна быть уникальной!
        # Лучше получать товары уже с короткими ссылками из партнерской программы

        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        # Добавляем UTM метки
        params["utm_source"] = [utm_source]
        params["utm_medium"] = [utm_medium]
        params["utm_campaign"] = [utm_campaign]

        new_query = urlencode(params, doseq=True)
        new_parsed = parsed._replace(query=new_query)
        return urlunparse(new_parsed)
    except Exception:
        return url


def extract_discount_from_data(data: dict) -> int:
    """Извлекает процент скидки из данных товара"""
    price_str = data.get("price", "")
    old_price_str = data.get("old_price", "") or data.get("original_price", "")
    description = (data.get("description", "") or "").lower()

    discount_match = re.search(r"(\d+)\s*%", description)
    if discount_match:
        return int(discount_match.group(1))

    if old_price_str and price_str:
        old_price = extract_price_from_string(old_price_str)
        new_price = extract_price_from_string(price_str)
        if old_price > 0 and new_price > 0 and old_price > new_price:
            return int((old_price - new_price) / old_price * 100)

    return 0
