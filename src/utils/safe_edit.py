# utils/safe_edit.py
"""Безопасное редактирование сообщений с проверкой хэша контента"""
import hashlib
import logging
from typing import Optional, Dict, Any
from aiogram import types
from aiogram.exceptions import TelegramBadRequest

logger = logging.getLogger(__name__)

# Кэш последних сообщений для проверки хэшей
_message_cache: Dict[int, Dict[str, Any]] = {}


def _get_content_hash(text: str, reply_markup: Optional[Any] = None) -> str:
    """Вычисляет хэш контента сообщения"""
    content = text or ""
    markup_str = ""
    if reply_markup:
        try:
            # Сериализуем клавиатуру в строку для хэширования
            if hasattr(reply_markup, "inline_keyboard"):
                markup_str = str(reply_markup.inline_keyboard)
            elif hasattr(reply_markup, "keyboard"):
                markup_str = str(reply_markup.keyboard)
        except Exception:
            pass
    full_content = f"{content}|{markup_str}"
    return hashlib.md5(full_content.encode("utf-8")).hexdigest()


async def safe_edit_text(
    message: types.Message,
    text: str,
    reply_markup: Optional[Any] = None,
    parse_mode: Optional[str] = None,
    bot: Optional[Any] = None,
    **kwargs,
) -> bool:
    """
    Безопасно редактирует текст сообщения, проверяя хэш контента.
    Перед редактированием получает текущее сообщение и сравнивает текст.

    Args:
        message: Message object to edit
        text: New text
        reply_markup: Optional reply markup
        parse_mode: Optional parse mode
        bot: Optional bot instance (for fetching current message)
        **kwargs: Additional arguments for edit_text

    Returns:
        True если редактирование успешно или не требуется, False при ошибке
    """
    try:
        message_id = message.message_id
        chat_id = message.chat.id

        # Вычисляем хэш нового контента
        new_hash = _get_content_hash(text, reply_markup)

        # Проверяем, был ли уже такой контент в кэше
        cache_key = f"{chat_id}_{message_id}"
        if cache_key in _message_cache:
            old_hash = _message_cache[cache_key].get("hash")
            if old_hash == new_hash:
                logger.debug(
                    f"Message {message_id} content unchanged (from cache), skipping edit"
                )
                return True

        # Если bot предоставлен, пытаемся получить текущее сообщение и сравнить текст
        if bot:
            try:
                # Получаем текущее сообщение через bot API
                current_message = await bot.get_chat(chat_id)
                # Note: get_chat doesn't return message content, but we can try forward_message
                # For now, we'll rely on the cache and hash comparison
                # In the future, we could store message text in DB and compare
            except Exception:
                pass

        # Альтернативный подход: сравниваем с сохраненным текстом из кэша
        if cache_key in _message_cache:
            cached_text = _message_cache[cache_key].get("text")
            if cached_text == text:
                logger.debug(
                    f"Message {message_id} text unchanged (exact match), skipping edit"
                )
                # Обновляем хэш на всякий случай
                _message_cache[cache_key] = {
                    "hash": new_hash,
                    "text": text,
                    "reply_markup": reply_markup,
                }
                return True

        # Редактируем сообщение
        try:
            await message.edit_text(
                text=text, reply_markup=reply_markup, parse_mode=parse_mode, **kwargs
            )

            # Сохраняем хэш в кэш
            _message_cache[cache_key] = {
                "hash": new_hash,
                "text": text,
                "reply_markup": reply_markup,
            }

            logger.debug(f"Message {message_id} edited successfully")
            return True

        except TelegramBadRequest as e:
            error_msg = str(e).lower()
            if "message is not modified" in error_msg:
                # Сообщение не изменилось - это нормально
                logger.debug(f"Message {message_id} not modified (expected)")
                # Обновляем кэш
                _message_cache[cache_key] = {
                    "hash": new_hash,
                    "text": text,
                    "reply_markup": reply_markup,
                }
                return True
            else:
                # Другая ошибка
                logger.warning(f"Failed to edit message {message_id}: {e}")
                raise

    except Exception as e:
        logger.exception(f"Error in safe_edit_text: {e}")
        return False


def clear_message_cache(
    chat_id: Optional[int] = None, message_id: Optional[int] = None
):
    """Очищает кэш сообщений"""
    if chat_id and message_id:
        cache_key = f"{chat_id}_{message_id}"
        _message_cache.pop(cache_key, None)
    elif chat_id:
        # Очищаем все сообщения для чата
        keys_to_remove = [
            k for k in _message_cache.keys() if k.startswith(f"{chat_id}_")
        ]
        for key in keys_to_remove:
            _message_cache.pop(key, None)
    else:
        # Очищаем весь кэш
        _message_cache.clear()


# Helper для callback.message.edit_text
async def safe_edit_callback_message(
    callback: types.CallbackQuery,
    text: str,
    reply_markup: Optional[Any] = None,
    parse_mode: Optional[str] = None,
    **kwargs,
) -> bool:
    """
    Безопасно редактирует сообщение из callback

    Returns:
        True если редактирование успешно или не требуется, False при ошибке
    """
    return await safe_edit_text(
        callback.message,
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
        **kwargs,
    )
