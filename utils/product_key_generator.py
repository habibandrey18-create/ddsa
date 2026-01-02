"""
Product Key Generator - creates normalized keys for product de-duplication
"""

import re
import logging
from typing import List

logger = logging.getLogger(__name__)


# Predefined list of common color words to remove
COLOR_WORDS = {
    # Russian colors
    "синий", "красный", "белый", "черный", "серый", "зеленый", "желтый", "оранжевый",
    "розовый", "фиолетовый", "коричневый", "голубой", "бирюзовый", "малиновый",
    "бордовый", "бежевый", "кремовый", "золотой", "серебряный", "платиновый",
    "графит", "изумрудный", "коралловый", "мятный", "лавандовый", "терракотовый",
    "темно", "светло", "ярко", "пастельный", "металлик",

    # English colors (just in case)
    "black", "white", "red", "blue", "green", "yellow", "orange", "pink", "purple",
    "brown", "gray", "grey", "gold", "silver", "platinum", "graphite", "emerald",
    "coral", "mint", "lavender", "terracotta", "dark", "light", "bright", "metallic",

    # Additional color variants
    "темно-серый", "темно-синий", "темно-зеленый", "темно-красный",
    "светло-серый", "светло-синий", "светло-зеленый", "светло-розовый",
}

# Common non-essential product descriptors to remove
NON_ESSENTIAL_WORDS = {
    # Seller-specific terms
    "с алисой", "без часов", "с zigbee", "для женщин", "для мужчин", "для детей",
    "детский", "женский", "мужской", "унисекс", "universal",

    # Size indicators (generic)
    "стандартный", "стандарт", "компактный", "мини", "макси", "большой", "маленький",

    # Quality indicators (too generic)
    "оригинальный", "оригинал", "качественный", "превосходный", "отличный",
    "хороший", "лучший", "топ", "премиум", "pro",

    # Common marketing phrases
    "новинка", "новый", "акция", "скидка", "распродажа", "хит продаж", "бестселлер",
    "популярный", "рекомендуемый", "выбор покупателей",

    # Technical terms that vary
    "bluetooth", "wifi", "usb", "hdmi", "type-c", "micro-usb", "lightning",
    "android", "ios", "windows", "macos",

    # Packaging variations
    "в коробке", "без коробки", "упаковка", "упакованный", "запакованный",

    # Version indicators
    "v1", "v2", "v3", "version", "версия", "модель", "серия",
}


def generate_product_key(title: str) -> str:
    """
    Creates a normalized product key for de-duplication by removing variations
    like colors, sellers, and non-essential descriptors.

    This function performs the following steps:
    1. Convert to lowercase
    2. Remove color words
    3. Remove non-essential product descriptors
    4. Remove punctuation
    5. Normalize whitespace

    Args:
        title: Product title string

    Returns:
        str: Normalized product key for duplicate detection

    Example:
        Input: "Умная колонка Яндекс Станция Лайт 2 с Алисой, без часов, 6 Вт, графит"
        Output: "умная колонка яндекс станция лайт 2 6 вт"
    """
    if not title or not isinstance(title, str):
        logger.warning(f"Invalid title provided to generate_product_key: {title}")
        return ""

    try:
        # Step 1: Convert to lowercase and strip
        normalized = title.lower().strip()

        # Step 2: Remove color words
        for color in COLOR_WORDS:
            # Use word boundaries to avoid partial matches
            normalized = re.sub(rf'\b{re.escape(color)}\b', '', normalized, flags=re.IGNORECASE)

        # Step 3: Remove non-essential words
        for word in NON_ESSENTIAL_WORDS:
            # Use word boundaries to avoid partial matches
            normalized = re.sub(rf'\b{re.escape(word)}\b', '', normalized, flags=re.IGNORECASE)

        # Step 4: Remove punctuation and special characters
        # Keep only letters, numbers, and spaces
        normalized = re.sub(r'[^\w\s]', ' ', normalized)

        # Step 5: Normalize whitespace - replace multiple spaces with single space
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        # Step 6: Remove common brand prefixes/suffixes that might vary
        # This helps catch products from same brand but different sellers
        brand_patterns = [
            r'\b(я\.м\.|яндекс\.маркет|яндекс\s+маркет)\b',  # Yandex Market indicators
            r'\b(ozon|wildberries|aliexpress|amazon)\b',      # Other marketplaces
            r'\b(официальный|официальный\s+дилер|дилер)\b',     # Seller indicators
        ]

        for pattern in brand_patterns:
            normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)

        # Final normalization
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        # Ensure we have meaningful content
        if len(normalized) < 3:
            logger.warning(f"Product key too short after normalization: '{normalized}' from '{title}'")
            # Fallback: use first few words of original title
            words = re.sub(r'[^\w\s]', ' ', title.lower()).split()
            normalized = ' '.join(words[:5])  # Take first 5 words

        logger.debug(f"Generated product key: '{normalized}' from '{title}'")
        return normalized

    except Exception as e:
        logger.error(f"Error generating product key for title '{title}': {e}")
        # Fallback: return a basic normalized version
        try:
            return re.sub(r'[^\w\s]', ' ', title.lower()).strip()[:100]
        except:
            return "error_normalizing"


def calculate_similarity(key1: str, key2: str) -> float:
    """
    Calculate similarity between two product keys.
    This is a simple implementation - could be enhanced with more sophisticated algorithms.

    Args:
        key1: First product key
        key2: Second product key

    Returns:
        float: Similarity score between 0.0 and 1.0
    """
    if not key1 or not key2:
        return 0.0

    # Simple word overlap similarity
    words1 = set(key1.lower().split())
    words2 = set(key2.lower().split())

    if not words1 or not words2:
        return 0.0

    intersection = words1.intersection(words2)
    union = words1.union(words2)

    return len(intersection) / len(union)

