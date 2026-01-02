# services/dependency_checker.py
"""Проверка зависимостей при старте"""
import sys
import importlib
import logging

logger = logging.getLogger(__name__)

REQUIRED_PACKAGES = [
    "aiogram",
    "aiohttp",
    "bs4",  # beautifulsoup4 импортируется как bs4
    "lxml",
    "PIL",  # Pillow
    "dotenv",
]

# Маппинг имен пакетов к именам модулей для импорта
PACKAGE_IMPORT_MAP = {
    "beautifulsoup4": "bs4",  # beautifulsoup4 устанавливается, но импортируется как bs4
    "Pillow": "PIL",  # Pillow устанавливается, но импортируется как PIL
    "python-dotenv": "dotenv",  # python-dotenv устанавливается, но импортируется как dotenv
}

# Обратный маппинг для проверки опциональных пакетов
REVERSE_IMPORT_MAP = {
    "bs4": "beautifulsoup4",
    "PIL": "Pillow",
    "dotenv": "python-dotenv",
}

OPTIONAL_PACKAGES = {
    "psutil": "Расширенная статистика системы",
    "qrcode": "Генерация QR-кодов",
    "Pillow": "Обработка изображений (уже есть через PIL)",
}


def check_dependencies():
    """Проверяет наличие всех зависимостей"""
    missing_required = []
    missing_optional = []

    # Проверка обязательных
    for package in REQUIRED_PACKAGES:
        try:
            # Используем маппинг если есть
            import_name = PACKAGE_IMPORT_MAP.get(package, package)
            importlib.import_module(import_name)
        except ImportError:
            missing_required.append(package)

    # Проверка опциональных
    for package, description in OPTIONAL_PACKAGES.items():
        try:
            # Используем маппинг для опциональных пакетов тоже
            import_name = PACKAGE_IMPORT_MAP.get(package, package)
            importlib.import_module(import_name)
        except ImportError:
            missing_optional.append((package, description))

    # Результаты
    if missing_required:
        logger.error(
            "❌ Отсутствуют обязательные пакеты: %s", ", ".join(missing_required)
        )
        logger.error("Установите: pip install %s", " ".join(missing_required))
        return False

    if missing_optional:
        logger.warning("⚠️ Отсутствуют опциональные пакеты:")
        for package, desc in missing_optional:
            logger.warning("  - %s: %s", package, desc)
        logger.warning(
            "Установите для полной функциональности: pip install %s",
            " ".join([p[0] for p in missing_optional]),
        )

    logger.info("✅ Все обязательные зависимости установлены")
    return True
