# bot.py
import asyncio
import logging
import os
import re
import sqlite3
import sys
from urllib.parse import urlparse
from typing import Dict, Any, Optional, List, Tuple

import sys

if sys.platform != "win32":
    try:
        import uvloop

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass

# Проверка наличия необходимых модулей
try:
    from aiogram import Bot, Dispatcher, types, F
except ImportError as e:
    print("=" * 60)
    print("ОШИБКА: Модуль aiogram не найден!")
    print("=" * 60)
    print("\nВозможные решения:")
    print("1. Активируйте виртуальное окружение:")
    print("   Windows: venv\\Scripts\\activate")
    print("   Linux/Mac: source venv/bin/activate")
    print("\n2. Или установите зависимости:")
    print("   pip install -r requirements.txt")
    print("\n3. Или используйте скрипт запуска:")
    print("   setup_and_run.bat")
    print("\n" + "=" * 60)
    sys.exit(1)

try:
    from aiogram.filters import Command, StateFilter
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.state import State, StatesGroup
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.enums import ParseMode
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
except ImportError:
    # Ошибка уже обработана выше
    sys.exit(1)

# Import settings directly from config.py file
import sys
import os
import importlib.util

# Get the path to config.py
config_py_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py")

try:
    # Load config.py directly as a module
    spec = importlib.util.spec_from_file_location("config_py", config_py_path)
    config_py = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_py)
    settings = config_py.settings
except (ImportError, AttributeError, RuntimeError) as e:
    # Fallback: create minimal settings object for when BOT_TOKEN is not set
    class FallbackSettings:
        BOT_TOKEN = None
        ADMIN_ID = 0
        CHANNEL_ID = "@test"
        ANCHOR_TEXT = "Test"
        DB_FILE = "test.db"
        # Add other defaults as needed for testing/development
        POST_INTERVAL = 3600
        SKIP_NO_PRICE = False
        MIN_PRICE = 0
        MAX_PRICE = 0
        MIN_DISCOUNT = 0
        NIGHT_START = 22
        NIGHT_END = 8
        IMAGE_MAX_MB = 5
        REF_CODE = None
        UTM_SOURCE = None
        UTM_MEDIUM = None
        UTM_CAMPAIGN = None
        DIGEST_FREQUENCY = 10
        DIGEST_MAX_ITEMS = 20
        DIGEST_MIN_ITEMS = 5
        USE_WEBHOOK = False
        WEBHOOK_URL = None
        WEBHOOK_PATH = None
        SCHEDULE_ENABLED = False
        SCHEDULE_HOURS = None
        SCHEDULE_ONE_PER_DAY = False

    settings = FallbackSettings()

from database import Database
from utils.scraper import scrape_yandex_market
from utils.image_proc import process_image
from utils.text_gen import generate_post_caption
from services.utils import (
    is_valid_yandex_market_url,
    extract_price_from_string,
    add_ref_and_utm,
    extract_discount_from_data,
)
from services.dependency_checker import check_dependencies
from services.image_service import remove_exif, check_image_quality, improve_image
from services.error_handler import ErrorHandler
from services.log_service import LogService
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Logging - для EXE логи в AppData, для скрипта - в logs/
import sys

if getattr(sys, "frozen", False):
    # EXE: логи в AppData
    appdata_dir = os.path.join(os.getenv("APPDATA"), "YandexMarketBot")
    if not os.path.exists(appdata_dir):
        os.makedirs(appdata_dir)
    log_dir = os.path.join(appdata_dir, "logs")
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    log_file = os.path.join(log_dir, "bot.log")
else:
    # Скрипт: логи в папке logs/
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    log_file = os.path.join(log_dir, "bot.log")

# Настройка логирования с ротацией и фильтрацией
from logging.handlers import RotatingFileHandler

# Формат для файла (подробный, для отладки)
file_formatter = logging.Formatter(
    "[%(asctime)s] %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

# Формат для консоли (краткий, только важное)
console_formatter = logging.Formatter(
    "[%(asctime)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S"
)

# Файловый обработчик - все уровни (включая DEBUG)
file_handler = RotatingFileHandler(
    log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(file_formatter)

# Консольный обработчик - только важные уровни
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)  # INFO, WARNING, ERROR
console_handler.setFormatter(console_formatter)


# Фильтр для консоли - убираем избыточные сообщения
class ConsoleFilter(logging.Filter):
    def filter(self, record):
        # Пропускаем DEBUG сообщения
        if record.levelno == logging.DEBUG:
            return False
        # Пропускаем избыточные JSON дампы
        message = record.getMessage()
        if '{"' in message[:100] and record.levelno < logging.WARNING:
            return False
        # Пропускаем слишком длинные сообщения (дампы)
        if len(message) > 500 and record.levelno < logging.WARNING:
            return False
        return True


console_handler.addFilter(ConsoleFilter())

# Настройка корневого логгера
logging.basicConfig(
    level=logging.DEBUG,  # Минимальный уровень для всех
    handlers=[file_handler, console_handler],
    force=True,  # Переопределяем существующие обработчики
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Уровень для этого модуля

# Проверка зависимостей при старте (только для скрипта, не для EXE)
if not getattr(sys, "frozen", False):
    if not check_dependencies():
        logger.error(
            "Критические зависимости отсутствуют! Бот может работать некорректно."
        )


# FSM состояния для интерактивного ввода
class AdminStates(StatesGroup):
    waiting_for_url = State()
    waiting_for_search_query = State()
    waiting_for_n_value = State()
    waiting_for_qr_url = State()
    waiting_for_schedule_hours = State()
    waiting_for_schedule_interval = State()


# Singleton service instances - initialized once at module level
from services.http_client import HTTPClient
from database import Database

http_client = HTTPClient()
db = Database()

# Init - с обработкой ошибок
try:
    logger.info("Инициализация бота...")
    bot = Bot(token=settings.BOT_TOKEN)
    logger.info("✅ Bot создан")
    # Используем MemoryStorage для FSM
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    logger.info("✅ Dispatcher создан")
    db = Database(db_file=settings.DB_FILE)
    logger.info("✅ Database создана")

    # Global scheduler instance (for /turbo command access)
    global_scheduler = None

    # Включаем автопубликацию и автопоиск при старте
    try:
        db.set_setting("auto_publish_enabled", "True")
        logger.info("✅ Автопубликация включена")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось включить автопубликацию: {e}")
except Exception as e:
    logger.exception("❌ Ошибка инициализации: %s", e)
    print(f"❌ Ошибка инициализации: {e}")
    import traceback

    traceback.print_exc()
    raise

# Инициализация сервисов
from services.analytics_service import AnalyticsService
# from services.content_service import (
#     generate_ideas,
#     create_compilation_post,
#     analyze_trends,
# )  # These functions don't exist yet
from services.file_service import (
    cleanup_old_files,
    get_directory_size,
    remove_empty_directories,
    check_disk_space,
)
from services.url_service import UrlService

# Импортируем функции для обратной совместимости
try:
    from services.url_service import generate_qr_code, shorten_url
except ImportError:
    # Если функции не найдены, используем методы класса
    generate_qr_code = UrlService.generate_qr_code
    shorten_url = UrlService.shorten_url

analytics = AnalyticsService(settings.DB_FILE)
# auto_search будет инициализирован после создания bot и db

# Инициализация error handler и log service
# ErrorHandler и LogService уже импортированы выше (строки 28-29)
error_handler = ErrorHandler(bot=bot, admin_id=settings.ADMIN_ID)
log_service = LogService(log_file=log_file)

# Используем FSM storage для состояний вместо глобального словаря
# user_states теперь управляется через FSMContext в обработчиках

# Глобальные настройки через сервис с сохранением в БД
from services.state_service import get_global_settings, StateService

# Инициализируем после создания db
global_settings = None  # Будет инициализирован после создания db

# Задачи воркеров
queue_worker_task = None

# Временное хранилище для совместимости (будет удалено после полного перехода на FSM)
user_states: Dict[int, Dict] = {}  # DEPRECATED: используйте FSMContext


# --- Helper functions ---
def validate_product_url(url: str) -> tuple[bool, str]:
    """
    Валидация URL товара перед публикацией.
    Проверяет наличие корректного product_id и формат URL.
    Возвращает (is_valid, reason)
    """
    if not url or not isinstance(url, str):
        return False, "Пустой или неверный URL"

    # Проверка базового формата
    if "market.yandex.ru" not in url:
        return False, "URL не относится к Яндекс.Маркету"

    # Проверка на cc-ссылки (партнёрские ссылки) - они не содержат product_id
    if "/cc/" in url:
        # Проверяем, что после /cc/ есть код
        cc_match = re.search(r"/cc/([A-Za-z0-9=,\-_]+)", url)
        if cc_match:
            cc_code = cc_match.group(1)
            # CC коды могут быть от 5 символов (например, 8MU8TK)
            # Убираем параметры и хвосты
            cc_code_clean = cc_code.split("?")[0].split(",")[0].split("&")[0]
            if len(cc_code_clean) >= 5 and len(cc_code_clean) <= 30:
                # Проверяем, что код не является зарезервированным словом
                invalid_codes = ["https", "http", "www", "market", "yandex", "ru"]
                if cc_code_clean.lower() not in invalid_codes:
                    return True, ""
                else:
                    return (
                        False,
                        f"Некорректный CC код (зарезервированное слово): {cc_code_clean[:20]}",
                    )
            else:
                return (
                    False,
                    f"Некорректный CC код (длина должна быть от 5 до 30 символов): {cc_code_clean[:20]}",
                )
        else:
            return False, "CC ссылка без кода"

    # Проверка на некорректные карточки (без product_id)
    # Примеры некорректных: /card/naturalnoye-mylo-rozovoye-t (без числового ID)
    # Корректные: /product/123456 или /card/slug-123456

    # Ищем product_id в URL (в пути или параметрах)
    # Сначала проверяем параметры (для длинных URL с параметрами)
    param_id_match = re.search(
        r"[?&](?:id|product_id|offer_id|productId)=(\d{6,})", url, re.IGNORECASE
    )
    if param_id_match:
        product_id = param_id_match.group(1)
        if product_id.isdigit() and len(product_id) >= 6:
            return True, ""

    # Ищем product_id в пути URL
    product_id_match = re.search(r"/(\d{6,})", url)
    if product_id_match:
        product_id = product_id_match.group(1)
        # Проверяем, что это действительно числовой ID (минимум 6 цифр)
        if product_id.isdigit() and len(product_id) >= 6:
            return True, ""
        else:
            return False, f"Неверный формат product_id: {product_id}"

    # Проверка на /card/ без числового ID в конце
    if "/card/" in url:
        # Проверяем, есть ли числовой ID в конце или в параметрах
        # Пример: /card/naturalnoye-mylo-rozovoye-t - некорректный
        # Пример: /card/slug-123456 - корректный
        card_match = re.search(r"/card/([^/?]+)", url)
        if card_match:
            card_slug = card_match.group(1)
            # Если в конце slug есть числовой ID - OK
            if re.search(r"-\d{6,}$", card_slug):
                return True, ""
            # Если есть числовой ID в параметрах
            if re.search(r"[?&]id=(\d{6,})", url):
                return True, ""
            return False, f"Карточка без числового ID: {card_slug}"

    # Проверка на /product/ с числовым ID
    if "/product/" in url:
        product_match = re.search(r"/product/(\d{6,})", url)
        if product_match:
            return True, ""
        return False, "URL /product/ без числового ID"

    # Если это зеркало/агрегированный URL без явного ID
    if "offer" in url.lower() or "business" in url.lower():
        # Проверяем наличие ID в параметрах
        if re.search(r"[?&](id|product_id|offer_id)=(\d{6,})", url, re.IGNORECASE):
            return True, ""
        return False, "Агрегированный URL без product_id в параметрах"

    # Проверка для длинных URL с параметрами (например, jkofe--3-sht--shokoladnyy-brauni---...)
    # Ищем числовой ID в любом месте URL (в параметрах или в конце пути)
    long_url_id_match = re.search(
        r"[?&](?:id|product_id|productId|offer_id)=(\d{6,})", url, re.IGNORECASE
    )
    if long_url_id_match:
        product_id = long_url_id_match.group(1)
        if product_id.isdigit() and len(product_id) >= 6:
            return True, ""

    # Если URL очень длинный и содержит много дефисов, но нет явного ID
    # Это может быть некорректная карточка
    if len(url) > 150 and url.count("-") > 10:
        # Пытаемся найти ID в конце URL после последнего дефиса
        last_part = url.split("/")[-1].split("?")[0]
        if re.search(r"-(\d{6,})$", last_part):
            return True, ""
        return (
            False,
            "Длинный URL без явного product_id (возможно, некорректная карточка)",
        )

    return False, "Не удалось определить product_id в URL"


def has_sufficient_product_data(data: dict) -> bool:
    """
    Check if data has sufficient content for publishing (title OR price OR images).
    This is more lenient than validate_product_data - allows publishing even with partial data.

    Args:
        data: Product data dictionary

    Returns:
        True if data has at least one of: title, price, or image
    """
    if not data:
        return False

    # Check for title (non-empty string)
    title = data.get("title", "").strip()
    has_title = bool(title and len(title) >= 3)  # Minimum 3 chars to avoid junk

    # Check for price (numeric or string that looks like price)
    price_str = data.get("price", "").strip()
    has_price = False
    if price_str:
        # Remove currency symbols and check if it's numeric or contains digits
        clean_price = price_str.replace("₽", "").replace("руб", "").replace("р", "").strip()
        has_price = any(char.isdigit() for char in clean_price)

    # Check for images (bytes or URL)
    has_image = bool(
        data.get("image_bytes") or
        data.get("image_url") or
        data.get("images")  # Some parsers might return multiple images
    )

    return has_title or has_price or has_image


def validate_product_data(data: dict, url: str) -> tuple[bool, str]:
    """
    Валидация данных товара перед публикацией.
    Проверяет наличие обязательных полей и фильтрует "пустышки".
    Возвращает (is_valid, reason)
    """
    if not data:
        logger.warning(f"validate_product_data: пустые данные для {url[:100]}")
        return False, "Нет данных товара"

    # Проверка обязательных полей
    title = data.get("title", "").strip()
    if not title or len(title) < 3:
        logger.warning(
            f"validate_product_data: некорректное название для {url[:100]}: '{title}'"
        )
        return False, "Нет названия товара или оно слишком короткое"

    # Проверка на "нереальные" названия (слишком короткие или подозрительные)
    if len(title) < 5:
        logger.warning(
            f"validate_product_data: слишком короткое название для {url[:100]}: '{title}'"
        )
        return False, f"Название слишком короткое: '{title}'"

    # Улучшенная проверка на "пустышки" - подозрительные паттерны в названии
    title_lower = title.lower()

    # Проверка на подозрительные паттерны (только дефисы, только цифры, только спецсимволы)
    if re.match(r"^[\s\-_]+$", title):
        logger.warning(
            f"validate_product_data: название содержит только спецсимволы для {url[:100]}: '{title}'"
        )
        return False, "Название содержит только спецсимволы"

    # Проверка на слишком много дефисов (может быть некорректный slug)
    if title.count("-") > 10:
        logger.warning(
            f"validate_product_data: слишком много дефисов в названии для {url[:100]}: '{title}'"
        )
        return False, "Слишком много дефисов в названии (возможно, некорректный slug)"

    # Проверка на повторяющиеся слова (может быть ошибка парсинга)
    words = title_lower.split()
    if len(words) > 3:
        word_counts = {}
        for word in words:
            if len(word) > 2:  # Игнорируем короткие слова
                word_counts[word] = word_counts.get(word, 0) + 1
        if any(count > 3 for count in word_counts.values()):
            logger.warning(
                f"validate_product_data: повторяющиеся слова в названии для {url[:100]}: '{title}'"
            )
            return False, "Повторяющиеся слова в названии (возможно, ошибка парсинга)"

    # Проверка цены (должна быть указана или "Цена уточняется")
    price_str = data.get("price", "").strip()
    if not price_str:
        logger.warning(f"validate_product_data: нет цены для {url[:100]}")
        return False, "Нет цены"
    # Согласованность с should_skip_product: если SKIP_NO_PRICE включен, отклоняем "Цена уточняется"
    if settings.SKIP_NO_PRICE and price_str == "Цена уточняется":
        logger.warning(
            f"validate_product_data: цена уточняется (SKIP_NO_PRICE=True) для {url[:100]}"
        )
        return False, "Нет цены"

    # Проверка наличия в продаже (если есть поле status)
    status = data.get("status", "").lower()
    if status and (
        "недоступен" in status or "снят" in status or "out of stock" in status
    ):
        logger.warning(
            f"validate_product_data: товар недоступен для {url[:100]}: {status}"
        )
        return False, f"Товар недоступен: {status}"

    # Проверка изображения (желательно, но не обязательно)
    image_url = data.get("image_url")
    image_bytes = data.get("image_bytes")
    if not image_url and not image_bytes:
        logger.debug(
            f"validate_product_data: нет изображения для {url[:100]}, но это не критично"
        )

    # Проверка is_valid от AI (если данные пришли от AI)
    flags = data.get("flags", [])
    if "ai_ok" in flags or "from_ai" in flags:
        # Если данные от AI, проверяем наличие is_valid
        # В scraper.py мы используем ValidatedResult, который всегда валиден
        # Но если есть явный флаг is_valid=False, отклоняем
        ai_is_valid = data.get("ai_is_valid")
        if ai_is_valid is False:
            reason_if_invalid = data.get("reason_if_invalid", "AI marked as invalid")
            logger.warning(
                f"validate_product_data: AI marked product as invalid for {url[:100]}: {reason_if_invalid}"
            )
            return False, f"AI validation failed: {reason_if_invalid}"

        # Проверка reason_if_invalid для фильтрации
        reason_if_invalid = data.get("reason_if_invalid", "").lower()
        if reason_if_invalid:
            # Фильтруем товары с низкой релевантностью, дубликатами, плохой ценой
            if any(
                keyword in reason_if_invalid
                for keyword in ["low_relevance", "duplicate", "bad_price", "not_found"]
            ):
                logger.warning(
                    f"validate_product_data: AI filtered product for {url[:100]}: {reason_if_invalid}"
                )
                return False, f"AI filter: {reason_if_invalid}"

    # Дополнительная проверка: если данные минимальные - это подозрительно
    if len(title) < 10 and not image_url and not image_bytes:
        logger.warning(
            f"validate_product_data: минимальные данные для {url[:100]}, возможно битая карточка"
        )
        return False, "Минимальные данные товара (возможно, битая карточка)"

    # Проверка на наличие описания или других полей (для лучшей валидации)
    description = data.get("description", "").strip()
    # Если нет описания, но есть хотя бы изображение - OK
    if not description and not image_url and not image_bytes:
        # Проверяем, что название достаточно информативное
        if len(title) < 15:
            logger.warning(
                f"validate_product_data: недостаточно данных для {url[:100]}: нет описания и изображения, короткое название"
            )
            return (
                False,
                "Недостаточно данных товара (нет описания и изображения, короткое название)",
            )

    return True, ""


def should_skip_product(data: dict) -> tuple[bool, str]:
    """Проверяет, нужно ли пропустить товар. Возвращает (skip, reason)"""
    # Проверка черного списка
    url = data.get("url", "")
    if db.is_blacklisted(url):
        return True, "В черном списке"

    # Проверка цены
    price_str = data.get("price", "")
    if settings.SKIP_NO_PRICE and (not price_str or price_str == "Цена уточняется"):
        return True, "Нет цены"

    price = extract_price_from_string(price_str)
    if price > 0:
        if settings.MIN_PRICE > 0 and price < settings.MIN_PRICE:
            return True, f"Цена ниже минимума ({settings.MIN_PRICE}₽)"
        if settings.MAX_PRICE > 0 and price > settings.MAX_PRICE:
            return True, f"Цена выше максимума ({settings.MAX_PRICE}₽)"

    # Проверка скидки
    if settings.MIN_DISCOUNT > 0:
        discount = extract_discount_from_data(data)
        if discount < settings.MIN_DISCOUNT:
            return (
                True,
                f"Скидка меньше минимума ({settings.MIN_DISCOUNT}%, найдено {discount}%)",
            )

    return False, ""


# --- Price Drop Monitor Storage ---
# Module-level storage for price drop info (URL -> price_drop_info dict)
_price_drop_info: Dict[str, Dict[str, any]] = {}


# --- CORE publish function ---
async def process_and_publish(
    url: str,
    chat_id: int = None,
    retry_count: int = 3,
    queue_id: Optional[int] = None,
) -> Tuple[bool, Optional[int]]:
    """
    Парсит товар и постит либо фото+текст, либо только текст (если фото нет).

    Args:
        url: Product URL
        chat_id: Optional chat ID for notifications
        retry_count: Number of retry attempts
        queue_id: Optional queue ID for state tracking

    Returns:
        Tuple of (success: bool, message_id: Optional[int])
    """
    from utils.correlation_id import set_correlation_id, get_correlation_id
    from utils.product_key_generator import generate_product_key
    import uuid
    from datetime import datetime

    # Генерируем correlation_id если его еще нет
    correlation_id = get_correlation_id()
    if not correlation_id:
        correlation_id = str(uuid.uuid4())[:8]
        set_correlation_id(correlation_id)
    logger.info(
        "process_and_publish: start %s (retry_count=%d, correlation_id=%s)",
        url,
        retry_count,
        correlation_id,
    )

    # Check Night Mode (silent posting during night hours)
    current_hour = datetime.now().hour
    night_start = settings.NIGHT_START
    night_end = settings.NIGHT_END

    # Handle night mode that spans midnight (e.g., 23:00 to 08:00)
    if night_start > night_end:
        # Night mode spans midnight (e.g., 23:00-08:00)
        is_night = current_hour >= night_start or current_hour < night_end
    else:
        # Night mode within same day (e.g., 22:00-23:00)
        is_night = night_start <= current_hour < night_end

    # Use silent notifications during night mode
    disable_notification = is_night

    if is_night:
        logger.info(
            "🌙 Night Mode active - posting silently (current_hour=%d, night_hours=%d-%d, correlation_id=%s)",
            current_hour,
            night_start,
            night_end,
            correlation_id,
        )

    # Валидация URL (базовая проверка)
    if not is_valid_yandex_market_url(url):
        error_msg = f"❌ Неверный URL Яндекс.Маркета: {url}"
        if chat_id:
            await bot.send_message(chat_id, error_msg)
        logger.warning(
            "process_and_publish: invalid URL %s (correlation_id=%s)",
            url,
            correlation_id,
        )
        return False, None

    # Расширенная валидация URL (проверка product_id)
    url_valid, url_reason = validate_product_url(url)
    if not url_valid:
        error_msg = f"❌ Некорректный URL товара: {url_reason}\nURL: {url[:100]}"
        if chat_id:
            await bot.send_message(chat_id, error_msg)
        logger.warning(
            "process_and_publish: invalid product URL %s: %s (correlation_id=%s)",
            url,
            url_reason,
            correlation_id,
        )
        # Помечаем в очередь ошибок для отладки
        try:
            db.add_to_error_queue(url, url_reason)
        except (sqlite3.Error, AttributeError, TypeError) as e:
            logger.debug(f"Failed to add to error queue: {e}")
        return False, None

    # 0) Check blacklist
    if db.is_blacklisted(url):
        if chat_id:
            await bot.send_message(chat_id, f"🚫 Товар в черном списке: {url}")
        logger.info(
            "process_and_publish: blacklisted url %s (correlation_id=%s)",
            url,
            correlation_id,
        )
        return False, None

    # 1) Check history (URL) - сначала проверяем БД с нормализацией
    if db.exists_url(url, check_normalized=True):
        if chat_id:
            await bot.send_message(chat_id, f"⚠️ Эта ссылка уже опубликована: {url}")
        logger.info(
            "process_and_publish: duplicate url (normalized check) %s (correlation_id=%s)",
            url,
            correlation_id,
        )
        return False, None

    # 1.5) Check channel for duplicates via Telegram API
    async def check_channel_duplicate(url_to_check: str, channel_id: str) -> bool:
        """Проверяет, есть ли ссылка в последних сообщениях канала"""
        try:
            import re

            # Извлекаем product_id из URL
            product_id_match = re.search(r"/(\d{6,})(?:\?|$)", url_to_check)
            if not product_id_match:
                return False

            product_id = product_id_match.group(1)
            normalized_url = re.sub(r"\?.*$", "", url_to_check)

            # Получаем последние сообщения из канала через Telegram Bot API
            try:
                # Используем метод get_chat для получения информации о канале
                # Затем получаем последние сообщения через forward или через поиск
                # В aiogram 3.x можно использовать метод получения сообщений через forward
                # Для проверки дубликатов используем поиск по product_id в тексте сообщений

                # Получаем последние сообщения из канала через метод get_chat_history
                # Но в aiogram 3.x нет прямого метода get_chat_history, используем другой подход
                # Для проверки дубликатов используем поиск по тексту в последних сообщениях
                # Проще всего - использовать метод получения сообщений через forward
                # Но для упрощения - проверяем через нормализованный URL и product_id
                # Если в канале есть сообщение с таким же product_id - это дубликат

                # Используем метод получения последних сообщений через API напрямую
                # Для проверки дубликатов используем более простой подход:
                # Проверяем через нормализованный URL в тексте сообщений
                # Если в канале есть сообщение с таким же product_id - это дубликат

                # В aiogram нет прямого метода get_chat_history, но можно использовать forward или search
                # Для упрощения - проверяем только через БД (уже сделано выше)
                # Если нужно проверить канал - можно использовать метод получения сообщений через API
                # Но для упрощения - пропускаем проверку канала, используем только БД

                # ВРЕМЕННО: отключаем проверку канала, так как она даёт ложные срабатывания
                # TODO: Реализовать правильную проверку дубликатов через канал Telegram используя правильный API
                return False  # Пока возвращаем False, используем только БД
            except Exception as api_error:
                logger.warning(
                    "check_channel_duplicate: error getting messages: %s",
                    str(api_error)[:200],
                )
                return False
        except Exception as e:
            logger.warning("check_channel_duplicate: error: %s", str(e)[:200])
            return False

    # Проверяем канал на дубликаты (ВРЕМЕННО ОТКЛЮЧЕНО - даёт ложные срабатывания)
    # TODO: Реализовать правильную проверку дубликатов через Telegram Bot API
    channel_id = settings.CHANNEL_ID
    if False and channel_id:  # Временно отключено
        try:
            is_duplicate = await check_channel_duplicate(url, channel_id)
            if is_duplicate:
                if chat_id:
                    await bot.send_message(
                        chat_id, f"⚠️ Эта ссылка уже опубликована: {url}"
                    )
                logger.info(
                    "process_and_publish: duplicate url found in channel %s (correlation_id=%s)",
                    url,
                    correlation_id,
                )
                return False, None
        except Exception as e:
            logger.warning(
                "process_and_publish: error in channel duplicate check: %s (correlation_id=%s)",
                str(e)[:200],
                correlation_id,
            )
            # Не блокируем публикацию, если проверка канала не удалась

    # 2) Нормализация URL и получение данных товара
    # Используем normalize_market_url для правильной обработки card-URL и cc-URL
    from utils.url_normalizer import normalize_market_url
    from services.scrape_service import get_product_data

    # Нормализуем URL (один раз, resolve_final_url вызывается внутри)
    url_info = await normalize_market_url(url, resolve_redirects=True)
    if not url_info:
        error_msg = f"❌ Ошибка нормализации URL: {url}"
        if chat_id:
            await bot.send_message(chat_id, error_msg)
        logger.error(
            "process_and_publish: normalize_market_url returned None for %s (correlation_id=%s)",
            url,
            correlation_id,
        )
        return False, None
    is_cc_url = url_info.is_cc_url

    # Инициализация переменных результата ДО retry-цикла (защита от UnboundLocalError)
    data: Optional[Dict[str, Any]] = None
    last_scrape_error: Optional[Exception] = None

    # Получаем данные товара (использует унифицированную retry-обёртку)
    try:
        data = await get_product_data(
            url,
            url_info=url_info,
            retry_count=retry_count,
            correlation_id=correlation_id,
            use_cache=True,
        )
    except Exception as e:
        last_scrape_error = e
        logger.warning(
            "process_and_publish: get_product_data exception for %s (correlation_id=%s): %s",
            url,
            correlation_id,
            str(e)[:200],
        )
    # Check if we have sufficient data for publishing (title OR price OR images)
    if not has_sufficient_product_data(data):
        # No useful data at all - try fallback approaches
        logger.warning(
            "process_and_publish: insufficient product data, trying fallbacks for %s (correlation_id=%s)",
            url,
            correlation_id,
        )

        # For cc URLs, try to create a link-only post
        if is_cc_url:
            logger.info(
                "process_and_publish: cc/ URL scrape failed, will create link-only post (correlation_id=%s)",
                correlation_id,
            )
            from services.post_service import create_link_only_post

            try:
                data = await create_link_only_post(url, chat_id, correlation_id)
                if not has_sufficient_product_data(data):
                    logger.warning(
                        "process_and_publish: link-only post also insufficient for %s (correlation_id=%s)",
                        url,
                        correlation_id,
                    )
                    error_msg = f"❌ Недостаточно данных для публикации: {url}"
                    if chat_id:
                        try:
                            await bot.send_message(chat_id, error_msg)
                        except Exception:
                            pass
                    return False, None
            except Exception as e:
                logger.error(
                    "process_and_publish: create_link_only_post failed for %s (correlation_id=%s): %s",
                    url,
                    correlation_id,
                    str(e)[:200],
                )
                error_msg = f"❌ Ошибка создания поста: {str(e)[:100]}"
                if chat_id:
                    try:
                        await bot.send_message(chat_id, error_msg)
                    except Exception:
                        pass
                return False, None
        else:
            # For card URLs, log warning but continue if we have ANY useful data
            # This allows fallback parsers to provide partial data
            logger.warning(
                "process_and_publish: scrape failed but continuing with partial data for %s (correlation_id=%s, error=%s)",
                url,
                correlation_id,
                str(last_scrape_error)[:200] if last_scrape_error else "unknown",
            )
            # Don't return False here - continue with whatever data we have
            # The validation later will catch truly unusable data
    else:
        # We have sufficient data - log success
        logger.info(
            "process_and_publish: sufficient product data obtained for %s (correlation_id=%s)",
            url,
            correlation_id,
        )

    # 3) Обеспечение партнёрской ссылки
    # УПРОЩЕННАЯ ЛОГИКА: Используем исходную ссылку с UTM параметрами
    try:
        data["product_url"] = (
            getattr(url_info, "card_url", None)
            or getattr(url_info, "original_url", None)
            or url
        )
    except AttributeError:
        # Fallback если url_info не имеет нужных атрибутов
        data["product_url"] = url
    data["ref_link"] = None
    data["has_ref"] = False

    # Check for price drop info and add to data
    if url in _price_drop_info:
        data["price_drop_info"] = _price_drop_info[url]
        logger.info(
            f"📉 Price drop detected for {url[:80]}...: {_price_drop_info[url]}"
        )
        # Remove from storage after use (one-time use)
        del _price_drop_info[url]

    # Flash Sale Detection: Check if discount > 40%
    discount = extract_discount_from_data(data)
    is_flash_sale = False
    if discount > 40:
        is_flash_sale = True
        data["flash_sale_info"] = {"discount_percent": discount}
        logger.info(f"🚨 FLASH SALE detected for {url[:80]}...: {discount}% discount!")

    # Валидация данных товара - сначала проверяем минимальные требования
    if not has_sufficient_product_data(data):
        error_msg = f"❌ Нет достаточных данных для публикации (нужен title или price или изображение)\nURL: {url[:100]}"
        if chat_id:
            await bot.send_message(chat_id, error_msg)
        logger.warning(
            "process_and_publish: insufficient data for publishing %s (correlation_id=%s)",
            url,
            correlation_id,
        )
        # Помечаем в очередь ошибок
        try:
            db.add_to_error_queue(url, "insufficient_product_data")
        except (sqlite3.Error, AttributeError, TypeError) as e:
            logger.debug(f"Failed to add to error queue: {e}")
        return False, None

    # Дополнительная валидация для качества данных (warnings only, not blocking)
    data_valid, data_reason = validate_product_data(data, url)
    if not data_valid:
        logger.warning(
            "process_and_publish: product validation warnings %s: %s (correlation_id=%s) - continuing anyway",
            url,
            data_reason,
            correlation_id,
        )
        # Log warning but don't block publishing - we have sufficient data
        if chat_id:
            try:
                await bot.send_message(chat_id, f"⚠️ Предупреждение валидации: {data_reason}")
            except Exception:
                pass

    # De-duplication check: Check if similar product was posted recently
    product_title = data.get("title", "").strip()
    if product_title:
        try:
            # Generate normalized product key for de-duplication
            product_key = generate_product_key(product_title)
            logger.debug(f"Generated product key for de-duplication: '{product_key}' from '{product_title}'")

            # Check if similar product was posted recently (configurable days)
            dedup_days = getattr(settings, 'DEDUP_DAYS_CHECK', 7)  # Default 7 days
            from database import has_been_posted_recently

            is_duplicate = await has_been_posted_recently(product_key, dedup_days)
            if is_duplicate:
                logger.info(
                    "process_and_publish: skipping duplicate product '%s' (key: '%s', days: %d, correlation_id=%s)",
                    product_title[:50],
                    product_key[:50],
                    dedup_days,
                    correlation_id,
                )
                # Send notification about duplicate
                if chat_id:
                    try:
                        await bot.send_message(
                            chat_id,
                            f"⚠️ Пропускаем дубликат товара: {product_title[:50]}...\n"
                            f"(похожий товар публиковался в последние {dedup_days} дней)"
                        )
                    except Exception as e:
                        logger.debug(f"Failed to send duplicate notification: {e}")
                return False, None

        except Exception as e:
            logger.warning(
                "process_and_publish: de-duplication check failed for '%s' (correlation_id=%s): %s",
                product_title[:50],
                correlation_id,
                str(e)[:200],
            )
            # Don't block posting if de-duplication check fails - continue with posting
    else:
        logger.debug("process_and_publish: no title available for de-duplication check")

    # 3) Process image if present with quality check
    photo_path = None
    img_hash = None
    if data.get("image_bytes"):
        try:
            # Проверка качества изображения
            is_good, quality_reason = check_image_quality(data["image_bytes"])
            if not is_good:
                logger.info(
                    "process_and_publish: плохое качество изображения: %s",
                    quality_reason,
                )
                if chat_id:
                    await bot.send_message(
                        chat_id, f"⚠️ Пропущено из-за качества: {quality_reason}"
                    )
                photo_path = None
                img_hash = None
            else:
                # Удаляем EXIF и улучшаем
                cleaned_image = remove_exif(data["image_bytes"])
                improved_image = improve_image(cleaned_image)
                photo_path, img_hash = process_image(
                    improved_image, settings.IMAGE_MAX_MB
                )
        except Exception as e:
            logger.exception("process_and_publish: image processing failed: %s", e)
            if chat_id:
                await bot.send_message(
                    chat_id, f"⚠️ Ошибка обработки изображения, продолжу без фото: {e}"
                )
            photo_path = None
            img_hash = None

    # 4) If image present, check duplicate image
    if img_hash and db.exists_image(img_hash):
        if chat_id:
            await bot.send_message(
                chat_id, f"⚠️ Дубликат изображения обнаружен для: {url}"
            )
        logger.info(
            "process_and_publish: duplicate image for %s (correlation_id=%s)",
            url,
            correlation_id,
        )
        # cleanup photo if created
        if photo_path and os.path.exists(photo_path):
            os.remove(photo_path)
        return False, None

    # 4.5) Check filters
    skip, reason = should_skip_product(data)
    if skip:
        if chat_id:
            await bot.send_message(chat_id, f"⏭️ Товар пропущен: {reason}")
        logger.info(
            "process_and_publish: filtered out %s: %s (correlation_id=%s)",
            url,
            reason,
            correlation_id,
        )
        if photo_path and os.path.exists(photo_path):
            os.remove(photo_path)
        return False, None

    # 4) Формирование финального URL для поста
    flags = data.get("flags", [])

    # Определяем источник данных для логирования
    data_source = "parser_only"
    if "ai_ok" in flags:
        data_source = "ai_ok"
    elif "ai_fallback" in flags:
        data_source = "ai_fallback"

    logger.info(
        f"Data source: {data_source}, flags: {', '.join(flags) if flags else 'none'}"
    )

    # УПРОЩЕННАЯ ЛОГИКА: Используем исходную ссылку с UTM параметрами
    try:
        product_url = (
            data.get("product_url")
            or getattr(url_info, "card_url", None)
            or getattr(url_info, "original_url", None)
            or url
        )
    except AttributeError:
        # Fallback если url_info не имеет нужных атрибутов
        product_url = data.get("product_url") or url
    # Use new affiliate service for Yandex ad-marking
    from services.affiliate_service import make_affiliate_link
    final_url = make_affiliate_link(product_url)
    logger.info(f"✅ Using URL with UTM parameters: {final_url[:100]}...")
    # 5) Отправка поста в канал
    from services.post_service import send_post_to_channel

    send_success, message_id = await send_post_to_channel(
        bot,
        data,
        photo_path=photo_path,
        retry_count=retry_count,
        chat_id=chat_id,
        correlation_id=correlation_id,
        disable_notification=disable_notification,
    )

    if not send_success:
        # Cleanup: удаляем временный файл изображения
        if photo_path and os.path.exists(photo_path):
            try:
                os.remove(photo_path)
            except Exception:
                pass
        return False, None

    # 5.5) Pin message if flash sale (with 24h cooldown)
    if is_flash_sale and message_id and settings.CHANNEL_ID:
        try:
            from datetime import datetime, timedelta

            # Check last pin time
            last_pin_time_str = db.get_setting("last_flash_sale_pin_time", "")
            can_pin = True

            if last_pin_time_str:
                try:
                    last_pin_time = datetime.fromisoformat(last_pin_time_str)
                    hours_since_last_pin = (
                        datetime.now() - last_pin_time
                    ).total_seconds() / 3600
                    if hours_since_last_pin < 24:
                        can_pin = False
                        logger.info(
                            f"⏭ Skipping pin (last pin was {hours_since_last_pin:.1f}h ago, need 24h cooldown)"
                        )
                except (ValueError, TypeError) as e:
                    logger.warning(f"⚠️ Error parsing last pin time: {e}, allowing pin")

            if can_pin:
                try:
                    await bot.pin_chat_message(
                        chat_id=settings.CHANNEL_ID,
                        message_id=message_id,
                        disable_notification=False,  # Notify about pinning
                    )
                    # Update last pin time
                    db.set_setting(
                        "last_flash_sale_pin_time", datetime.now().isoformat()
                    )
                    logger.info(
                        f"📌 Pinned flash sale message (message_id: {message_id}, discount: {discount}%)"
                    )
                except Exception as pin_error:
                    logger.warning(f"⚠️ Failed to pin message: {pin_error}")
        except Exception as e:
            logger.warning(f"⚠️ Error in pinning logic: {e}")

    # 6) Save to DB (store url, image hash, message_id, channel_id and template_type)
    title = data.get("title", "")
    channel_id = str(settings.CHANNEL_ID) if settings.CHANNEL_ID else None

    # Для A/B тестирования - получаем тип шаблона из данных
    template_type = data.get("template_type", None)

    db.add_post_to_history(
        url=url,
        img_hash=img_hash or "",
        title=title,
        message_id=message_id,
        channel_id=channel_id,
        template_type=template_type,
    )

    # Update publishing state if we have queue_id (from queue processing)
    if queue_id and message_id:
        from models.publishing_state import PublishingState
        from services.formatting_service import get_formatting_service

        # Generate caption for database storage
        formatting_service = get_formatting_service()
        caption = await formatting_service.format_product_post(data)
        db.update_publishing_state(
            queue_id,
            PublishingState.POSTED.value,
            message_id=message_id,
            chat_id=settings.CHANNEL_ID,
            text=caption,
        )

    if chat_id:
        await bot.send_message(chat_id, f"✅ Опубликовано: {data.get('title')}")
    logger.info(
        "process_and_publish: published %s (correlation_id=%s, message_id=%s)",
        url,
        correlation_id,
        message_id,
    )

    # Record product in de-duplication database (only on successful posting)
    if product_title:
        try:
            from database import add_posted_product
            success = await add_posted_product(product_key)
            if success:
                logger.debug(f"Recorded posted product for de-duplication: '{product_key}'")
            else:
                logger.warning(f"Failed to record posted product: '{product_key}'")
        except Exception as e:
            logger.warning(f"Error recording posted product '{product_key}': {e}")
            # Don't fail the posting if recording fails

    # Cleanup: удаляем временный файл изображения
    if photo_path and os.path.exists(photo_path):
        try:
            os.remove(photo_path)
        except Exception:
            pass

    return True, message_id


# --- Price Drop Monitor worker ---
async def price_monitor_worker():
    """Фоновый воркер для мониторинга падения цен (каждые 6 часов)"""
    logger.info("📉 Price Drop Monitor worker started")

    from services.price_monitor import PriceMonitorService

    monitor = PriceMonitorService(db)

    while True:
        try:
            # Ждем 6 часов (21600 секунд)
            await asyncio.sleep(6 * 60 * 60)

            logger.info("🔍 Запуск проверки падения цен...")

            # Проверяем падение цен
            price_drops = await monitor.check_price_drops(limit=50)

            if price_drops:
                # Обрабатываем найденные падения цен
                added_count = await monitor.process_price_drops(price_drops)
                logger.info(
                    f"📉 Обработано падений цен: {len(price_drops)}, добавлено в очередь: {added_count}"
                )
            else:
                logger.info("📉 Падений цен не обнаружено")

        except Exception as e:
            logger.exception(f"❌ Ошибка в Price Drop Monitor worker: {e}")
            # При ошибке ждем 1 час перед следующей попыткой
            await asyncio.sleep(60 * 60)


# --- Digest generation ---
async def generate_digest_message(
    items: List[Tuple[int, str]], correlation_id: str
) -> Optional[str]:
    """
    Генерирует сообщение дайджеста из нескольких товаров

    Args:
        items: Список кортежей (task_id, url)
        correlation_id: ID для корреляции логов

    Returns:
        Сформированное сообщение дайджеста или None при ошибке
    """
    from utils.url_normalizer import normalize_market_url
    from services.scrape_service import get_product_data
    from utils.text_gen import get_emoji_by_category

    digest_items = []

    for task_id, url in items:
        try:
            # Нормализуем URL
            url_info = await normalize_market_url(url, resolve_redirects=True)
            if not url_info:
                logger.warning(
                    f"Digest: failed to normalize URL {url[:50]} (correlation_id={correlation_id})"
                )
                continue

            # Получаем данные товара
            data = await get_product_data(
                url,
                url_info=url_info,
                retry_count=1,  # Одна попытка для дайджеста
                correlation_id=correlation_id,
                use_cache=True,
            )

            if not data or not data.get("title"):
                logger.warning(
                    f"Digest: failed to get data for {url[:50]} (correlation_id={correlation_id})"
                )
                continue

            # Формируем финальный URL с партнерскими параметрами
            try:
                product_url = (
                    data.get("product_url")
                    or getattr(url_info, "card_url", None)
                    or getattr(url_info, "original_url", None)
                    or url
                )
            except AttributeError:
                product_url = data.get("product_url") or url

            # Use new affiliate service for Yandex ad-marking
            from services.affiliate_service import make_affiliate_link
            final_url = make_affiliate_link(product_url)

            # Получаем данные для дайджеста
            title = data.get("title", "").strip()
            price = data.get("price", "Цена уточняется")
            emoji = get_emoji_by_category(title)

            digest_items.append(
                {
                    "task_id": task_id,
                    "emoji": emoji,
                    "title": title,
                    "price": price,
                    "url": final_url,
                }
            )

        except Exception as e:
            logger.warning(
                f"Digest: error processing item {url[:50]}: {e} (correlation_id={correlation_id})"
            )
            continue

    if not digest_items:
        logger.warning(
            f"Digest: no valid items to include (correlation_id={correlation_id})"
        )
        return None

    # Формируем сообщение дайджеста
    message_parts = ["🔥 <b>Подборка лучших находок:</b>\n"]

    for idx, item in enumerate(digest_items, 1):
        message_parts.append(
            f"\n{idx}. {item['emoji']} <b>{item['title']}</b> — {item['price']}\n"
            f"👉 <a href=\"{item['url']}\">Смотреть на Маркете</a>"
        )

    return "\n".join(message_parts)


async def send_digest(
    items: List[Tuple[int, str]], correlation_id: str
) -> Tuple[bool, Optional[int]]:
    """
    Отправляет дайджест в канал

    Args:
        items: Список кортежей (task_id, url)
        correlation_id: ID для корреляции логов

    Returns:
        Tuple (success: bool, message_id: Optional[int])
    """
    try:
        # Генерируем сообщение дайджеста
        digest_message = await generate_digest_message(items, correlation_id)
        if not digest_message:
            logger.warning(
                f"Digest: failed to generate message (correlation_id={correlation_id})"
            )
            return False, None

        # Отправляем в канал
        from aiogram.enums import ParseMode

        sent_message = await bot.send_message(
            chat_id=settings.CHANNEL_ID,
            text=digest_message,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False,
        )

        message_id = sent_message.message_id
        logger.info(
            f"Digest: sent successfully with {len(items)} items (message_id={message_id}, correlation_id={correlation_id})"
        )

        # Помечаем все товары как опубликованные
        from models.publishing_state import PublishingState

        for task_id, url in items:
            try:
                db.update_publishing_state(
                    task_id,
                    PublishingState.POSTED.value,
                    message_id=message_id,
                    chat_id=settings.CHANNEL_ID,
                    text=digest_message,
                )
                db.mark_as_done(task_id)
                # Сохраняем в историю
                db.add_post_to_history(
                    url=url,
                    img_hash="",  # Дайджест без изображения
                    title=f"Digest item: {url[:50]}",
                    message_id=message_id,
                    channel_id=(
                        str(settings.CHANNEL_ID) if settings.CHANNEL_ID else None
                    ),
                )
            except Exception as e:
                logger.warning(f"Digest: error marking item {task_id} as done: {e}")

        return True, message_id

    except Exception as e:
        logger.exception(
            f"Digest: error sending digest (correlation_id={correlation_id}): {e}"
        )
        return False, None


# --- Queue worker ---
async def queue_worker(db=None, http_client=None) -> None:
    """Воркер автопубликации с поддержкой расписания"""
    from datetime import datetime
    from utils.correlation_id import set_correlation_id

    # Use passed db instance or create a new one as fallback
    if db is None:
        from database import Database

        db = Database()

    global_settings = get_global_settings()
    logger.info("🚀 Queue worker started")
    logger.info(f"Using db: {db is not None}, http_client: {http_client is not None}")
    cache_cleanup_counter = 0
    publish_counter = 0
    last_publish_time = None
    posts_since_last_digest = 0  # Счетчик постов с последнего дайджеста

    while True:
        try:
            # Проверяем, включена ли автопубликация
            if not global_settings.get_auto_publish_enabled():
                await asyncio.sleep(60)  # Проверяем каждую минуту
                continue

            # Проверка расписания
            schedule_settings = global_settings.get_schedule_settings()
            if schedule_settings.get("enabled"):
                now = datetime.now()
                current_hour = now.hour

                # Проверяем, можно ли публиковать по расписанию
                schedule_hours = schedule_settings.get("hours", [])
                if schedule_hours and current_hour not in schedule_hours:
                    # Не время для публикации
                    await asyncio.sleep(60)
                    continue

                # Проверка "один в день"
                if schedule_settings.get("one_per_day") and last_publish_time:
                    if now.date() == last_publish_time.date():
                        # Уже опубликовано сегодня
                        await asyncio.sleep(60)
                        continue

            # Периодическая очистка старого кэша (каждые 100 итераций)
            cache_cleanup_counter += 1
            if cache_cleanup_counter >= 100:
                db.clear_old_cache(max_age_hours=48)
                cache_cleanup_counter = 0
                logger.debug("Queue worker: cleared old cache")

            # Проверяем, пора ли отправлять дайджест
            should_send_digest = posts_since_last_digest >= settings.DIGEST_FREQUENCY

            if should_send_digest:
                # Проверяем, достаточно ли товаров в очереди для дайджеста
                queue_items = db.get_queue_urls(limit=settings.DIGEST_MAX_ITEMS)

                if len(queue_items) >= settings.DIGEST_MIN_ITEMS:
                    # Время для дайджеста! Берем несколько товаров
                    digest_items = queue_items[: settings.DIGEST_MAX_ITEMS]
                    correlation_id = set_correlation_id()

                    logger.info(
                        f"Digest time! Processing {len(digest_items)} items for digest "
                        f"(posts_since_last_digest={posts_since_last_digest}, correlation_id={correlation_id})"
                    )

                    # Обновляем статусы всех товаров на processing
                    from models.publishing_state import PublishingState

                    for task_id, url in digest_items:
                        db.update_publishing_state(
                            task_id, PublishingState.PROCESSING.value
                        )

                    try:
                        # Отправляем дайджест
                        success, message_id = await send_digest(
                            digest_items, correlation_id
                        )

                        if success:
                            last_publish_time = datetime.now()
                            posts_since_last_digest = 0  # Сбрасываем счетчик
                            publish_counter += len(digest_items)
                            logger.info(
                                f"Digest sent successfully with {len(digest_items)} items "
                                f"(message_id={message_id}, correlation_id={correlation_id})"
                            )
                        else:
                            # Если дайджест не отправился, помечаем товары как failed
                            logger.warning(
                                f"Digest failed (correlation_id={correlation_id})"
                            )
                            for task_id, url in digest_items:
                                db.update_publishing_state(
                                    task_id,
                                    PublishingState.FAILED.value,
                                    error="Digest generation failed",
                                )
                                db.mark_as_error(task_id)

                            # Продолжаем с обычными постами
                            should_send_digest = False

                    except Exception as digest_error:
                        logger.exception(
                            f"Digest error (correlation_id={correlation_id}): {digest_error}"
                        )
                        # Помечаем товары как failed
                        for task_id, url in digest_items:
                            try:
                                db.update_publishing_state(
                                    task_id,
                                    PublishingState.FAILED.value,
                                    error=str(digest_error)[:200],
                                )
                                db.mark_as_error(task_id)
                            except Exception:
                                pass

                        # Продолжаем с обычными постами
                        should_send_digest = False

                    # Используем интервал из настроек расписания
                    schedule_settings = global_settings.get_schedule_settings()
                    interval = schedule_settings.get("interval", settings.POST_INTERVAL)
                    await asyncio.sleep(interval)
                    continue
                else:
                    # Недостаточно товаров для дайджеста, продолжаем обычные посты
                    logger.debug(
                        f"Not enough items for digest ({len(queue_items)} < {settings.DIGEST_MIN_ITEMS}), "
                        f"continuing with single posts"
                    )
                    should_send_digest = False

            # Обычный режим: публикуем один товар
            if not should_send_digest:
                task = db.get_next_from_queue()
                if task:
                    task_id, url = task
                    publish_counter += 1
                    # Устанавливаем correlation_id для этой задачи
                    correlation_id = set_correlation_id()
                    logger.info(
                        "Queue worker: processing %s (публикация #%d, correlation_id=%s)",
                        url,
                        publish_counter,
                        correlation_id,
                    )
                    logger.info(
                        "Queue worker: взял товар из очереди, URL: %s", url[:100]
                    )
                    # Update publishing state: queued → processing
                    from models.publishing_state import PublishingState

                    db.update_publishing_state(
                        task_id, PublishingState.PROCESSING.value
                    )

                    logger.info("Queue worker: подготовка поста...")
                    try:
                        # Update publishing state: processing → ready (before publishing)
                        db.update_publishing_state(task_id, PublishingState.READY.value)

                        success, message_id = await process_and_publish(
                            url, settings.ADMIN_ID, queue_id=task_id
                        )
                        if success:
                            # Update publishing state: ready → posted (with message_id)
                            if message_id:
                                db.update_publishing_state(
                                    task_id,
                                    PublishingState.POSTED.value,
                                    message_id=message_id,
                                    chat_id=settings.CHANNEL_ID,
                                )
                            db.mark_as_done(task_id)
                            last_publish_time = datetime.now()
                            posts_since_last_digest += 1  # Увеличиваем счетчик постов
                            logger.info(
                                "Queue worker: публикация успешна, URL: %s, message_id: %s, "
                                "posts_since_last_digest: %d",
                                url[:100],
                                message_id,
                                posts_since_last_digest,
                            )
                        else:
                            # Update publishing state: ready → failed
                            db.update_publishing_state(
                                task_id,
                                PublishingState.FAILED.value,
                                error="Publication failed",
                            )
                            db.mark_as_error(task_id)
                            logger.warning(
                                "Queue worker: ошибка публикации, URL: %s (correlation_id=%s)",
                                url[:100],
                                correlation_id,
                            )
                    except Exception as publish_error:
                        error_msg = str(publish_error)[:200]
                        # Update publishing state: ready → failed
                        db.update_publishing_state(
                            task_id, PublishingState.FAILED.value, error=error_msg
                        )
                        db.mark_as_error(task_id)
                        logger.exception(
                            "Queue worker: исключение при публикации, URL: %s, error: %s (correlation_id=%s)",
                            url[:100],
                            publish_error,
                            correlation_id,
                        )

                    # Используем интервал из настроек расписания
                    schedule_settings = global_settings.get_schedule_settings()
                    interval = schedule_settings.get("interval", settings.POST_INTERVAL)
                    await asyncio.sleep(interval)
                else:
                    # Если очередь пуста, проверяем каждые 60 секунд
                    if publish_counter == 0:
                        logger.debug(
                            "Очередь пуста, жду товары... (проверка каждые 60 сек)"
                        )
                    await asyncio.sleep(60)
        except Exception as e:
            logger.exception("queue_worker error: %s", e)
            await asyncio.sleep(60)


# --- Handlers ---
def create_main_keyboard() -> InlineKeyboardMarkup:
    """Создает главную клавиатуру с кнопками команд"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔐 Админка", callback_data="cmd_admin_panel")],
            [
                InlineKeyboardButton(text="📊 Статус", callback_data="cmd_status"),
                InlineKeyboardButton(text="🔄 Перезапуск", callback_data="cmd_restart"),
            ],
            [
                InlineKeyboardButton(
                    text="🧪 Тест пост", callback_data="cmd_test_post"
                ),
                InlineKeyboardButton(
                    text="⚡ Срочный пост", callback_data="cmd_force_post"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📝 Последний пост", callback_data="cmd_last_post"
                ),
                InlineKeyboardButton(text="ℹ️ Инфо", callback_data="cmd_info"),
            ],
            [InlineKeyboardButton(text="🔍 Проверка", callback_data="cmd_check_auto")],
            [InlineKeyboardButton(text="📋 Логи", callback_data="cmd_log")],
        ]
    )
    return keyboard


def add_back_button(keyboard: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
    """Добавляет кнопку 'Главное меню' к существующей клавиатуре"""
    if keyboard.inline_keyboard:
        keyboard.inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню", callback_data="cmd_main_menu"
                )
            ]
        )
    return keyboard


def create_back_button() -> InlineKeyboardMarkup:
    """Создает клавиатуру только с кнопкой 'Главное меню'"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню", callback_data="cmd_main_menu"
                )
            ]
        ]
    )


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    is_admin = message.from_user.id == settings.ADMIN_ID

    text = "👋 Привет! Я бот-постер для Яндекс.Маркета.\n\n"
    text += "<b>Основные команды:</b>\n"
    text += "/info — статус очереди\n"

    if is_admin:
        text += "\n<b>Админ панель:</b>\n"
        text += "Используйте кнопки ниже или команды:\n"
        text += "/post, /q, /stats, /clear, /remove\n"
        text += "/help — подробная справка"

        keyboard = create_main_keyboard()
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    else:
        await message.answer(
            text + "\n\nТакже можно прислать .txt с ссылками (одна ссылка на строку).",
            parse_mode=ParseMode.HTML,
        )


# Обработчики кнопок
@dp.callback_query(F.data.startswith("cmd_"))
async def handle_command_button(callback: types.CallbackQuery):
    """Обработчик кнопок команд"""
    if callback.from_user.id != settings.ADMIN_ID:
        await callback.answer("❌ Нет прав.", show_alert=True)
        return

    command = callback.data.replace("cmd_", "")

    if command == "main_menu":
        await cmd_main_menu_button(callback)
    elif command == "admin_panel":
        await cmd_admin_panel_button(callback)
    elif command == "status":
        await cmd_status_button(callback)
    elif command == "restart":
        await cmd_restart_button(callback)
    elif command == "test_post":
        await callback.answer("📝 Используйте: /test_post <url>", show_alert=True)
    elif command == "force_post":
        await cmd_force_post_button(callback)
    elif command == "last_post":
        await cmd_last_post_button(callback)
    elif command == "info":
        await cmd_info_button(callback)
    elif command == "log":
        await cmd_log_button(callback)
    elif command.startswith("log_"):
        await handle_log_action(callback, command)
    elif command == "auto_search":
        await callback.answer(
            "🔍 Используйте: /auto_search <запрос> [количество]", show_alert=True
        )
    elif command == "check_auto":
        await cmd_check_auto_button(callback)
    # Обработка админских разделов
    elif command.startswith("admin_"):
        await handle_admin_section(callback, command)
    elif command.startswith("queue_"):
        await handle_queue_action(callback, command)
    elif command.startswith("analytics_"):
        await handle_analytics_action(callback, command)
    elif command.startswith("content_"):
        await handle_content_action(callback, command)
    elif command.startswith("system_"):
        await handle_system_action(callback, command)
    elif command.startswith("schedule_"):
        await handle_schedule_action(callback, command)
    elif command.startswith("management_"):
        await handle_management_action(callback, command)
    elif command.startswith("add_search_"):
        # Добавление товара из результатов поиска в очередь
        try:
            idx_str = command.replace("add_search_", "")
            idx = int(idx_str) - 1  # Индекс с 0

            user_id = callback.from_user.id
            state = user_states.get(user_id, {})
            search_results = state.get("search_results", [])

            if not search_results or idx < 0 or idx >= len(search_results):
                await callback.answer(
                    "⚠️ Товар не найден в результатах поиска", show_alert=True
                )
                return

            product = search_results[idx]
            url = product.get("url", "")

            if not url:
                await callback.answer("❌ Неверный URL товара", show_alert=True)
                return

            # Проверяем валидность URL
            is_valid, reason = validate_product_url(url)
            if not is_valid:
                await callback.answer(f"❌ Неверный URL: {reason}", show_alert=True)
                return

            # Проверяем, нет ли уже в очереди (Problem #1: add normalization)
            if db.exists_url(url, check_normalized=True):
                await callback.answer("⚠️ Товар уже в истории", show_alert=True)
                return

            # Добавляем в очередь
            if db.add_to_queue(url):
                await callback.answer(
                    f"✅ Товар #{idx + 1} добавлен в очередь", show_alert=True
                )
                logger.info(
                    f"Admin {user_id} added product from search to queue: {url[:100]}"
                )
            else:
                await callback.answer("⚠️ Товар уже в очереди", show_alert=True)
        except (ValueError, IndexError) as e:
            await callback.answer("❌ Неверный индекс товара", show_alert=True)
        except Exception as e:
            logger.exception("add_search error: %s", e)
            await callback.answer(f"❌ Ошибка: {str(e)[:100]}", show_alert=True)

    elif command.startswith("post_now_"):
        # Срочная публикация товара по task_id
        task_id_str = command.replace("post_now_", "")
        try:
            task_id = int(task_id_str)
            queue_items = db.get_queue_urls(limit=1000)
            url_to_publish = None
            for tid, url in queue_items:
                if tid == task_id:
                    url_to_publish = url
                    break

            if not url_to_publish:
                await callback.answer("⚠️ Товар не найден в очереди", show_alert=True)
                return

            await callback.answer("⚡ Публикую срочно...", show_alert=False)
            success = await process_and_publish(url_to_publish, callback.from_user.id)
            if success:
                db.mark_as_done(task_id)
                from utils.safe_edit import safe_edit_callback_message

                await safe_edit_callback_message(
                    callback,
                    f"✅ <b>Товар опубликован!</b>\n\n" f"🔗 {url_to_publish[:60]}...",
                    parse_mode=ParseMode.HTML,
                )
                await callback.answer("✅ Опубликовано!", show_alert=True)
            else:
                from utils.safe_edit import safe_edit_callback_message

                await safe_edit_callback_message(
                    callback,
                    f"❌ <b>Ошибка публикации</b>\n\n" f"🔗 {url_to_publish[:60]}...",
                    parse_mode=ParseMode.HTML,
                )
                await callback.answer("❌ Ошибка", show_alert=True)
        except ValueError:
            await callback.answer("❌ Неверный ID товара", show_alert=True)
        except Exception as e:
            logger.exception("post_now error: %s", e)
            await callback.answer(f"❌ Ошибка: {str(e)[:100]}", show_alert=True)

    # В aiogram 3.x нет атрибута called, просто вызываем answer если нужно
    # (большинство обработчиков уже вызывают answer самостоятельно)


async def handle_log_action(callback: types.CallbackQuery, command: str):
    """Обработка действий с логами"""
    from utils.safe_edit import safe_edit_text

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Все логи", callback_data="cmd_log_all")],
            [
                InlineKeyboardButton(
                    text="❌ Только ошибки", callback_data="cmd_log_errors"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚠️ Ошибки и предупреждения", callback_data="cmd_log_warnings"
                )
            ],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="cmd_log_refresh")],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню", callback_data="cmd_main_menu"
                )
            ],
        ]
    )

    try:
        if getattr(sys, "frozen", False):
            log_file = os.path.join(
                os.getenv("APPDATA"), "YandexMarketBot", "logs", "bot.log"
            )
        else:
            log_file = "logs/bot.log"

        if not os.path.exists(log_file):
            await safe_edit_text(
                callback.message, "📭 Файл логов не найден", reply_markup=keyboard
            )
            await callback.answer()
            return

        # Используем log_service для получения важных логов
        from services.log_service import LogService

        log_service = LogService(log_file)

        if command == "log_all":
            # Все логи
            logs = log_service.get_recent_logs(limit=100, min_level="DEBUG")
            text = f"📋 <b>Все логи (последние {len(logs)}):</b>\n\n"
        elif command == "log_errors":
            # Только ошибки
            logs = log_service.get_important_logs(limit=50)
            logs = [
                log
                for log in logs
                if isinstance(log, dict)
                and (
                    "ERROR" in log.get("level", "")
                    or "EXCEPTION" in log.get("message", "").upper()
                )
            ]
            text = f"❌ <b>Только ошибки ({len(logs)}):</b>\n\n"
        elif command == "log_warnings":
            # Ошибки и предупреждения
            logs = log_service.get_important_logs(limit=50)
            logs = [
                log
                for log in logs
                if isinstance(log, dict)
                and (
                    "ERROR" in log.get("level", "")
                    or "WARNING" in log.get("level", "")
                    or "EXCEPTION" in log.get("message", "").upper()
                )
            ]
            text = f"⚠️ <b>Ошибки и предупреждения ({len(logs)}):</b>\n\n"
        elif command == "log_refresh":
            # Обновить - показываем важные логи
            logs = log_service.get_important_logs(limit=30)
            text = f"📋 <b>Важные логи (последние {len(logs)}):</b>\n\n"
        else:
            logs = log_service.get_important_logs(limit=30)
            text = f"📋 <b>Важные логи (последние {len(logs)}):</b>\n\n"

        if logs:
            # Логи возвращаются как словари, нужно их отформатировать
            if logs and isinstance(logs[0], dict):
                # Используем format_logs_for_message для форматирования
                log_text = log_service.format_logs_for_message(logs, max_length=4000)
                text = log_text  # format_logs_for_message уже включает заголовок
            else:
                # Если это строки (старый формат)
                log_text = "\n".join(str(log) for log in logs)
        if len(log_text) > 4000:
            log_text = log_text[-4000:]
            text += f"<code>{log_text}</code>"
        else:
            text += "Нет записей"

        await safe_edit_text(
            callback.message, text, reply_markup=keyboard, parse_mode=ParseMode.HTML
        )
        await callback.answer()
    except Exception as e:
        logger.exception("log action error: %s", e)
        await safe_edit_text(
            callback.message, f"❌ Ошибка: {str(e)[:200]}", reply_markup=keyboard
        )
        await callback.answer()


# Обработчики для кнопок
async def cmd_main_menu_button(callback: types.CallbackQuery):
    """Обработчик кнопки 'Главное меню'"""
    is_admin = callback.from_user.id == settings.ADMIN_ID

    text = "👋 Привет! Я бот-постер для Яндекс.Маркета.\n\n"
    text += "<b>Основные команды:</b>\n"
    text += "/info — статус очереди\n"

    if is_admin:
        text += "\n<b>Админ панель:</b>\n"
        text += "Используйте кнопки ниже или команды:\n"
        text += "/post, /q, /stats, /clear, /remove\n"
        text += "/help — подробная справка"

        keyboard = create_main_keyboard()
        try:
            await callback.message.edit_text(
                text, parse_mode=ParseMode.HTML, reply_markup=keyboard
            )
        except (Exception, asyncio.TimeoutError) as e:
            logger.debug(f"Failed to edit message, sending new: {e}")
            await callback.message.answer(
                text, parse_mode=ParseMode.HTML, reply_markup=keyboard
            )
    else:
        text += "\n\nТакже можно прислать .txt с ссылками (одна ссылка на строку)."
        try:
            await callback.message.edit_text(text, parse_mode=ParseMode.HTML)
        except (Exception, asyncio.TimeoutError) as e:
            logger.debug(f"Failed to edit message, sending new: {e}")
            await callback.message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("circuit_breaker", "cb_status"))
async def cmd_circuit_breaker_status(message: types.Message):
    """Show circuit breaker status (admin only)."""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Доступ запрещён")
        return

    try:
        from services.circuit_breaker import get_circuit_breaker

        circuit_breaker = get_circuit_breaker()
        status = circuit_breaker.get_status()

        state_emoji = {"CLOSED": "✅", "OPEN": "🚨", "HALF_OPEN": "🔍"}

        emoji = state_emoji.get(status["state"], "❓")

        status_text = (
            f"{emoji} **Circuit Breaker Status**\n\n"
            f"**State:** {status['state']}\n"
            f"**Failures:** {status['consecutive_failures']}/{status['failure_threshold']}\n"
            f"**Available:** {'✅ Yes' if status['is_available'] else '❌ No'}\n"
        )

        if status["state"] == "OPEN":
            minutes = status["time_until_retry"] // 60
            seconds = status["time_until_retry"] % 60
            status_text += f"**Retry in:** {minutes}m {seconds}s\n"

        await message.answer(status_text, parse_mode="Markdown")

    except Exception as e:
        logger.exception(f"Error getting circuit breaker status: {e}")
        await message.answer(f"❌ Ошибка: {e}")


async def cmd_status_button(callback: types.CallbackQuery):
    """Обработчик кнопки статуса"""
    try:
        import psutil

        cpu = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        stats = db.get_stats()
        queue_count = db.get_queue_count()

        text = (
            f"📊 <b>Статус бота</b>\n\n"
            f"💻 CPU: {cpu}%\n"
            f"💾 Память: {memory.percent}%\n"
            f"⏳ В очереди: {queue_count}\n"
            f"✅ Опубликовано: {stats.get('published', 0)}\n"
            f"❌ Ошибок: {stats.get('errors', 0)}"
        )
        keyboard = create_back_button()
        await callback.message.answer(
            text, parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    except ImportError:
        stats = db.get_stats()
        queue_count = db.get_queue_count()
        text = (
            f"📊 <b>Статус бота</b>\n\n"
            f"⏳ В очереди: {queue_count}\n"
            f"✅ Опубликовано: {stats.get('published', 0)}\n"
            f"❌ Ошибок: {stats.get('errors', 0)}\n\n"
            f"💡 Установите psutil для детальной статистики"
        )
        keyboard = create_back_button()
        await callback.message.answer(
            text, parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    except Exception as e:
        logger.exception("status error: %s", e)
        keyboard = create_back_button()
        await callback.message.answer(
            f"❌ Ошибка: {str(e)[:200]}", reply_markup=keyboard
        )


async def cmd_restart_button(callback: types.CallbackQuery):
    """Обработчик кнопки перезапуска"""
    await callback.message.answer("🔄 Перезапуск бота...")
    import sys
    import os

    os.execv(sys.executable, [sys.executable] + sys.argv)


async def cmd_force_post_button(callback: types.CallbackQuery):
    """Обработчик кнопки срочного поста"""
    keyboard = create_back_button()
    task = db.get_next_from_queue()
    if task:
        task_id, url = task
        await callback.message.answer(f"⚡ Обрабатываю срочно: {url[:50]}...")
        success, _ = await process_and_publish(
            url, callback.message.chat.id
        )
        if success:
            db.mark_as_done(task_id)
            await callback.message.answer("✅ Опубликовано!", reply_markup=keyboard)
        else:
            await callback.message.answer("❌ Ошибка публикации", reply_markup=keyboard)
    else:
        await callback.message.answer("📭 Очередь пуста", reply_markup=keyboard)


async def cmd_last_post_button(callback: types.CallbackQuery):
    """Обработчик кнопки последнего поста"""
    last = db.get_last_post()
    keyboard = create_back_button()
    if last:
        text = (
            f"📝 <b>Последний пост</b>\n\n"
            f"🔗 URL: {last.get('url', 'N/A')}\n"
            f"📅 Дата: {last.get('date_added', 'N/A')}\n"
            f"📌 Название: {last.get('title', 'N/A')[:50]}"
        )
        await callback.message.answer(
            text, parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    else:
        await callback.message.answer("📭 Постов еще нет", reply_markup=keyboard)


async def cmd_info_button(callback: types.CallbackQuery):
    """Обработчик кнопки инфо"""
    count = db.get_queue_count()
    stats = db.get_stats()
    text = (
        f"📊 <b>Статистика бота</b>\n\n"
        f"⏳ В очереди: {count}\n"
        f"✅ Опубликовано: {stats.get('published', 0)}\n"
        f"❌ Ошибок: {stats.get('errors', 0)}\n"
        f"⏱ Интервал: {settings.POST_INTERVAL} сек."
    )
    keyboard = create_back_button()
    await callback.message.answer(
        text, parse_mode=ParseMode.HTML, reply_markup=keyboard
    )


async def cmd_check_auto_button(callback: types.CallbackQuery):
    """Обработчик кнопки 'Проверка' - сразу ищет 1 товар и публикует его"""
    if callback.from_user.id != settings.ADMIN_ID:
        await callback.answer("❌ Нет прав.", show_alert=True)
        return

    await callback.answer("🔍 Ищу товар и публикую...")
    AUTO_MAIN_PAGE_ENABLED = os.getenv("AUTO_MAIN_PAGE_ENABLED", "True").lower() in (
        "1",
        "true",
        "yes",
    )
    POST_INTERVAL_HOURS = settings.POST_INTERVAL / 3600

    queue_count_before = db.get_queue_count()
    stats = db.get_stats()

    search_status = ""

    try:
        from services.auto_search_service import AutoSearchService

        auto_search_service = AutoSearchService(db, bot)

        # Ищем 1 товар через главную страницу
        search_status += "🔗 Ищу товар на главной странице...\n"
        try:
            added = await auto_search_service.auto_add_products_from_main_page(
                max_add=1
            )
            if added > 0:
                search_status += f"✅ Найден товар\n"
            else:
                search_status += "⚠️ Товар не найден\n"
        except Exception as e:
            logger.exception(f"Ошибка поиска товара: {e}")
            search_status += f"❌ Ошибка поиска: {str(e)[:100]}\n"
        # Сразу публикуем найденный товар
        task = db.get_next_from_queue()
        if task:
            task_id, url = task
            search_status += f"\n📤 Публикую товар...\n"
            try:
                success, message_id = await process_and_publish(
                    url, settings.ADMIN_ID
                )
                if success:
                    search_status += f"✅ Товар успешно опубликован!\n"
                else:
                    search_status += f"⚠️ Не удалось опубликовать товар\n"
            except Exception as e:
                logger.exception(f"Ошибка публикации {url}: {e}")
                search_status += f"❌ Ошибка публикации: {str(e)[:100]}\n"
        else:
            search_status += f"\n⚠️ В очереди нет товаров для публикации\n"

    except Exception as e:
        logger.exception(f"Ошибка в cmd_check_auto_button: {e}")
        search_status += f"❌ Ошибка: {str(e)[:100]}\n"
    queue_count_after = db.get_queue_count()
    stats_after = db.get_stats()

    status_text = "🔍 <b>Результат проверки</b>\n\n"

    status_text += f"📊 <b>Очередь:</b> {queue_count_after} товаров"
    if queue_count_before != queue_count_after:
        status_text += f" ({queue_count_before} → {queue_count_after})"
    status_text += (
        f"\n📝 <b>Опубликовано:</b> {stats_after.get('published', 0)} товаров"
    )
    if stats.get("published", 0) != stats_after.get("published", 0):
        status_text += (
            f" (+{stats_after.get('published', 0) - stats.get('published', 0)})"
        )
    status_text += f"\n⏰ <b>Интервал публикации:</b> {POST_INTERVAL_HOURS:.0f} часа"

    if search_status:
        status_text += f"\n\n<b>📋 Детали:</b>\n{search_status}"

    keyboard = add_back_button(create_main_keyboard())
    from utils.safe_edit import safe_edit_callback_message

    await safe_edit_callback_message(
        callback, status_text, parse_mode=ParseMode.HTML, reply_markup=keyboard
    )


async def cmd_log_button(callback: types.CallbackQuery):
    """Обработчик кнопки логов - фильтрует и показывает только важные логи"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Все логи", callback_data="cmd_log_all")],
            [
                InlineKeyboardButton(
                    text="❌ Только ошибки", callback_data="cmd_log_errors"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚠️ Ошибки и предупреждения", callback_data="cmd_log_warnings"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню", callback_data="cmd_main_menu"
                )
            ],
        ]
    )

    try:
        # Определяем путь к логам
        if getattr(sys, "frozen", False):
            log_file = os.path.join(
                os.getenv("APPDATA"), "YandexMarketBot", "logs", "bot.log"
            )
        else:
            log_file = "logs/bot.log"

        if not os.path.exists(log_file):
            from utils.safe_edit import safe_edit_callback_message

            await safe_edit_callback_message(
                callback, "📭 Файл логов не найден", reply_markup=keyboard
            )
            await callback.answer()
            return

        # Читаем и фильтруем логи
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Фильтруем важные логи (ERROR, WARNING, INFO с ключевыми словами)
        important_lines = []
        keywords = [
            "ERROR",
            "WARNING",
            "INFO",
            "публикация",
            "публикован",
            "ошибка",
            "error",
            "exception",
            "worker",
            "queue",
        ]

        for line in lines[-200:]:  # Берем последние 200 строк для фильтрации
            line_upper = line.upper()
            if any(keyword.upper() in line_upper for keyword in keywords):
                # Убираем избыточные JSON дампы и отладочную информацию
                if "DEBUG" not in line_upper and '{"' not in line[:50]:
                    important_lines.append(line)

        # Берем последние 50 важных строк
        filtered_lines = (
            important_lines[-50:] if len(important_lines) > 50 else important_lines
        )

        if not filtered_lines:
            text = "📋 <b>Важные логи</b>\n\nНет важных записей в последних логах."
        else:
            log_text = "".join(filtered_lines)
            if len(log_text) > 4000:
                log_text = log_text[-4000:]
            text = f"📋 <b>Последние важные логи ({len(filtered_lines)} записей):</b>\n\n<code>{log_text}</code>"

        from utils.safe_edit import safe_edit_callback_message

        await safe_edit_callback_message(
            callback, text, parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.exception("log error: %s", e)
        from utils.safe_edit import safe_edit_callback_message

        await safe_edit_callback_message(
            callback, f"❌ Ошибка чтения логов: {str(e)[:200]}", reply_markup=keyboard
        )
        await callback.answer()


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Справка по командам"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    help_text = (
        "📖 <b>Справка по командам</b>\n\n"
        "<b>Управление постами:</b>\n"
        "/post &lt;url&gt; — опубликовать сейчас\n"
        "/q &lt;url&gt; [priority] [time] — добавить в очередь\n"
        "/test_post &lt;url&gt; — предпросмотр\n"
        "/force_post — срочная публикация\n"
        "/batch &lt;N&gt; — пакетная обработка\n\n"
        "<b>Очередь:</b>\n"
        "/clear — очистить очередь\n"
        "/remove — удалить (с выбором)\n"
        "/next [N] — следующие товары\n"
        "/duplicates — поиск дубликатов\n\n"
        "<b>Аналитика:</b>\n"
        "/stats — статистика\n"
        "/analytics — детальная аналитика\n"
        "/trends — анализ трендов\n"
        "/history [N] — история\n"
        "/export — экспорт данных\n\n"
        "<b>Контент:</b>\n"
        "/ideas [N] — идеи для постов\n"
        "/compilation [N] — создать подборку\n"
        "/random — случайный товар\n"
        "/discounts — товары со скидками\n"
        "/search &lt;запрос&gt; — поиск\n\n"
        "<b>Система:</b>\n"
        "/status — статус бота\n"
        "/health — проверка здоровья\n"
        "/disk — место на диске\n"
        "/cleanup — автоочистка\n"
        "/schedule — расписание\n"
        "/backup — резервная копия БД\n"
        "/version — версия\n\n"
        "<b>Управление:</b>\n"
        "/restart — перезапуск\n"
        "/reload_config — перезагрузка конфига\n"
        "/log — логи\n"
        "/blacklist — черный список\n"
        "/qr &lt;url&gt; — QR-код"
    )
    await message.answer(help_text, parse_mode=ParseMode.HTML)


@dp.message(Command("backup"))
async def cmd_backup(message: types.Message):
    """Создать резервную копию базы данных"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    await message.answer("📦 Создание резервной копии базы данных...")

    try:
        from services.backup_service import create_backup

        success = await create_backup(settings.ADMIN_ID, bot, settings.DB_FILE)

        if success:
            await message.answer("✅ Резервная копия успешно создана и отправлена!")
        else:
            await message.answer(
                "❌ Ошибка при создании резервной копии. Проверьте логи."
            )
    except Exception as e:
        logger.exception("Backup command error: %s", e)
        await message.answer(f"❌ Ошибка резервного копирования: {str(e)[:200]}")


@dp.message(Command("post"))
async def cmd_post_immediate(message: types.Message):
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ У вас нет прав на мгновенный пост.")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /post <url>")
        return
    await message.answer("⏳ Парсю и публикую...")
    await process_and_publish(args[1], message.chat.id)


@dp.message(Command("turbo"))
async def cmd_turbo(message: types.Message):
    """Переключение между режимами автопоиска: Turbo (10 сек) и Normal (1 час)"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ У вас нет прав.")
        return

    global global_scheduler
    if not global_scheduler:
        await message.answer("❌ Планировщик не запущен")
        return

    # Получаем текущее задание
    jobs = global_scheduler.get_jobs()
    if not jobs:
        await message.answer("❌ Нет активных заданий автопоиска")
        return

    job = jobs[0]  # Предполагаем, что первое задание - автопоиск
    current_interval = job.trigger.interval.total_seconds()

    if current_interval > 60:  # Если интервал больше минуты, переключаем на turbo (10 сек)
        new_interval = 10
        await message.answer("🚀 Turbo Mode ON (10 сек)")
    else:  # Иначе переключаем на normal (1 час = 3600 сек)
        new_interval = 3600
        await message.answer("🐢 Normal Mode ON (1 час)")

    # Перепланируем задание с новым интервалом
    global_scheduler.reschedule_job(
        job.id,
        trigger='interval',
        seconds=new_interval
    )

@dp.message(Command("run_now"))
async def cmd_run_now(message: types.Message):
    """Запустить автопоиск немедленно"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ У вас нет прав.")
        return

    await message.answer("🔎 Force search started...")

    # Создаем сервис и запускаем поиск
    from services.auto_search_service import AutoSearchService

    auto_search_service = AutoSearchService(db, bot)

    try:
        await auto_search_service.run_search_and_queue(global_settings, bot)
        await message.answer("✅ Force search completed")
    except Exception as e:
        logger.exception("run_now error: %s", e)
        await message.answer(f"❌ Error: {str(e)[:200]}")


@dp.message(Command("get_ref", "getref"))
async def cmd_get_ref(message: types.Message):
    """Получить ссылку для товара"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /get_ref <url> [--browser]")
        return

    url = args[1]
    use_browser = "--browser" in args or "-b" in args

    await message.answer("🔗 Получаю ссылку...")

    try:
        from services.url_service import UrlService
        from services.partner_link_service import PartnerLinkService

        url_info_dict = UrlService.parse_url(url)
        is_cc_url = url_info_dict.get("is_cc", False)

        # Если это уже cc-ссылка, просто возвращаем её как есть
        if is_cc_url:
            logger.info("get_ref: detected cc/ URL, returning as-is: %s", url)
            response = (
                f"📦 <b>Ссылка на товар (cc/)</b>\n\n"
                f"✅ <b>Ссылка:</b>\n{url}\n\n"
                f"💡 <b>Это cc-ссылка для вставки.</b>\n"
                f"Используйте её напрямую, не нужно передавать в /post.\n\n"
                f"🏷️ <b>Флаги:</b> cc_url_direct, from_input\n"
            )
            await message.answer(response, parse_mode=ParseMode.HTML)
            return

        # Для card/... URL пытаемся извлечь или сгенерировать cc
        partner_service = PartnerLinkService()

        # Сначала пытаемся извлечь CC из параметров URL
        cc_code_from_url = UrlService.extract_cc_code(url)

        if cc_code_from_url:
            # CC код уже есть в URL, строим партнёрскую ссылку
            ref_link = UrlService.build_cc_link(cc_code_from_url)
            logger.info("get_ref: found CC code in URL params: %s", cc_code_from_url)

            response = (
                f"📦 <b>Результат получения ссылки</b>\n\n"
                f"🔗 <b>Исходная ссылка:</b>\n{url}\n\n"
                f"✅ <b>Ссылка:</b>\n{ref_link}\n\n"
                f"💡 <b>Это cc-ссылка для вставки.</b>\n"
                f"Используйте её напрямую, не нужно передавать в /post.\n\n"
                f"🏷️ <b>Флаги:</b> from_input_url, cc_found_in_params\n"
            )
            await message.answer(response, parse_mode=ParseMode.HTML)
            return

        # Если CC нет в URL, пытаемся сгенерировать через сервис
        result = await partner_service.get_product_with_partner_link(
            url, use_browser=use_browser
        )

        # Форматируем ответ
        flags = result.get("flags", [])
        flags_text = ", ".join(flags) if flags else "нет"
        has_ref = result.get("has_ref", False)
        product_url = result.get("product_url", url)

        # Определяем источник данных
        data_source = "parser_only"
        if "ai_ok" in flags:
            data_source = "ai_ok"
        elif "ai_fallback" in flags:
            data_source = "ai_fallback"
        elif any(f in flags for f in ["ai_ok", "from_ai"]):
            data_source = "ai_ok"

        source_emoji = {"ai_ok": "🤖", "ai_fallback": "⚠️", "parser_only": "🔧"}.get(
            data_source, "🔧"
        )

        response = (
            f"📦 <b>Результат получения ссылки</b>\n\n"
            f"🔗 <b>Исходная ссылка:</b>\n{url}\n\n"
        )

        if has_ref and result.get("ref_link"):
            response += f"✅ <b>Ссылка:</b>\n{result['ref_link']}\n\n"
            response += f"💡 <b>Это cc-ссылка для вставки.</b>\n"
            response += f"Используйте её напрямую, не нужно передавать в /post.\n\n"
        else:
            response += f"⚠️ <b>Ссылка:</b> не найдена\n\n"
            response += f"🔗 <b>Обычная ссылка:</b>\n{product_url}\n\n"

        if result.get("title"):
            response += f"📝 <b>Название:</b> {result['title']}\n"
        if result.get("price"):
            response += f"💰 <b>Цена:</b> {result['price']}\n"

        response += f"\n{source_emoji} <b>Источник данных:</b> {data_source}\n"
        response += f"🏷️ <b>Флаги:</b> {flags_text}\n"

        if "needs_login" in result.get("flags", []):
            response += "\n💡 Используйте /login для входа в аккаунт"

        await message.answer(response, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.exception("get_ref error: %s", e)
        await message.answer(f"❌ Ошибка: {str(e)[:200]}")


@dp.message(Command("ai_metrics", "aimetrics"))
async def cmd_ai_metrics(message: types.Message):
    """Показать метрики работы AI"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    try:
        from services.ai_metrics import get_ai_metrics
        from services.ai_cache import get_ai_cache

        metrics = get_ai_metrics()
        cache = get_ai_cache()

        stats = metrics.get_stats()
        cache_stats = cache.get_stats()

        response = (
            f"🤖 <b>Метрики AI обогащения</b>\n\n"
            f"📊 <b>Общая статистика:</b>\n"
            f"  • Всего запросов: {stats['total_requests']}\n"
            f"  • Успешных (ai_ok): {stats['ai_ok']}\n"
            f"  • Ошибок (ai_error): {stats['ai_error']}\n"
            f"  • Fallback (ai_fallback): {stats['ai_fallback']}\n"
            f"  • Успешность: {stats['ai_ok_ratio']:.1f}%\n\n"
            f"⏱ <b>Производительность:</b>\n"
            f"  • Среднее время ответа: {stats['avg_timing_ms']:.0f} мс\n\n"
            f"💰 <b>Стоимость (24ч):</b>\n"
            f"  • Токены: {stats['total_tokens_24h']}\n"
            f"  • Стоимость: {stats['total_cost_24h']:.2f} ₽\n\n"
            f"📈 <b>За последний час:</b>\n"
            f"  • ai_ok: {stats['hour_stats']['ai_ok']}\n"
            f"  • ai_error: {stats['hour_stats']['ai_error']}\n"
            f"  • ai_fallback: {stats['hour_stats']['ai_fallback']}\n"
            f"  • Доля успешных: {stats['hour_ai_ratio']:.1f}%\n\n"
            f"💾 <b>Кэш:</b>\n"
            f"  • Всего записей: {cache_stats['total']}\n"
            f"  • Активных: {cache_stats['active']}\n"
            f"  • Истекших: {cache_stats['expired']}\n"
        )

        await message.answer(response, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.exception("ai_metrics error: %s", e)
        await message.answer(f"❌ Ошибка: {str(e)[:200]}")


@dp.message(Command("login"))
async def cmd_login(message: types.Message):
    """Интерактивный вход в Яндекс для сохранения cookies (только для админа)"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    await message.answer(
        "🔐 <b>Интерактивный вход в Яндекс</b>\n\n"
        "Откроется браузер для входа в аккаунт.\n"
        "После входа cookies будут сохранены для использования ссылок.\n\n"
        "⏳ Запускаю браузер...",
        parse_mode=ParseMode.HTML,
    )

    try:
        from services.partner_link_service import PartnerLinkService

        service = PartnerLinkService()

        # Запускаем в фоне, чтобы не блокировать бота
        await message.answer(
            "⏳ <b>Процесс входа запущен</b>\n\n"
            "Откройте консоль/терминал где запущен бот.\n"
            "Там откроется браузер для входа.\n\n"
            "После входа нажмите Enter в консоли.",
            parse_mode=ParseMode.HTML,
        )

        success = await service.interactive_login()

        if success:
            await message.answer(
                "✅ Cookies saved. Bot will now try to generate ref-links with your account."
            )
        else:
            await message.answer(
                "❌ Ошибка при входе.\n\n"
                "Возможные причины:\n"
                "• Playwright не установлен\n"
                "• Браузеры не установлены\n"
                "• Таймаут входа (5 минут)\n\n"
                "Проверьте логи в консоли."
            )
    except ImportError:
        await message.answer(
            "❌ Playwright не установлен.\n\n"
            "Установите:\n"
            "1. pip install playwright\n"
            "2. python -m playwright install chromium"
        )
    except Exception as e:
        logger.exception("login error: %s", e)
        await message.answer(f"❌ Ошибка: {str(e)[:200]}")


@dp.message(Command("cancel_login"))
async def cmd_cancel_login(message: types.Message):
    """Отмена процесса входа (заглушка)"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return
    await message.answer("ℹ️ Команда отмены входа (реализация в процессе)")


@dp.message(Command("q"))
async def cmd_add_to_queue(message: types.Message):
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /q <url>")
        return
    url = args[1]
    if db.add_to_queue(url):
        count = db.get_queue_count()
        await message.answer(f"✅ Добавлено в очередь. Всего: {count}")
    else:
        await message.answer("⚠️ Эта ссылка уже в очереди.")


@dp.message(Command("info"))
async def cmd_info(message: types.Message):
    count = db.get_queue_count()
    stats = db.get_stats()
    await message.answer(
        f"📊 <b>Статистика бота</b>\n\n"
        f"⏳ В очереди: {count}\n"
        f"✅ Опубликовано: {stats.get('published', 0)}\n"
        f"❌ Ошибок: {stats.get('errors', 0)}\n"
        f"⏱ Интервал: {settings.POST_INTERVAL} сек."
    )


@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return
    stats = db.get_stats()
    await message.answer(
        f"📈 <b>Детальная статистика</b>\n\n"
        f"✅ Опубликовано всего: {stats.get('published', 0)}\n"
        f"⏳ В очереди: {stats.get('pending', 0)}\n"
        f"❌ Ошибок: {stats.get('errors', 0)}\n"
        f"📝 В истории: {stats.get('history', 0)}\n"
        f"🔄 Успешных сегодня: {stats.get('today', 0)}"
    )


@dp.message(Command("ab_stats"))
async def cmd_ab_stats(message: types.Message):
    """Показывает статистику A/B тестирования caption"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    try:
        ab_stats = db.get_ab_test_stats()

        if not ab_stats["template_stats"]:
            await message.answer(
                "📊 <b>A/B Testing Stats</b>\n\nНет данных для анализа. Посты с A/B тестированием еще не публиковались."
            )
            return

        response = "📊 <b>A/B Testing Statistics</b>\n\n"

        # Общая статистика
        total = ab_stats["total_stats"]
        response += f"📈 <b>Общая статистика:</b>\n"
        response += f"• Всего A/B постов: {total['total_ab_posts']}\n"
        response += f"• Средние просмотры: {total['overall_avg_views']:.1f}\n"
        response += f"• Всего просмотров: {total['overall_total_views']}\n\n"

        # Статистика по шаблонам
        response += "📋 <b>По типам шаблонов:</b>\n"
        for template in ab_stats["template_stats"]:
            emoji = "😊" if template["template_type"] == "emoji_heavy" else "💼"
            name = (
                "Emoji-heavy"
                if template["template_type"] == "emoji_heavy"
                else "Professional"
            )
            response += f"{emoji} <b>{name}:</b>\n"
            response += f"  • Постов: {template['total_posts']}\n"
            response += f"  • Ср. просмотры: {template['avg_views']:.1f}\n"
            response += f"  • Всего просмотров: {template['total_views']}\n"
            response += (
                f"  • Мин/Макс: {template['min_views']}/{template['max_views']}\n\n"
            )

        # Статистика за неделю
        if ab_stats["weekly_stats"]:
            response += "📅 <b>За последние 7 дней:</b>\n"
            for template in ab_stats["weekly_stats"]:
                emoji = "😊" if template["template_type"] == "emoji_heavy" else "💼"
                name = (
                    "Emoji-heavy"
                    if template["template_type"] == "emoji_heavy"
                    else "Professional"
                )
                response += f"{emoji} {name}:\n"
                response += f"  • Постов: {template['posts_last_week']}\n"
                response += f"  • Ср. просмотры: {template['avg_views_week']:.1f}\n\n"

        # Определение победителя
        if len(ab_stats["template_stats"]) >= 2:
            sorted_templates = sorted(
                ab_stats["template_stats"], key=lambda x: x["avg_views"], reverse=True
            )
            winner = sorted_templates[0]
            loser = sorted_templates[1]

            winner_emoji = "😊" if winner["template_type"] == "emoji_heavy" else "💼"
            winner_name = (
                "Emoji-heavy"
                if winner["template_type"] == "emoji_heavy"
                else "Professional"
            )

            response += f"🏆 <b>Лидер по просмотрам:</b> {winner_emoji} {winner_name}\n"
            response += (
                f"   ({winner['avg_views']:.1f} vs {loser['avg_views']:.1f} просмотров)"
            )

        await message.answer(response)

    except Exception as e:
        logger.exception(f"Error in ab_stats command: {e}")
        await message.answer(
            f"❌ Ошибка при получении статистики A/B тестирования: {str(e)[:200]}"
        )


@dp.message(Command("clear"))
async def cmd_clear_queue(message: types.Message):
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return
    count = db.clear_queue()
    await message.answer(f"🗑 Очищено из очереди: {count}")


@dp.message(Command("remove"))
async def cmd_remove_from_queue(message: types.Message):
    """Показывает список элементов очереди с кнопками для удаления"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    # Получаем элементы очереди
    queue_items = db.get_queue_urls(limit=50)  # Показываем первые 50

    if not queue_items:
        await message.answer("📭 Очередь пуста")
        return

    # Создаем клавиатуру с кнопками
    keyboard = []

    # Группируем по 2 кнопки в ряд
    for i in range(0, min(len(queue_items), 20), 2):  # Максимум 20 элементов (10 рядов)
        row = []
        for j in range(2):
            if i + j < len(queue_items):
                task_id, url = queue_items[i + j]
                # Обрезаем URL для отображения
                display_url = url[:30] + "..." if len(url) > 30 else url
                row.append(
                    InlineKeyboardButton(
                        text=f"❌ {i+j+1}", callback_data=f"remove_{task_id}"
                    )
                )
        keyboard.append(row)

    # Кнопка "Удалить все"
    keyboard.append(
        [InlineKeyboardButton(text="🗑 Удалить все", callback_data="remove_all")]
    )
    # Кнопка "Отмена"
    keyboard.append(
        [InlineKeyboardButton(text="❌ Отмена", callback_data="remove_cancel")]
    )

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    text = f"🗑️ <b>Удаление из очереди</b>\n\n"
    text += f"📊 Всего в очереди: {len(queue_items)}\n"
    text += f"👆 Выберите элемент для удаления:\n\n"

    # Показываем первые 10 элементов в тексте
    for idx, (task_id, url) in enumerate(queue_items[:10], 1):
        short_url = url[:50] + "..." if len(url) > 50 else url
        text += f"{idx}. {short_url}\n"

    if len(queue_items) > 10:
        text += f"\n... и еще {len(queue_items) - 10} элементов"

    await message.answer(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


@dp.callback_query(F.data.startswith("remove_"))
async def handle_remove_callback(callback: types.CallbackQuery):
    """Обработка нажатия на кнопку удаления"""
    if callback.from_user.id != settings.ADMIN_ID:
        await callback.answer("❌ Нет прав.", show_alert=True)
        return

    data = callback.data

    if data == "remove_cancel":
        from utils.safe_edit import safe_edit_callback_message

        await safe_edit_callback_message(callback, "❌ Отменено")
        await callback.answer()
        return

    if data == "remove_all":
        # Подтверждение удаления всех элементов
        count = db.get_queue_count()
        if count == 0:
            await callback.answer("⚠️ Очередь уже пуста", show_alert=True)
            return

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Подтвердить", callback_data="remove_all_confirm"
                    )
                ],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="remove_cancel")],
            ]
        )

        from utils.safe_edit import safe_edit_callback_message

        await safe_edit_callback_message(
            callback,
            f"⚠️ <b>Подтверждение удаления</b>\n\n"
            f"Будет удалено <b>все {count}</b> элементов из очереди.\n"
            f"Это действие нельзя отменить!",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        await callback.answer()
        return

    if data == "remove_all_confirm":
        # Удаление всех элементов
        count = db.clear_queue()
        logger.info(
            f"Admin {callback.from_user.id} removed all from queue: {count} items"
        )
        await callback.message.edit_text(
            f"✅ <b>Все элементы удалены</b>\n\n" f"Удалено элементов: <b>{count}</b>",
            parse_mode=ParseMode.HTML,
        )
        await callback.answer("✅ Все удалено", show_alert=True)
        return

    # Извлекаем task_id из callback_data
    if data.startswith("remove_"):
        task_id_str = data.replace("remove_", "")
        try:
            task_id = int(task_id_str)

            # Получаем URL по task_id
            queue_items = db.get_queue_urls(limit=1000)
            url_to_remove = None
            for tid, url in queue_items:
                if tid == task_id:
                    url_to_remove = url
                    break

            if not url_to_remove:
                await callback.answer("⚠️ Элемент не найден", show_alert=True)
                return

            # Удаляем из очереди
            if db.remove_from_queue(task_id=task_id):
                await callback.answer("✅ Удалено из очереди", show_alert=True)

                # Обновляем сообщение
                remaining = db.get_queue_count()
                await callback.message.edit_text(
                    f"✅ <b>Удалено из очереди</b>\n\n"
                    f"🔗 {url_to_remove[:60]}...\n\n"
                    f"📊 Осталось в очереди: {remaining}",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await callback.answer("⚠️ Ошибка при удалении", show_alert=True)

        except ValueError:
            await callback.answer("⚠️ Неверный ID", show_alert=True)


# Обработчики интерактивного ввода
@dp.message(F.text & ~F.text.startswith("/"))
async def handle_text_input(message: types.Message):
    """Обработка текстового ввода для интерактивных команд"""
    if message.from_user.id != settings.ADMIN_ID:
        return

    user_id = message.from_user.id
    state = user_states.get(user_id, {})

    if not state:
        return  # Нет активного состояния

    state_type = state.get("state")
    text = message.text.strip()

    if state_type == "waiting_qr_url" or state_type == "waiting_for_qr_url":
        # Генерация QR-кода
        user_states.pop(user_id, None)
        if not text.startswith("http"):
            await message.answer(
                "❌ Неверный URL. Введите корректную ссылку вида https://..."
            )
            return

        await generate_and_send_qr(message, text)
        return

    if state_type == "waiting_qr_url_old":
        # Старая версия (для совместимости)
        if not text.startswith("http"):
            await message.answer(
                "❌ Неверный URL. Введите корректную ссылку вида https://..."
            )
            return

        try:
            from services.url_service import generate_qr_code

            qr_bytes = generate_qr_code(text)  # Не async функция
            if qr_bytes:
                from io import BytesIO

                qr_file = types.BufferedInputFile(qr_bytes, filename="qrcode.png")
                await message.answer_photo(
                    photo=qr_file, caption=f"📱 QR-код для:\n{text}"
                )
            else:
                await message.answer("❌ Ошибка генерации QR-кода")
        except Exception as e:
            logger.exception("QR generation error: %s", e)
            await message.answer(f"❌ Ошибка: {str(e)[:200]}")

        # Очищаем состояние
        user_states.pop(user_id, None)

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🏠 Главное меню", callback_data="cmd_main_menu"
                    )
                ]
            ]
        )
        await message.answer("✅ Готово", reply_markup=keyboard)

    elif state_type == "waiting_search_query":
        # Поиск товаров
        if len(text) < 2:
            await message.answer("❌ Запрос слишком короткий. Минимум 2 символа.")
            return

        await message.answer(f"🔍 Ищу товары по запросу: {text}...")

        try:
            from services.auto_search_service import AutoSearchService

            search_service = AutoSearchService(db, bot)
            products = await search_service.search_products(text, max_results=20)

            if not products:
                await message.answer(
                    f"📭 По запросу '{text}' ничего не найдено.\n"
                    f"Попробуйте другой запрос или используйте автопоиск."
                )
            else:
                text_result = f"🔍 <b>Найдено товаров: {len(products)}</b>\n\n"
                keyboard_buttons = []

                for idx, product in enumerate(products[:10], 1):
                    title = product.get("title", "Без названия")[:50]
                    url = product.get("url", "")
                    text_result += f"{idx}. <b>{title}</b>\n"
                    text_result += f"   🔗 {url[:60]}...\n\n"

                    # Кнопка для добавления в очередь
                    if idx <= 5:  # Первые 5 товаров
                        keyboard_buttons.append(
                            [
                                InlineKeyboardButton(
                                    text=f"➕ Добавить {idx}",
                                    callback_data=f"cmd_add_search_{idx}",
                                )
                            ]
                        )

                if len(products) > 10:
                    text_result += f"... и еще {len(products) - 10} товаров"

                # Сохраняем результаты поиска во временное хранилище
                if user_id not in user_states:
                    user_states[user_id] = {}
                user_states[user_id]["search_results"] = products

                keyboard_buttons.append(
                    [
                        InlineKeyboardButton(
                            text="🏠 Главное меню", callback_data="cmd_main_menu"
                        )
                    ]
                )

                keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
                await message.answer(
                    text_result, reply_markup=keyboard, parse_mode=ParseMode.HTML
                )
        except Exception as e:
            logger.exception("Search error: %s", e)
            await message.answer(
                f"❌ Ошибка поиска: {str(e)[:200]}\n"
                f"Попробуйте позже или используйте автопоиск."
            )

        # Очищаем состояние
        user_states.pop(user_id, None)

    elif state_type == "waiting_schedule_hours":
        # Настройка часов расписания
        try:
            hours = [
                int(h.strip())
                for h in text.split(",")
                if h.strip().isdigit() and 0 <= int(h.strip()) <= 23
            ]
            if not hours:
                await message.answer(
                    "❌ Неверный формат. Введите часы от 0 до 23 через запятую (например: 9,12,15,18)"
                )
                return

            global_settings = get_global_settings()
            global_settings.update_schedule_settings(hours=sorted(set(hours)))
            schedule_settings = global_settings.get_schedule_settings()
            hours_text = ", ".join([f"{h:02d}:00" for h in schedule_settings["hours"]])
            await message.answer(f"✅ Часы установлены: {hours_text}")
            user_states.pop(user_id, None)

            # Показываем обновленные настройки через новое сообщение
            enabled = schedule_settings.get("enabled", False)
            one_per_day = schedule_settings.get("one_per_day", False)
            interval = schedule_settings.get("interval", settings.POST_INTERVAL)
            interval_text = (
                f"{interval // 60} мин" if interval < 3600 else f"{interval // 3600} ч"
            )

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=f"{'✅' if enabled else '❌'} Включить/Выключить",
                            callback_data="cmd_schedule_toggle",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="⏰ Настроить часы", callback_data="cmd_schedule_hours"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=f"{'✅' if one_per_day else '❌'} Один в день",
                            callback_data="cmd_schedule_one_per_day",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="⏱ Настроить интервал",
                            callback_data="cmd_schedule_interval",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="💾 Сохранить", callback_data="cmd_schedule_save"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🏠 Главное меню", callback_data="cmd_main_menu"
                        )
                    ],
                ]
            )

            text = (
                "⏰ <b>Настройка расписания</b>\n\n"
                f"📅 Включено: {'✅ Да' if enabled else '❌ Нет'}\n"
                f"🕐 Часы: {hours_text}\n"
                f"📆 Один в день: {'✅ Да' if one_per_day else '❌ Нет'}\n"
                f"⏱ Интервал: {interval_text}\n\n"
                "Выберите параметр для настройки:"
            )
            await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        except ValueError:
            await message.answer(
                "❌ Ошибка: неверный формат. Введите числа от 0 до 23 через запятую"
            )

    elif state_type == "waiting_schedule_interval":
        # Настройка интервала
        try:
            interval = int(text.strip())
            if interval < 60:
                await message.answer("❌ Интервал должен быть не менее 60 секунд")
                return

            global_settings = get_global_settings()
            global_settings.update_schedule_settings(interval=interval)
            schedule_settings = global_settings.get_schedule_settings()
            interval_text = (
                f"{interval // 60} мин" if interval < 3600 else f"{interval // 3600} ч"
            )
            await message.answer(f"✅ Интервал установлен: {interval_text}")
            user_states.pop(user_id, None)

            # Показываем обновленные настройки через новое сообщение
            enabled = schedule_settings.get("enabled", False)
            hours = schedule_settings.get("hours", [])
            one_per_day = schedule_settings.get("one_per_day", False)
            hours_text = (
                ", ".join([f"{h:02d}:00" for h in sorted(hours)])
                if hours
                else "Не задано"
            )

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=f"{'✅' if enabled else '❌'} Включить/Выключить",
                            callback_data="cmd_schedule_toggle",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="⏰ Настроить часы", callback_data="cmd_schedule_hours"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=f"{'✅' if one_per_day else '❌'} Один в день",
                            callback_data="cmd_schedule_one_per_day",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="⏱ Настроить интервал",
                            callback_data="cmd_schedule_interval",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="💾 Сохранить", callback_data="cmd_schedule_save"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🏠 Главное меню", callback_data="cmd_main_menu"
                        )
                    ],
                ]
            )

            text = (
                "⏰ <b>Настройка расписания</b>\n\n"
                f"📅 Включено: {'✅ Да' if enabled else '❌ Нет'}\n"
                f"🕐 Часы: {hours_text}\n"
                f"📆 Один в день: {'✅ Да' if one_per_day else '❌ Нет'}\n"
                f"⏱ Интервал: {interval_text}\n\n"
                "Выберите параметр для настройки:"
            )
            await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        except ValueError:
            await message.answer("❌ Ошибка: введите число (интервал в секундах)")


@dp.message(F.document)
async def handle_file(message: types.Message):
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return
    doc = message.document
    if not doc.file_name or not doc.file_name.endswith(".txt"):
        await message.answer("❌ Пришлите .txt файл")
        return

    # Безопасность: ограничение размера файла (1MB)
    if doc.file_size and doc.file_size > 1024 * 1024:
        await message.answer("❌ Файл слишком большой (максимум 1MB)")
        return

    try:
        file = await bot.get_file(doc.file_id)
        io_obj = await bot.download_file(file.file_path)
        content = io_obj.read().decode("utf-8", errors="ignore")

        # Валидация и фильтрация URL
        lines = content.splitlines()
        urls = []
        invalid_count = 0
        for line in lines:
            line = line.strip()
            if line.startswith("http"):
                if is_valid_yandex_market_url(line):
                    urls.append(line)
                else:
                    invalid_count += 1

        added = 0
        duplicates = 0
        for u in urls:
            if db.add_to_queue(u):
                added += 1
            else:
                duplicates += 1

        total = db.get_queue_count()
        result_msg = (
            f"📄 <b>Обработка файла завершена</b>\n\n"
            f"✅ Валидных URL: {len(urls)}\n"
            f"➕ Добавлено: {added}\n"
            f"⚠️ Дубликатов: {duplicates}\n"
            f"❌ Невалидных: {invalid_count}\n"
            f"📊 В очереди: {total}"
        )
        await message.answer(result_msg)
    except Exception as e:
        logger.exception("handle_file error: %s", e)
        await message.answer(f"❌ Ошибка обработки файла: {str(e)[:200]}")


# --- Новые команды (20 функций) ---


@dp.message(Command("ideas"))
async def cmd_ideas(message: types.Message):
    """Генерирует идеи для постов"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    args = message.text.split()
    count = 10
    if len(args) > 1:
        try:
            count = min(int(args[1]), 20)
        except ValueError:
            pass

    ideas = generate_ideas(count)
    text = f"💡 <b>Идеи для постов ({len(ideas)}):</b>\n\n"
    for i, idea in enumerate(ideas, 1):
        text += f"{i}. {idea}\n"

    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("compilation"))
async def cmd_compilation(message: types.Message):
    """Создает подборку из последних товаров"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    args = message.text.split()
    limit = 5
    if len(args) > 1:
        try:
            limit = min(int(args[1]), 20)
        except ValueError:
            pass

    await message.answer("⏳ Создаю подборку...")

    # Получаем историю и кэш
    history = db.get_history(limit=limit * 2)  # Берем больше, чтобы отфильтровать

    if not history:
        await message.answer("📭 Недостаточно товаров для подборки.")
        return

    # Собираем данные из кэша
    items = []
    for h in history:
        url = h.get("url", "")
        if not url:
            continue

        # Пробуем получить из кэша
        data = db.get_cached_data(url, max_age_hours=168)  # Неделя
        if data and data.get("title"):
            items.append(
                {
                    "title": data.get("title", ""),
                    "price": data.get("price", "Цена уточняется"),
                    "url": url,
                    "image_url": data.get("image_url", ""),
                }
            )

        if len(items) >= limit:
            break

    if not items:
        # Fallback: используем данные из истории
        items = [
            {
                "title": h.get("title", "Без названия"),
                "price": "Цена уточняется",
                "url": h.get("url", ""),
            }
            for h in history[:limit]
        ]

    if not items:
        await message.answer("📭 Недостаточно товаров с данными для подборки.")
        return

    compilation = create_compilation_post(items)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Опубликовать подборку",
                    callback_data="cmd_compilation_publish",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Создать другую", callback_data="cmd_compilation_new"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню", callback_data="cmd_main_menu"
                )
            ],
        ]
    )

    await message.answer(
        compilation,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=keyboard,
    )


@dp.message(Command("trends"))
async def cmd_trends(message: types.Message):
    """Анализ трендов по истории"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    await message.answer("📊 Анализирую тренды...")

    history = db.get_history(limit=500)
    trends = analyze_trends(history)

    if not trends:
        await message.answer("📭 Недостаточно данных для анализа.")
        return

    text = f"📊 <b>Анализ трендов</b>\n\n"
    text += f"📝 Всего товаров: {trends.get('total_items', 0)}\n\n"

    if trends.get("categories"):
        text += "<b>📂 По категориям:</b>\n"
        total_cat = sum(trends["categories"].values())
        for cat, count in sorted(
            trends["categories"].items(), key=lambda x: x[1], reverse=True
        ):
            percentage = (count / total_cat * 100) if total_cat > 0 else 0
            cat_name = {
                "food": "🍫 Еда",
                "tech": "📱 Техника",
                "clothing": "👕 Одежда",
                "toys": "🧸 Игрушки",
                "other": "📦 Другое",
            }.get(cat, cat)
            text += f"{cat_name}: {count} ({percentage:.1f}%)\n"

    if trends.get("price_ranges"):
        text += f"\n💰 <b>По ценовым диапазонам:</b>\n"
        for range_name, count in sorted(
            trends["price_ranges"].items(), key=lambda x: x[1], reverse=True
        ):
            text += f"{range_name}: {count}\n"

    if trends.get("most_popular"):
        text += f"\n🔥 <b>Самая популярная категория:</b> {trends['most_popular']}\n"

    if trends.get("trend_percentage"):
        text += f"\n📈 <b>Тренд:</b> {trends['trend_percentage']:.1f}%"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Детальная аналитика", callback_data="cmd_analytics"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню", callback_data="cmd_main_menu"
                )
            ],
        ]
    )

    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@dp.message(Command("random"))
async def cmd_random(message: types.Message):
    """Случайный товар из очереди"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    import random

    queue_items = db.get_queue_urls(limit=1000)
    if not queue_items:
        await message.answer("📭 Очередь пуста.")
        return

    task_id, url = random.choice(queue_items)

    # Пробуем получить данные из кэша
    data = db.get_cached_data(url, max_age_hours=48)
    title = "Без названия"
    price = "Цена уточняется"

    if data:
        title = data.get("title", "Без названия")
        price = data.get("price", "Цена уточняется")

    text = (
        f"🎲 <b>Случайный товар:</b>\n\n"
        f"📦 <b>{title}</b>\n"
        f"💰 {price}\n"
        f"🔗 {url}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Опубликовать сейчас", callback_data=f"post_now_{task_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎲 Другой товар", callback_data="cmd_random_another"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню", callback_data="cmd_main_menu"
                )
            ],
        ]
    )

    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@dp.message(Command("discounts"))
async def cmd_discounts(message: types.Message):
    """Показать товары со скидками из очереди"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    # Получаем товары из очереди и проверяем скидки
    queue_items = db.get_queue_urls(limit=100)
    if not queue_items:
        await message.answer("📭 Очередь пуста.")
        return

    await message.answer("⏳ Проверяю скидки... Это может занять время.")

    items_with_discount = []
    for task_id, url in queue_items[:20]:  # Проверяем первые 20
        try:
            data = db.get_cached_data(url, max_age_hours=48)  # Увеличиваем время кэша
            if not data:
                # Если нет в кэше, пробуем парсить
                try:
                    from utils.scraper import scrape_yandex_market

                    data = await scrape_yandex_market(url)
                    if data:
                        db.set_cached_data(url, data)
                except Exception:
                    continue

            if data:
                discount = extract_discount_from_data(data)
                if discount >= settings.MIN_DISCOUNT:
                    title = data.get("title", "Без названия")
                    price = data.get("price", "Цена уточняется")
                    old_price = data.get("old_price", "")
                    items_with_discount.append(
                        (task_id, url, discount, title, price, old_price)
                    )
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            logger.debug(f"Error processing discount for {url[:50]}: {e}")
            continue

    if items_with_discount:
        # Сортируем по размеру скидки
        items_with_discount.sort(key=lambda x: x[2], reverse=True)
        top_items = items_with_discount[:10]  # Топ-10

        text = f"💰 <b>Товары со скидками (найдено {len(items_with_discount)}, показываю топ-{len(top_items)}):</b>\n\n"
        for task_id, url, discount, title, price, old_price in top_items:
            text += f"🔥 <b>{discount}%</b> — {title[:40]}...\n"
            if old_price:
                text += f"   💰 {old_price} → {price}\n"
            else:
                text += f"   💰 {price}\n"
            text += f"   🔗 {url[:50]}...\n\n"

        # Кнопки для публикации топ-3
        keyboard_buttons = []
        for i, (task_id, url, discount, title, _, _) in enumerate(top_items[:3], 1):
            keyboard_buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"📢 Опубликовать #{i} ({discount}%)",
                        callback_data=f"post_now_{task_id}",
                    )
                ]
            )
        keyboard_buttons.append(
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню", callback_data="cmd_main_menu"
                )
            ]
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    else:
        await message.answer("📭 Товаров со скидками не найдено.")


@dp.message(Command("qr"))
async def cmd_qr(message: types.Message, state: FSMContext):
    """Генерирует QR-код для ссылки (интерактивный ввод)"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    args = message.text.split()
    if len(args) >= 2:
        # URL передан как аргумент
        url = args[1]
        await generate_and_send_qr(message, url)
    else:
        # Запрашиваем URL интерактивно
        user_states[message.from_user.id] = {
            "state": "waiting_for_qr_url",
            "message_id": message.message_id,
        }
        await message.answer(
            "📱 <b>Генерация QR-кода</b>\n\n" "Отправьте URL для генерации QR-кода:",
            parse_mode=ParseMode.HTML,
        )


async def generate_and_send_qr(message: types.Message, url: str):
    """Генерирует и отправляет QR-код"""
    try:
        if not is_valid_yandex_market_url(url):
            await message.answer("❌ Неверный URL Яндекс.Маркета")
            return

        await message.answer("⏳ Генерирую QR-код...")
        qr_bytes = generate_qr_code(url)

        if qr_bytes:
            qr_file = types.BufferedInputFile(qr_bytes, filename="qrcode.png")
            await message.answer_photo(
                qr_file,
                caption=f"📱 <b>QR-код</b>\n\n🔗 {url}",
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.answer(
                "❌ Ошибка генерации QR-кода. Установите: pip install qrcode[pil]"
            )
    except Exception as e:
        logger.exception("Error generating QR code: %s", e)
        await message.answer(f"❌ Ошибка: {str(e)[:200]}")


@dp.message(Command("analytics"))
async def cmd_analytics(message: types.Message):
    """Детальная аналитика"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    daily_stats = analytics.get_daily_stats(days=7)
    category_stats = analytics.get_category_stats()

    text = "📊 <b>Детальная аналитика</b>\n\n"
    text += "<b>За последние 7 дней:</b>\n"
    for stat in daily_stats[:7]:
        text += f"📅 {stat['date']}: {stat['count']} постов\n"

    if category_stats:
        text += "\n<b>По категориям:</b>\n"
        cat_names = {
            "food": "🍫 Еда",
            "tech": "📱 Техника",
            "clothing": "👕 Одежда",
            "toys": "🧸 Игрушки",
            "other": "📦 Другое",
        }
        for cat, count in sorted(
            category_stats.items(), key=lambda x: x[1], reverse=True
        ):
            text += f"{cat_names.get(cat, cat)}: {count}\n"

    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("disk"))
async def cmd_disk(message: types.Message):
    """Проверка места на диске"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    disk_info = check_disk_space()
    if disk_info:
        total_gb = disk_info["total"] / (1024**3)
        used_gb = disk_info["used"] / (1024**3)
        free_gb = disk_info["free"] / (1024**3)
        percent = disk_info["percent_used"]

        text = (
            f"💾 <b>Информация о диске</b>\n\n"
            f"📦 Всего: {total_gb:.2f} GB\n"
            f"📊 Использовано: {used_gb:.2f} GB ({percent:.1f}%)\n"
            f"🆓 Свободно: {free_gb:.2f} GB"
        )
        await message.answer(text, parse_mode=ParseMode.HTML)
    else:
        await message.answer("❌ Ошибка получения информации о диске")


@dp.message(Command("cleanup"))
async def cmd_cleanup(message: types.Message):
    """Автоматическая очистка старых файлов"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    await message.answer("🧹 Начинаю очистку...")

    deleted_photos = cleanup_old_files("/tmp", max_age_days=7, pattern="*.jpg")
    removed_dirs = remove_empty_directories("/tmp")

    text = (
        f"✅ <b>Очистка завершена</b>\n\n"
        f"🗑 Удалено фото: {deleted_photos}\n"
        f"📁 Удалено пустых папок: {removed_dirs}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("next"))
async def cmd_next(message: types.Message):
    """Показать следующие N товаров из очереди"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    args = message.text.split()
    limit = 5
    if len(args) > 1:
        try:
            limit = min(int(args[1]), 20)
        except ValueError:
            pass

    queue_items = db.get_queue_urls(limit=limit)
    if not queue_items:
        await message.answer("📭 Очередь пуста.")
        return

    text = f"📋 <b>Следующие {len(queue_items)} товаров:</b>\n\n"
    for i, (task_id, url) in enumerate(queue_items, 1):
        short_url = shorten_url(url, max_length=60)
        text += f"{i}. {short_url}\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Удалить первый", callback_data=f"remove_first"
                )
            ],
            [
                InlineKeyboardButton(
                    text="👁️ Предпросмотр первого", callback_data=f"preview_first"
                )
            ],
        ]
    )

    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@dp.message(Command("reload_config"))
async def cmd_reload_config(message: types.Message):
    """Перезагружает конфигурацию без перезапуска"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    try:
        from services.config_service import reload_settings

        reload_settings()
        await message.answer("✅ Конфигурация перезагружена!")
    except Exception as e:
        logger.exception("reload_config error: %s", e)
        await message.answer(f"❌ Ошибка перезагрузки: {str(e)[:200]}")


@dp.message(Command("health"))
async def cmd_health(message: types.Message):
    """Проверка здоровья бота"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    health_status = []

    # Проверка БД
    try:
        db.get_queue_count()
        health_status.append("✅ База данных")
    except (sqlite3.Error, AttributeError, Exception) as e:
        logger.debug(f"DB health check failed: {e}")
        health_status.append("❌ База данных")

    # Проверка бота
    try:
        await bot.get_me()
        health_status.append("✅ Telegram API")
    except (Exception, asyncio.TimeoutError) as e:
        logger.debug(f"Telegram API health check failed: {e}")
        health_status.append("❌ Telegram API")

    # Проверка места на диске
    disk_info = check_disk_space()
    if disk_info and disk_info.get("percent_used", 0) < 90:
        health_status.append("✅ Место на диске")
    else:
        health_status.append("⚠️ Мало места на диске")

    text = "🏥 <b>Проверка здоровья бота</b>\n\n" + "\n".join(health_status)
    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("batch"))
async def cmd_batch(message: types.Message):
    """Пакетная обработка товаров"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /batch <count> — обработать N товаров")
        return

    try:
        count = int(args[1])
        count = min(count, 10)  # Максимум 10 за раз
    except ValueError:
        await message.answer("❌ Неверное количество")
        return

    await message.answer(f"⚡ Обрабатываю {count} товаров...")

    processed = 0
    for _ in range(count):
        task = db.get_next_from_queue()
        if task:
            task_id, url = task
            success, _ = await process_and_publish(url, show_progress=False)
            if success:
                db.mark_as_done(task_id)
                processed += 1
            else:
                db.mark_as_error(task_id)
            await asyncio.sleep(2)  # Небольшая задержка между постами

    await message.answer(f"✅ Обработано: {processed} из {count}")


@dp.message(Command("search"))
async def cmd_search(message: types.Message):
    """Поиск товаров в истории"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /search <запрос>")
        return

    query = " ".join(args[1:]).lower()
    history = db.get_history(limit=100)

    results = []
    for item in history:
        title = (item.get("title", "") or "").lower()
        if query in title:
            results.append(item)

    if results:
        text = f"🔍 <b>Найдено {len(results)}:</b>\n\n"
        for i, item in enumerate(results[:10], 1):
            title = item.get("title", "Без названия")[:50]
            text += f"{i}. {title}\n🔗 {item.get('url', '')[:60]}...\n\n"
        await message.answer(text, parse_mode=ParseMode.HTML)
    else:
        await message.answer("📭 Ничего не найдено")


@dp.message(Command("duplicates"))
async def cmd_duplicates(message: types.Message):
    """Поиск дубликатов в очереди и истории (по URL, title, image hash)"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    await message.answer("🔍 Ищу дубликаты... Это может занять время.")

    # Поиск дубликатов в очереди
    queue_items = db.get_queue_urls(limit=1000)
    seen_urls = {}
    seen_normalized = {}
    duplicates_url = []
    duplicates_normalized = []

    for task_id, url in queue_items:
        normalized = db.normalize_url(url)

        # Точное совпадение URL
        if url in seen_urls:
            duplicates_url.append((task_id, url, seen_urls[url]))
        else:
            seen_urls[url] = task_id

        # Нормализованное совпадение
        if normalized in seen_normalized and normalized:
            duplicates_normalized.append((task_id, url, seen_normalized[normalized]))
        else:
            seen_normalized[normalized] = task_id

    # Поиск дубликатов по title в истории
    history = db.get_history(limit=500)
    seen_titles = {}
    duplicates_title = []

    for item in history:
        title = item.get("title", "").strip().lower()
        url = item.get("url", "")
        if title and len(title) > 5:  # Игнорируем слишком короткие названия
            if title in seen_titles:
                duplicates_title.append((url, title, seen_titles[title]))
            else:
                seen_titles[title] = url

    # Формируем ответ
    text = "🔍 <b>Поиск дубликатов</b>\n\n"

    if duplicates_url:
        text += f"⚠️ <b>Точные дубликаты URL ({len(duplicates_url)}):</b>\n"
        for task_id, url, original_id in duplicates_url[:5]:
            text += f"ID {task_id}: {url[:50]}...\n(оригинал: {original_id})\n\n"
        if len(duplicates_url) > 5:
            text += f"... и еще {len(duplicates_url) - 5} дубликатов\n\n"

    if duplicates_normalized:
        text += f"⚠️ <b>Дубликаты (нормализованные URL) ({len(duplicates_normalized)}):</b>\n"
        for task_id, url, original_id in duplicates_normalized[:5]:
            text += f"ID {task_id}: {url[:50]}...\n(оригинал: {original_id})\n\n"
        if len(duplicates_normalized) > 5:
            text += f"... и еще {len(duplicates_normalized) - 5} дубликатов\n\n"

    if duplicates_title:
        text += f"⚠️ <b>Дубликаты по названию ({len(duplicates_title)}):</b>\n"
        for url, title, original_url in duplicates_title[:5]:
            text += f"'{title[:40]}...'\n{url[:50]}...\n(оригинал: {original_url[:50]}...)\n\n"
        if len(duplicates_title) > 5:
            text += f"... и еще {len(duplicates_title) - 5} дубликатов\n\n"

    if not duplicates_url and not duplicates_normalized and not duplicates_title:
        text += "✅ Дубликатов не найдено"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Удалить дубликаты", callback_data="cmd_duplicates_remove"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню", callback_data="cmd_main_menu"
                )
            ],
        ]
    )

    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@dp.message(Command("schedule"))
async def cmd_schedule(message: types.Message):
    """Управление расписанием"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    text = (
        f"📅 <b>Текущее расписание</b>\n\n"
        f"⏰ Включено: {'Да' if settings.SCHEDULE_ENABLED else 'Нет'}\n"
        f"🕐 Часы: {settings.SCHEDULE_HOURS or 'Не задано'}\n"
        f"📆 Один в день: {'Да' if settings.SCHEDULE_ONE_PER_DAY else 'Нет'}\n"
        f"⏱ Интервал: {settings.POST_INTERVAL} сек"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("referral"))
async def cmd_referral(message: types.Message):
    """Получить товары с главной страницы"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    args = message.text.split()
    max_add = 20
    if len(args) > 1:
        try:
            max_add = min(int(args[1]), 50)
        except ValueError:
            pass

    await message.answer(f"🔗 Получаю товары с главной страницы...")

    try:
        from services.auto_search_service import AutoSearchService

        auto_search_service = AutoSearchService(db, bot)

        added = await auto_search_service.auto_add_products_from_main_page(
            max_add=max_add
        )

        total = db.get_queue_count()
        await message.answer(
            f"✅ <b>Товары с главной страницы</b>\n\n"
            f"➕ Добавлено товаров: {added}\n"
            f"📊 Всего в очереди: {total}\n\n"
            f"💡 Товары будут опубликованы автоматически",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.exception("referral error: %s", e)
        await message.answer(f"❌ Ошибка: {str(e)[:200]}")


@dp.message(Command("check_ref"))
async def cmd_check_ref(message: types.Message):
    """Проверка реферального кода и ссылок"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    # Проверяем REF_CODE из конфига
    ref_code = settings.REF_CODE or "НЕ УСТАНОВЛЕН"

    # Проверяем последние опубликованные ссылки
    history = db.get_history(limit=5)

    text = f"🔗 <b>Проверка реферальных ссылок</b>\n\n"
    text += f"📋 <b>REF_CODE в .env:</b> {ref_code}\n\n"

    if ref_code == "НЕ УСТАНОВЛЕН":
        text += "⚠️ <b>ВНИМАНИЕ!</b> REF_CODE не установлен в .env\n"
        text += "Добавьте в .env:\n"
        text += "<code>REF_CODE=cc/8BuJ7Z</code>\n\n"
    else:
        if ref_code.startswith("cc/"):
            text += (
                f"✅ Реферальный код в правильном формате: <code>{ref_code}</code>\n\n"
            )
        else:
            text += (
                f"⚠️ Реферальный код не в формате cc/XXXXX: <code>{ref_code}</code>\n\n"
            )

    # Проверяем последние ссылки
    if history:
        text += f"📊 <b>Последние 5 опубликованных ссылок:</b>\n\n"
        for idx, item in enumerate(history, 1):
            url = item.get("url", "")
            if "/cc/" in url:
                # Извлекаем код из ссылки
                code = url.split("/cc/")[-1].split("?")[0]
                if ref_code and ref_code.startswith("cc/"):
                    ref_code_clean = ref_code.replace("cc/", "")
                    if code == ref_code_clean:
                        status = "✅ ВАША"
                    else:
                        status = f"⚠️ ЧУЖАЯ (код: {code})"
                else:
                    status = f"🔗 Код: {code}"
                text += f"{idx}. {status}\n"
                text += f"   {url[:60]}...\n\n"
            else:
                text += f"{idx}. ⚠️ Длинная ссылка (не реферальная)\n"
                text += f"   {url[:60]}...\n\n"
    else:
        text += "📭 Нет опубликованных ссылок для проверки\n"

    # Проверяем очередь
    queue_items = db.get_queue_urls(limit=5)
    if queue_items:
        text += f"\n📋 <b>Следующие 5 ссылок в очереди:</b>\n\n"
        for idx, (task_id, url) in enumerate(queue_items, 1):
            if "/cc/" in url:
                code = url.split("/cc/")[-1].split("?")[0]
                if ref_code and ref_code.startswith("cc/"):
                    ref_code_clean = ref_code.replace("cc/", "")
                    if code == ref_code_clean:
                        status = "✅ ВАША"
                    else:
                        status = f"⚠️ ЧУЖАЯ (код: {code})"
                else:
                    status = f"🔗 Код: {code}"
                text += f"{idx}. {status}\n"
                text += f"   {url[:50]}...\n\n"

    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("log"))
async def cmd_log(message: types.Message):
    """Показывает последние важные логи"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    try:
        args = message.text.split()
        limit = 30
        if len(args) > 1:
            try:
                limit = min(int(args[1]), 100)  # Максимум 100 логов
            except ValueError:
                pass

        await message.answer("⏳ Загружаю логи...")

        # Получаем важные логи
        logs = log_service.get_important_logs(limit=limit)
        formatted = log_service.format_logs_for_message(logs, max_length=4000)

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 Обновить", callback_data="cmd_log_refresh"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="📋 Все логи (50)", callback_data="cmd_log_all_50"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="📋 Все логи (100)", callback_data="cmd_log_all_100"
                    )
                ],
            ]
        )

        await message.answer(
            formatted, reply_markup=keyboard, parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.exception("Error showing logs: %s", e)
        await message.answer(f"❌ Ошибка загрузки логов: {str(e)[:200]}")


@dp.callback_query(F.data.startswith("cmd_log_"))
async def handle_log_callback(callback: types.CallbackQuery):
    """Обработка callback для логов"""
    if callback.from_user.id != settings.ADMIN_ID:
        await callback.answer("❌ Нет прав.", show_alert=True)
        return

    command = callback.data.replace("cmd_log_", "")

    try:
        if command == "refresh":
            limit = 30
        elif command == "all_50":
            limit = 50
        elif command == "all_100":
            limit = 100
        else:
            limit = 30

        await callback.answer("⏳ Загружаю...", show_alert=False)

        # Получаем логи
        if "all" in command:
            logs = log_service.get_recent_logs(limit=limit, min_level="INFO")
        else:
            logs = log_service.get_important_logs(limit=limit)

        formatted = log_service.format_logs_for_message(logs, max_length=4000)

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 Обновить", callback_data="cmd_log_refresh"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="📋 Все логи (50)", callback_data="cmd_log_all_50"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="📋 Все логи (100)", callback_data="cmd_log_all_100"
                    )
                ],
            ]
        )

        await callback.message.edit_text(
            formatted, reply_markup=keyboard, parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.exception("Error handling log callback: %s", e)
        await callback.answer(f"❌ Ошибка: {str(e)[:200]}", show_alert=True)


@dp.message(Command("history"))
async def cmd_history(message: types.Message):
    """История публикаций"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    args = message.text.split()
    limit = 10
    if len(args) > 1:
        try:
            limit = min(int(args[1]), 50)
        except ValueError:
            pass

    history = db.get_history(limit=limit)
    if not history:
        await message.answer("📭 История пуста.")
        return

    text = f"📜 <b>История публикаций (последние {len(history)}):</b>\n\n"
    for idx, item in enumerate(history, 1):
        title = item.get("title", "Без названия")[:50]
        url = item.get("url", "")[:60]
        date = item.get("date", "")[:10] if item.get("date") else "Неизвестно"
        text += f"{idx}. <b>{title}</b>\n"
        text += f"   🔗 {url}...\n"
        text += f"   📅 {date}\n\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Больше (25)", callback_data="cmd_analytics_history_25"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📊 Больше (50)", callback_data="cmd_analytics_history_50"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню", callback_data="cmd_main_menu"
                )
            ],
        ]
    )
    await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


@dp.message(Command("export"))
async def cmd_export(message: types.Message):
    """Экспорт данных в JSON"""
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Нет прав.")
        return

    await message.answer("💾 Экспортирую данные...")

    try:
        import json
        from datetime import datetime

        stats = db.get_stats()
        queue_items = db.get_queue_urls(limit=1000)
        history_items = db.get_history(limit=1000)

        export_data = {
            "export_date": datetime.now().isoformat(),
            "statistics": stats,
            "queue_count": len(queue_items),
            "queue_items": [{"id": tid, "url": url} for tid, url in queue_items[:100]],
            "history_count": len(history_items),
            "history_items": history_items[:100],
        }

        export_file = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        await message.answer_document(
            document=types.FSInputFile(export_file),
            caption="💾 <b>Экспорт данных</b>\n\nСтатистика, очередь и история товаров",
            parse_mode=ParseMode.HTML,
        )

        if os.path.exists(export_file):
            os.remove(export_file)
    except Exception as e:
        logger.exception("Export error: %s", e)
        await message.answer(f"❌ Ошибка экспорта: {str(e)[:200]}")


@dp.message(Command("version"))
async def cmd_version(message: types.Message):
    """Версия бота и информация"""
    import sys
    import platform

    text = (
        f"ℹ️ <b>Информация о боте</b>\n\n"
        f"🐍 Python: {sys.version.split()[0]}\n"
        f"💻 Платформа: {platform.system()} {platform.release()}\n"
        f"📦 Версия бота: 2.0\n"
        f"📁 БД: {settings.DB_FILE}\n"
        f"📊 Канал: {settings.CHANNEL_ID}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


# ========== АДМИНКА - ОСНОВНЫЕ ФУНКЦИИ ==========


def create_admin_panel_keyboard() -> InlineKeyboardMarkup:
    """Создает главное меню админки"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Очередь", callback_data="cmd_admin_queue")],
            [
                InlineKeyboardButton(
                    text="📊 Аналитика", callback_data="cmd_admin_analytics"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📝 Контент", callback_data="cmd_admin_content"
                )
            ],
            [InlineKeyboardButton(text="⚙️ Система", callback_data="cmd_admin_system")],
            [
                InlineKeyboardButton(
                    text="🔧 Управление", callback_data="cmd_admin_management"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню", callback_data="cmd_main_menu"
                )
            ],
        ]
    )
    return keyboard


async def cmd_admin_panel_button(callback: types.CallbackQuery):
    """Обработчик кнопки Админка"""
    text = "🔐 <b>Админ-панель Yandex.Market бота</b>\n\n" "Выберите раздел:"
    keyboard = create_admin_panel_keyboard()
    from utils.safe_edit import safe_edit_callback_message

    await safe_edit_callback_message(
        callback, text, reply_markup=keyboard, parse_mode=ParseMode.HTML
    )


async def handle_admin_section(callback: types.CallbackQuery, command: str):
    """Обработка разделов админки"""
    if command == "admin_queue":
        await admin_queue_section(callback)
    elif command == "admin_analytics":
        await admin_analytics_section(callback)
    elif command == "admin_content":
        await admin_content_section(callback)
    elif command == "admin_system":
        await admin_system_section(callback)
    elif command == "admin_management":
        await admin_management_section(callback)


async def admin_queue_section(callback: types.CallbackQuery):
    """Раздел Очередь"""
    queue_count = db.get_queue_count()
    stats = db.get_stats()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Очистить очередь", callback_data="cmd_queue_clear"
                )
            ],
            [InlineKeyboardButton(text="❌ Удалить", callback_data="cmd_queue_remove")],
            [
                InlineKeyboardButton(
                    text="⏭ Следующие N", callback_data="cmd_queue_next"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔍 Поиск дубликатов", callback_data="cmd_queue_duplicates"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню", callback_data="cmd_main_menu"
                )
            ],
        ]
    )

    text = (
        "📋 <b>Очередь</b>\n\n"
        f"📊 Всего в очереди: {queue_count}\n"
        f"✅ Опубликовано: {stats.get('published', 0)}\n"
        f"❌ Ошибок: {stats.get('errors', 0)}\n"
        f"📅 Сегодня: {stats.get('today', 0)}\n\n"
        "Выберите действие:"
    )

    from utils.safe_edit import safe_edit_callback_message

    await safe_edit_callback_message(
        callback, text, reply_markup=keyboard, parse_mode=ParseMode.HTML
    )


async def handle_queue_action(callback: types.CallbackQuery, command: str):
    """Обработка действий с очередью"""
    if command == "queue_clear":
        count = db.get_queue_count()
        if count == 0:
            await callback.answer("⚠️ Очередь уже пуста", show_alert=True)
            return

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Подтвердить", callback_data="cmd_queue_clear_confirm"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отмена", callback_data="cmd_admin_queue"
                    )
                ],
            ]
        )

        await callback.message.edit_text(
            f"⚠️ <b>Подтверждение очистки</b>\n\n"
            f"Будет удалено <b>{count}</b> элементов из очереди.\n"
            f"Это действие нельзя отменить!",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    elif command == "queue_clear_confirm":
        count = db.clear_queue()
        logger.info(f"Admin {callback.from_user.id} cleared queue: {count} items")
        await callback.message.edit_text(
            f"✅ <b>Очередь очищена</b>\n\n" f"Удалено элементов: <b>{count}</b>",
            parse_mode=ParseMode.HTML,
        )
        await callback.answer("✅ Очередь очищена", show_alert=True)
    elif command == "queue_remove":
        # Используем существующую функцию cmd_remove_from_queue
        queue_items = db.get_queue_urls(limit=50)
        if not queue_items:
            await callback.answer("⚠️ Очередь пуста", show_alert=True)
            return

        keyboard = []
        for i in range(0, min(len(queue_items), 20), 2):
            row = []
            for j in range(2):
                if i + j < len(queue_items):
                    task_id, url = queue_items[i + j]
                    row.append(
                        InlineKeyboardButton(
                            text=f"❌ {i+j+1}", callback_data=f"remove_{task_id}"
                        )
                    )
            keyboard.append(row)

        # Кнопка "Удалить все"
        keyboard.append(
            [
                InlineKeyboardButton(
                    text="🗑 Удалить все", callback_data="cmd_queue_remove_all"
                )
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню", callback_data="cmd_main_menu"
                )
            ]
        )

        text = f"🗑️ <b>Удаление из очереди</b>\n\n"
        text += f"📊 Всего в очереди: {len(queue_items)}\n"
        text += f"👆 Выберите элемент для удаления:\n\n"

        for idx, (task_id, url) in enumerate(queue_items[:10], 1):
            short_url = url[:50] + "..." if len(url) > 50 else url
            text += f"{idx}. {short_url}\n"

        if len(queue_items) > 10:
            text += f"\n... и еще {len(queue_items) - 10} элементов"

        from utils.safe_edit import safe_edit_callback_message

        await safe_edit_callback_message(
            callback,
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode=ParseMode.HTML,
        )
    elif command == "queue_remove_all":
        count = db.get_queue_count()
        if count == 0:
            await callback.answer("⚠️ Очередь уже пуста", show_alert=True)
            return

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Подтвердить",
                        callback_data="cmd_queue_remove_all_confirm",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отмена", callback_data="cmd_queue_remove"
                    )
                ],
            ]
        )

        from utils.safe_edit import safe_edit_callback_message

        await safe_edit_callback_message(
            callback,
            f"⚠️ <b>Подтверждение удаления</b>\n\n"
            f"Будет удалено <b>все {count}</b> элементов из очереди.\n"
            f"Это действие нельзя отменить!",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    elif command == "queue_remove_all_confirm":
        count = db.clear_queue()
        logger.info(
            f"Admin {callback.from_user.id} removed all from queue: {count} items"
        )
        from utils.safe_edit import safe_edit_callback_message

        await safe_edit_callback_message(
            callback,
            f"✅ <b>Все элементы удалены</b>\n\n" f"Удалено элементов: <b>{count}</b>",
            parse_mode=ParseMode.HTML,
        )
        await callback.answer("✅ Все удалено", show_alert=True)
    elif command == "queue_next":
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="10", callback_data="cmd_queue_next_10")],
                [InlineKeyboardButton(text="25", callback_data="cmd_queue_next_25")],
                [InlineKeyboardButton(text="50", callback_data="cmd_queue_next_50")],
                [
                    InlineKeyboardButton(
                        text="🏠 Главное меню", callback_data="cmd_main_menu"
                    )
                ],
            ]
        )
        from utils.safe_edit import safe_edit_callback_message

        await safe_edit_callback_message(
            callback,
            "⏭ <b>Следующие N элементов</b>\n\n" "Выберите количество:",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    elif command.startswith("queue_next_"):
        n_str = command.replace("queue_next_", "")
        try:
            n = int(n_str)
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
                            text="🏠 Главное меню", callback_data="cmd_main_menu"
                        )
                    ]
                ]
            )
            await callback.message.edit_text(
                text, reply_markup=keyboard, parse_mode=ParseMode.HTML
            )
        except ValueError:
            await callback.answer("❌ Ошибка: неверное значение", show_alert=True)
    elif command == "queue_duplicates":
        await callback.answer("🔍 Ищу дубликаты...", show_alert=False)
        try:
            queue_items = db.get_queue_urls(limit=1000)

            url_counts = {}
            for task_id, url in queue_items:
                normalized = db.normalize_url(url)
                if normalized not in url_counts:
                    url_counts[normalized] = []
                url_counts[normalized].append((task_id, url))

            duplicates = {
                url: items for url, items in url_counts.items() if len(items) > 1
            }

            if not duplicates:
                text = "✅ <b>Дубликаты не найдены</b>\n\nВсе URL в очереди уникальны."
            else:
                total_duplicates = sum(len(items) - 1 for items in duplicates.values())
                text = f"🔍 <b>Найдено дубликатов: {len(duplicates)} групп</b>\n"
                text += f"📊 Всего повторяющихся записей: {total_duplicates}\n\n"

                for idx, (url_key, items) in enumerate(
                    list(duplicates.items())[:10], 1
                ):
                    # Берем первый URL для отображения
                    display_url = items[0][1]
                    short_url = (
                        display_url[:50] + "..."
                        if len(display_url) > 50
                        else display_url
                    )
                    text += f"{idx}. {short_url}\n"
                    text += f"   Повторений: {len(items)} (ID: {', '.join(str(tid) for tid, _ in items[:3])}"
                    if len(items) > 3:
                        text += f", ..."
                    text += ")\n\n"

                if len(duplicates) > 10:
                    text += f"... и еще {len(duplicates) - 10} групп дубликатов"

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🏠 Главное меню", callback_data="cmd_main_menu"
                        )
                    ]
                ]
            )
            await callback.message.edit_text(
                text, reply_markup=keyboard, parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.exception("Duplicates command error: %s", e)
            await callback.message.edit_text(
                f"❌ Ошибка поиска дубликатов: {str(e)[:200]}",
                parse_mode=ParseMode.HTML,
            )


async def admin_analytics_section(callback: types.CallbackQuery):
    """Раздел Аналитика"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Статистика", callback_data="cmd_analytics_stats"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📈 Детальная аналитика",
                    callback_data="cmd_analytics_detailed",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📉 Тренды", callback_data="cmd_analytics_trends"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📜 История", callback_data="cmd_analytics_history"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💾 Экспорт", callback_data="cmd_analytics_export"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню", callback_data="cmd_main_menu"
                )
            ],
        ]
    )

    text = "📊 <b>Аналитика</b>\n\nВыберите действие:"
    from utils.safe_edit import safe_edit_callback_message

    await safe_edit_callback_message(
        callback, text, reply_markup=keyboard, parse_mode=ParseMode.HTML
    )


async def admin_content_section(callback: types.CallbackQuery):
    """Раздел Контент"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💡 Идеи", callback_data="cmd_content_ideas")],
            [
                InlineKeyboardButton(
                    text="📦 Создать подборку", callback_data="cmd_content_compilation"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎲 Случайный товар", callback_data="cmd_content_random"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏷 Товары со скидкой", callback_data="cmd_content_discounts"
                )
            ],
            [InlineKeyboardButton(text="🔍 Поиск", callback_data="cmd_content_search")],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню", callback_data="cmd_main_menu"
                )
            ],
        ]
    )

    text = "📝 <b>Контент</b>\n\nВыберите действие:"
    from utils.safe_edit import safe_edit_callback_message

    await safe_edit_callback_message(
        callback, text, reply_markup=keyboard, parse_mode=ParseMode.HTML
    )


async def admin_system_section(callback: types.CallbackQuery):
    """Раздел Система"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статус", callback_data="cmd_system_status")],
            [
                InlineKeyboardButton(
                    text="❤️ Проверка здоровья", callback_data="cmd_system_health"
                )
            ],
            [InlineKeyboardButton(text="💿 Диск", callback_data="cmd_system_disk")],
            [
                InlineKeyboardButton(
                    text="🧹 Автоочистка", callback_data="cmd_system_cleanup"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⏰ Расписание", callback_data="cmd_system_schedule"
                )
            ],
            [InlineKeyboardButton(text="ℹ️ Версия", callback_data="cmd_system_version")],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню", callback_data="cmd_main_menu"
                )
            ],
        ]
    )

    text = "⚙️ <b>Система</b>\n\nВыберите действие:"
    from utils.safe_edit import safe_edit_callback_message

    await safe_edit_callback_message(
        callback, text, reply_markup=keyboard, parse_mode=ParseMode.HTML
    )


async def admin_management_section(callback: types.CallbackQuery):
    """Раздел Управление"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Перезапуск", callback_data="cmd_management_restart"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ Перезагрузить конфиг", callback_data="cmd_management_reload"
                )
            ],
            [InlineKeyboardButton(text="📋 Логи", callback_data="cmd_management_log")],
            [
                InlineKeyboardButton(
                    text="🚫 Черный список", callback_data="cmd_management_blacklist"
                )
            ],
            [InlineKeyboardButton(text="📱 QR-код", callback_data="cmd_management_qr")],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню", callback_data="cmd_main_menu"
                )
            ],
        ]
    )

    text = "🔧 <b>Управление</b>\n\nВыберите действие:"
    from utils.safe_edit import safe_edit_callback_message

    await safe_edit_callback_message(
        callback, text, reply_markup=keyboard, parse_mode=ParseMode.HTML
    )


async def handle_analytics_action(callback: types.CallbackQuery, command: str):
    """Обработка действий аналитики"""
    if command == "analytics_stats":
        # Краткая статистика
        stats = db.get_stats()
        queue_count = db.get_queue_count()
        text = (
            f"📊 <b>Статистика</b>\n\n"
            f"📋 В очереди: {queue_count}\n"
            f"✅ Опубликовано: {stats.get('published', 0)}\n"
            f"❌ Ошибок: {stats.get('errors', 0)}\n"
            f"📅 Сегодня: {stats.get('today', 0)}"
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🏠 Главное меню", callback_data="cmd_main_menu"
                    )
                ]
            ]
        )
        from utils.safe_edit import safe_edit_callback_message

        await safe_edit_callback_message(
            callback, text, reply_markup=keyboard, parse_mode=ParseMode.HTML
        )
        await callback.answer()
    elif command == "analytics_history":
        # Запрашиваем N для истории
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="10", callback_data="cmd_analytics_history_10"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="25", callback_data="cmd_analytics_history_25"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="50", callback_data="cmd_analytics_history_50"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🏠 Главное меню", callback_data="cmd_main_menu"
                    )
                ],
            ]
        )
        from utils.safe_edit import safe_edit_callback_message

        await safe_edit_callback_message(
            callback,
            "📜 <b>История публикаций</b>\n\n" "Выберите количество записей:",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        await callback.answer()
    elif command.startswith("analytics_history_"):
        # История публикаций
        n_str = command.replace("analytics_history_", "")
        try:
            n = int(n_str)
            # Получаем последние N публикаций из истории
            # Используем функцию из БД для получения истории
            try:
                history = db.get_history(limit=n)
                if history:
                    text = (
                        f"📜 <b>История публикаций (последние {len(history)}):</b>\n\n"
                    )
                    for idx, item in enumerate(history, 1):
                        url = item.get("url", "N/A")
                        date = item.get("date", "N/A")
                        title = (
                            item.get("title", "")[:40]
                            if item.get("title")
                            else "Без названия"
                        )
                        text += f"{idx}. {title}\n"
                        text += f"   📅 {date[:10] if len(str(date)) > 10 else date}\n"
                        text += f"   🔗 {url[:50]}...\n\n"
                else:
                    text = f"📜 <b>История публикаций</b>\n\nИстория пуста."
            except AttributeError:
                # Если функция get_history не существует, используем заглушку
                text = f"📜 <b>История публикаций (последние {n}):</b>\n\n"
                text += "Функция получения истории из БД будет реализована позже."

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🏠 Главное меню", callback_data="cmd_main_menu"
                        )
                    ]
                ]
            )
            from utils.safe_edit import safe_edit_callback_message

            await safe_edit_callback_message(
                callback, text, reply_markup=keyboard, parse_mode=ParseMode.HTML
            )
            await callback.answer()
        except ValueError:
            await callback.answer("❌ Ошибка: неверное значение", show_alert=True)
    elif command == "analytics_detailed":
        # Детальная аналитика
        await callback.answer("📈 Загружаю аналитику...", show_alert=False)

        try:
            from utils.safe_edit import safe_edit_callback_message

            stats = db.get_stats()
            queue_count = db.get_queue_count()

            # Получаем статистику через AnalyticsService
            daily_stats = analytics.get_daily_stats(days=7)
            category_stats = analytics.get_category_stats()
            price_ranges = analytics.get_price_range_stats()
            error_stats = analytics.get_error_stats()
            time_distribution = analytics.get_time_distribution(days=7)
            top_products = analytics.get_top_products(limit=5)

            text = "📈 <b>Детальная аналитика</b>\n\n"

            # Общая статистика
            text += f"📊 <b>Общая статистика:</b>\n"
            text += f"✅ Опубликовано всего: {stats.get('published', 0)}\n"
            text += f"📋 В очереди: {queue_count}\n"
            text += f"❌ Ошибок: {error_stats.get('total_errors', 0)}\n"
            text += f"📅 Сегодня: {stats.get('today', 0)}\n\n"

            # Последние 7 дней
            text += f"<b>📅 Последние 7 дней:</b>\n"
            for stat in daily_stats:
                date_str = stat["date"][:10] if len(stat["date"]) > 10 else stat["date"]
                text += f"• {date_str}: {stat['count']} постов\n"

            # Топ категорий
            if category_stats:
                text += f"\n<b>📂 Топ категорий:</b>\n"
                sorted_cats = sorted(
                    category_stats.items(), key=lambda x: x[1], reverse=True
                )
                total_cat = sum(category_stats.values())
                for cat, count in sorted_cats[:5]:
                    percentage = (count / total_cat * 100) if total_cat > 0 else 0
                    cat_name = {
                        "food": "🍫 Еда",
                        "tech": "📱 Техника",
                        "clothing": "👕 Одежда",
                        "toys": "🧸 Игрушки",
                        "other": "📦 Другое",
                    }.get(cat, cat)
                    text += f"• {cat_name}: {count} ({percentage:.1f}%)\n"

            # Ценовые диапазоны
            if any(price_ranges.values()):
                text += f"\n<b>💰 Ценовые диапазоны:</b>\n"
                total_prices = sum(price_ranges.values())
                for range_name, count in price_ranges.items():
                    if count > 0:
                        percentage = (
                            (count / total_prices * 100) if total_prices > 0 else 0
                        )
                        text += f"• {range_name}₽: {count} ({percentage:.1f}%)\n"

            # Распределение по времени
            peak_hours = sorted(
                time_distribution.items(), key=lambda x: x[1], reverse=True
            )[:3]
            if peak_hours and any(count > 0 for _, count in peak_hours):
                text += f"\n<b>⏰ Пиковые часы:</b>\n"
                for hour, count in peak_hours:
                    if count > 0:
                        text += f"• {hour}: {count} постов\n"

            # Топ товаров
            if top_products:
                text += f"\n<b>🔥 Топ товаров:</b>\n"
                for idx, product in enumerate(top_products[:3], 1):
                    title = (
                        product["title"][:30] if product["title"] else "Без названия"
                    )
                    text += f"{idx}. {title} ({product['count']} раз)\n"

            # Статистика ошибок
            if error_stats.get("by_reason"):
                text += f"\n<b>❌ Ошибки по типам:</b>\n"
                sorted_errors = sorted(
                    error_stats["by_reason"].items(), key=lambda x: x[1], reverse=True
                )
                for reason, count in sorted_errors[:3]:
                    text += f"• {reason[:40]}: {count}\n"

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💾 Экспорт", callback_data="cmd_analytics_export"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🔄 Обновить", callback_data="cmd_analytics_detailed"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🏠 Главное меню", callback_data="cmd_main_menu"
                        )
                    ],
                ]
            )
            await safe_edit_callback_message(
                callback, text, reply_markup=keyboard, parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.exception("Analytics error: %s", e)
            from utils.safe_edit import safe_edit_callback_message

            await safe_edit_callback_message(
                callback, f"❌ Ошибка: {str(e)[:200]}", parse_mode=ParseMode.HTML
            )
        await callback.answer()
    elif command == "analytics_trends":
        # Анализ трендов
        await callback.answer("📉 Анализирую тренды...", show_alert=False)

        try:
            # Получаем историю публикаций за последние 7 дней
            from datetime import datetime, timedelta

            stats = db.get_stats()

            # Анализ категорий (если есть в данных)
            queue_items = db.get_queue_urls(
                limit=500
            )  # Увеличили лимит для лучшей статистики
            categories = {}
            price_ranges = {"0-1000": 0, "1000-5000": 0, "5000-10000": 0, "10000+": 0}

            for task_id, url in queue_items:
                try:
                    data = db.get_cached_data(url, max_age_hours=168)
                    if data:
                        # Пытаемся определить категорию из URL или данных
                        category = "Другое"
                        title_lower = data.get("title", "").lower()
                        url_lower = url.lower()

                        if (
                            "smartphone" in url_lower
                            or "смартфон" in title_lower
                            or "iphone" in title_lower
                        ):
                            category = "Смартфоны"
                        elif (
                            "laptop" in url_lower
                            or "ноутбук" in title_lower
                            or "macbook" in title_lower
                        ):
                            category = "Ноутбуки"
                        elif (
                            "tablet" in url_lower
                            or "планшет" in title_lower
                            or "ipad" in title_lower
                        ):
                            category = "Планшеты"
                        elif (
                            "headphone" in url_lower
                            or "наушник" in title_lower
                            or "airpods" in title_lower
                        ):
                            category = "Наушники"
                        elif "tv" in url_lower or "телевизор" in title_lower:
                            category = "Телевизоры"
                        elif (
                            "watch" in url_lower
                            or "часы" in title_lower
                            or "apple watch" in title_lower
                        ):
                            category = "Часы"

                        categories[category] = categories.get(category, 0) + 1

                        # Анализ ценовых диапазонов
                        price_str = data.get("price", "")
                        if price_str and price_str != "Цена уточняется":
                            try:
                                from services.utils import extract_price_from_string

                                price = extract_price_from_string(price_str)
                                if price > 0:
                                    if price < 1000:
                                        price_ranges["0-1000"] += 1
                                    elif price < 5000:
                                        price_ranges["1000-5000"] += 1
                                    elif price < 10000:
                                        price_ranges["5000-10000"] += 1
                                    else:
                                        price_ranges["10000+"] += 1
                            except Exception:
                                pass
                except Exception as e:
                    logger.debug(f"Error processing trend data for {url[:50]}: {e}")
                    continue

            text = "📉 <b>Анализ трендов</b>\n\n"
            text += f"📊 Всего в очереди: {len(queue_items)}\n"
            text += f"✅ Опубликовано: {stats.get('published', 0)}\n"
            text += f"📅 Сегодня: {stats.get('today', 0)}\n\n"

            if categories:
                text += "<b>Популярные категории:</b>\n"
                sorted_cats = sorted(
                    categories.items(), key=lambda x: x[1], reverse=True
                )
                for cat, count in sorted_cats[:7]:
                    percentage = (count / len(queue_items) * 100) if queue_items else 0
                    text += f"• {cat}: {count} ({percentage:.1f}%)\n"

            if any(price_ranges.values()):
                text += "\n<b>Ценовые диапазоны:</b>\n"
                for range_name, count in price_ranges.items():
                    if count > 0:
                        percentage = (
                            (count / len(queue_items) * 100) if queue_items else 0
                        )
                        text += f"• {range_name}₽: {count} ({percentage:.1f}%)\n"

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🏠 Главное меню", callback_data="cmd_main_menu"
                        )
                    ]
                ]
            )
            from utils.safe_edit import safe_edit_callback_message

            await safe_edit_callback_message(
                callback, text, reply_markup=keyboard, parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.exception("Trends analysis error: %s", e)
            from utils.safe_edit import safe_edit_callback_message

            await safe_edit_callback_message(
                callback,
                f"❌ Ошибка анализа трендов: {str(e)[:200]}",
                parse_mode=ParseMode.HTML,
            )
        await callback.answer()
    elif command == "analytics_export":
        # Экспорт данных
        await callback.answer("💾 Экспортирую данные...", show_alert=False)

        try:
            import json
            from datetime import datetime

            stats = db.get_stats()
            queue_items = db.get_queue_urls(limit=1000)

            # Формируем данные для экспорта
            export_data = {
                "export_date": datetime.now().isoformat(),
                "statistics": stats,
                "queue_count": len(queue_items),
                "queue_items": [
                    {"id": tid, "url": url} for tid, url in queue_items[:100]
                ],
            }

            # Создаем временный файл
            export_file = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(export_file, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)

            # Отправляем файл
            await callback.message.answer_document(
                document=types.FSInputFile(export_file),
                caption="💾 <b>Экспорт данных</b>\n\nСтатистика и очередь товаров",
                parse_mode=ParseMode.HTML,
            )

            # Удаляем временный файл
            if os.path.exists(export_file):
                os.remove(export_file)

            await callback.answer("✅ Экспорт завершен", show_alert=True)
        except Exception as e:
            logger.exception("Export error: %s", e)
            from utils.safe_edit import safe_edit_callback_message

            await safe_edit_callback_message(
                callback,
                f"❌ Ошибка экспорта: {str(e)[:200]}",
                parse_mode=ParseMode.HTML,
            )
            await callback.answer()
    else:
        await callback.answer("⏳ В разработке", show_alert=True)


async def handle_content_action(callback: types.CallbackQuery, command: str):
    """Обработка действий контента"""
    if command == "content_search":
        # Запрашиваем запрос для поиска
        await callback.message.edit_text(
            "🔍 <b>Поиск товаров</b>\n\n" "Введите запрос для поиска:",
            parse_mode=ParseMode.HTML,
        )
        user_states[callback.from_user.id] = {
            "state": "waiting_search_query",
            "message_id": callback.message.message_id,
        }
        await callback.answer()
    elif command == "content_ideas":
        # Запрашиваем N для идей
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="5", callback_data="cmd_content_ideas_5")],
                [InlineKeyboardButton(text="10", callback_data="cmd_content_ideas_10")],
                [InlineKeyboardButton(text="20", callback_data="cmd_content_ideas_20")],
                [
                    InlineKeyboardButton(
                        text="🏠 Главное меню", callback_data="cmd_main_menu"
                    )
                ],
            ]
        )
        await callback.message.edit_text(
            "💡 <b>Идеи для контента</b>\n\n" "Выберите количество идей:",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        await callback.answer()
    elif command == "content_random":
        # Случайный товар из очереди
        try:
            queue_items = db.get_queue_urls(limit=1000)
            if not queue_items:
                await callback.answer("⚠️ Очередь пуста", show_alert=True)
                return

            import random

            task_id, url = random.choice(queue_items)

            # Пытаемся получить данные о товаре из кэша
            data = db.get_cached_data(url, max_age_hours=168)  # До 7 дней
            if data:
                title = data.get("title", "Без названия")
                price = data.get("price", "Цена уточняется")
                description = data.get("description", "")
                if description:
                    description = (
                        description[:100] + "..."
                        if len(description) > 100
                        else description
                    )
                text = f"🎲 <b>Случайный товар</b>\n\n" f"📌 {title}\n" f"💰 {price}\n"
                if description:
                    text += f"📝 {description}\n\n"
                text += f"🔗 {url}"
            else:
                text = f"🎲 <b>Случайный товар</b>\n\n🔗 {url}\n\n<i>Данные о товаре не найдены в кэше</i>"

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="📝 Опубликовать",
                            callback_data=f"cmd_post_now_{task_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🎲 Еще один", callback_data="cmd_content_random"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🏠 Главное меню", callback_data="cmd_main_menu"
                        )
                    ],
                ]
            )
            await callback.message.edit_text(
                text, reply_markup=keyboard, parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.exception("Random command error: %s", e)
            await callback.message.edit_text(
                f"❌ Ошибка получения случайного товара: {str(e)[:200]}",
                parse_mode=ParseMode.HTML,
            )
        await callback.answer()

    elif command == "content_discounts":
        # Товары со скидкой
        await callback.answer("🔍 Ищу товары со скидкой...", show_alert=False)

        try:
            queue_items = db.get_queue_urls(limit=1000)
            discounts_found = []

            for task_id, url in queue_items:
                try:
                    data = db.get_cached_data(url, max_age_hours=168)
                    if data:
                        discount = extract_discount_from_data(data)
                        if discount > 0:
                            discounts_found.append((task_id, url, data, discount))
                except Exception as e:
                    logger.debug(f"Error processing discount for {url[:50]}: {e}")
                    continue

            if not discounts_found:
                text = "🏷 <b>Товары со скидкой</b>\n\nТовары со скидкой не найдены в очереди."
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🏠 Главное меню", callback_data="cmd_main_menu"
                            )
                        ]
                    ]
                )
            else:
                # Сортируем по размеру скидки
                discounts_found.sort(key=lambda x: x[3], reverse=True)
                text = f"🏷 <b>Товары со скидкой ({len(discounts_found)}):</b>\n\n"

                for idx, (task_id, url, data, discount) in enumerate(
                    discounts_found[:10], 1
                ):
                    title = data.get("title", "Без названия")[:40]
                    price = data.get("price", "Цена уточняется")
                    text += f"{idx}. {title}\n"
                    text += f"   💰 {price} (-{discount}%)\n"
                    text += f"   🔗 {url[:50]}...\n\n"

                if len(discounts_found) > 10:
                    text += f"... и еще {len(discounts_found) - 10} товаров"

                # Добавляем кнопки для публикации топ-3 товаров со скидкой
                keyboard_buttons = []
                for idx, (task_id, url, data, discount) in enumerate(
                    discounts_found[:3], 1
                ):
                    title_short = data.get("title", "Товар")[:30]
                    keyboard_buttons.append(
                        [
                            InlineKeyboardButton(
                                text=f"📝 Опубликовать #{idx} (-{discount}%)",
                                callback_data=f"cmd_post_now_{task_id}",
                            )
                        ]
                    )
                keyboard_buttons.append(
                    [
                        InlineKeyboardButton(
                            text="🏠 Главное меню", callback_data="cmd_main_menu"
                        )
                    ]
                )
                keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

            await callback.message.edit_text(
                text, reply_markup=keyboard, parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.exception("Discounts command error: %s", e)
            await callback.message.edit_text(
                f"❌ Ошибка поиска товаров со скидкой: {str(e)[:200]}",
                parse_mode=ParseMode.HTML,
            )
        await callback.answer()
    elif command == "content_compilation":
        # Создание подборки - запрашиваем параметры
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="5 товаров", callback_data="cmd_content_compilation_5"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="10 товаров", callback_data="cmd_content_compilation_10"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="20 товаров", callback_data="cmd_content_compilation_20"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🏠 Главное меню", callback_data="cmd_main_menu"
                    )
                ],
            ]
        )
        await callback.message.edit_text(
            "📦 <b>Создать подборку</b>\n\n" "Выберите количество товаров:",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        await callback.answer()

    elif command.startswith("content_ideas_"):
        # Идеи для контента
        n_str = command.replace("content_ideas_", "")
        try:
            n = int(n_str)
            await callback.answer("💡 Генерирую идеи...", show_alert=False)

            # Используем сервис генерации идей
            try:
                # from services.content_service import generate_ideas
                # ideas = generate_ideas(n)  # Не async функция - function doesn't exist
                if ideas:
                    text = f"💡 <b>Идеи для контента ({len(ideas)}):</b>\n\n"
                    for idx, idea in enumerate(ideas, 1):
                        text += f"{idx}. {idea}\n\n"
                else:
                    text = "💡 <b>Идеи для контента</b>\n\nИдеи не найдены. Попробуйте позже."
            except Exception as e:
                logger.exception("Ideas generation error: %s", e)
                text = (
                    f"💡 <b>Идеи для контента</b>\n\nОшибка генерации: {str(e)[:200]}"
                )

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🏠 Главное меню", callback_data="cmd_main_menu"
                        )
                    ]
                ]
            )
            await callback.message.edit_text(
                text, reply_markup=keyboard, parse_mode=ParseMode.HTML
            )
        except ValueError:
            await callback.answer("❌ Ошибка: неверное значение", show_alert=True)

    elif command.startswith("content_compilation_"):
        # Создание подборки из N товаров
        n_str = command.replace("content_compilation_", "")
        try:
            n = int(n_str)
            if n <= 0 or n > 50:
                await callback.answer(
                    "❌ Количество должно быть от 1 до 50", show_alert=True
                )
                return

            queue_items = db.get_queue_urls(limit=n * 2)  # Берем больше для фильтрации

            if not queue_items:
                await callback.answer("⚠️ Очередь пуста", show_alert=True)
                return

            # Фильтруем товары с данными и берем первые N
            items_with_data = []
            for task_id, url in queue_items:
                try:
                    data = db.get_cached_data(url, max_age_hours=168)
                    if data and data.get("title"):
                        items_with_data.append((task_id, url, data))
                        if len(items_with_data) >= n:
                            break
                except Exception:
                    continue

            if not items_with_data:
                await callback.answer(
                    "⚠️ Не найдено товаров с данными в кэше", show_alert=True
                )
                return

            # Формируем подборку
            compilation_text = (
                f"📦 <b>Подборка из {len(items_with_data)} товаров:</b>\n\n"
            )

            for idx, (task_id, url, data) in enumerate(items_with_data, 1):
                title = data.get("title", "Без названия")[:50]
                price = data.get("price", "Цена уточняется")
                compilation_text += f"{idx}. <b>{title}</b>\n"
                compilation_text += f"   💰 {price}\n"
                compilation_text += f'   🔗 <a href="{url}">{url[:50]}...</a>\n\n'

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🏠 Главное меню", callback_data="cmd_main_menu"
                        )
                    ]
                ]
            )
            await callback.message.edit_text(
                compilation_text, reply_markup=keyboard, parse_mode=ParseMode.HTML
            )
            await callback.answer()
        except ValueError:
            await callback.answer("❌ Ошибка: неверное значение", show_alert=True)
        except Exception as e:
            logger.exception("Compilation command error: %s", e)
            await callback.message.edit_text(
                f"❌ Ошибка создания подборки: {str(e)[:200]}",
                parse_mode=ParseMode.HTML,
            )
            await callback.answer()
            await callback.answer()
        except ValueError:
            await callback.answer("❌ Ошибка: неверное значение", show_alert=True)
    else:
        await callback.answer("⏳ В разработке", show_alert=True)


async def handle_system_action(callback: types.CallbackQuery, command: str):
    """Обработка действий системы"""
    global_settings = get_global_settings()

    if command == "system_toggle_autopublish":
        # Переключение автопубликации
        current = global_settings.get_auto_publish_enabled()
        global_settings.set_auto_publish_enabled(not current)
        new_value = global_settings.get_auto_publish_enabled()
        status = "включена" if new_value else "выключена"
        icon = "✅" if new_value else "❌"

        logger.info(f"Admin {callback.from_user.id} toggled autopublish: {status}")

        # Вычисляем следующее время публикации
        next_time = "сразу" if new_value else "не запланировано"
        schedule_settings = global_settings.get_schedule_settings()
        if new_value and schedule_settings.get("enabled"):
            from datetime import datetime, timedelta

            now = datetime.now()
            schedule_hours = schedule_settings.get("hours", [])
            if schedule_hours:
                next_hour = min(
                    [h for h in schedule_hours if h > now.hour],
                    default=schedule_hours[0],
                )
                if next_hour <= now.hour:
                    next_time = f"завтра в {next_hour:02d}:00"
                else:
                    next_time = f"сегодня в {next_hour:02d}:00"

        await callback.message.edit_text(
            f"{icon} <b>Автопубликация {status}</b>\n\n"
            f"Следующее выполнение: {next_time}",
            parse_mode=ParseMode.HTML,
        )
        await callback.answer(f"Автопубликация {status}", show_alert=True)

        # Возвращаемся в раздел системы
        await asyncio.sleep(2)
        await admin_system_section(callback)

    elif command == "system_schedule":
        # Настройка расписания
        await show_schedule_settings(callback)

    elif command == "system_status":
        # Статус системы
        await cmd_status_button(callback)

    elif command == "system_health":
        # Проверка здоровья
        try:
            import psutil

            cpu = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            text = (
                f"❤️ <b>Проверка здоровья</b>\n\n"
                f"💻 CPU: {cpu}%\n"
                f"💾 Память: {memory.percent}% ({memory.used / 1024**3:.1f} GB / {memory.total / 1024**3:.1f} GB)\n"
                f"💿 Диск: {disk.percent}% ({disk.used / 1024**3:.1f} GB / {disk.total / 1024**3:.1f} GB)\n\n"
                f"🤖 Автопубликация: {'✅ Включена' if global_settings.get_auto_publish_enabled() else '❌ Выключена'}\n"
                f"📋 В очереди: {db.get_queue_count()}"
            )
        except ImportError:
            text = (
                f"❤️ <b>Проверка здоровья</b>\n\n"
                f"🤖 Автопубликация: {'✅ Включена' if global_settings.get_auto_publish_enabled() else '❌ Выключена'}\n"
                f"📋 В очереди: {db.get_queue_count()}\n\n"
                f"💡 Установите psutil для детальной статистики"
            )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🏠 Главное меню", callback_data="cmd_main_menu"
                    )
                ]
            ]
        )
        await callback.message.edit_text(
            text, reply_markup=keyboard, parse_mode=ParseMode.HTML
        )
        await callback.answer()

    elif command == "system_disk":
        # Информация о диске
        try:
            from services.file_service import check_disk_space, get_directory_size

            disk_info = check_disk_space()
            text = f"💿 <b>Диск</b>\n\n{disk_info}"
        except (ImportError, AttributeError, Exception) as e:
            logger.debug(f"Failed to get disk info: {e}")
            text = "💿 <b>Диск</b>\n\nИнформация недоступна"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🏠 Главное меню", callback_data="cmd_main_menu"
                    )
                ]
            ]
        )
        await callback.message.edit_text(
            text, reply_markup=keyboard, parse_mode=ParseMode.HTML
        )
        await callback.answer()

    elif command == "system_cleanup":
        # Автоочистка
        try:
            from services.file_service import cleanup_old_files

            cleaned = cleanup_old_files()
            text = f"🧹 <b>Автоочистка</b>\n\nОчищено файлов: {cleaned}"
        except (ImportError, AttributeError, Exception) as e:
            logger.debug(f"Failed to cleanup: {e}")
            text = "🧹 <b>Автоочистка</b>\n\nОшибка при очистке"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🏠 Главное меню", callback_data="cmd_main_menu"
                    )
                ]
            ]
        )
        await callback.message.edit_text(
            text, reply_markup=keyboard, parse_mode=ParseMode.HTML
        )
        await callback.answer()

    elif command == "system_version":
        # Версия
        import sys, platform

        text = (
            f"ℹ️ <b>Версия</b>\n\n"
            f"🐍 Python: {sys.version.split()[0]}\n"
            f"💻 Платформа: {platform.system()} {platform.release()}\n"
            f"📦 Версия бота: 2.0\n"
            f"📁 БД: {settings.DB_FILE}\n"
            f"📊 Канал: {settings.CHANNEL_ID}"
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🏠 Главное меню", callback_data="cmd_main_menu"
                    )
                ]
            ]
        )
        await callback.message.edit_text(
            text, reply_markup=keyboard, parse_mode=ParseMode.HTML
        )
        await callback.answer()

    else:
        await callback.answer("⏳ В разработке", show_alert=True)


async def show_schedule_settings(callback: types.CallbackQuery):
    """Показ настроек расписания"""
    global_settings = get_global_settings()
    schedule_settings = global_settings.get_schedule_settings()

    enabled = schedule_settings.get("enabled", False)
    hours = schedule_settings.get("hours", [])
    one_per_day = schedule_settings.get("one_per_day", False)
    interval = schedule_settings.get("interval", settings.POST_INTERVAL)

    hours_text = (
        ", ".join([f"{h:02d}:00" for h in sorted(hours)]) if hours else "Не задано"
    )
    interval_text = (
        f"{interval // 60} мин" if interval < 3600 else f"{interval // 3600} ч"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{'✅' if enabled else '❌'} Включить/Выключить",
                    callback_data="cmd_schedule_toggle",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⏰ Настроить часы", callback_data="cmd_schedule_hours"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"{'✅' if one_per_day else '❌'} Один в день",
                    callback_data="cmd_schedule_one_per_day",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⏱ Настроить интервал", callback_data="cmd_schedule_interval"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💾 Сохранить", callback_data="cmd_schedule_save"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню", callback_data="cmd_main_menu"
                )
            ],
        ]
    )

    text = (
        "⏰ <b>Настройка расписания</b>\n\n"
        f"📅 Включено: {'✅ Да' if enabled else '❌ Нет'}\n"
        f"🕐 Часы: {hours_text}\n"
        f"📆 Один в день: {'✅ Да' if one_per_day else '❌ Нет'}\n"
        f"⏱ Интервал: {interval_text}\n\n"
        "Выберите параметр для настройки:"
    )

    await callback.message.edit_text(
        text, reply_markup=keyboard, parse_mode=ParseMode.HTML
    )
    await callback.answer()


async def handle_schedule_action(callback: types.CallbackQuery, command: str):
    """Обработка действий расписания"""
    global_settings = get_global_settings()

    if command == "schedule_toggle":
        schedule_settings = global_settings.get_schedule_settings()
        new_enabled = not schedule_settings.get("enabled", False)
        global_settings.update_schedule_settings(enabled=new_enabled)
        await show_schedule_settings(callback)

    elif command == "schedule_one_per_day":
        schedule_settings = global_settings.get_schedule_settings()
        new_one_per_day = not schedule_settings.get("one_per_day", False)
        global_settings.update_schedule_settings(one_per_day=new_one_per_day)
        await show_schedule_settings(callback)

    elif command == "schedule_hours":
        # Запрашиваем часы для настройки
        await callback.message.edit_text(
            "⏰ <b>Настройка часов</b>\n\n"
            "Введите часы через запятую (например: 9,12,15,18):",
            parse_mode=ParseMode.HTML,
        )
        user_states[callback.from_user.id] = {
            "state": "waiting_schedule_hours",
            "message_id": callback.message.message_id,
        }
        await callback.answer()

    elif command == "schedule_interval":
        # Запрашиваем интервал
        await callback.message.edit_text(
            "⏱ <b>Настройка интервала</b>\n\n"
            "Введите интервал в секундах (например: 3600 для 1 часа):",
            parse_mode=ParseMode.HTML,
        )
        user_states[callback.from_user.id] = {
            "state": "waiting_schedule_interval",
            "message_id": callback.message.message_id,
        }
        await callback.answer()

    elif command == "schedule_save":
        # Сохранение настроек
        schedule_settings = global_settings.get_schedule_settings()
        logger.info(
            f"Admin {callback.from_user.id} saved schedule settings: {schedule_settings}"
        )
        await callback.message.edit_text(
            "✅ <b>Настройки расписания сохранены</b>\n\n"
            "Изменения вступят в силу немедленно.",
            parse_mode=ParseMode.HTML,
        )
        await callback.answer("✅ Сохранено", show_alert=True)
        await asyncio.sleep(2)
        await show_schedule_settings(callback)


async def handle_management_action(callback: types.CallbackQuery, command: str):
    """Обработка действий управления"""
    if command == "management_qr":
        # Запрашиваем URL для QR-кода
        await callback.message.edit_text(
            "📱 <b>Генерация QR-кода</b>\n\n" "Введите URL для генерации QR-кода:",
            parse_mode=ParseMode.HTML,
        )
        # Устанавливаем состояние ожидания URL
        user_states[callback.from_user.id] = {
            "state": "waiting_qr_url",
            "message_id": callback.message.message_id,
        }
        await callback.answer()
    elif command == "management_log":
        await cmd_log_button(callback)
    elif command == "management_restart":
        await cmd_restart_button(callback)
    elif command == "management_blacklist":
        # Показываем черный список
        blacklist = db.get_blacklist()
        if not blacklist:
            text = "🚫 <b>Черный список пуст</b>"
        else:
            text = f"🚫 <b>Черный список ({len(blacklist)}):</b>\n\n"
            for idx, item in enumerate(blacklist[:10], 1):
                text += f"{idx}. {item['url'][:50]}...\n"
                if item.get("reason"):
                    text += f"   Причина: {item['reason']}\n"
                text += "\n"
            if len(blacklist) > 10:
                text += f"... и еще {len(blacklist) - 10} элементов"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🏠 Главное меню", callback_data="cmd_main_menu"
                    )
                ]
            ]
        )
        await callback.message.edit_text(
            text, reply_markup=keyboard, parse_mode=ParseMode.HTML
        )
        await callback.answer()
    elif command == "management_reload":
        # Перезагрузка конфига
        await callback.answer("⚙️ Перезагружаю конфиг...", show_alert=False)
        try:
            from services.config_service import reload_settings

            reload_settings()
            text = "✅ <b>Конфигурация перезагружена!</b>\n\nИзменения применены."
        except ImportError:
            # Если сервис не существует, пробуем перезагрузить config напрямую
            import importlib
            import config

            importlib.reload(config)
            text = (
                "✅ <b>Конфигурация перезагружена!</b>\n\nМодуль config перезагружен."
            )
        except Exception as e:
            logger.exception("reload_config error: %s", e)
            text = f"❌ <b>Ошибка перезагрузки:</b>\n{str(e)[:200]}"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🏠 Главное меню", callback_data="cmd_main_menu"
                    )
                ]
            ]
        )
        await callback.message.edit_text(
            text, reply_markup=keyboard, parse_mode=ParseMode.HTML
        )
        await callback.answer()
    else:
        await callback.answer("⏳ В разработке", show_alert=True)


# --- Run ---
async def main():
    # Track background tasks for graceful shutdown
    background_tasks = []

    # Track services that need cleanup
    services_to_cleanup = []

    # Services are now initialized at module level as singletons

    try:
        logger.info("🚀 Запуск бота...")

        # Настройка middleware для dependency injection
        from middlewares.db_middleware import DatabaseMiddleware
        from middlewares.http_client_middleware import HttpClientMiddleware

        dp.update.middleware(DatabaseMiddleware(db))
        dp.update.middleware(HttpClientMiddleware(http_client))

        logger.info("✅ Middleware настроены")

        # Проверяем, нужно ли использовать webhook
        if settings.USE_WEBHOOK and settings.WEBHOOK_URL:
            # Устанавливаем webhook
            logger.info(
                f"🔗 Установка webhook: {settings.WEBHOOK_URL}{settings.WEBHOOK_PATH}"
            )
            await bot.set_webhook(
                url=f"{settings.WEBHOOK_URL}{settings.WEBHOOK_PATH}",
                drop_pending_updates=True,
            )
            logger.info("✅ Webhook установлен")
            logger.info(
                f"📡 Webhook URL: {settings.WEBHOOK_URL}{settings.WEBHOOK_PATH}"
            )
            logger.warning(
                "⚠️ Для работы webhook нужен запущенный сервер (например, через aiogram webhook server)"
            )
        else:
            # Используем polling
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("✅ Webhook удален, используется polling")

        # Запускаем AI воркер
        try:
            from services.ai_worker import get_ai_worker

            ai_worker = get_ai_worker()
            await ai_worker.start()
            services_to_cleanup.append(ai_worker)
            logger.info("AI worker started")
        except Exception as e:
            logger.warning(f"Failed to start AI worker: {e}")

        # Инициализируем AI content service (Groq)
        try:
            from services.ai_content_service import init_ai_content_service

            # Try to get GROQ API key from environment or use hardcoded value
            groq_api_key = os.getenv("GROQ_API_KEY") or "your_groq_api_key_here"

            init_ai_content_service(groq_api_key)
            if groq_api_key:
                logger.info("✅ AI content service (Groq) initialized")
            else:
                logger.warning("⚠️ No GROQ_API_KEY found - AI descriptions will use fallback")
        except Exception as e:
            logger.warning(f"Failed to initialize AI content service: {e}")

        # Запускаем автопубликацию
        queue_task = asyncio.create_task(queue_worker(db, http_client))
        background_tasks.append(queue_task)
        logger.info("✅ Queue worker запущен (автопубликация включена)")

        # Настраиваем планировщик для автопоиска
        global global_scheduler
        global_scheduler = AsyncIOScheduler()
        AUTO_SEARCH_ENABLED = os.getenv("AUTO_SEARCH_ENABLED", "True").lower() in (
            "1",
            "true",
            "yes",
        )
        AUTO_MAIN_PAGE_ENABLED = os.getenv(
            "AUTO_MAIN_PAGE_ENABLED", "True"
        ).lower() in ("1", "true", "yes")

        if AUTO_SEARCH_ENABLED or AUTO_MAIN_PAGE_ENABLED:
            # Используем APScheduler с простым interval заданием
            from services.auto_search_service import AutoSearchService

            auto_search_service = AutoSearchService(db, bot)

            # Простое interval задание согласно требованиям
            global_scheduler.add_job(
                auto_search_service.run_search_and_queue,
                'interval',
                seconds=int(os.getenv("AUTO_SEARCH_INTERVAL", 3600)),  # Default: 1 hour
                args=[bot]  # Remove config from args as it's not needed
            )

            logger.info("✅ Auto search scheduler настроен (interval режим)")
        else:
            logger.info(
                "ℹ️ Автопоиск отключен (AUTO_SEARCH_ENABLED и AUTO_MAIN_PAGE_ENABLED)"
            )

        # Запускаем планировщик
        global_scheduler.start()
        services_to_cleanup.append(global_scheduler)

        # Запускаем сервис автоматизации
        try:
            from services.automation_service import get_automation_service

            automation = get_automation_service(db, bot)
            await automation.start()
            services_to_cleanup.append(automation)
            logger.info("✅ Automation service started")
        except Exception as e:
            logger.warning(f"⚠️ Failed to start automation service: {e}")

        # Запускаем сервис резервного копирования (каждые 24 часа)
        if settings.ADMIN_ID:
            try:
                from services.backup_service import backup_worker

                backup_task = asyncio.create_task(
                    backup_worker(
                        settings.ADMIN_ID, bot, settings.DB_FILE, interval_hours=24
                    )
                )
                background_tasks.append(backup_task)
                logger.info(
                    "✅ Backup worker запущен (резервное копирование каждые 24 часа)"
                )
            except Exception as e:
                logger.warning(f"⚠️ Failed to start backup worker: {e}")

        # Запускаем сервис очистки старых постов с мертвыми ссылками (каждые 24 часа)
        try:
            from services.cleanup_service import cleanup_worker

            cleanup_task = asyncio.create_task(
                cleanup_worker(
                    db, bot, settings.CHANNEL_ID, interval_hours=24, hours_threshold=48
                )
            )
            background_tasks.append(cleanup_task)
            logger.info(
                "✅ Cleanup worker запущен (очистка старых постов каждые 24 часа)"
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to start cleanup worker: {e}")

        # Запускаем сервис очистки распроданных товаров (опционально)
        CLEANER_ENABLED = os.getenv("CLEANER_ENABLED", "True").lower() in (
            "1",
            "true",
            "yes",
        )
        if CLEANER_ENABLED:
            try:
                from services.cleaner_service import CleanerService

                cleaner = CleanerService(db=db, bot=bot)
                cleaner_interval = int(os.getenv("CLEANER_INTERVAL_HOURS", "6"))
                cleaner_task = asyncio.create_task(
                    cleaner.run_periodic_cleanup(
                        interval_hours=cleaner_interval,
                        check_hours=48,
                        delete_messages=True,
                    )
                )
                background_tasks.append(cleaner_task)
                logger.info(
                    f"✅ Sold-out cleaner запущен (проверка каждые {cleaner_interval} часов)"
                )
            except Exception as e:
                logger.warning(f"⚠️ Failed to start sold-out cleaner: {e}")
        else:
            logger.info(
                "ℹ️ Sold-out cleaner отключен (установите CLEANER_ENABLED=True в .env для включения)"
            )

        logger.info("✅ Бот запущен и готов к работе!")

        logger.info("✅ Бот запущен и готов к работе!")
        logger.info("📊 Текущая очередь: %d товаров", db.get_queue_count())

        try:
            # Запускаем polling или webhook сервер
            if settings.USE_WEBHOOK and settings.WEBHOOK_URL:
                # Для webhook нужен отдельный сервер (например, через aiogram webhook server)
                # Здесь просто запускаем polling как fallback
                logger.warning(
                    "⚠️ Webhook режим требует отдельного сервера. Запускаем polling..."
                )
                await dp.start_polling(bot)
            else:
                await dp.start_polling(bot)
        except KeyboardInterrupt:
            logger.info("🛑 Получен KeyboardInterrupt, начинаем graceful shutdown...")
        finally:
            # Graceful shutdown sequence
            logger.info("🔄 Начинаем graceful shutdown...")

            # 1. Cancel all background tasks
            logger.info("🛑 Отменяем фоновые задачи...")
            for task in background_tasks:
                if not task.done():
                    task.cancel()

            # Wait for background tasks to complete
            try:
                await asyncio.gather(*background_tasks, return_exceptions=True)
                logger.info("✅ Фоновые задачи остановлены")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при остановке фоновых задач: {e}")

            # 2. Stop services that have cleanup methods
            logger.info("🛑 Останавливаем сервисы...")
            for service in services_to_cleanup:
                try:
                    if hasattr(service, "stop"):
                        await service.stop()
                        logger.info(f"✅ Сервис {type(service).__name__} остановлен")
                    else:
                        logger.warning(
                            f"⚠️ Сервис {type(service).__name__} не имеет метода stop"
                        )
                except Exception as e:
                    logger.warning(
                        f"⚠️ Ошибка при остановке сервиса {type(service).__name__}: {e}"
                    )

            # 3. Close HTTP client sessions
            logger.info("🔌 Закрываем HTTP соединения...")
            try:
                from services.http_client import HTTPClient

                # Get existing HTTPClient instance if available, otherwise create new one
                # Note: In a production app, you'd want to maintain a global instance
                http_client_cleanup = HTTPClient()
                await http_client_cleanup.close()
                logger.info("✅ HTTP клиент закрыт")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при закрытии HTTP клиента: {e}")

            # 4. Close database connection
            logger.info("💾 Закрываем соединение с базой данных...")
            try:
                if hasattr(db, "connection") and db.connection:
                    db.connection.close()
                    logger.info("✅ Соединение с БД закрыто")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при закрытии соединения с БД: {e}")

            # 5. Log final metrics
            try:
                from services.metrics import Metrics

                metrics = Metrics()
                metrics.log_summary()
                logger.info("✅ Метрики сохранены")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при логировании метрик: {e}")

            logger.info("✅ Bot stopped safely")
    except Exception as e:
        logger.exception("❌ Критическая ошибка при запуске: %s", e)
        print(f"\n[ERROR] Startup failed: {e}")
        print("\nПроверьте:")
        print("1. Файл .env существует и содержит BOT_TOKEN")
        print("2. BOT_TOKEN правильный")
        print("3. Интернет подключен")
        input("\nНажмите Enter для выхода...")
        raise


if __name__ == "__main__":
    import sys
    import traceback
    import io

    # Исправляем кодировку для Windows
    if sys.platform == "win32":
        try:
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace"
            )
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer, encoding="utf-8", errors="replace"
            )
        except Exception:
            pass  # Если не удалось, продолжаем как есть

    try:
        print("=" * 50)
        print("🚀 Запуск YandexMarketBot")
        print("=" * 50)

        # Проверяем наличие .env перед запуском
        if getattr(sys, "frozen", False):
            appdata_dir = os.path.join(os.getenv("APPDATA"), "YandexMarketBot")
            env_path = os.path.join(appdata_dir, ".env")
            print(f"📁 Режим: EXE")
            print(f"📁 AppData: {appdata_dir}")
        else:
            env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
            print(f"📁 Режим: Python скрипт")

        print(f"🔍 Проверка .env: {env_path}")

        if not os.path.exists(env_path):
            print(f"\n❌ ОШИБКА: Файл .env не найден!")
            print(f"   Ожидаемый путь: {env_path}")
            print("\nСоздайте файл .env с настройками:")
            print("BOT_TOKEN=ваш_токен_бота")
            print("CHANNEL_ID=@ваш_канал")
            print("ADMIN_ID=ваш_telegram_id")
            input("\nНажмите Enter для выхода...")
            sys.exit(1)

        print("✅ .env найден")
        print("🔄 Импорт модулей...")

        # Проверяем импорты
        try:
            import config

            print("✅ config импортирован")
        except Exception as e:
            print(f"❌ Ошибка импорта config: {e}")
            traceback.print_exc()
            input("\nНажмите Enter для выхода...")
            sys.exit(1)

        try:
            from database import Database

            print("✅ database импортирован")
        except Exception as e:
            print(f"❌ Ошибка импорта database: {e}")
            traceback.print_exc()
            input("\nНажмите Enter для выхода...")
            sys.exit(1)

        print("✅ Все модули импортированы")
        print("🚀 Запуск бота...\n")

        asyncio.run(main())

    except KeyboardInterrupt:
        logger.info("⏹ Остановка бота...")
        print("\n⏹ Бот остановлен пользователем")
        input("\nНажмите Enter для выхода...")
    except Exception as e:
        logger.exception("❌ Критическая ошибка: %s", e)
        print("\n" + "=" * 50)
        print("❌ КРИТИЧЕСКАЯ ОШИБКА")
        print("=" * 50)
        print(f"\nОшибка: {e}")
        print("\nДетали ошибки:")
        traceback.print_exc()
        print("\n" + "=" * 50)
        print("\nДетали ошибки также сохранены в лог файл")
        if getattr(sys, "frozen", False):
            log_path = os.path.join(
                os.getenv("APPDATA"), "YandexMarketBot", "logs", "bot.log"
            )
            print(f"Путь к логу: {log_path}")
        input("\nНажмите Enter для выхода...")
        sys.exit(1)
