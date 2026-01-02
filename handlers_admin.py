"""
Полноценная админка для Yandex.Market бота
Все команды через кнопки, интерактивный ввод параметров
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Optional
from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import config
from database import Database

logger = logging.getLogger(__name__)

router = Router()


# FSM состояния для интерактивного ввода
class AdminStates(StatesGroup):
    waiting_for_url = State()
    waiting_for_search_query = State()
    waiting_for_n_value = State()
    waiting_for_qr_url = State()
    waiting_for_schedule_hours = State()
    waiting_for_schedule_interval = State()


# Глобальное хранилище состояний (в продакшене лучше использовать Redis)
user_states: Dict[int, Dict] = {}


def is_admin(user_id: int) -> bool:
    """Проверка является ли пользователь администратором"""
    return user_id == config.ADMIN_ID or user_id in getattr(config, "ADMIN_IDS", [])


# ========== ГЛАВНОЕ МЕНЮ ==========
def create_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Создает главное меню админки"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Очередь", callback_data="admin_queue")],
            [
                InlineKeyboardButton(
                    text="📊 Аналитика", callback_data="admin_analytics"
                )
            ],
            [InlineKeyboardButton(text="📝 Контент", callback_data="admin_content")],
            [InlineKeyboardButton(text="⚙️ Система", callback_data="admin_system")],
            [
                InlineKeyboardButton(
                    text="🔧 Управление", callback_data="admin_management"
                )
            ],
        ]
    )
    return keyboard


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Главная команда админки"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У тебя нет доступа к админ-панели.")
        return

    admin_text = "🔐 <b>Админ-панель Yandex.Market бота</b>\n\n" "Выберите раздел:"

    keyboard = create_main_menu_keyboard()
    await message.answer(admin_text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "admin_main_menu")
async def admin_main_menu_callback(callback: CallbackQuery):
    """Возврат в главное меню"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    admin_text = "🔐 <b>Админ-панель Yandex.Market бота</b>\n\n" "Выберите раздел:"

    keyboard = create_main_menu_keyboard()
    await callback.message.edit_text(
        admin_text, reply_markup=keyboard, parse_mode="HTML"
    )
    try:
        await callback.answer()
    except:
        pass  # Already answered


# ========== РАЗДЕЛ: ОЧЕРЕДЬ ==========
def create_queue_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура раздела Очередь"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Очистить очередь", callback_data="queue_clear"
                )
            ],
            [InlineKeyboardButton(text="❌ Удалить", callback_data="queue_remove")],
            [InlineKeyboardButton(text="⏭ Следующие N", callback_data="queue_next")],
            [
                InlineKeyboardButton(
                    text="🔍 Поиск дубликатов", callback_data="queue_duplicates"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню", callback_data="admin_main_menu"
                )
            ],
        ]
    )
    return keyboard


@router.callback_query(F.data == "admin_queue")
async def admin_queue_callback(callback: CallbackQuery):
    """Раздел Очередь"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    db = Database(config.DB_FILE)
    queue_count = db.get_queue_count()
    stats = db.get_queue_stats()

    text = (
        "📋 <b>Очередь</b>\n\n"
        f"📊 Всего в очереди: {queue_count}\n"
        f"✅ Опубликовано: {stats.get('published', 0)}\n"
        f"❌ Ошибок: {stats.get('errors', 0)}\n"
        f"📅 Сегодня: {stats.get('today', 0)}\n\n"
        "Выберите действие:"
    )

    keyboard = create_queue_keyboard()
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    try:
        await callback.answer()
    except:
        pass  # Already answered


@router.callback_query(F.data == "queue_clear")
async def queue_clear_callback(callback: CallbackQuery):
    """Очистка очереди с подтверждением"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    db = Database(config.DB_FILE)
    count = db.get_queue_count()

    if count == 0:
        await callback.answer("⚠️ Очередь уже пуста", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить", callback_data="queue_clear_confirm"
                )
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_queue")],
        ]
    )

    await callback.message.edit_text(
        f"⚠️ <b>Подтверждение очистки</b>\n\n"
        f"Будет удалено <b>{count}</b> элементов из очереди.\n"
        f"Это действие нельзя отменить!",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    try:
        await callback.answer()
    except:
        pass  # Already answered


@router.callback_query(F.data == "queue_clear_confirm")
async def queue_clear_confirm_callback(callback: CallbackQuery):
    """Подтверждение очистки очереди"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    db = Database(config.DB_FILE)
    count = db.clear_queue()

    logger.info(f"Admin {callback.from_user.id} cleared queue: {count} items")

    await callback.message.edit_text(
        f"✅ <b>Очередь очищена</b>\n\n" f"Удалено элементов: <b>{count}</b>",
        parse_mode="HTML",
    )
    try:
        await callback.answer("✅ Очередь очищена", show_alert=True)
    except:
        pass  # Already answered


@router.callback_query(F.data == "queue_remove")
async def queue_remove_callback(callback: CallbackQuery):
    """Удаление из очереди с кнопкой 'Удалить все'"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    db = Database(config.DB_FILE)
    queue_items = db.get_queue_urls(limit=50)

    if not queue_items:
        await callback.answer("⚠️ Очередь пуста", show_alert=True)
        return

    # Создаем клавиатуру с кнопками
    keyboard = []

    # Группируем по 2 кнопки в ряд
    for i in range(0, min(len(queue_items), 20), 2):
        row = []
        for j in range(2):
            if i + j < len(queue_items):
                task_id, url = queue_items[i + j]
                display_url = url[:30] + "..." if len(url) > 30 else url
                row.append(
                    InlineKeyboardButton(
                        text=f"❌ {i+j+1}", callback_data=f"queue_remove_item_{task_id}"
                    )
                )
        keyboard.append(row)

    # Кнопка "Удалить все"
    keyboard.append(
        [InlineKeyboardButton(text="🗑 Удалить все", callback_data="queue_remove_all")]
    )
    keyboard.append(
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_main_menu")]
    )

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    text = f"🗑️ <b>Удаление из очереди</b>\n\n"
    text += f"📊 Всего в очереди: {len(queue_items)}\n"
    text += f"👆 Выберите элемент для удаления:\n\n"

    # Показываем первые 10 элементов
    for idx, (task_id, url) in enumerate(queue_items[:10], 1):
        short_url = url[:50] + "..." if len(url) > 50 else url
        text += f"{idx}. {short_url}\n"

    if len(queue_items) > 10:
        text += f"\n... и еще {len(queue_items) - 10} элементов"

    await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    try:
        await callback.answer()
    except:
        pass  # Already answered


@router.callback_query(F.data == "queue_remove_all")
async def queue_remove_all_callback(callback: CallbackQuery):
    """Удаление всех элементов с подтверждением"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    db = Database(config.DB_FILE)
    count = db.get_queue_count()

    if count == 0:
        await callback.answer("⚠️ Очередь уже пуста", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить", callback_data="queue_remove_all_confirm"
                )
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="queue_remove")],
        ]
    )

    await callback.message.edit_text(
        f"⚠️ <b>Подтверждение удаления</b>\n\n"
        f"Будет удалено <b>все {count}</b> элементов из очереди.\n"
        f"Это действие нельзя отменить!",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    try:
        await callback.answer()
    except:
        pass  # Already answered


@router.callback_query(F.data == "queue_remove_all_confirm")
async def queue_remove_all_confirm_callback(callback: CallbackQuery):
    """Подтверждение удаления всех элементов"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    db = Database(config.DB_FILE)
    count = db.clear_queue()

    logger.info(f"Admin {callback.from_user.id} removed all from queue: {count} items")

    await callback.message.edit_text(
        f"✅ <b>Все элементы удалены</b>\n\n" f"Удалено элементов: <b>{count}</b>",
        parse_mode="HTML",
    )
    try:
        await callback.answer("✅ Все удалено", show_alert=True)
    except:
        pass  # Already answered


@router.callback_query(F.data.startswith("queue_remove_item_"))
async def queue_remove_item_callback(callback: CallbackQuery):
    """Удаление одного элемента из очереди"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    task_id_str = callback.data.replace("queue_remove_item_", "")
    try:
        task_id = int(task_id_str)
        db = Database(config.DB_FILE)

        # Получаем URL для логирования
        queue_items = db.get_queue_urls(limit=1000)
        url_to_remove = None
        for tid, url in queue_items:
            if tid == task_id:
                url_to_remove = url
                break

        if db.remove_from_queue(task_id=task_id):
            logger.info(
                f"Admin {callback.from_user.id} removed item {task_id} from queue: {url_to_remove}"
            )
            remaining = db.get_queue_count()
            try:
                await callback.answer("✅ Удалено из очереди", show_alert=True)
            except:
                pass  # Already answered
            await callback.message.edit_text(
                f"✅ <b>Удалено из очереди</b>\n\n"
                f"🔗 {url_to_remove[:60]}...\n\n"
                f"📊 Осталось в очереди: {remaining}",
                parse_mode="HTML",
            )
        else:
            await callback.answer("⚠️ Элемент не найден", show_alert=True)
    except ValueError:
        await callback.answer("❌ Ошибка: неверный ID", show_alert=True)


@router.callback_query(F.data == "queue_next")
async def queue_next_callback(callback: CallbackQuery, state: FSMContext):
    """Следующие N элементов - запрос количества"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="10", callback_data="queue_next_10")],
            [InlineKeyboardButton(text="25", callback_data="queue_next_25")],
            [InlineKeyboardButton(text="50", callback_data="queue_next_50")],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню", callback_data="admin_main_menu"
                )
            ],
        ]
    )

    await callback.message.edit_text(
        "⏭ <b>Следующие N элементов</b>\n\n" "Выберите количество:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    try:
        await callback.answer()
    except:
        pass  # Already answered


@router.callback_query(F.data.startswith("queue_next_"))
async def queue_next_n_callback(callback: CallbackQuery):
    """Показ следующих N элементов"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    n_str = callback.data.replace("queue_next_", "")
    try:
        n = int(n_str)
        db = Database(config.DB_FILE)
        queue_items = db.get_queue_urls(limit=n)

        if not queue_items:
            await callback.answer("⚠️ Очередь пуста", show_alert=True)
            return

        text = f"📋 <b>Следующие {len(queue_items)} элементов:</b>\n\n"
        for idx, (task_id, url) in enumerate(queue_items, 1):
            short_url = url[:60] + "..." if len(url) > 60 else url
            text += f"{idx}. {short_url}\n"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🏠 Главное меню", callback_data="admin_main_menu"
                    )
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        try:
            await callback.answer()
        except:
            pass  # Already answered
    except ValueError:
        try:
            await callback.answer("❌ Ошибка: неверное значение", show_alert=True)
        except:
            pass  # Already answered


@router.callback_query(F.data == "queue_duplicates")
async def queue_duplicates_callback(callback: CallbackQuery):
    """Поиск дубликатов в очереди"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    await callback.answer("🔍 Ищу дубликаты...", show_alert=False)

    db = Database(config.DB_FILE)
    queue_items = db.get_queue_urls(limit=1000)

    # Ищем дубликаты по URL
    url_counts = {}
    for task_id, url in queue_items:
        # Нормализуем URL (убираем параметры)
        clean_url = url.split("?")[0].split("#")[0]
        if clean_url not in url_counts:
            url_counts[clean_url] = []
        url_counts[clean_url].append((task_id, url))

    duplicates = {url: items for url, items in url_counts.items() if len(items) > 1}

    if not duplicates:
        text = "✅ <b>Дубликаты не найдены</b>"
    else:
        text = f"🔍 <b>Найдено дубликатов: {len(duplicates)}</b>\n\n"
        for idx, (url, items) in enumerate(list(duplicates.items())[:10], 1):
            short_url = url[:50] + "..." if len(url) > 50 else url
            text += f"{idx}. {short_url}\n"
            text += f"   Повторений: {len(items)}\n\n"

        if len(duplicates) > 10:
            text += f"... и еще {len(duplicates) - 10} дубликатов"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню", callback_data="admin_main_menu"
                )
            ]
        ]
    )

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    try:
        await callback.answer()
    except:
        pass  # Already answered


# ========== РАЗДЕЛ: СИСТЕМА ==========
def create_system_keyboard(autopublish_enabled: bool) -> InlineKeyboardMarkup:
    """Клавиатура раздела Система"""
    autopublish_text = (
        "✅ Автопубликация: ВКЛ" if autopublish_enabled else "❌ Автопубликация: ВЫКЛ"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=autopublish_text, callback_data="system_toggle_autopublish"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню", callback_data="admin_main_menu"
                )
            ],
        ]
    )
    return keyboard


@router.callback_query(F.data == "admin_system")
async def admin_system_callback(callback: CallbackQuery):
    """Раздел Система"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    db = Database(config.DB_FILE)
    autopublish_enabled = db.get_setting("auto_publish_enabled", "False").lower() in (
        "true",
        "1",
        "yes",
    )

    text = (
        "⚙️ <b>Система</b>\n\n"
        f"📢 Автопубликация: {'✅ Включена' if autopublish_enabled else '❌ Выключена'}\n\n"
        "Выберите действие:"
    )

    keyboard = create_system_keyboard(autopublish_enabled)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    try:
        await callback.answer()
    except:
        pass  # Already answered


@router.callback_query(F.data == "system_toggle_autopublish")
async def system_toggle_autopublish_callback(callback: CallbackQuery):
    """Переключение автопубликации"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    db = Database(config.DB_FILE)
    current_value = db.get_setting("auto_publish_enabled", "False").lower() in (
        "true",
        "1",
        "yes",
    )
    new_value = not current_value

    db.set_setting("auto_publish_enabled", "True" if new_value else "False")

    logger.info(f"Admin {callback.from_user.id} toggled autopublish: {new_value}")

    status_text = "✅ включена" if new_value else "❌ выключена"
    await callback.answer(f"Автопубликация {status_text}", show_alert=True)

    # Обновляем интерфейс
    text = (
        "⚙️ <b>Система</b>\n\n"
        f"📢 Автопубликация: {'✅ Включена' if new_value else '❌ Выключена'}\n\n"
        "Выберите действие:"
    )

    keyboard = create_system_keyboard(new_value)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    try:
        await callback.answer()
    except:
        pass  # Already answered
