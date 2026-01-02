# handlers/callbacks.py
"""Обработчики callback запросов"""
from typing import Dict, Any, Optional
from aiogram import Bot, types, F
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging
import src.config as config
from database import Database
from decorators import admin_only, handle_errors

logger = logging.getLogger(__name__)


def register_callbacks_handlers(
    dp, bot: Bot, db: Database, user_states: dict, global_settings
):
    """Регистрирует обработчики callback запросов"""

    @dp.callback_query(F.data.startswith("cmd_"))
    @handle_errors("callback_cmd")
    async def handle_command_button(callback: types.CallbackQuery):
        """Обработчик кнопок команд"""
        if callback.from_user.id != config.ADMIN_ID:
            await callback.answer("❌ Нет прав.", show_alert=True)
            return

        command = callback.data.replace("cmd_", "")

        # Импортируем функции из bot.py для совместимости
        from bot import (
            cmd_main_menu_button,
            cmd_admin_panel_button,
            cmd_status_button,
            cmd_restart_button,
            cmd_force_post_button,
            cmd_last_post_button,
            cmd_info_button,
            cmd_log_button,
            handle_log_action,
            cmd_check_auto_button,
            handle_admin_section,
            handle_queue_action,
            handle_analytics_action,
            handle_content_action,
            handle_system_action,
            handle_schedule_action,
            handle_management_action,
        )

        if command == "main_menu":
            await cmd_main_menu_button(callback)
        elif command == "admin_panel":
            await cmd_admin_panel_button(callback)
        elif command == "status":
            await cmd_status_button(callback)
        elif command == "restart":
            await cmd_restart_button(callback)
        elif command == "test_post":
            await callback.answer("📝 Используйте: /test_post <url>", show_alert=True)
        elif command == "force_post":
            await cmd_force_post_button(callback)
        elif command == "last_post":
            await cmd_last_post_button(callback)
        elif command == "info":
            await cmd_info_button(callback)
        elif command == "log":
            await cmd_log_button(callback)
        elif command.startswith("log_"):
            await handle_log_action(callback, command)
        elif command == "auto_search":
            await callback.answer(
                "🔍 Используйте: /auto_search <запрос> [количество]", show_alert=True
            )
        elif command == "check_auto":
            await cmd_check_auto_button(callback)
        elif command.startswith("admin_"):
            await handle_admin_section(callback, command)
        elif command.startswith("queue_"):
            await handle_queue_action(callback, command)
        elif command.startswith("analytics_"):
            await handle_analytics_action(callback, command)
        elif command.startswith("content_"):
            await handle_content_action(callback, command)
        elif command.startswith("system_"):
            await handle_system_action(callback, command)
        elif command.startswith("schedule_"):
            await handle_schedule_action(callback, command)
        elif command.startswith("management_"):
            await handle_management_action(callback, command)
        elif command.startswith("add_search_"):
            # Добавление товара из результатов поиска в очередь
            try:
                idx_str = command.replace("add_search_", "")
                idx = int(idx_str) - 1

                user_id = callback.from_user.id
                state = user_states.get(user_id, {})
                search_results = state.get("search_results", [])

                if not search_results or idx < 0 or idx >= len(search_results):
                    await callback.answer(
                        "⚠️ Товар не найден в результатах поиска", show_alert=True
                    )
                    return

                product = search_results[idx]
                url = product.get("url", "")

                if not url:
                    await callback.answer("❌ Неверный URL товара", show_alert=True)
                    return

                # Проверяем валидность URL
                from bot import validate_product_url

                is_valid, reason = validate_product_url(url)
                if not is_valid:
                    await callback.answer(f"❌ Неверный URL: {reason}", show_alert=True)
                    return

                # Проверяем, нет ли уже в очереди (Problem #1: add normalization)
                if db.exists_url(url, check_normalized=True):
                    await callback.answer("⚠️ Товар уже в истории", show_alert=True)
                    return

                # Добавляем в очередь
                if db.add_to_queue(url):
                    await callback.answer(
                        f"✅ Товар #{idx + 1} добавлен в очередь", show_alert=True
                    )
                    logger.info(
                        f"Admin {user_id} added product from search to queue: {url[:100]}"
                    )
                else:
                    await callback.answer("⚠️ Товар уже в очереди", show_alert=True)
            except (ValueError, IndexError) as e:
                await callback.answer("❌ Неверный индекс товара", show_alert=True)
            except Exception as e:
                logger.exception("add_search error: %s", e)
                await callback.answer(f"❌ Ошибка: {str(e)[:100]}", show_alert=True)
        elif command.startswith("post_now_"):
            # Срочная публикация товара по task_id
            task_id_str = command.replace("post_now_", "")
            try:
                task_id = int(task_id_str)
                queue_items = db.get_queue_urls(limit=1000)
                url_to_publish = None
                for tid, url in queue_items:
                    if tid == task_id:
                        url_to_publish = url
                        break

                if not url_to_publish:
                    await callback.answer(
                        "⚠️ Товар не найден в очереди", show_alert=True
                    )
                    return

                await callback.answer("⚡ Публикую срочно...", show_alert=False)
                from bot import process_and_publish

                success = await process_and_publish(
                    url_to_publish, callback.from_user.id
                )
                if success:
                    db.mark_as_done(task_id)
                    await safe_edit_callback_message(
                        callback,
                        f"✅ <b>Товар опубликован!</b>\n\n"
                        f"🔗 {url_to_publish[:60]}...",
                        parse_mode=ParseMode.HTML,
                    )
                    await callback.answer("✅ Опубликовано!", show_alert=True)
                else:
                    await safe_edit_callback_message(
                        callback,
                        f"❌ <b>Ошибка публикации</b>\n\n"
                        f"🔗 {url_to_publish[:60]}...",
                        parse_mode=ParseMode.HTML,
                    )
                    await callback.answer("❌ Ошибка", show_alert=True)
            except ValueError:
                await callback.answer("❌ Неверный ID товара", show_alert=True)
            except Exception as e:
                logger.exception("post_now error: %s", e)
                await callback.answer(f"❌ Ошибка: {str(e)[:100]}", show_alert=True)

    # Обработчики кнопок товаров
    @dp.callback_query(F.data == "show_savings")
    @handle_errors("callback_savings")
    async def handle_show_savings(callback: types.CallbackQuery):
        """Показывает информацию об экономии"""
        await callback.answer("💰 Экономия отображается в цене выше!", show_alert=True)

    @dp.callback_query(F.data == "show_reviews")
    @handle_errors("callback_reviews")
    async def handle_show_reviews(callback: types.CallbackQuery):
        """Показывает отзывы о товаре"""
        # В будущем можно реализовать показ отзывов
        await callback.answer("💬 Отзывы доступны на сайте Маркета", show_alert=True)

    @dp.callback_query(F.data == "show_similar")
    @handle_errors("callback_similar")
    async def handle_show_similar(callback: types.CallbackQuery):
        """Показывает похожие товары"""
        await callback.answer("🔍 Ищем похожие товары...", show_alert=True)

    @dp.callback_query(F.data == "add_favorite")
    @handle_errors("callback_favorite")
    async def handle_add_favorite(callback: types.CallbackQuery):
        """Добавляет товар в избранное"""
        await callback.answer("❤️ Добавлено в избранное!", show_alert=True)

    @dp.callback_query(F.data.startswith("category_"))
    @handle_errors("callback_category")
    async def handle_category_filter(callback: types.CallbackQuery):
        """Фильтрация по категориям"""
        category = callback.data.replace("category_", "")
        category_names = {
            "tech": "Техника",
            "food": "Еда",
            "clothing": "Одежда",
            "toys": "Игрушки",
            "books": "Книги",
            "cosmetics": "Косметика"
        }
        category_name = category_names.get(category, category)
        await callback.answer(f"📂 Фильтр: {category_name}", show_alert=True)

    @dp.callback_query(F.data.startswith("page_"))
    @handle_errors("callback_page")
    async def handle_page_navigation(callback: types.CallbackQuery):
        """Навигация по страницам"""
        page = callback.data.replace("page_", "")
        await callback.answer(f"📄 Страница {page}", show_alert=True)

    @dp.callback_query(F.data == "current_page")
    @handle_errors("callback_current_page")
    async def handle_current_page(callback: types.CallbackQuery):
        """Текущая страница"""
        await callback.answer("📍 Это текущая страница", show_alert=True)

    @dp.callback_query(F.data.startswith("remove_"))
    @admin_only
    @handle_errors("callback_remove")
    async def handle_remove_callback(callback: types.CallbackQuery):
        """Обработчик удаления из очереди"""
        task_id_str = callback.data.replace("remove_", "")
        try:
            task_id = int(task_id_str)
            if db.remove_from_queue(task_id=task_id):
                await callback.answer("✅ Удалено", show_alert=True)
                # Обновляем сообщение
                await safe_edit_callback_message(
                    callback,
                    "✅ <b>Товар удалён из очереди</b>",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await callback.answer("⚠️ Товар не найден", show_alert=True)
        except ValueError:
            await callback.answer("❌ Неверный ID", show_alert=True)
        except Exception as e:
            logger.exception("remove callback error: %s", e)
            await callback.answer(f"❌ Ошибка: {str(e)[:100]}", show_alert=True)
