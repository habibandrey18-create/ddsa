"""Smart hashtag generator from product titles"""

import re
import logging
from typing import List, Set

logger = logging.getLogger(__name__)

# Category keywords mapping
CATEGORY_KEYWORDS = {
    # Electronics
    "iphone": ["#iPhone", "#Apple", "#Смартфон"],
    "samsung": ["#Samsung", "#Смартфон", "#Телефон"],
    "xiaomi": ["#Xiaomi", "#Смартфон"],
    "наушники": ["#Наушники", "#Аудио"],
    "airpods": ["#AirPods", "#Apple", "#Наушники"],
    "ноутбук": ["#Ноутбук", "#Техника"],
    "macbook": ["#MacBook", "#Apple", "#Ноутбук"],
    "playstation": ["#PlayStation", "#PS5", "#Игры"],
    "xbox": ["#Xbox", "#Игры"],
    # Fashion
    "nike": ["#Nike", "#Спорт", "#Одежда"],
    "adidas": ["#Adidas", "#Спорт"],
    "кроссовки": ["#Кроссовки", "#Обувь"],
    "джинсы": ["#Джинсы", "#Одежда"],
    "футболка": ["#Футболка", "#Одежда"],
    # Beauty
    "косметика": ["#Косметика", "#Красота"],
    "парфюм": ["#Парфюм", "#Красота"],
    "шампунь": ["#Шампунь", "#Уход"],
    # Home
    "посуда": ["#Посуда", "#ДляДома"],
    "чайник": ["#Чайник", "#Кухня"],
    "пылесос": ["#Пылесос", "#Техника"],
    # Kids
    "lego": ["#LEGO", "#Игрушки", "#ДляДетей"],
    "игрушки": ["#Игрушки", "#ДляДетей"],
    "конструктор": ["#Конструктор", "#Игрушки"],
    # Books
    "книга": ["#Книги", "#Чтение"],
    "учебник": ["#Учебники", "#Книги"],
}

# Garbage words to remove from titles
GARBAGE_WORDS = [
    "купить",
    "дешево",
    "скидка",
    "распродажа",
    "акция",
    "выгодно",
    "недорого",
    "цена",
    "заказать",
    "доставка",
    "бесплатная доставка",
    "быстрая доставка",
    "в наличии",
    "интернет-магазин",
    "магазин",
    "официальный",
    "оригинал",
    "buy",
    "cheap",
    "discount",
    "sale",
    "free shipping",
]


def clean_title(title: str) -> str:
    """
    Remove garbage words from product title.

    Args:
        title: Raw product title

    Returns:
        Cleaned title
    """
    if not title:
        return title

    cleaned = title
    title_lower = title.lower()

    # Remove garbage words (case-insensitive)
    for garbage in GARBAGE_WORDS:
        # Use regex to remove whole words only
        pattern = r"\b" + re.escape(garbage) + r"\b"
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    # Clean up extra spaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Remove trailing punctuation from garbage removal
    cleaned = re.sub(r"\s*[,;]\s*$", "", cleaned)

    return cleaned


def generate_hashtags(title: str, max_tags: int = 5) -> List[str]:
    """
    Generate relevant hashtags from product title.

    Args:
        title: Product title
        max_tags: Maximum number of hashtags to generate

    Returns:
        List of hashtags
    """
    if not title:
        return []

    hashtags: Set[str] = set()
    title_lower = title.lower()

    # Check for category keywords
    for keyword, tags in CATEGORY_KEYWORDS.items():
        if keyword in title_lower:
            hashtags.update(tags[:2])  # Add first 2 tags from category

    # Extract brand names (capitalized words)
    words = title.split()
    for word in words:
        # If word is capitalized and longer than 3 chars, might be a brand
        if len(word) > 3 and word[0].isupper() and word.isalpha():
            # Check if it's not a common word
            if word.lower() not in ["для", "от", "года", "лет", "the", "with", "and"]:
                hashtags.add(f"#{word}")

    # Add generic tags if not enough specific ones
    if len(hashtags) < 2:
        # Try to extract product type
        if any(word in title_lower for word in ["телефон", "смартфон", "iphone"]):
            hashtags.add("#Смартфон")
        elif any(word in title_lower for word in ["наушники", "headphones"]):
            hashtags.add("#Наушники")
        elif any(word in title_lower for word in ["ноутбук", "macbook", "laptop"]):
            hashtags.add("#Ноутбук")
        elif any(word in title_lower for word in ["одежда", "футболка", "куртка"]):
            hashtags.add("#Одежда")
        elif any(word in title_lower for word in ["книга", "book"]):
            hashtags.add("#Книги")
        else:
            hashtags.add("#ЯндексМаркет")

    # Always add general tag
    hashtags.add("#Скидки")

    # Limit to max_tags
    return list(hashtags)[:max_tags]


def enhance_post_text(
    title: str, description: str = "", price: str = "", discount: str = ""
) -> str:
    """
    Enhance post text with cleaned title and smart hashtags.

    Args:
        title: Product title
        description: Product description
        price: Product price
        discount: Discount info

    Returns:
        Enhanced text with hashtags
    """
    # Clean title
    cleaned_title = clean_title(title)

    # Generate hashtags
    hashtags = generate_hashtags(title)
    hashtag_text = " ".join(hashtags)

    # Build enhanced text
    text_parts = []

    # Title
    if cleaned_title:
        text_parts.append(f"<b>{cleaned_title}</b>")

    # Description
    if description and len(description) > 10:
        # Limit description length
        desc = description[:300]
        if len(description) > 300:
            desc += "..."
        text_parts.append(f"\n{desc}")

    # Price
    if price:
        price_line = f"\n💰 <b>Цена:</b> {price}"
        if discount:
            price_line += f" <b>(-{discount})</b>"
        text_parts.append(price_line)

    # Hashtags
    if hashtag_text:
        text_parts.append(f"\n\n{hashtag_text}")

    return "\n".join(text_parts)













