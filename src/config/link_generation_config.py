# config/link_generation_config.py
"""
Link Generation Configuration
Centralized constants and configuration for link generation service
"""
from pathlib import Path
from typing import List, Dict

# Directories
# Используем абсолютные пути относительно директории проекта
import os
import sys

# Определяем базовую директорию проекта
try:
    # Пытаемся использовать __file__ если доступен
    if "__file__" in globals():
        _base_dir = Path(__file__).parent.parent.resolve()
    else:
        # Fallback: используем директорию, где находится скрипт
        if getattr(sys, "frozen", False):
            # Если запущено как EXE
            _base_dir = Path(sys.executable).parent.resolve()
        else:
            # Если запущено как скрипт
            _base_dir = Path(sys.argv[0]).parent.resolve()
except Exception:
    # Последний fallback: текущая рабочая директория
    _base_dir = Path.cwd().resolve()

DEBUG_DIR = _base_dir / "debug"
DEBUG_DIR.mkdir(exist_ok=True, parents=True)

STORAGE_STATE_DIR = _base_dir / "storage_states"
STORAGE_STATE_DIR.mkdir(exist_ok=True, parents=True)

# User-Agent rotation list (up-to-date real browser UAs)
USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
]

# Viewport presets for browser contexts
VIEWPORTS: List[Dict[str, int]] = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
]

# Link Generation Defaults
DEFAULT_HEADLESS = False  # Изменено на False для видимости браузера при отладке
DEFAULT_TIMEOUT = 30  # seconds
DEFAULT_MAX_RETRIES = 3
DEFAULT_DEBUG = True

# Worker Configuration
WORKER_MAX_WORKERS = 2  # Number of concurrent link generation tasks
WORKER_JOB_TIMEOUT = 180  # Job timeout in seconds (увеличено до 180 для более медленных страниц и извлечения ссылки из "Поделиться")
WORKER_CLEANUP_INTERVAL = 3600  # Clean old results every hour
WORKER_RESULT_TTL = 3600  # Keep results for 1 hour

# Network Interception
NETWORK_RESPONSE_TIMEOUT = 10000  # milliseconds
NETWORK_API_PATTERNS = [
    "market.yandex.ru/api/",
    "platform-api.yandex.ru",
    "/share",
    "resolveSharingPopupV2",  # #region agent edit - добавляем resolveSharingPopupV2 в паттерны
    "resolve",  # #endregion
]

# Button Selectors (in order of preference)
SHARE_BUTTON_SELECTORS = [
    'button[aria-label="Поделиться"]',
    'button:has-text("Поделиться")',
    'button[aria-label*="Поделиться"]',
    '[data-testid*="share"]',
]

# Copy Link Button Selectors (for clipboard fallback)
COPY_LINK_BUTTON_SELECTORS = [
    'button[aria-label*="Копировать"]',
    'button:has-text("Копировать")',
    'button:has-text("Copy")',
    'button[aria-label*="Copy"]',
    '[data-testid*="copy"]',
    'button:has-text("Скопировать")',
]

# Share Modal Selectors (for waiting for modal to appear)
SHARE_MODAL_SELECTORS = [
    '[role="dialog"]',
    '[data-testid*="modal"]',
    '[class*="Modal"]',
    '[class*="modal"]',
    '[class*="ShareModal"]',
    '[class*="share-modal"]',
]

# Browser Launch Arguments
# Флаги для скрытия автоматизации и предотвращения CAPTCHA
BROWSER_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--lang=ru-RU,ru",
    # Дополнительные флаги для скрытия автоматизации
    "--disable-infobars",  # Скрывает предупреждение об автоматизации
    "--disable-web-security",  # Отключает некоторые проверки безопасности (может помочь обойти детекцию)
    "--disable-features=IsolateOrigins,site-per-process",  # Отключает изоляцию сайтов
    "--disable-site-isolation-trials",  # Отключает изоляцию сайтов
    "--disable-extensions-except",  # Отключает расширения
    "--disable-plugins-discovery",  # Отключает обнаружение плагинов
    "--disable-default-apps",  # Отключает приложения по умолчанию
    "--exclude-switches=enable-automation",  # Исключает переключатель автоматизации
    "--disable-background-timer-throttling",  # Отключает троттлинг таймеров в фоне
    "--disable-backgrounding-occluded-windows",  # Отключает фоновую обработку скрытых окон
    "--disable-renderer-backgrounding",  # Отключает фоновую обработку рендерера
    "--disable-features=TranslateUI",  # Отключает UI перевода
    "--disable-ipc-flooding-protection",  # Отключает защиту от IPC flooding
]

# Browser Context Options
BROWSER_LOCALE = "ru-RU"
BROWSER_TIMEZONE = "Europe/Moscow"
BROWSER_PERMISSIONS = ["clipboard-read", "clipboard-write"]

# Human-like Interaction Delays (in seconds)
HOVER_DELAY_MIN = 0.1
HOVER_DELAY_MAX = 0.3
CLICK_DELAY_MIN = 0.2
CLICK_DELAY_MAX = 0.5
MOUSE_MOVE_DELAY_MIN = 0.05
MOUSE_MOVE_DELAY_MAX = 0.15
NETWORK_WAIT_MIN = 1.5
NETWORK_WAIT_MAX = 2.5
RETRY_DELAY_MIN = 1.0
RETRY_DELAY_MAX = 2.0

# XHR Reproduction
XHR_REPRODUCTION_TIMEOUT = 10  # seconds
XHR_HEADERS_TO_REMOVE = [
    "Content-Length",  # Will be recalculated
    "Connection",  # Hop-by-hop header
    "Transfer-Encoding",  # Hop-by-hop header
]

# Storage State Fingerprinting
STORAGE_STATE_HASH_MOD = 10000  # For fingerprint generation

# Circuit Breaker (can be overridden)
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 3
CIRCUIT_BREAKER_OPEN_DURATION = 300  # 5 minutes in seconds

# XHR Cache Configuration
XHR_CACHE_TTL = 3600  # Cache TTL in seconds (1 hour)
XHR_CACHE_MAX_SIZE = 50  # Maximum cached XHRs
