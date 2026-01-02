# services/logging_service.py
"""Улучшенная система логирования с разделением по типам логов"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional


class LoggingService:
    """Централизованный сервис логирования с разделением по файлам"""

    def __init__(self):
        # Определяем директорию для логов
        if getattr(sys, "frozen", False):
            appdata_dir = os.path.join(os.getenv("APPDATA"), "YandexMarketBot")
            if not os.path.exists(appdata_dir):
                os.makedirs(appdata_dir)
            self.log_dir = os.path.join(appdata_dir, "logs")
        else:
            self.log_dir = "logs"

        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

        # Пути к файлам логов
        self.info_log = os.path.join(self.log_dir, "info.log")
        self.error_log = os.path.join(self.log_dir, "error.log")
        self.playwright_log = os.path.join(self.log_dir, "playwright.log")
        self.publishing_log = os.path.join(self.log_dir, "publishing.log")
        self.bot_log = os.path.join(self.log_dir, "bot.log")

        self._setup_loggers()

    def _setup_loggers(self):
        """Настройка всех логгеров"""
        # Импортируем CorrelationIDFilter
        from utils.correlation_id import CorrelationIDFilter

        correlation_filter = CorrelationIDFilter()

        # Формат для файлов (с correlation_id)
        file_formatter = logging.Formatter(
            "[%(asctime)s] [%(correlation_id)s] %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Формат для консоли (с correlation_id)
        console_formatter = logging.Formatter(
            "[%(asctime)s] [%(correlation_id)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        )

        # Корневой логгер
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        # Очищаем существующие обработчики
        root_logger.handlers.clear()

        # 1. info.log - INFO и выше
        info_handler = RotatingFileHandler(
            self.info_log, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        info_handler.setLevel(logging.INFO)
        info_handler.setFormatter(file_formatter)
        info_handler.addFilter(correlation_filter)
        info_handler.addFilter(lambda record: record.levelno >= logging.INFO)
        root_logger.addHandler(info_handler)

        # 2. error.log - только ERROR и CRITICAL
        error_handler = RotatingFileHandler(
            self.error_log, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_formatter)
        error_handler.addFilter(correlation_filter)
        error_handler.addFilter(lambda record: record.levelno >= logging.ERROR)
        root_logger.addHandler(error_handler)

        # 3. playwright.log - логи Playwright
        playwright_handler = RotatingFileHandler(
            self.playwright_log,
            maxBytes=10 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        playwright_handler.setLevel(logging.DEBUG)
        playwright_handler.setFormatter(file_formatter)
        playwright_logger = logging.getLogger("playwright")
        playwright_logger.addHandler(playwright_handler)
        playwright_logger.setLevel(logging.DEBUG)
        playwright_logger.propagate = False

        # 4. publishing.log - логи публикации
        publishing_handler = RotatingFileHandler(
            self.publishing_log,
            maxBytes=10 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        publishing_handler.setLevel(logging.DEBUG)
        publishing_handler.setFormatter(file_formatter)
        publishing_logger = logging.getLogger("publishing")
        publishing_logger.addHandler(publishing_handler)
        publishing_logger.setLevel(logging.DEBUG)
        publishing_logger.propagate = False

        # 5. bot.log - все логи (для совместимости)
        bot_handler = RotatingFileHandler(
            self.bot_log, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        bot_handler.setLevel(logging.DEBUG)
        bot_handler.setFormatter(file_formatter)
        bot_handler.addFilter(correlation_filter)
        root_logger.addHandler(bot_handler)

        # Консольный обработчик с фильтром
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(console_formatter)
        console_handler.addFilter(correlation_filter)

        class ConsoleFilter(logging.Filter):
            def filter(self, record):
                if record.levelno == logging.DEBUG:
                    return False
                message = record.getMessage()
                if '{"' in message[:100] and record.levelno < logging.WARNING:
                    return False
                if len(message) > 500 and record.levelno < logging.WARNING:
                    return False
                return True

        console_handler.addFilter(ConsoleFilter())
        root_logger.addHandler(console_handler)

    def get_logger(self, name: str) -> logging.Logger:
        """Получить логгер с указанным именем"""
        return logging.getLogger(name)

    def get_playwright_logger(self) -> logging.Logger:
        """Получить логгер для Playwright"""
        return logging.getLogger("playwright")

    def get_publishing_logger(self) -> logging.Logger:
        """Получить логгер для публикации"""
        return logging.getLogger("publishing")


# Глобальный экземпляр
_logging_service: Optional[LoggingService] = None


def get_logging_service() -> LoggingService:
    """Получить глобальный экземпляр сервиса логирования"""
    global _logging_service
    if _logging_service is None:
        _logging_service = LoggingService()
    return _logging_service
