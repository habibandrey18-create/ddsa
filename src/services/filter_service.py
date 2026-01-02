# services/filter_service.py
"""Сервис фильтрации товаров по черному списку и другим критериям"""
import logging
import re
from typing import Dict, Optional, Tuple
import src.config as config

logger = logging.getLogger(__name__)


def should_filter_product(
    product: Dict, reason_prefix: str = ""
) -> Tuple[bool, Optional[str]]:
    """
    Проверяет, нужно ли отфильтровать товар.

    Args:
        product: Словарь с данными товара (должен содержать 'title' и опционально 'price')
        reason_prefix: Префикс для сообщения о причине фильтрации

    Returns:
        Tuple[bool, Optional[str]]: (should_filter, reason)
        - should_filter: True если товар нужно отфильтровать
        - reason: Причина фильтрации или None
    """
    title = product.get("title", "").strip()
    if not title:
        return True, "Пустое название"

    title_lower = title.lower()

    # Проверка стоп-слов в названии
    stop_words = getattr(config, "FILTER_STOP_WORDS", [])
    if stop_words:
        for word in stop_words:
            if word.lower() in title_lower:
                reason = f"{reason_prefix}Blacklist: содержит '{word}'"
                logger.info(f"🚫 Skipped [{title[:50]}...] ({reason})")
                return True, reason

    # Проверка минимальной цены (если цена доступна)
    price = product.get("price")
    if price is not None:
        # Если price - строка, пытаемся извлечь число
        if isinstance(price, str):
            price_num = _extract_price_from_string(price)
        else:
            price_num = float(price) if price else 0

        filter_min_price = getattr(config, "FILTER_MIN_PRICE", 0)
        if filter_min_price > 0 and price_num > 0 and price_num < filter_min_price:
            reason = f"{reason_prefix}Price: {price_num}₽ < {filter_min_price}₽"
            logger.info(f"🚫 Skipped [{title[:50]}...] ({reason})")
            return True, reason

    return False, None


def _extract_price_from_string(price_str: str) -> float:
    """Извлекает числовое значение цены из строки"""
    if not price_str:
        return 0.0

    # Удаляем все символы кроме цифр, точки и запятой
    price_clean = re.sub(r"[^\d.,]", "", str(price_str))
    # Заменяем запятую на точку
    price_clean = price_clean.replace(",", ".")

    try:
        return float(price_clean)
    except (ValueError, TypeError):
        return 0.0













