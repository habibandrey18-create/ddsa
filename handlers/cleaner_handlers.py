"""Handlers for sold-out cleaner commands"""

import logging
from aiogram import types, Router
from aiogram.filters import Command

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("clean_sold_out"))
async def cmd_clean_sold_out(message: types.Message):
    """
    Команда для ручной очистки распроданных товаров.
    Использование: /clean_sold_out [hours] [delete|edit]

    Args:
        hours: Количество часов назад для проверки (по умолчанию 48)
        delete|edit: Режим работы - удалять или редактировать сообщения (по умолчанию delete)
    """
    try:
        from database import Database
        from aiogram import Bot
        import config

        # Parse arguments
        args = message.text.split()[1:] if message.text else []

        hours = 48
        delete_mode = True

        if args:
            try:
                hours = int(args[0])
            except (ValueError, IndexError):
                pass

            if len(args) > 1:
                mode = args[1].lower()
                delete_mode = mode == "delete"

        # Initialize cleaner
        db = Database()
        bot = Bot(token=config.BOT_TOKEN)

        from services.cleaner_service import CleanerService

        cleaner = CleanerService(db=db, bot=bot)

        # Run cleanup
        await message.answer(f"🔍 Проверяю посты за последние {hours} часов...")

        stats = await cleaner.clean_sold_out_posts(
            hours=hours, delete_messages=delete_mode, edit_caption=not delete_mode
        )

        # Format response
        result_text = f"""
✅ Очистка завершена!

📊 Статистика:
• Проверено постов: {stats['checked']}
• Найдено распроданных: {stats['sold_out']}
• {'Удалено' if delete_mode else 'Отредактировано'}: {stats['deleted'] if delete_mode else stats['edited']}
• Ошибок: {stats['errors']}
"""

        await message.answer(result_text)

    except Exception as e:
        logger.exception(f"Error in clean_sold_out command: {e}")
        await message.answer(f"❌ Ошибка при очистке: {str(e)[:200]}")


@router.message(Command("cleaner_status"))
async def cmd_cleaner_status(message: types.Message):
    """Показывает статус очистки распроданных товаров"""
    try:
        from database import Database

        db = Database()

        # Get recent posts count
        recent_posts = db.get_recent_posts_with_messages(hours=48)

        status_text = f"""
📊 Статус очистки распроданных товаров:

• Постов за последние 48 часов: {len(recent_posts)}
• С message_id: {sum(1 for p in recent_posts if p.get('message_id'))}

💡 Используйте /clean_sold_out для ручной очистки
💡 Автоматическая очистка запускается при старте бота (если включена)
"""

        await message.answer(status_text)

    except Exception as e:
        logger.exception(f"Error in cleaner_status command: {e}")
        await message.answer(f"❌ Ошибка: {str(e)[:200]}")













