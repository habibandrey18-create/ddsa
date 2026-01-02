"""Professional text formatting service for Telegram posts"""

import re
import logging
import random
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Enhanced A/B Testing Templates with better discount visualization
TEMPLATE_A = {
    "name": "emoji_heavy",
    "template": """🔥 <b>{title}</b>

{discount_badge}{price_section}

✍️ <i>{description}</i>
{review_summary}

{hashtags}

👉 <a href="{url}">Купить на Маркете</a>""",
}

TEMPLATE_B = {
    "name": "professional",
    "template": """{title}

{discount_badge}{price_section}

Описание: {description}
{review_summary}

{hashtags}

Ссылка: {url}""",
}

# New modern template with enhanced visuals
TEMPLATE_C = {
    "name": "modern_compact",
    "template": """{discount_badge}
🔥 <b>{title}</b>

{price_section}

💬 {description}

{hashtags}
🛒 <a href="{url}">Купить</a>""",
}


def clean_title(title: str) -> str:
    """
    Очищает название товара от технического мусора.

    Удаляет:
    - "Global Version", "RU/A", "EU Version"
    - Артикулы в скобках
    - Технические коды
    - Рекламные фразы
    """
    if not title:
        return title

    cleaned = title

    # Удаляем технические версии
    patterns_to_remove = [
        r"\b(Global Version|RU/A|EU Version|International Version)\b",
        r"\b(Версия для России|Российская версия)\b",
        r"\([A-Z0-9]{6,}\)",  # Артикулы в скобках типа (ABC123456)
        r"\[[A-Z0-9]{6,}\]",  # Артикулы в квадратных скобках
        r"\b[A-Z]{2,}\d{4,}\b",  # Коды типа ABC1234
        r"\b(Артикул|Арт\.|SKU|Код):\s*[A-Z0-9]+\b",  # "Артикул: ABC123"
        r"\b(купить|заказать|дешево|скидка|распродажа|акция)\b",  # Рекламные слова
        r"\s+",  # Множественные пробелы
    ]

    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)

    # Удаляем текст в скобках (часто технические детали)
    cleaned = re.sub(r"\([^)]*\)", "", cleaned)
    cleaned = re.sub(r"\[[^\]]*\]", "", cleaned)

    # Очистка пробелов
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Удаляем лишние знаки препинания
    cleaned = re.sub(r"[,;]{2,}", ",", cleaned)
    cleaned = cleaned.strip(" ,;")

    return cleaned


def format_price_section(current_price: str, old_price: Optional[str] = None) -> str:
    """
    Создает красивую секцию цены с визуализацией скидки.

    Args:
        current_price: Текущая цена
        old_price: Старая цена (для перечеркивания)

    Returns:
        Отформатированная секция цены
    """
    if not current_price:
        return "💰 Цена уточняется"

    # Убираем лишние символы
    price_clean = str(current_price).strip()

    if old_price:
        old_price_clean = str(old_price).strip()
        # Вычисляем экономию
        try:
            savings = float(old_price_clean.replace(' ', '').replace(',', '.')) - float(price_clean.replace(' ', '').replace(',', '.'))
            savings_text = f" (экономия {savings:.0f} ₽)"
        except (ValueError, TypeError):
            savings_text = ""

        return f"💰 <b>{price_clean}</b> <s>{old_price_clean}</s>{savings_text}"

    return f"💰 <b>{price_clean}</b>"


def format_discount_badge(discount_percent: float, old_price: Optional[str] = None, current_price: Optional[str] = None) -> str:
    """
    Создает бэйдж скидки для заголовка.

    Args:
        discount_percent: Процент скидки
        old_price: Старая цена
        current_price: Текущая цена

    Returns:
        Бэйдж скидки или пустая строка
    """
    if discount_percent > 0:
        return f"🔥 СКИДКА -{int(discount_percent)}% 🔥\n"
    elif old_price and current_price:
        try:
            old = float(str(old_price).replace(' ', '').replace(',', '.'))
            current = float(str(current_price).replace(' ', '').replace(',', '.'))
            calc_percent = ((old - current) / old) * 100
            if calc_percent >= 5:  # Только значимые скидки
                return f"🔥 СКИДКА -{int(calc_percent)}% 🔥\n"
        except (ValueError, TypeError):
            pass

    return ""


def format_price(price: str, old_price: Optional[str] = None) -> str:
    """
    Устаревшая функция для обратной совместимости.
    Используйте format_price_section вместо неё.
    """
    return format_price_section(price, old_price)


def format_discount(discount_percent: float) -> str:
    """
    Форматирует информацию о скидке.

    Args:
        discount_percent: Процент скидки (0-100)

    Returns:
        Отформатированная строка или пустая строка если скидки нет
    """
    if discount_percent <= 0:
        return ""

    return f"📉 Скидка: -{int(discount_percent)}%"


def truncate_description(description: str, max_length: int = 200) -> str:
    """
    Обрезает описание до нужной длины.

    Args:
        description: Полное описание
        max_length: Максимальная длина

    Returns:
        Обрезанное описание
    """
    if not description:
        return ""

    # Убираем лишние пробелы
    desc = re.sub(r"\s+", " ", description).strip()

    if len(desc) <= max_length:
        return desc

    # Обрезаем по предложениям
    sentences = desc.split(".")
    result = ""

    for sentence in sentences:
        if len(result + sentence + ".") <= max_length:
            result += sentence + "."
        else:
            break

    # Если ничего не набралось, обрезаем по словам
    if not result:
        words = desc.split()
        for word in words:
            if len(result + word + " ") <= max_length - 3:
                result += word + " "
            else:
                break
        result = result.strip() + "..."
    else:
        result = result.strip()

    return result


def format_product_post(
    title: str,
    price: str,
    description: str = "",
    discount_percent: float = 0,
    old_price: Optional[str] = None,
    product_url: str = "",
    anchor_text: str = "Смотреть на Маркете",
) -> str:
    """
    Форматирует профессиональный пост для Telegram канала.

    Args:
        title: Название товара
        price: Текущая цена
        description: Описание товара
        discount_percent: Процент скидки
        old_price: Старая цена (опционально)
        product_url: Ссылка на товар
        anchor_text: Текст ссылки

    Returns:
        Отформатированный HTML текст поста
    """
    # Очищаем название
    clean_title_text = clean_title(title)

    # Форматируем цену
    price_text = format_price(price, old_price)

    # Форматируем скидку
    discount_text = format_discount(discount_percent)

    # Обрезаем описание
    short_desc = truncate_description(description, max_length=200)

    # Формируем пост
    parts = []

    # Заголовок
    parts.append(f"🔥 <b>{clean_title_text}</b>")
    parts.append("")  # Пустая строка

    # Цена и скидка
    parts.append(price_text)
    if discount_text:
        parts.append(discount_text)
    parts.append("")  # Пустая строка

    # Описание
    if short_desc:
        parts.append(f"✍️ <i>{short_desc}</i>")
        parts.append("")  # Пустая строка

    # Ссылка
    if product_url:
        parts.append(f'👉 <a href="{product_url}">{anchor_text}</a>')

    return "\n".join(parts)


def enhance_existing_caption(
    caption: str, price: str = None, discount_percent: float = 0
) -> str:
    """
    Улучшает существующий caption, добавляя профессиональное форматирование.

    Args:
        caption: Существующий текст поста
        price: Цена (если нужно добавить)
        discount_percent: Процент скидки

    Returns:
        Улучшенный текст
    """
    if not caption:
        return caption

    # Извлекаем title из caption (первая строка с <b>)
    title_match = re.search(r"<b>(.*?)</b>", caption)
    if title_match:
        title = title_match.group(1)
        cleaned_title = clean_title(title)
        # Заменяем title в caption
        caption = caption.replace(f"<b>{title}</b>", f"🔥 <b>{cleaned_title}</b>")

    # Добавляем форматирование цены если её нет
    if price and "💰" not in caption and "Цена" not in caption:
        price_text = format_price(price)
        discount_text = format_discount(discount_percent)

        # Вставляем после заголовка
        if "<b>" in caption:
            parts = caption.split("\n", 1)
            caption = parts[0] + "\n\n" + price_text
            if discount_text:
                caption += "\n" + discount_text
            if len(parts) > 1:
                caption += "\n\n" + parts[1]

    return caption


def get_random_template() -> Tuple[str, Dict[str, Any]]:
    """
    Возвращает случайный A/B тест шаблон.

    Returns:
        Tuple из (template_type, template_config)
    """
    template = random.choice([TEMPLATE_A, TEMPLATE_B])
    return template["name"], template


def format_product_post_ab(
    title: str,
    price: str,
    description: str = "",
    discount_percent: float = 0,
    old_price: Optional[str] = None,
    product_url: str = "",
    template_type: Optional[str] = None,
    review_summary: Optional[str] = None,
    category: str = "default",
    enable_hashtags: bool = True,
) -> Tuple[str, str]:
    """
    Форматирует пост для A/B тестирования с указанным шаблоном.
    Новая версия с поддержкой отзывов, хэштегов и улучшенной визуализацией скидок.

    Args:
        title: Название товара
        price: Текущая цена
        description: Описание товара
        discount_percent: Процент скидки
        old_price: Старая цена (опционально)
        product_url: Ссылка на товар
        template_type: Тип шаблона ("emoji_heavy", "professional", "modern_compact").
                        Если None - выбирается случайно.
        review_summary: Суммаризованные отзывы (опционально)
        category: Категория товара для хэштегов
        enable_hashtags: Включать ли хэштеги

    Returns:
        Tuple из (caption, template_type)
    """
    # Выбираем шаблон
    if template_type:
        if template_type == "emoji_heavy":
            template_config = TEMPLATE_A
        elif template_type == "professional":
            template_config = TEMPLATE_B
        elif template_type == "modern_compact":
            template_config = TEMPLATE_C
        else:
            # Fallback на случайный
            template_type, template_config = get_random_template()
    else:
        template_type, template_config = get_random_template()

    # Очищаем название
    clean_title_text = clean_title(title)

    # Создаем секцию цены с улучшенной визуализацией
    price_section = format_price_section(price, old_price)

    # Создаем бэйдж скидки
    discount_badge = format_discount_badge(discount_percent, old_price, price)

    # Форматируем отзывы
    review_text = ""
    if review_summary:
        review_text = format_review_summary(review_summary)

    # Генерируем хэштеги
    hashtags = ""
    if enable_hashtags:
        hashtags = generate_hashtags(title, category)
        if hashtags:
            hashtags = f"\n{hashtags}"

    # Обрезаем описание
    short_desc = truncate_description(description, max_length=200)

    # Формируем caption по шаблону
    template = template_config["template"]

    # Заменяем плейсхолдеры
    caption = template.format(
        title=clean_title_text,
        price_section=price_section,
        discount_badge=discount_badge,
        description=short_desc,
        review_summary=review_text,
        hashtags=hashtags,
        url=product_url,
    )

    return caption, template_type


def format_review_summary(review_summary: str, max_length: int = 150) -> str:
    """
    Форматирует суммаризованные отзывы для поста.

    Args:
        review_summary: Суммаризованный текст отзывов
        max_length: Максимальная длина

    Returns:
        Отформатированный текст отзывов
    """
    if not review_summary or not review_summary.strip():
        return ""

    summary = review_summary.strip()
    if len(summary) > max_length:
        summary = summary[:max_length-3] + "..."

    return f"\n🤖 <i>Отзывы: {summary}</i>"


def generate_hashtags(title: str, category: str = "default", max_hashtags: int = 3) -> str:
    """
    Генерирует навигационные хэштеги на основе названия товара и категории.

    Args:
        title: Название товара
        category: Категория товара
        max_hashtags: Максимальное количество хэштегов

    Returns:
        Строка с хэштегами через пробел
    """
    if not title:
        return ""

    hashtags = []
    title_lower = title.lower()

    # Категорийные хэштеги
    category_hashtags = {
        "tech": ["#техника", "#гаджеты", "#электроника"],
        "food": ["#еда", "#продукты", "#вкусняшки"],
        "clothing": ["#одежда", "#мода", "#стиль"],
        "toys": ["#игрушки", "#детские", "#развитие"],
        "books": ["#книги", "#чтение", "#образование"],
        "cosmetics": ["#косметика", "#красота", "#уход"],
        "default": ["#покупки", "#товары", "#маркет"]
    }

    # Добавляем хэштеги категории
    cat_hashtags = category_hashtags.get(category, category_hashtags["default"])
    hashtags.extend(cat_hashtags[:2])  # Максимум 2 от категории

    # Специфические хэштеги на основе названия
    specific_hashtags = []

    # Техника
    if any(word in title_lower for word in ["телефон", "смартфон", "iphone", "android", "samsung"]):
        specific_hashtags.extend(["#смартфоны", "#мобильные"])
    elif any(word in title_lower for word in ["ноутбук", "компьютер", "macbook"]):
        specific_hashtags.extend(["#ноутбуки", "#компьютеры"])
    elif any(word in title_lower for word in ["наушник", "гарнитура", "bluetooth"]):
        specific_hashtags.extend(["#наушники", "#аудио"])

    # Одежда
    elif any(word in title_lower for word in ["куртк", "пальто", "ветровка"]):
        specific_hashtags.extend(["#верхняяодежда", "#осень"])
    elif any(word in title_lower for word in ["кроссовк", "ботинок", "туфл"]):
        specific_hashtags.extend(["#обувь", "#sneakers"])

    # Еда
    elif any(word in title_lower for word in ["шоколад", "конфет"]):
        specific_hashtags.extend(["#сладости", "#десерты"])
    elif any(word in title_lower for word in ["кофе", "чай"]):
        specific_hashtags.extend(["#напитки", "#кофе"])

    # Общие
    elif any(word in title_lower for word in ["скидк", "акци", "распродаж"]):
        specific_hashtags.extend(["#скидки", "#акции"])

    hashtags.extend(specific_hashtags)

    # Убираем дубликаты и ограничиваем количество
    unique_hashtags = list(dict.fromkeys(hashtags))[:max_hashtags]

    return " ".join(unique_hashtags) if unique_hashtags else ""


def get_random_template():
    """
    Возвращает случайный шаблон из доступных.

    Returns:
        Tuple из (template_type, template_config)
    """
    import random
    templates = [TEMPLATE_A, TEMPLATE_B, TEMPLATE_C]
    template_config = random.choice(templates)
    return template_config["name"], template_config
