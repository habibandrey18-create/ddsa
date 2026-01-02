# decorators.py
"""Декораторы для упрощения кода и улучшения архитектуры"""
from functools import wraps
from typing import Callable, Any
import logging
from aiogram import types
import src.config as config

logger = logging.getLogger(__name__)


def admin_only(func: Callable) -> Callable:
    """Декоратор для проверки прав администратора"""

    @wraps(func)
    async def wrapper(
        message_or_callback: types.Message | types.CallbackQuery, *args, **kwargs
    ):
        user_id = None
        if isinstance(message_or_callback, types.Message):
            user_id = message_or_callback.from_user.id
            if user_id != config.ADMIN_ID:
                await message_or_callback.answer("❌ Нет прав.")
                return
        elif isinstance(message_or_callback, types.CallbackQuery):
            user_id = message_or_callback.from_user.id
            if user_id != config.ADMIN_ID:
                await message_or_callback.answer("❌ Нет прав.", show_alert=True)
                return

        return await func(message_or_callback, *args, **kwargs)

    return wrapper


def handle_errors(context: str = "Unknown"):
    """Декоратор для централизованной обработки ошибок"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.exception(f"Error in {context} ({func.__name__}): {e}")
                # Пытаемся отправить сообщение об ошибке, если есть доступ к message/callback
                for arg in args:
                    if isinstance(arg, (types.Message, types.CallbackQuery)):
                        try:
                            if isinstance(arg, types.Message):
                                await arg.answer(f"❌ Ошибка: {str(e)[:200]}")
                            else:
                                await arg.answer(
                                    f"❌ Ошибка: {str(e)[:200]}", show_alert=True
                                )
                        except Exception:
                            pass
                        break
                raise

        return wrapper

    return decorator
