"""
Button Service - генерация интерактивных inline кнопок для постов
"""

import logging
from typing import Optional, Dict, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)


def create_purchase_buttons(
    product_url: str,
    price: str,
    old_price: Optional[str] = None,
    has_discount: bool = False
) -> InlineKeyboardMarkup:
    """
    Создает inline кнопки для покупки товара.

    Args:
        product_url: Ссылка на товар на Yandex Market
        price: Текущая цена товара
        old_price: Старая цена (если есть скидка)
        has_discount: Есть ли скидка

    Returns:
        InlineKeyboardMarkup с кнопками
    """
    buttons = []

    # Основная кнопка "Купить" с ценой для повышения CTR
    buy_button_text = f"🛒 Купить за {price}"
    # Ограничиваем длину текста кнопки (Telegram limit ~20 chars visible)
    if len(buy_button_text) > 20:
        buy_button_text = f"🛒 Купить ({price})"
    if len(buy_button_text) > 25:
        buy_button_text = "🛒 Купить сейчас"

    buy_button = InlineKeyboardButton(
        text=buy_button_text,
        url=product_url
    )
    buttons.append([buy_button])

    # Дополнительные кнопки для товаров со скидкой
    if has_discount and old_price:
        # Кнопка "Показать экономию"
        savings_text = f"💰 Экономия: {calculate_savings(price, old_price)}"
        savings_button = InlineKeyboardButton(
            text=savings_text,
            callback_data="show_savings"
        )
        buttons.append([savings_button])

    # Кнопка "Поделиться"
    share_button = InlineKeyboardButton(
        text="📤 Поделиться",
        url=f"https://t.me/share/url?url={product_url}"
    )
    buttons.append([share_button])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def calculate_savings(current_price: str, old_price: str) -> str:
    """
    Рассчитывает сумму экономии.

    Args:
        current_price: Текущая цена
        old_price: Старая цена

    Returns:
        Строка с суммой экономии
    """
    try:
        current = float(current_price.replace(" ", "").replace(",", "."))
        old = float(old_price.replace(" ", "").replace(",", "."))
        savings = old - current
        return f"{savings:.0f} ₽"
    except (ValueError, TypeError):
        return "?"


def create_product_action_buttons(
    product_data: Dict[str, Any],
    show_reviews: bool = True,
    show_similar: bool = False
) -> InlineKeyboardMarkup:
    """
    Создает расширенные кнопки действий для товара.

    Args:
        product_data: Данные товара
        show_reviews: Показывать ли кнопку отзывов
        show_similar: Показывать ли кнопку похожих товаров

    Returns:
        InlineKeyboardMarkup с расширенными кнопками
    """
    buttons = []

    # Основная кнопка покупки
    product_url = product_data.get("url") or product_data.get("product_url", "")
    if product_url:
        buy_button = InlineKeyboardButton(
            text="🛒 Купить сейчас",
            url=product_url
        )
        buttons.append([buy_button])

    # Кнопки дополнительных действий
    action_buttons = []

    if show_reviews and product_data.get("reviews"):
        action_buttons.append(
            InlineKeyboardButton(
                text="💬 Отзывы",
                callback_data="show_reviews"
            )
        )

    if show_similar:
        action_buttons.append(
            InlineKeyboardButton(
                text="🔍 Похожие товары",
                callback_data="show_similar"
            )
        )

    if action_buttons:
        buttons.append(action_buttons)

    # Кнопка "Добавить в избранное" (callback)
    favorite_button = InlineKeyboardButton(
        text="❤️ В избранное",
        callback_data="add_favorite"
    )
    buttons.append([favorite_button])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_navigation_buttons(
    category: str,
    current_page: int = 1,
    total_pages: int = 1
) -> InlineKeyboardMarkup:
    """
    Создает кнопки навигации для категоризации товаров.

    Args:
        category: Категория товара
        current_page: Текущая страница
        total_pages: Общее количество страниц

    Returns:
        InlineKeyboardMarkup с кнопками навигации
    """
    buttons = []

    # Кнопки категорий
    category_buttons = []
    categories = {
        "tech": "📱 Техника",
        "food": "🍕 Еда",
        "clothing": "👕 Одежда",
        "toys": "🧸 Игрушки",
        "books": "📚 Книги",
        "cosmetics": "💄 Косметика"
    }

    for cat_key, cat_name in categories.items():
        if cat_key == category:
            # Текущая категория - выделяем
            category_buttons.append(
                InlineKeyboardButton(
                    text=f"✅ {cat_name}",
                    callback_data=f"category_{cat_key}"
                )
            )
        else:
            category_buttons.append(
                InlineKeyboardButton(
                    text=cat_name,
                    callback_data=f"category_{cat_key}"
                )
            )

    # Разбиваем на строки по 2 кнопки
    for i in range(0, len(category_buttons), 2):
        buttons.append(category_buttons[i:i+2])

    # Кнопки навигации по страницам
    if total_pages > 1:
        nav_buttons = []
        if current_page > 1:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"page_{current_page-1}"
                )
            )

        nav_buttons.append(
            InlineKeyboardButton(
                text=f"{current_page}/{total_pages}",
                callback_data="current_page"
            )
        )

        if current_page < total_pages:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="Вперед ➡️",
                    callback_data=f"page_{current_page+1}"
                )
            )

        buttons.append(nav_buttons)

    return InlineKeyboardMarkup(inline_keyboard=buttons)
