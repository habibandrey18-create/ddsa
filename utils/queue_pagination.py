"""Interactive queue management with pagination"""

from typing import List, Tuple
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def create_queue_page(
    items: List[Tuple[int, str]],
    page: int = 0,
    items_per_page: int = 5,
    total_items: int = None,
) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Create paginated queue view with interactive buttons.

    Args:
        items: List of (queue_id, url) tuples
        page: Current page number (0-based)
        items_per_page: Items to show per page
        total_items: Total number of items (for pagination)

    Returns:
        Tuple of (text_message, inline_keyboard)
    """
    if not items:
        return "📭 Очередь пуста", None

    # Calculate pagination
    total_items = total_items or len(items)
    total_pages = (total_items + items_per_page - 1) // items_per_page
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(items))
    page_items = items[start_idx:end_idx]

    # Build message text
    text = f"📋 <b>Очередь публикаций</b>\n"
    text += f"Страница {page + 1}/{total_pages} (всего: {total_items})\n\n"

    for idx, (queue_id, url) in enumerate(page_items, start=start_idx + 1):
        # Truncate URL for display
        display_url = url[:60] + "..." if len(url) > 60 else url
        text += f"{idx}. <code>{display_url}</code>\n"

    # Build keyboard
    keyboard = []

    # Row 1: Delete buttons for each item (2 per row)
    delete_buttons = []
    for queue_id, url in page_items:
        delete_buttons.append(
            InlineKeyboardButton(
                text=f"🗑 {queue_id}", callback_data=f"queue_delete:{queue_id}"
            )
        )

    # Split delete buttons into rows of 3
    for i in range(0, len(delete_buttons), 3):
        keyboard.append(delete_buttons[i : i + 3])

    # Row N: Navigation buttons
    nav_row = []

    if page > 0:
        nav_row.append(
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"queue_page:{page - 1}")
        )

    # Page indicator
    nav_row.append(
        InlineKeyboardButton(
            text=f"📄 {page + 1}/{total_pages}", callback_data="queue_page:current"
        )
    )

    if page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton(
                text="Вперед ➡️", callback_data=f"queue_page:{page + 1}"
            )
        )

    if nav_row:
        keyboard.append(nav_row)

    # Row N+1: Actions
    actions_row = [
        InlineKeyboardButton(text="🔄 Обновить", callback_data=f"queue_page:{page}"),
        InlineKeyboardButton(text="🗑 Очистить всё", callback_data="queue_clear_all"),
    ]
    keyboard.append(actions_row)

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    return text, markup


def create_stats_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for stats view"""
    keyboard = [
        [
            InlineKeyboardButton(text="📊 График", callback_data="stats_graph"),
            InlineKeyboardButton(text="📈 Детали", callback_data="stats_details"),
        ],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="stats_refresh")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)













