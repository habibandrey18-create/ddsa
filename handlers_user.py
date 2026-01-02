"""
Обработчики для обычных пользователей
Поиск товаров на Yandex.Market
"""

import logging
import urllib.parse
from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import Command, CommandStart
import config
import database
from utils import scraper

logger = logging.getLogger(__name__)

router = Router()

# Хранилище выбранных категорий для пользователей
# Формат: {user_id: category_key}
user_categories = {}

# Хранилище результатов поиска товаров
# Формат: {user_id: {message_id: [список товаров]}}
products_storage = {}

# Маппинг категорий на ID категорий Yandex Market
CATEGORY_IDS = {
    "category_smartphones": "91491",  # Смартфоны
    "category_laptops": "91013",  # Ноутбуки
    "category_tablets": "6427100",  # Планшеты
    "category_headphones": "56179410",  # Наушники
    "category_tvs": "90531",  # Телевизоры
}

CATEGORY_NAMES = {
    "category_smartphones": "Смартфоны",
    "category_laptops": "Ноутбуки",
    "category_tablets": "Планшеты",
    "category_headphones": "Наушники",
    "category_tvs": "Телевизоры",
}


async def search_products(query: str, category_id: str = None, limit: int = 5):
    """
    Поиск товаров на Yandex Market
    Возвращает список товаров с информацией
    """
    try:
        # Формируем URL для поиска
        base_url = "https://market.yandex.ru/search"
        params = {
            "text": query,
            "cvredirect": "2",
        }

        if category_id:
            params["hid"] = category_id

        search_url = f"{base_url}?{urllib.parse.urlencode(params)}"
        logger.info(f"Searching products: {search_url}")

        # Используем scraper для получения данных
        # Для поиска нужно будет парсить страницу результатов
        # Пока возвращаем заглушку - в реальности нужно парсить HTML страницы поиска
        # или использовать API если доступно

        # Временная заглушка - в реальности здесь должен быть парсинг результатов поиска
        return []

    except Exception as e:
        logger.error(f"Error searching products: {e}")
        return []


@router.message(CommandStart())
async def cmd_start(message: Message):
    """
    Обработчик команды /start
    Приветствие с кнопкой "Начать работу"
    """
    user = message.from_user

    # Добавляем пользователя в БД
    await database.add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    # Формируем приветственное сообщение
    welcome_text = (
        "👋 <b>Добро пожаловать в Yandex.Market бот!</b>\n\n"
        "Я помогу тебе найти товары на Яндекс.Маркете.\n\n"
        "Нажми кнопку ниже, чтобы начать работу."
    )

    # Создаем клавиатуру с кнопкой "Начать работу"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Начать работу", callback_data="start_work")]
        ]
    )

    await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message):
    """
    Обработчик команды /help
    """
    help_text = (
        "📖 <b>Справка по использованию бота</b>\n\n"
        "🔍 <b>Поиск товаров:</b>\n"
        "1. Нажми /start и выбери категорию\n"
        "2. Отправь название товара для поиска\n"
        'Например: "iPhone 15" или "MacBook Pro"\n\n'
        "📱 <b>Категории:</b>\n"
        "• Смартфоны\n"
        "• Ноутбуки\n"
        "• Планшеты\n"
        "• Наушники\n"
        "• Телевизоры\n\n"
        "📊 <b>Статистика:</b>\n"
        "Используй /stats чтобы посмотреть свою статистику."
    )

    await message.answer(help_text, parse_mode="HTML")


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """
    Показ статистики пользователя
    """
    user_id = message.from_user.id
    stats = await database.get_user_stats(user_id)

    if stats:
        # Получаем выбранную категорию если есть
        current_category = user_categories.get(user_id)
        category_text = ""
        if current_category:
            category_name = CATEGORY_NAMES.get(current_category, "Не выбрана")
            category_text = f"\n📂 Текущая категория: {category_name}"

        stats_text = (
            f"📊 <b>Твоя статистика:</b>\n\n"
            f"👤 Имя: {stats.get('first_name', 'N/A')}\n"
            f"📥 Найдено товаров: {stats.get('downloads_count', 0)}{category_text}\n"
            f"📅 Дата регистрации: {stats.get('joined_at', 'N/A')[:10]}\n"
            f"🕐 Последняя активность: {stats.get('last_activity', 'N/A')[:16]}"
        )
    else:
        stats_text = "❌ Статистика не найдена. Используй /start для начала."

    await message.answer(stats_text, parse_mode="HTML")


@router.callback_query(F.data == "start_work")
async def start_work_callback(callback: CallbackQuery):
    """
    Обработчик кнопки "Начать работу"
    Показывает выбор категорий
    """
    # Создаем клавиатуру с категориями
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📱 Смартфоны", callback_data="category_smartphones"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💻 Ноутбуки", callback_data="category_laptops"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📱 Планшеты", callback_data="category_tablets"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎧 Наушники", callback_data="category_headphones"
                )
            ],
            [InlineKeyboardButton(text="📺 Телевизоры", callback_data="category_tvs")],
        ]
    )

    await callback.message.edit_text(
        "📂 <b>Выберите категорию товаров:</b>\n\n"
        "После выбора категории отправьте название товара для поиска.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("category_"))
async def category_callback(callback: CallbackQuery):
    """
    Обработчик выбора категории
    Сохраняет выбор и предлагает ввести запрос
    """
    user_id = callback.from_user.id
    category_key = callback.data
    category_name = CATEGORY_NAMES.get(category_key, "Неизвестная категория")

    # Сохраняем выбранную категорию
    user_categories[user_id] = category_key

    await callback.answer(f"✅ Выбрана категория: {category_name}", show_alert=False)

    # Показываем сообщение с инструкцией
    await callback.message.edit_text(
        f"✅ <b>Категория выбрана: {category_name}</b>\n\n"
        "🔍 Теперь отправьте название товара для поиска.\n"
        "Например: <i>iPhone 15</i> или <i>Samsung Galaxy</i>",
        parse_mode="HTML",
    )


@router.message(F.text & ~F.text.startswith("/"))
async def handle_search(message: Message):
    """
    Обработчик текстовых сообщений - поиск товаров
    """
    user_id = message.from_user.id
    query = message.text.strip()

    if len(query) < 2:
        await message.answer("❌ Запрос слишком короткий. Минимум 2 символа.")
        return

    # Проверяем, выбрана ли категория
    category_key = user_categories.get(user_id)
    if not category_key:
        await message.answer(
            "⚠️ Сначала выберите категорию!\n\n"
            'Используйте /start и нажмите "Начать работу"',
            parse_mode="HTML",
        )
        return

    category_name = CATEGORY_NAMES.get(category_key, "Неизвестная категория")
    category_id = CATEGORY_IDS.get(category_key)

    # Показываем что ищем
    search_msg = await message.answer(
        f"🔍 Ищу товары в категории <b>{category_name}</b>...", parse_mode="HTML"
    )

    # Ищем товары
    # Пока используем заглушку - в реальности нужно реализовать парсинг поиска
    # Для демонстрации создадим поисковую ссылку
    base_url = "https://market.yandex.ru/search"
    params = {
        "text": query,
        "cvredirect": "2",
    }
    if category_id:
        params["hid"] = category_id

    search_url = f"{base_url}?{urllib.parse.urlencode(params)}"

    # Показываем ссылку на поиск и предлагаем использовать её
    # В будущем здесь будет парсинг результатов
    results_text = (
        f"🔍 <b>Поиск: {query}</b>\n"
        f"📂 Категория: {category_name}\n\n"
        f'🔗 <a href="{search_url}">Открыть результаты на Яндекс.Маркете</a>\n\n'
        f"<i>Функция автоматического парсинга результатов находится в разработке.</i>"
    )

    await search_msg.edit_text(
        results_text, parse_mode="HTML", disable_web_page_preview=False
    )
