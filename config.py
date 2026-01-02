# config.py
import os
import sys
from typing import List, Optional
from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env file for os.getenv() to work
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv not available, rely on Pydantic only


# Для EXE файла: ищем .env в AppData, чтобы не засорять рабочий стол
if getattr(sys, "frozen", False):
    # Если запущено как EXE - используем AppData
    appdata_dir = os.path.join(os.getenv("APPDATA"), "YandexMarketBot")
    if not os.path.exists(appdata_dir):
        os.makedirs(appdata_dir)
    env_path = os.path.join(appdata_dir, ".env")
    # Также пробуем рядом с EXE (для совместимости)
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    env_path_exe = os.path.join(exe_dir, ".env")
else:
    # Если запущено как скрипт
    application_path = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(application_path, ".env")
    env_path_exe = None

# Определяем путь к .env файлу для pydantic-settings
env_file_path = (
    env_path
    if os.path.exists(env_path)
    else (env_path_exe if env_path_exe and os.path.exists(env_path_exe) else ".env")
)


class Settings(BaseSettings):
    """Application settings with validation and type safety"""

    # Bot configuration
    BOT_TOKEN: Optional[str] = None
    TELEGRAM_BOT_TOKEN: Optional[str] = None  # Alternative name

    CHANNEL_ID: str = "@marketi_tochka"
    ADMIN_ID: int = 0

    # Anchor / link text in the generated post
    ANCHOR_TEXT: str = "Яндекс.Маркет"

    # Use official Yandex Market API (best) — requires valid OAuth/Bearer token
    USE_OFFICIAL_API: bool = False

    # Token for API requests (Bearer token / OAuth access token)
    YANDEX_OAUTH_TOKEN: str = ""
    YANDEX_API_KEY: str = ""  # Alternative name

    # If True, the bot will use the exact URL the user sent (keeps referral params).
    KEEP_ORIGINAL_URL: bool = True

    IMAGE_MAX_MB: int = 5
    POST_INTERVAL: int = 10800  # 3 часа по умолчанию

    # Database
    DB_FILE: Optional[str] = None

    # Фильтры товаров
    MIN_PRICE: float = 0.0  # Минимальная цена
    MAX_PRICE: float = 0.0  # Максимальная цена (0 = без ограничений)
    MIN_DISCOUNT: int = 0  # Минимальная скидка в %

    SKIP_NO_PRICE: bool = True  # Пропускать товары без цены

    # Blacklist фильтр для автопоиска
    FILTER_STOP_WORDS_STR: str = (
        "б/у,запчасти,вибратор,уцененный,сломанный,чехол для,стекло для"
    )
    FILTER_MIN_PRICE: float = 500.0  # Минимальная цена для фильтрации в автопоиске

    # Реф-коды и UTM метки
    REF_CODE: str = ""  # Реферальный код для добавления в ссылки
    UTM_SOURCE: str = "telegram"  # UTM source
    UTM_MEDIUM: str = "bot"  # UTM medium
    UTM_CAMPAIGN: str = "marketi_tochka"  # UTM campaign

    # Yandex Distribution credentials (optional, for official partner link method)
    AFFILIATE_CLID: str = ""  # Partner CLID from Yandex Distribution
    AFFILIATE_VID: str = ""  # Partner VID from Yandex Distribution

    # Yandex Affiliate parameters for ad-marking (Erid system)
    YANDEX_REF_CLID: Optional[str] = None  # Partner CLID for affiliate links
    YANDEX_REF_VID: Optional[str] = None   # Partner VID for affiliate links
    YANDEX_REF_ERID: Optional[str] = None  # Ad token for Erid ad-marking

    # Rate limiting
    API_RATE_LIMIT: int = 10  # Запросов в минуту
    API_RATE_WINDOW: int = 60  # Окно в секундах

    # HTTP настройки
    HTTP_TIMEOUT: int = 30  # Таймаут HTTP запросов в секундах
    HTTP_MAX_RETRIES: int = 3  # Максимум повторных попыток
    HTTP_RETRY_DELAY: float = 2.0  # Базовая задержка между попытками в секундах

    # Proxy rotation settings
    PROXY_LIST_STR: str = "socks5://TV4GO0:1Z7dhD8iey@109.248.15.182:5501,socks5://TV4GO0:1Z7dhD8iey@109.248.15.188:5501,socks5://TV4GO0:1Z7dhD8iey@109.248.15.207:5501,socks5://TV4GO0:1Z7dhD8iey@109.248.15.209:5501,socks5://TV4GO0:1Z7dhD8iey@109.248.15.220:5501,socks5://TV4GO0:1Z7dhD8iey@109.248.15.223:5501"  # Список прокси через запятую

    # Кэширование
    CACHE_ENABLED: bool = True
    CACHE_TTL_HOURS: int = 24  # Время жизни кэша в часах

    # Планирование публикаций
    SCHEDULE_ENABLED: bool = False
    SCHEDULE_HOURS: str = ""  # Через запятую: "9,12,15,18"
    SCHEDULE_ONE_PER_DAY: bool = False

    # Автоматический поиск товаров
    AUTO_SEARCH_ENABLED: bool = True
    AUTO_SEARCH_INTERVAL: int = (
        3600  # DEPRECATED: Используется адаптивное расписание вместо фиксированного интервала
    )
    AUTO_SEARCH_QUERIES: str = ""  # Запросы через запятую: "наушники,смартфон,кофе"
    AUTO_SEARCH_MAX_PER_QUERY: int = 5  # Максимум товаров на один запрос

    # Автоматическое получение товаров с главной страницы
    AUTO_MAIN_PAGE_ENABLED: bool = True
    AUTO_MAIN_PAGE_MAX: int = 10  # Максимум товаров за раз

    # Периодические дайджесты (подборки товаров)
    DIGEST_FREQUENCY: int = 15  # Отправлять дайджест каждые X постов
    DIGEST_MIN_ITEMS: int = 3  # Минимум товаров для формирования дайджеста
    DIGEST_MAX_ITEMS: int = 5  # Максимум товаров в дайджесте

    # Night Mode - тихий режим (посты без звука/вибрации)
    NIGHT_START: int = 23  # Начало ночного режима (23:00)
    NIGHT_END: int = 8  # Конец ночного режима (08:00)

    # De-duplication settings
    DEDUP_DAYS_CHECK: int = 7  # Количество дней для проверки дубликатов

    # Cookies encryption
    COOKIES_ENCRYPTION_KEY: str = ""  # Ключ для шифрования cookies (опционально)

    # Webhook настройки (опционально, для использования webhook вместо polling)
    WEBHOOK_URL: str = ""  # URL для webhook (например: https://yourdomain.com/webhook)
    WEBHOOK_PATH: str = "/webhook"  # Путь для webhook
    WEBHOOK_PORT: int = 8443  # Порт для webhook сервера
    USE_WEBHOOK: bool = False  # Использовать webhook вместо polling

    # ChatGPT 5.1 API для обогащения данных
    CHATGPT_API_KEY: str = ""
    OPENAI_API_KEY: str = ""  # Alternative name
    GROQ_API_KEY: str = ""  # New Groq API key
    CHATGPT_API_URL: str = "https://api.openai.com/v1/chat/completions"
    CHATGPT_MODEL: str = "gpt-4o"  # Можно указать gpt-5.1 когда будет доступен

    # CAPTCHA solving service (2captcha, rucaptcha, anticaptcha)
    CAPTCHA_API_KEY: str = ""
    CAPTCHA_SERVICE: str = "rucaptcha"  # По умолчанию rucaptcha

    # Yandex Browser integration - use existing browser profile
    USE_YANDEX_BROWSER_PROFILE: bool = False
    YANDEX_BROWSER_USER_DATA_DIR: str = ""  # Путь к user data directory браузера Yandex
    YANDEX_BROWSER_EXECUTABLE_PATH: str = (
        ""  # Путь к исполняемому файлу браузера Yandex
    )
    CONNECT_TO_EXISTING_BROWSER: bool = False  # Подключиться к запущенному браузеру
    EXISTING_BROWSER_CDP_URL: str = ""  # CDP URL для подключения к запущенному браузеру

    # Новая архитектура: Postgres + Redis
    USE_POSTGRES: bool = False  # Включить Postgres вместо SQLite
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "yandex_market_bot"
    POSTGRES_USER: str = "bot_user"
    POSTGRES_PASSWORD: str = ""

    USE_REDIS: bool = False  # Включить Redis для очередей и кэша
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None

    # Архитектура: Фильтры качества
    QUALITY_MIN_PRICE: int = 100
    QUALITY_MIN_DISCOUNT: int = 10
    QUALITY_MIN_RATING: float = 4.2
    QUALITY_MIN_REVIEWS: int = 50

    # Архитектура: Лимиты брендов
    BRAND_WINDOW_SIZE: int = 50  # Размер sliding window для брендов
    BRAND_MAX_PER_WINDOW: int = 1  # Макс брендов в окне

    # Архитектура: Буфер публикации
    PUBLISH_INTERVAL: int = 60  # Секунд между публикациями
    PUBLISH_BATCH_SIZE: int = 1  # Количество постов за раз

    # HTTP клиент
    USER_AGENT: str = "YandexMarketBot/2.0 (+https://example.com/bot)"

    # Prompt for future LLM integration (kept for reference)
    LLM_SYSTEM_PROMPT: str = """
Ты — генератор коротких рекламных постов для телеграм-канала @marketi_tochka.
Составь пост (русский, 4–8 линий, лаконично, без воды):
1) В заголовке — точное название (title).
2) Указать упаковку/количество если есть.
3) 2–3 буллета «почему брать».
4) В конце вставить: "👉 Ссылка: {ANCHOR_TEXT}" (ссылка должна быть HTML тегом).
5) Не добавлять лишних хэштегов.
6) Подбор эмодзи по категории.
"""

    model_config = SettingsConfigDict(
        env_file=env_file_path,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("BOT_TOKEN", mode="before")
    @classmethod
    def validate_bot_token(cls, v, info):
        """Validate that BOT_TOKEN is set"""
        if v is None:
            # Try alternative name
            alt_token = info.data.get("TELEGRAM_BOT_TOKEN")
            if alt_token:
                return alt_token

        if not v:
            error_msg = "BOT_TOKEN is not set in environment (.env)"
            if getattr(sys, "frozen", False):
                appdata_dir = os.path.join(os.getenv("APPDATA"), "YandexMarketBot")
                env_path = os.path.join(appdata_dir, ".env")
                error_msg += f"\n\nПроверьте файл: {env_path}"
                error_msg += "\nУбедитесь, что в файле указан BOT_TOKEN=ваш_токен"
            raise ValueError(error_msg)
        return v

    @field_validator("YANDEX_OAUTH_TOKEN", mode="before")
    @classmethod
    def validate_yandex_token(cls, v, info):
        """Handle alternative YANDEX_API_KEY name"""
        if not v:
            alt_key = info.data.get("YANDEX_API_KEY")
            if alt_key:
                return alt_key
        return v

    @field_validator("CHATGPT_API_KEY", mode="before")
    @classmethod
    def validate_chatgpt_token(cls, v, info):
        """Handle alternative OPENAI_API_KEY name"""
        if not v:
            alt_key = info.data.get("OPENAI_API_KEY")
            if alt_key:
                return alt_key
        return v

    @field_validator("GROQ_API_KEY", mode="before")
    @classmethod
    def validate_groq_token(cls, v, info):
        """Handle GROQ_API_KEY"""
        return v or ""

    @field_validator("CAPTCHA_API_KEY", mode="before")
    @classmethod
    def validate_captcha_key(cls, v, info):
        """Handle alternative 2CAPTCHA_API_KEY name"""
        if not v:
            # Check for alternative environment variable name
            import os

            alt_key = os.getenv("2CAPTCHA_API_KEY", "")
            if alt_key:
                return alt_key
        return v

    @field_validator("DB_FILE", mode="before")
    @classmethod
    def set_db_file(cls, v, info):
        """Set default DB file path based on execution context"""
        if v is not None:
            return v

        if getattr(sys, "frozen", False):
            # Если запущено как EXE - используем AppData
            appdata_dir = os.path.join(os.getenv("APPDATA"), "YandexMarketBot")
            if not os.path.exists(appdata_dir):
                os.makedirs(appdata_dir)
            return os.path.join(appdata_dir, "bot_database.db")
        else:
            # Если запущено как скрипт
            return "bot_database.db"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Additional validation and computed fields
        self._setup_computed_fields()

    def _setup_computed_fields(self):
        """Setup computed fields that depend on the loaded settings"""
        pass  # We'll add computed fields below as global variables


# Create settings instance
settings = Settings()


# Export common variables for backward compatibility and convenience
ANCHOR_TEXT = settings.ANCHOR_TEXT


# Computed fields for backward compatibility
BOT_TOKEN = settings.BOT_TOKEN
TOKEN = BOT_TOKEN  # Алиас для совместимости
CHANNEL_ID = settings.CHANNEL_ID
ADMIN_ID = settings.ADMIN_ID
ADMIN_IDS = [ADMIN_ID] if ADMIN_ID else []  # Для совместимости

ANCHOR_TEXT = settings.ANCHOR_TEXT
USE_OFFICIAL_API = settings.USE_OFFICIAL_API
YANDEX_OAUTH_TOKEN = settings.YANDEX_OAUTH_TOKEN
KEEP_ORIGINAL_URL = settings.KEEP_ORIGINAL_URL

IMAGE_MAX_MB = settings.IMAGE_MAX_MB
POST_INTERVAL = settings.POST_INTERVAL
DB_FILE = settings.DB_FILE

# Фильтры товаров
MIN_PRICE = settings.MIN_PRICE
MAX_PRICE = settings.MAX_PRICE
MIN_DISCOUNT = settings.MIN_DISCOUNT
SKIP_NO_PRICE = settings.SKIP_NO_PRICE

# Blacklist фильтр для автопоиска
FILTER_STOP_WORDS_STR = settings.FILTER_STOP_WORDS_STR
FILTER_STOP_WORDS = (
    [w.strip() for w in FILTER_STOP_WORDS_STR.split(",") if w.strip()]
    if FILTER_STOP_WORDS_STR
    else []
)
FILTER_MIN_PRICE = settings.FILTER_MIN_PRICE

# Реф-коды и UTM метки
REF_CODE = settings.REF_CODE
UTM_SOURCE = settings.UTM_SOURCE
UTM_MEDIUM = settings.UTM_MEDIUM
UTM_CAMPAIGN = settings.UTM_CAMPAIGN

# Yandex Distribution credentials
AFFILIATE_CLID = settings.AFFILIATE_CLID
AFFILIATE_VID = settings.AFFILIATE_VID

# Yandex Affiliate parameters for ad-marking
YANDEX_REF_CLID = settings.YANDEX_REF_CLID
YANDEX_REF_VID = settings.YANDEX_REF_VID
YANDEX_REF_ERID = settings.YANDEX_REF_ERID

# Rate limiting
API_RATE_LIMIT = settings.API_RATE_LIMIT
API_RATE_WINDOW = settings.API_RATE_WINDOW

# HTTP настройки
HTTP_TIMEOUT = settings.HTTP_TIMEOUT
HTTP_MAX_RETRIES = settings.HTTP_MAX_RETRIES
HTTP_RETRY_DELAY = settings.HTTP_RETRY_DELAY

# Proxy rotation settings
PROXY_LIST_STR = settings.PROXY_LIST_STR
PROXY_LIST = (
    [p.strip() for p in PROXY_LIST_STR.split(",") if p.strip()]
    if PROXY_LIST_STR
    else []
)

# Кэширование
CACHE_ENABLED = settings.CACHE_ENABLED
CACHE_TTL_HOURS = settings.CACHE_TTL_HOURS

# Планирование публикаций
SCHEDULE_ENABLED = settings.SCHEDULE_ENABLED
SCHEDULE_HOURS = settings.SCHEDULE_HOURS
SCHEDULE_ONE_PER_DAY = settings.SCHEDULE_ONE_PER_DAY

# Автоматический поиск товаров
AUTO_SEARCH_ENABLED = settings.AUTO_SEARCH_ENABLED
AUTO_SEARCH_INTERVAL = settings.AUTO_SEARCH_INTERVAL
AUTO_SEARCH_QUERIES = settings.AUTO_SEARCH_QUERIES
AUTO_SEARCH_MAX_PER_QUERY = settings.AUTO_SEARCH_MAX_PER_QUERY

# Автоматическое получение товаров с главной страницы
AUTO_MAIN_PAGE_ENABLED = settings.AUTO_MAIN_PAGE_ENABLED
AUTO_MAIN_PAGE_MAX = settings.AUTO_MAIN_PAGE_MAX

# Периодические дайджесты
DIGEST_FREQUENCY = settings.DIGEST_FREQUENCY
DIGEST_MIN_ITEMS = settings.DIGEST_MIN_ITEMS
DIGEST_MAX_ITEMS = settings.DIGEST_MAX_ITEMS

# Night Mode
NIGHT_START = settings.NIGHT_START
NIGHT_END = settings.NIGHT_END

# Cookies encryption
COOKIES_ENCRYPTION_KEY = settings.COOKIES_ENCRYPTION_KEY

# Webhook настройки
WEBHOOK_URL = settings.WEBHOOK_URL
WEBHOOK_PATH = settings.WEBHOOK_PATH
WEBHOOK_PORT = settings.WEBHOOK_PORT
USE_WEBHOOK = settings.USE_WEBHOOK

# ChatGPT API
CHATGPT_API_KEY = settings.CHATGPT_API_KEY
CHATGPT_API_URL = settings.CHATGPT_API_URL
CHATGPT_MODEL = settings.CHATGPT_MODEL

# Groq API
GROQ_API_KEY = settings.GROQ_API_KEY

# CAPTCHA solving
CAPTCHA_API_KEY = settings.CAPTCHA_API_KEY
CAPTCHA_SERVICE = settings.CAPTCHA_SERVICE

# Yandex Browser integration
USE_YANDEX_BROWSER_PROFILE = settings.USE_YANDEX_BROWSER_PROFILE
YANDEX_BROWSER_USER_DATA_DIR = settings.YANDEX_BROWSER_USER_DATA_DIR
YANDEX_BROWSER_EXECUTABLE_PATH = settings.YANDEX_BROWSER_EXECUTABLE_PATH
CONNECT_TO_EXISTING_BROWSER = settings.CONNECT_TO_EXISTING_BROWSER
EXISTING_BROWSER_CDP_URL = settings.EXISTING_BROWSER_CDP_URL

# Prompt for future LLM integration
LLM_SYSTEM_PROMPT = settings.LLM_SYSTEM_PROMPT

# Новая архитектура: Postgres + Redis
USE_POSTGRES = settings.USE_POSTGRES
POSTGRES_HOST = settings.POSTGRES_HOST
POSTGRES_PORT = settings.POSTGRES_PORT
POSTGRES_DB = settings.POSTGRES_DB
POSTGRES_USER = settings.POSTGRES_USER
POSTGRES_PASSWORD = settings.POSTGRES_PASSWORD

USE_REDIS = settings.USE_REDIS
REDIS_HOST = settings.REDIS_HOST
REDIS_PORT = settings.REDIS_PORT
REDIS_DB = settings.REDIS_DB
REDIS_PASSWORD = settings.REDIS_PASSWORD

# Архитектура: Фильтры качества
QUALITY_MIN_PRICE = settings.QUALITY_MIN_PRICE
QUALITY_MIN_DISCOUNT = settings.QUALITY_MIN_DISCOUNT
QUALITY_MIN_RATING = settings.QUALITY_MIN_RATING
QUALITY_MIN_REVIEWS = settings.QUALITY_MIN_REVIEWS

# Архитектура: Лимиты брендов
BRAND_WINDOW_SIZE = settings.BRAND_WINDOW_SIZE
BRAND_MAX_PER_WINDOW = settings.BRAND_MAX_PER_WINDOW

# Архитектура: Буфер публикации
PUBLISH_INTERVAL = settings.PUBLISH_INTERVAL
PUBLISH_BATCH_SIZE = settings.PUBLISH_BATCH_SIZE

# HTTP клиент
USER_AGENT = settings.USER_AGENT

# Параметры аффилиатной программы
AFFILIATE_CC_BASE_URL = "https://market.yandex.ru/cc/"
AFFILIATE_ERID_BASE = "MyChannel"  # базовый ERID, будет дополняться уникальной частью

# Настройки хэштегов
HASHTAG_COUNT = 5

# API настройки
USE_OFFICIAL_API = False

# Параметры фильтров товаров
RATING_THRESHOLD = 4.2
REVIEWS_THRESHOLD = 50
DISCOUNT_THRESHOLD = 10

# Настройки брендов
BRAND_REPEAT_LIMIT = 3
BRAND_WHITELIST = ["Apple", "Xiaomi"]
BRAND_BLACKLIST = ["no-name"]

# Интервал публикаций (в часах)
POST_INTERVAL_HOURS = 2

# Файлы
OFFSET_FILE = "offsets.json"

# Отладочные настройки
VALIDATOR_STRICT = False  # Ослабить валидацию для тестирования
DEBUG_MODE = True  # Включить дополнительное логирование

# Режим работы
ENVIRONMENT: str = "dev"  # "dev" или "prod"
# Отладочные настройки
VALIDATOR_STRICT = False  # Ослабить валидацию для тестирования
DEBUG_MODE = True  # Включить дополнительное логирование

# Режим работы
ENVIRONMENT: str = "dev"  # "dev" или "prod"