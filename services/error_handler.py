# services/error_handler.py
"""Централизованный обработчик ошибок для бота"""
import logging
import traceback
from typing import Optional, Dict, Any
from functools import wraps
from aiogram import Bot
from aiogram.types import Message, CallbackQuery

logger = logging.getLogger(__name__)


class ErrorHandler:
    """Централизованный обработчик ошибок"""

    def __init__(self, bot: Optional[Bot] = None, admin_id: Optional[int] = None):
        self.bot = bot
        self.admin_id = admin_id
        self.error_stats: Dict[str, int] = {}

    async def handle_error(
        self,
        error: Exception,
        context: Optional[str] = None,
        user_id: Optional[int] = None,
        notify_admin: bool = True,
    ) -> str:
        """
        Обрабатывает ошибку и возвращает понятное сообщение для пользователя

        Args:
            error: Исключение
            context: Контекст, где произошла ошибка
            user_id: ID пользователя (если есть)
            notify_admin: Уведомить админа о критической ошибке

        Returns:
            Понятное сообщение об ошибке для пользователя
        """
        error_type = type(error).__name__
        error_msg = str(error)

        # Увеличиваем счетчик ошибок
        self.error_stats[error_type] = self.error_stats.get(error_type, 0) + 1

        # Логируем ошибку
        logger.error(
            f"Error in {context or 'unknown'}: {error_type}: {error_msg}", exc_info=True
        )

        # Определяем понятное сообщение для пользователя
        user_message = self._get_user_friendly_message(error_type, error_msg)

        # Уведомляем админа о критических ошибках
        if notify_admin and self.bot and self.admin_id:
            try:
                admin_msg = (
                    f"⚠️ <b>Ошибка в боте</b>\n\n"
                    f"📍 Контекст: {context or 'неизвестно'}\n"
                    f"🔴 Тип: {error_type}\n"
                    f"📝 Сообщение: {error_msg[:200]}\n"
                )
                if user_id:
                    admin_msg += f"👤 Пользователь: {user_id}\n"

                await self.bot.send_message(self.admin_id, admin_msg, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Failed to notify admin about error: {e}")

        return user_message

    def _get_user_friendly_message(self, error_type: str, error_msg: str) -> str:
        """Преобразует техническую ошибку в понятное сообщение"""
        # Скрываем чувствительную информацию
        if "token" in error_msg.lower() or "password" in error_msg.lower():
            return "❌ Ошибка аутентификации. Обратитесь к администратору."

        # Специфичные сообщения для разных типов ошибок
        if "timeout" in error_msg.lower() or "TimeoutError" in error_type:
            return "⏱️ Превышено время ожидания. Попробуйте позже."

        if "connection" in error_msg.lower() or "ConnectionError" in error_type:
            return "🌐 Ошибка подключения. Проверьте интернет-соединение."

        if "not found" in error_msg.lower() or "NotFound" in error_type:
            return "🔍 Запрашиваемый ресурс не найден."

        if "permission" in error_msg.lower() or "PermissionError" in error_type:
            return "🚫 Недостаточно прав для выполнения операции."

        if "validation" in error_msg.lower() or "ValidationError" in error_type:
            return "❌ Некорректные данные. Проверьте введенные значения."

        # Общее сообщение
        return "❌ Произошла ошибка. Попробуйте позже или обратитесь к администратору."

    def get_error_stats(self) -> Dict[str, int]:
        """Возвращает статистику ошибок"""
        return self.error_stats.copy()

    def reset_stats(self):
        """Сбрасывает статистику ошибок"""
        self.error_stats.clear()


# Глобальный экземпляр (будет инициализирован в bot.py)
error_handler: Optional[ErrorHandler] = None


def error_handler_decorator(func):
    """Декоратор для автоматической обработки ошибок в обработчиках"""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            if error_handler:
                context = f"{func.__module__}.{func.__name__}"
                user_id = None

                # Пытаемся извлечь user_id из аргументов
                for arg in args:
                    if isinstance(arg, (Message, CallbackQuery)):
                        user_id = (
                            arg.from_user.id if hasattr(arg, "from_user") else None
                        )
                        break

                user_message = await error_handler.handle_error(
                    e, context=context, user_id=user_id, notify_admin=True
                )

                # Отправляем сообщение пользователю, если возможно
                for arg in args:
                    if isinstance(arg, Message):
                        try:
                            await arg.answer(user_message)
                        except Exception:
                            pass
                        break
                    elif isinstance(arg, CallbackQuery):
                        try:
                            await arg.answer(user_message, show_alert=True)
                        except Exception:
                            pass
                        break
            else:
                # Если error_handler не инициализирован, просто логируем
                logger.exception(f"Unhandled error in {func.__name__}")

            return None

    return wrapper
