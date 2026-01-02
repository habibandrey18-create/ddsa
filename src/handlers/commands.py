# handlers/commands.py
"""Обработчики команд бота"""
from typing import Optional
from aiogram import Bot, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging
import src.config as config
from database import Database
from decorators import admin_only, handle_errors

logger = logging.getLogger(__name__)


def register_commands_handlers(
    dp, bot: Bot, db: Database, user_states: dict, schedule_settings: dict
):
    """Регистрирует обработчики команд"""

    @dp.message(Command("start"))
    @handle_errors("command_start")
    async def cmd_start(message: types.Message):
        is_admin = message.from_user.id == config.ADMIN_ID

        text = "👋 Привет! Я бот-постер для Яндекс.Маркета.\n\n"
        text += "<b>Основные команды:</b>\n"
        text += "/info — статус очереди\n"

        if is_admin:
            text += "\n<b>Админ панель:</b>\n"
            text += "Используйте кнопки ниже или команды:\n"
            text += "/post, /q, /stats, /clear, /remove\n"
            text += "/help — подробная справка"

            from bot import create_main_keyboard

            keyboard = create_main_keyboard()
            await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        else:
            await message.answer(
                text
                + "\n\nТакже можно прислать .txt с ссылками (одна ссылка на строку).",
                parse_mode=ParseMode.HTML,
            )

    @dp.message(Command("help"))
    @admin_only
    @handle_errors("command_help")
    async def cmd_help(message: types.Message):
        """Справка по командам"""
        help_text = (
            "📖 <b>Справка по командам</b>\n\n"
            "<b>Управление постами:</b>\n"
            "/post &lt;url&gt; — опубликовать сейчас\n"
            "/q &lt;url&gt; [priority] [time] — добавить в очередь\n"
            "/test_post &lt;url&gt; — предпросмотр\n"
            "/force_post — срочная публикация\n"
            "/batch &lt;N&gt; — пакетная обработка\n\n"
            "<b>Очередь:</b>\n"
            "/clear — очистить очередь\n"
            "/remove — удалить (с выбором)\n"
            "/next [N] — следующие товары\n"
            "/duplicates — поиск дубликатов\n\n"
            "<b>Аналитика:</b>\n"
            "/stats — статистика\n"
            "/analytics — детальная аналитика\n"
            "/trends — анализ трендов\n"
            "/history [N] — история\n"
            "/export — экспорт данных\n\n"
            "<b>Контент:</b>\n"
            "/ideas [N] — идеи для постов\n"
            "/compilation [N] — создать подборку\n"
            "/random — случайный товар\n"
            "/discounts — товары со скидками\n"
            "/search &lt;запрос&gt; — поиск\n\n"
            "<b>Система:</b>\n"
            "/status — статус бота\n"
            "/health — проверка здоровья\n"
            "/disk — место на диске\n"
            "/cleanup — автоочистка\n"
            "/schedule — расписание\n"
            "/version — версия\n\n"
            "<b>Сбор ссылок:</b>\n"
            "/collect_links [N] — собрать ссылки через браузер\n"
            "/collect_links_file — собрать ссылки и сохранить в файл\n\n"
            "<b>Управление:</b>\n"
            "/restart — перезапуск\n"
            "/reload_config — перезагрузка конфига\n"
            "/log — логи\n"
            "/blacklist — черный список\n"
            "/qr &lt;url&gt; — QR-код\n\n"
            "<b>Файлы:</b>\n"
            "Отправьте .txt файл с ссылками (одна ссылка на строку) для добавления в очередь"
        )
        await message.answer(help_text, parse_mode=ParseMode.HTML)

    @dp.message(Command("collect_links"))
    @admin_only
    @handle_errors("command_collect_links")
    async def cmd_collect_links(message: types.Message):
        """Сбор ссылок через браузер"""
        args = message.text.split()
        max_products = 50
        if len(args) > 1:
            try:
                max_products = min(int(args[1]), 100)
            except ValueError:
                pass

        referral_url = "https://market.yandex.ru/page/referral_products?generalContext=t%3DcprPage%3Bcpk%3Dreferral_products%3B&rs=eJwzEv7EKMDBKLDwEKsEg8bqk6waP06xAgA8ewZy"

        await message.answer(
            f"🎁 Начинаю сбор ссылок...\n"
            f"📊 Максимум товаров: {max_products}\n"
            f"⏳ Это может занять несколько минут..."
        )

        try:
            from src.services.referral_link_collector import ReferralLinkCollector

            collector = ReferralLinkCollector()

            # Запускаем сбор в фоне
            import asyncio

            collected_links = await collector.collect_links(referral_url, max_products)

            if collected_links:
                # Сохраняем в файл
                output_file = collector.save_links_to_file(collected_links)

                await message.answer(
                    f"✅ Сбор завершен!\n"
                    f"📊 Собрано ссылок: {len(collected_links)}\n"
                    f"💾 Сохранено в: {output_file}\n\n"
                    f"Отправьте файл {output_file} боту для добавления ссылок в очередь."
                )
            else:
                await message.answer("❌ Не удалось собрать ссылки. Проверьте логи.")
        except Exception as e:
            logger.exception("Collect links error: %s", e)
            await message.answer(f"❌ Ошибка сбора ссылок: {str(e)[:200]}")

    @dp.message(Command("collect_links_file"))
    @admin_only
    @handle_errors("command_collect_links_file")
    async def cmd_collect_links_file(message: types.Message):
        """Сбор ссылок и автоматическое добавление в очередь"""
        args = message.text.split()
        max_products = 50
        if len(args) > 1:
            try:
                max_products = min(int(args[1]), 100)
            except ValueError:
                pass

        referral_url = "https://market.yandex.ru/page/referral_products?generalContext=t%3DcprPage%3Bcpk%3Dreferral_products%3B&rs=eJwzEv7EKMDBKLDwEKsEg8bqk6waP06xAgA8ewZy"

        await message.answer(
            f"🎁 Начинаю сбор ссылок...\n"
            f"📊 Максимум товаров: {max_products}\n"
            f"⏳ Это может занять несколько минут..."
        )

        try:
            from src.services.referral_link_collector import ReferralLinkCollector

            collector = ReferralLinkCollector()

            collected_links = await collector.collect_links(referral_url, max_products)

            if collected_links:
                # Сохраняем в файл
                output_file = collector.save_links_to_file(collected_links)

                # Добавляем в очередь
                added = 0
                skipped = 0
                for url in collected_links:
                    if db.exists_url(
                        url, check_normalized=True
                    ):  # Problem #1: add normalization
                        skipped += 1
                        continue
                    if db.add_to_queue(url):
                        added += 1

                await message.answer(
                    f"✅ Сбор и добавление завершены!\n"
                    f"📊 Собрано ссылок: {len(collected_links)}\n"
                    f"✅ Добавлено в очередь: {added}\n"
                    f"⏭️ Пропущено (уже опубликовано): {skipped}\n"
                    f"💾 Сохранено в: {output_file}"
                )
            else:
                await message.answer("❌ Не удалось собрать ссылки. Проверьте логи.")
        except Exception as e:
            logger.exception("Collect links error: %s", e)
            await message.answer(f"❌ Ошибка сбора ссылок: {str(e)[:200]}")

    @dp.message(Command("history"))
    @admin_only
    @handle_errors("command_history")
    async def cmd_history(message: types.Message):
        """История публикаций"""
        args = message.text.split()
        limit = 10
        if len(args) > 1:
            try:
                limit = min(int(args[1]), 50)
            except ValueError:
                pass

        history = db.get_history(limit=limit)
        if not history:
            await message.answer("📭 История пуста.")
            return

        text = f"📜 <b>История публикаций (последние {len(history)}):</b>\n\n"
        for idx, item in enumerate(history, 1):
            title = item.get("title", "Без названия")[:50]
            url = item.get("url", "")[:60]
            date = item.get("date", "")[:10] if item.get("date") else "Неизвестно"
            text += f"{idx}. <b>{title}</b>\n"
            text += f"   🔗 {url}...\n"
            text += f"   📅 {date}\n\n"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📊 Больше (25)", callback_data="cmd_analytics_history_25"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="📊 Больше (50)", callback_data="cmd_analytics_history_50"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🏠 Главное меню", callback_data="cmd_main_menu"
                    )
                ],
            ]
        )
        await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)

    @dp.message(Command("export"))
    @admin_only
    @handle_errors("command_export")
    async def cmd_export(message: types.Message):
        """Экспорт данных в JSON"""
        await message.answer("💾 Экспортирую данные...")

        try:
            import json
            import os
            from datetime import datetime

            stats = db.get_stats()
            queue_items = db.get_queue_urls(limit=1000)
            history_items = db.get_history(limit=1000)

            export_data = {
                "export_date": datetime.now().isoformat(),
                "statistics": stats,
                "queue_count": len(queue_items),
                "queue_items": [
                    {"id": tid, "url": url} for tid, url in queue_items[:100]
                ],
                "history_count": len(history_items),
                "history_items": history_items[:100],
            }

            export_file = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(export_file, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)

            await message.answer_document(
                document=types.FSInputFile(export_file),
                caption="💾 <b>Экспорт данных</b>\n\nСтатистика, очередь и история товаров",
                parse_mode=ParseMode.HTML,
            )

            if os.path.exists(export_file):
                os.remove(export_file)
        except Exception as e:
            logger.exception("Export error: %s", e)
            await message.answer(f"❌ Ошибка экспорта: {str(e)[:200]}")

    @dp.message(Command("status"))
    @admin_only
    @handle_errors("command_status")
    async def cmd_status(message: types.Message):
        """Статус бота"""
        try:
            from datetime import datetime

            # Gather stats
            queue_count = db.get_queue_count()

            # Count rows in history where created_at is today
            today = datetime.utcnow().date()
            daily_count = db.get_stats().get("today", 0)

            # Check time of last successful auto_search run
            last_run_str = db.get_setting("last_auto_search_run", "")
            minutes_ago = "N/A"
            if last_run_str:
                try:
                    last_run = datetime.fromisoformat(
                        last_run_str.replace("Z", "+00:00")
                    )
                    time_diff = datetime.utcnow() - last_run
                    minutes_ago = int(time_diff.total_seconds() / 60)
                except (ValueError, TypeError):
                    try:
                        last_run = datetime.strptime(last_run_str, "%Y-%m-%d %H:%M:%S")
                        time_diff = datetime.utcnow() - last_run
                        minutes_ago = int(time_diff.total_seconds() / 60)
                    except (ValueError, TypeError):
                        minutes_ago = "N/A"

            # Format message
            status_text = (
                "📊 <b>Bot Status</b>\n"
                "🟢 System: Online\n"
                f"📦 Queue: {queue_count} items\n"
                f"📢 Posted Today: {daily_count}\n"
                f"🕒 Last Search: {minutes_ago} min ago"
            )

            await message.answer(status_text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.exception("Status command error: %s", e)
            await message.answer(f"❌ Ошибка получения статуса: {str(e)[:200]}")
