"""Handlers for analytics and interactive queue management"""

import logging
from aiogram import types, Router, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
    BufferedInputFile,
)

logger = logging.getLogger(__name__)

# Router for analytics handlers
router = Router()


async def cmd_stats_visual(message: types.Message, db, analytics_service):
    """
    Enhanced stats command with visual graph.
    Usage: /stats_visual or /statsv
    """
    try:
        from utils.queue_pagination import create_stats_keyboard

        # Generate text summary
        summary_text = analytics_service.get_summary_text()

        # Send text first
        await message.answer(summary_text, parse_mode="HTML")

        # Try to generate and send graph
        try:
            graph_buffer = analytics_service.generate_activity_graph(days=7)
            if graph_buffer:
                # Send as photo
                photo = BufferedInputFile(graph_buffer.read(), filename="activity.png")
                await message.answer_photo(
                    photo,
                    caption="📊 График активности за 7 дней",
                    reply_markup=create_stats_keyboard(),
                )
            else:
                await message.answer("⚠️ Не удалось сгенерировать график")
        except Exception as e:
            logger.warning(f"Could not generate graph: {e}")
            await message.answer(
                "📊 График временно недоступен (matplotlib not installed)"
            )

    except Exception as e:
        logger.exception(f"Error in stats_visual: {e}")
        await message.answer(f"❌ Ошибка: {str(e)[:100]}")


async def cmd_queue_interactive(message: types.Message, db):
    """
    Interactive queue management with pagination.
    Usage: /queue or /q
    """
    try:
        from utils.queue_pagination import create_queue_page

        # Get queue items
        items = db.get_queue_urls(limit=100)  # Get up to 100 items
        total = db.get_queue_count()

        if not items:
            await message.answer("📭 Очередь пуста")
            return

        # Create first page
        text, markup = create_queue_page(
            items, page=0, items_per_page=5, total_items=total
        )

        await message.answer(text, reply_markup=markup, parse_mode="HTML")

    except Exception as e:
        logger.exception(f"Error in queue_interactive: {e}")
        await message.answer(f"❌ Ошибка: {str(e)[:100]}")


async def handle_queue_pagination(callback: types.CallbackQuery, db):
    """
    Handle queue pagination callbacks.
    Handles: queue_page:N, queue_delete:ID, queue_clear_all
    """
    try:
        from utils.queue_pagination import create_queue_page

        data = callback.data

        # Parse callback data
        if data.startswith("queue_page:"):
            # Pagination
            page_str = data.split(":")[1]

            if page_str == "current":
                await callback.answer("Текущая страница")
                return

            page = int(page_str)

            # Get queue items
            items = db.get_queue_urls(limit=100)
            total = db.get_queue_count()

            # Create page
            text, markup = create_queue_page(
                items, page=page, items_per_page=5, total_items=total
            )

            # Update message
            await callback.message.edit_text(
                text, reply_markup=markup, parse_mode="HTML"
            )
            await callback.answer()

        elif data.startswith("queue_delete:"):
            # Delete specific item
            queue_id = int(data.split(":")[1])

            # Remove from queue
            success = db.remove_from_queue(task_id=queue_id)

            if success:
                await callback.answer(f"✅ Удалено #{queue_id}", show_alert=False)

                # Refresh the page
                # Get current page from message
                items = db.get_queue_urls(limit=100)
                total = db.get_queue_count()

                if items:
                    text, markup = create_queue_page(
                        items, page=0, items_per_page=5, total_items=total
                    )
                    await callback.message.edit_text(
                        text, reply_markup=markup, parse_mode="HTML"
                    )
                else:
                    await callback.message.edit_text("📭 Очередь пуста")
            else:
                await callback.answer("❌ Не удалось удалить", show_alert=True)

        elif data == "queue_clear_all":
            # Clear entire queue (with confirmation)
            count = db.clear_queue()
            await callback.answer(f"🗑 Очищено {count} элементов", show_alert=True)
            await callback.message.edit_text("📭 Очередь очищена")

        else:
            await callback.answer("❓ Неизвестная команда")

    except Exception as e:
        logger.exception(f"Error in queue pagination: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)[:50]}", show_alert=True)


async def handle_stats_callback(callback: types.CallbackQuery, analytics_service):
    """Handle stats view callbacks"""
    try:
        data = callback.data

        if data == "stats_graph":
            # Generate and send graph
            graph_buffer = analytics_service.generate_activity_graph(days=7)
            if graph_buffer:
                from aiogram.types import BufferedInputFile

                photo = BufferedInputFile(graph_buffer.read(), filename="activity.png")
                await callback.message.answer_photo(
                    photo, caption="📊 График активности за 7 дней"
                )
                await callback.answer("✅ График отправлен")
            else:
                await callback.answer("❌ Ошибка генерации графика", show_alert=True)

        elif data == "stats_details":
            # Send detailed text stats
            summary = analytics_service.get_summary_text()
            await callback.message.answer(summary, parse_mode="HTML")
            await callback.answer("✅ Детали отправлены")

        elif data == "stats_refresh":
            # Refresh stats
            summary = analytics_service.get_summary_text()
            await callback.message.edit_text(summary, parse_mode="HTML")
            await callback.answer("🔄 Обновлено")

        else:
            await callback.answer("❓ Неизвестная команда")

    except Exception as e:
        logger.exception(f"Error in stats callback: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)[:50]}", show_alert=True)













