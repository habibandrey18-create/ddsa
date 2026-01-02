# services/log_service.py
"""Сервис для работы с логами"""
import os
import re
import logging
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class LogService:
    """Сервис для чтения и фильтрации логов"""

    def __init__(self, log_file: str):
        self.log_file = log_file

    def get_recent_logs(
        self,
        limit: int = 50,
        min_level: str = "INFO",
        keywords: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
    ) -> List[Dict[str, str]]:
        """
        Получает последние логи с фильтрацией

        Args:
            limit: Максимальное количество логов
            min_level: Минимальный уровень (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            keywords: Ключевые слова для включения
            exclude_keywords: Ключевые слова для исключения

        Returns:
            Список словарей с логами: [{"level": "...", "time": "...", "message": "..."}, ...]
        """
        if not os.path.exists(self.log_file):
            return []

        level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
        min_level_num = level_order.get(min_level.upper(), 1)

        logs = []
        keywords_lower = [k.lower() for k in (keywords or [])]
        exclude_lower = [k.lower() for k in (exclude_keywords or [])]

        try:
            with open(self.log_file, "r", encoding="utf-8", errors="ignore") as f:
                # Читаем файл с конца (последние строки)
                lines = f.readlines()
                # Берем последние N строк для анализа
                recent_lines = lines[-1000:] if len(lines) > 1000 else lines

                for line in reversed(recent_lines):
                    if len(logs) >= limit:
                        break

                    # Парсим строку лога
                    log_entry = self._parse_log_line(line)
                    if not log_entry:
                        continue

                    # Фильтр по уровню
                    log_level = log_entry.get("level", "INFO")
                    if level_order.get(log_level, 1) < min_level_num:
                        continue

                    # Фильтр по ключевым словам
                    message_lower = log_entry.get("message", "").lower()

                    if keywords_lower:
                        if not any(kw in message_lower for kw in keywords_lower):
                            continue

                    if exclude_lower:
                        if any(kw in message_lower for kw in exclude_lower):
                            continue

                    logs.append(log_entry)

            # Возвращаем в хронологическом порядке
            return list(reversed(logs))

        except Exception as e:
            logger.error(f"Error reading logs: {e}")
            return []

    def _parse_log_line(self, line: str) -> Optional[Dict[str, str]]:
        """Парсит строку лога в словарь"""
        if not line.strip():
            return None

        # Формат: [2025-01-01 12:00:00] INFO module: message
        pattern = r"\[([^\]]+)\]\s+(\w+)\s+([^:]+):\s*(.+)"
        match = re.match(pattern, line.strip())

        if match:
            time_str, level, module, message = match.groups()
            return {
                "time": time_str,
                "level": level,
                "module": module,
                "message": message,
            }

        # Альтернативный формат: просто сообщение
        return {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "level": "INFO",
            "module": "unknown",
            "message": line.strip(),
        }

    def get_important_logs(self, limit: int = 30) -> List[Dict[str, str]]:
        """
        Получает только важные логи (ERROR, WARNING, публикации, ошибки)

        Args:
            limit: Максимальное количество логов

        Returns:
            Список важных логов
        """
        important_keywords = [
            "ERROR",
            "WARNING",
            "CRITICAL",
            "публикация",
            "публикован",
            "ошибка",
            "error",
            "exception",
            "worker",
            "queue",
            "failed",
            "success",
            "успешно",
            "неудачно",
        ]

        return self.get_recent_logs(
            limit=limit,
            min_level="INFO",
            keywords=important_keywords,
            exclude_keywords=["DEBUG", "debug"],
        )

    def format_logs_for_message(
        self, logs: List[Dict[str, str]], max_length: int = 4000
    ) -> str:
        """
        Форматирует логи для отправки в Telegram

        Args:
            logs: Список логов
            max_length: Максимальная длина сообщения

        Returns:
            Отформатированная строка
        """
        if not logs:
            return "📋 <b>Логи не найдены</b>"

        text = f"📋 <b>Последние {len(logs)} важных логов:</b>\n\n"

        level_icons = {
            "DEBUG": "🔍",
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "CRITICAL": "🚨",
        }

        for log in logs:
            level = log.get("level", "INFO")
            icon = level_icons.get(level, "ℹ️")
            time = log.get("time", "")[:16]  # Обрезаем до секунд
            message = log.get("message", "")[:200]  # Обрезаем длинные сообщения

            # Экранируем HTML
            message = (
                message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            )

            log_line = f"{icon} <code>{time}</code> {message}\n"

            if len(text) + len(log_line) > max_length:
                text += f"\n... и еще {len(logs) - logs.index(log)} логов"
                break

            text += log_line

        return text
