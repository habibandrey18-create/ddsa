# handlers/messages.py
"""Обработчики текстовых сообщений"""
from typing import Dict, Any, Optional
from aiogram import Bot, types, F
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging
import config
from database import Database
from decorators import admin_only, handle_errors

logger = logging.getLogger(__name__)


def register_messages_handlers(dp, bot: Bot, db: Database, user_states: dict):
    """Регистрирует обработчики текстовых сообщений"""

    @dp.message(F.text & ~F.text.startswith("/"))
    @handle_errors("message_text")
    async def handle_text_input(message: types.Message):
        """Обработка текстового ввода для интерактивных команд"""
        if message.from_user.id != config.ADMIN_ID:
            return

        user_id = message.from_user.id
        state = user_states.get(user_id, {})

        if not state:
            return  # Нет активного состояния

        state_type = state.get("state")
        text = message.text.strip()

        if state_type == "waiting_qr_url" or state_type == "waiting_for_qr_url":
            # Генерация QR-кода
            user_states.pop(user_id, None)
            if not text.startswith("http"):
                await message.answer(
                    "❌ Неверный URL. Введите корректную ссылку вида https://..."
                )
                return

            from bot import generate_and_send_qr

            await generate_and_send_qr(message, text)
            return

        if state_type == "waiting_search_query":
            # Поиск товаров
            if len(text) < 2:
                await message.answer("❌ Запрос слишком короткий. Минимум 2 символа.")
                return

            await message.answer(f"🔍 Ищу товары по запросу: {text}...")

            try:
                from services.auto_search_service import AutoSearchService

                search_service = AutoSearchService(db, bot)
                products = await search_service.search_products(text, max_results=20)

                if not products:
                    await message.answer(
                        f"📭 По запросу '{text}' ничего не найдено.\n"
                        f"Попробуйте другой запрос или используйте автопоиск."
                    )
                else:
                    text_result = f"🔍 <b>Найдено товаров: {len(products)}</b>\n\n"
                    keyboard_buttons = []

                    for idx, product in enumerate(products[:10], 1):
                        title = product.get("title", "Без названия")[:50]
                        url = product.get("url", "")
                        text_result += f"{idx}. <b>{title}</b>\n"
                        text_result += f"   🔗 {url[:60]}...\n\n"

                        # Кнопка для добавления в очередь
                        if idx <= 5:  # Первые 5 товаров
                            keyboard_buttons.append(
                                [
                                    InlineKeyboardButton(
                                        text=f"➕ Добавить {idx}",
                                        callback_data=f"cmd_add_search_{idx}",
                                    )
                                ]
                            )

                    if len(products) > 10:
                        text_result += f"... и еще {len(products) - 10} товаров"

                    # Сохраняем результаты поиска во временное хранилище
                    if user_id not in user_states:
                        user_states[user_id] = {}
                    user_states[user_id]["search_results"] = products

                    keyboard_buttons.append(
                        [
                            InlineKeyboardButton(
                                text="🏠 Главное меню", callback_data="cmd_main_menu"
                            )
                        ]
                    )

                    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
                    await message.answer(
                        text_result, reply_markup=keyboard, parse_mode=ParseMode.HTML
                    )
            except Exception as e:
                logger.exception("Search error: %s", e)
                await message.answer(
                    f"❌ Ошибка поиска: {str(e)[:200]}\n"
                    f"Попробуйте позже или используйте автопоиск."
                )

            # Очищаем состояние
            user_states.pop(user_id, None)

        elif state_type == "waiting_schedule_hours":
            # Настройка часов расписания
            try:
                hours = [
                    int(h.strip())
                    for h in text.split(",")
                    if h.strip().isdigit() and 0 <= int(h.strip()) <= 23
                ]
                if not hours:
                    await message.answer(
                        "❌ Неверный формат. Введите часы от 0 до 23 через запятую (например: 9,12,15,18)"
                    )
                    return

                from services.state_service import get_global_settings

                global_settings = get_global_settings()
                global_settings.update_schedule_settings(hours=sorted(set(hours)))
                schedule_settings = global_settings.get_schedule_settings()
                hours_text = ", ".join(
                    [f"{h:02d}:00" for h in schedule_settings["hours"]]
                )
                await message.answer(f"✅ Часы установлены: {hours_text}")
                user_states.pop(user_id, None)

                # Показываем обновленные настройки
                from bot import show_schedule_settings

                # Создаем фиктивный callback для показа настроек
                class FakeCallback:
                    def __init__(self, message):
                        self.message = message
                        self.from_user = message.from_user

                fake_callback = FakeCallback(message)
                await show_schedule_settings(fake_callback)
            except ValueError:
                await message.answer(
                    "❌ Ошибка: неверный формат. Введите числа от 0 до 23 через запятую"
                )

        elif state_type == "waiting_schedule_interval":
            # Настройка интервала
            try:
                interval = int(text.strip())
                if interval < 60:
                    await message.answer("❌ Интервал должен быть не менее 60 секунд")
                    return

                from services.state_service import get_global_settings

                global_settings = get_global_settings()
                global_settings.update_schedule_settings(interval=interval)
                schedule_settings = global_settings.get_schedule_settings()
                interval_text = (
                    f"{interval // 60} мин"
                    if interval < 3600
                    else f"{interval // 3600} ч"
                )
                await message.answer(f"✅ Интервал установлен: {interval_text}")
                user_states.pop(user_id, None)

                # Показываем обновленные настройки
                from bot import show_schedule_settings

                class FakeCallback:
                    def __init__(self, message):
                        self.message = message
                        self.from_user = message.from_user

                fake_callback = FakeCallback(message)
                await show_schedule_settings(fake_callback)
            except ValueError:
                await message.answer("❌ Ошибка: введите число (интервал в секундах)")

    @dp.message(F.document)
    @admin_only
    @handle_errors("message_document")
    async def handle_file(message: types.Message):
        """Обработка файлов с URL"""
        doc = message.document
        if not doc.file_name or not doc.file_name.endswith(".txt"):
            await message.answer("❌ Пришлите .txt файл")
            return

        # Безопасность: ограничение размера файла (1MB)
        if doc.file_size and doc.file_size > 1024 * 1024:
            await message.answer("❌ Файл слишком большой (максимум 1MB)")
            return

        try:
            file = await bot.get_file(doc.file_id)
            io_obj = await bot.download_file(file.file_path)
            content = io_obj.read().decode("utf-8", errors="ignore")

            # Валидация и фильтрация URL
            lines = content.splitlines()
            urls = []
            invalid_count = 0
            skipped_count = 0

            for line in lines:
                line = line.strip()
                # Пропускаем комментарии и пустые строки
                if not line or line.startswith("#"):
                    continue

                if line.startswith("http"):
                    # Проверяем валидность URL
                    from bot import is_valid_product_url

                    is_valid, error_msg = is_valid_product_url(line)
                    if is_valid:
                        # Проверяем, не опубликован ли уже товар (Problem #1: add normalization)
                        if db.exists_url(line, check_normalized=True):
                            skipped_count += 1
                            continue
                        urls.append(line)
                    else:
                        invalid_count += 1

            if not urls:
                await message.answer(
                    f"❌ В файле нет валидных URL Яндекс.Маркета\n"
                    f"⚠️ Невалидных: {invalid_count}\n"
                    f"⏭️ Пропущено (уже опубликовано): {skipped_count}"
                )
                return

            # Добавляем в очередь
            added = 0
            already_in_queue = 0
            for url in urls:
                queue_id = db.add_to_queue(url)
                if queue_id:
                    added += 1
                else:
                    already_in_queue += 1

            text = f"✅ Добавлено в очередь: {added} товаров"
            if already_in_queue > 0:
                text += f"\n⏭️ Уже в очереди: {already_in_queue}"
            if skipped_count > 0:
                text += f"\n⏭️ Пропущено (уже опубликовано): {skipped_count}"
            if invalid_count > 0:
                text += f"\n⚠️ Пропущено невалидных: {invalid_count}"

            await message.answer(text)
        except Exception as e:
            logger.exception("File processing error: %s", e)
            await message.answer(f"❌ Ошибка обработки файла: {str(e)[:200]}")
