"""
Message Formatting Service - создание постов с улучшенной презентацией
"""

import re
import logging
from typing import Dict, Any, Optional, List

from src.services.ai_review_summarizer_service import summarize_reviews_with_openai

logger = logging.getLogger(__name__)


def calculate_discount_percent(current_price: str, old_price: str) -> float:
    """
    Вычисляет процент скидки на основе текущей и старой цены.

    Args:
        current_price: Текущая цена (строка с числом)
        old_price: Старая цена (строка с числом)

    Returns:
        float: Процент скидки (0-100), или 0 если расчет невозможен
    """
    try:
        # Извлекаем числа из строк цен
        current_clean = re.sub(r'[^\d.,]', '', current_price.replace(',', '.'))
        old_clean = re.sub(r'[^\d.,]', '', old_price.replace(',', '.'))

        current_float = float(current_clean)
        old_float = float(old_clean)

        if old_float <= 0 or current_float >= old_float:
            return 0.0

        discount = ((old_float - current_float) / old_float) * 100
        return round(discount, 1)

    except (ValueError, ZeroDivisionError) as e:
        logger.debug(f"Не удалось рассчитать скидку: current={current_price}, old={old_price}, error={e}")
        return 0.0


def generate_hashtags(category: str = "", brand: str = "", title: str = "") -> str:
    """
    Генерирует релевантные хэштеги на основе категории, бренда и названия товара.

    Args:
        category: Категория товара
        brand: Бренд товара
        title: Название товара

    Returns:
        str: Строка с хэштегами через пробел
    """
    hashtags = []

    # Базовые хэштеги по категориям
    category_hashtags = {
        "food": ["#еда", "#продукты", "#кулинария", "#вкусняшки"],
        "tech": ["#техника", "#гаджеты", "#электроника", "#технологии"],
        "clothing": ["#одежда", "#мода", "#стиль", "#shopping"],
        "toys": ["#игрушки", "#детские_товары", "#развитие", "#дети"],
        "books": ["#книги", "#читаем", "#образование", "#литература"],
        "cosmetics": ["#косметика", "#красота", "#уход", "#beauty"],
        "kitchen": ["#кухня", "#кухонная_техника", "#готовка", "#дом"],
        "home": ["#дом", "#уют", "#интерьер", "#бытовая_техника"],
        "sports": ["#спорт", "#активный_отдых", "#здоровье", "#фитнес"],
        "auto": ["#авто", "#автотовары", "#транспорт", "#машина"],
    }

    # Определяем категорию из названия если не указана
    if not category and title:
        title_lower = title.lower()
        if any(word in title_lower for word in ["кухн", "блендер", "мультиварк", "чайник", "кофеварк"]):
            category = "kitchen"
        elif any(word in title_lower for word in ["телефон", "ноутбук", "компьютер", "планшет", "телевизор"]):
            category = "tech"
        elif any(word in title_lower for word in ["одежд", "рубашк", "куртк", "обувь", "кроссовк"]):
            category = "clothing"
        elif any(word in title_lower for word in ["игрушк", "lego", "конструктор"]):
            category = "toys"
        elif any(word in title_lower for word in ["книг", "учебник"]):
            category = "books"
        elif any(word in title_lower for word in ["косметик", "крем", "шампунь"]):
            category = "cosmetics"
        elif any(word in title_lower for word in ["спорт", "тренажер", "велосипед"]):
            category = "sports"
        elif any(word in title_lower for word in ["авто", "шина", "масло", "аккумулятор"]):
            category = "auto"

    # Добавляем хэштеги категории
    if category in category_hashtags:
        hashtags.extend(category_hashtags[category][:3])  # Максимум 3 хэштега категории

    # Добавляем бренд если есть
    if brand and len(brand.strip()) > 2:
        # Очищаем бренд от специальных символов
        brand_clean = re.sub(r'[^\w\s]', '', brand).strip()
        if brand_clean and len(brand_clean) <= 20:  # Не слишком длинный бренд
            hashtags.append(f"#{brand_clean.lower()}")

    # Добавляем общие хэштеги
    general_hashtags = ["#покупки", "#товары", "#интернетмагазин", "#shopping"]
    hashtags.extend(general_hashtags[:2])  # Максимум 2 общих

    # Убираем дубликаты и ограничиваем количество
    unique_hashtags = list(dict.fromkeys(hashtags))[:6]  # Максимум 6 хэштегов

    return " ".join(unique_hashtags)


async def generate_post_caption(
    title: str,
    current_price: str,
    description: str = "",
    old_price: Optional[str] = None,
    reviews: Optional[List[str]] = None,
    category: str = "",
    brand: str = "",
    product_url: str = ""
) -> str:
    """
    Генерирует пост с улучшенной презентацией, включая:
    - Заголовок
    - Цену и скидку с процентами
    - Описание на основе отзывов (или fallback)
    - Хэштеги

    Args:
        title: Название товара
        current_price: Текущая цена
        description: Базовое описание товара
        old_price: Старая цена (для расчета скидки)
        reviews: Список отзывов для суммирования
        category: Категория товара
        brand: Бренд товара
        product_url: Ссылка на товар

    Returns:
        str: Отформатированный HTML текст поста
    """
    parts = []

    # 1. ЗАГОЛОВОК
    clean_title = title.strip()
    parts.append(f"🔥 <b>{clean_title}</b>")
    parts.append("")  # Пустая строка

    # 2. ЦЕНА И СКИДКА
    discount_percent = 0.0
    if old_price:
        discount_percent = calculate_discount_percent(current_price, old_price)
        # Форматируем как указано в требованиях
        parts.append(f"✅ {current_price} ₽ ( скидка -{discount_percent:.0f}%)")
        parts.append(f"❌ {old_price} ₽")
    else:
        # Обычная цена без скидки
        parts.append(f"💰 <b>Цена: {current_price} ₽</b>")
    parts.append("")  # Пустая строка

    # 3. ОПИСАНИЕ
    description_text = ""

    # Сначала пытаемся использовать AI-суммирование отзывов
    if reviews and len(reviews) > 0:
        try:
            logger.debug(f"Пытаемся суммировать {len(reviews)} отзывов через AI")
            ai_summary = await summarize_reviews_with_openai(reviews)
            if ai_summary and ai_summary.strip():
                description_text = ai_summary.strip()
                logger.info(f"Используем AI-суммирование отзывов: {description_text[:50]}...")
            else:
                logger.debug("AI-суммирование вернуло пустой результат, используем fallback")
        except Exception as e:
            logger.warning(f"Ошибка при AI-суммировании отзывов: {e}")

    # Fallback на базовое описание если AI не сработал или нет отзывов
    if not description_text and description:
        # Используем базовое описание, обрезаем до разумной длины
        desc_clean = re.sub(r'\s+', ' ', description.strip())
        if len(desc_clean) > 150:
            desc_clean = desc_clean[:147] + "..."
        description_text = desc_clean

    # Если совсем нет описания - используем generic fallback
    if not description_text:
        description_text = "Качественный товар с хорошими отзывами покупателей."

    parts.append(f"✍️ <i>{description_text}</i>")
    parts.append("")  # Пустая строка

    # 4. ССЫЛКА
    if product_url:
        parts.append(f'👉 <a href="{product_url}">Смотреть на Маркете</a>')
        parts.append("")  # Пустая строка

    # 5. ХЭШТЕГИ
    hashtags = generate_hashtags(category, brand, title)
    if hashtags:
        parts.append(hashtags)

    return "\n".join(parts)

