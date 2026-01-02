# services/backup_service.py
"""Сервис для создания резервных копий базы данных"""
import os
import shutil
import logging
from datetime import datetime
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


async def create_backup(
    admin_id: int, bot_instance, db_file_path: Optional[str] = None
) -> bool:
    """
    Создает резервную копию базы данных и отправляет её администратору через Telegram.

    Args:
        admin_id: ID администратора в Telegram
        bot_instance: Экземпляр бота (aiogram Bot)
        db_file_path: Путь к файлу базы данных (если None, используется config.DB_FILE)

    Returns:
        True если резервная копия успешно создана и отправлена, False в противном случае
    """
    try:
        # Импортируем config здесь, чтобы избежать циклических импортов
        import config

        # Определяем путь к базе данных
        if db_file_path is None:
            db_file_path = getattr(config, "DB_FILE", "bot_database.db")

        # Проверяем существование файла базы данных
        if not os.path.exists(db_file_path):
            logger.error(f"❌ Файл базы данных не найден: {db_file_path}")
            if admin_id and bot_instance:
                try:
                    await bot_instance.send_message(
                        admin_id,
                        f"❌ Ошибка резервного копирования: файл базы данных не найден\n"
                        f"Путь: {db_file_path}",
                    )
                except Exception as e:
                    logger.warning(f"Не удалось отправить сообщение об ошибке: {e}")
            return False

        # Создаем имя файла резервной копии с датой
        backup_dir = os.path.dirname(db_file_path) or "."
        timestamp = datetime.now().strftime("%Y_%m_%d")
        backup_filename = f"bot_backup_{timestamp}.db"
        backup_path = os.path.join(backup_dir, backup_filename)

        # Пытаемся создать резервную копию
        # SQLite поддерживает безопасное копирование при использовании WAL режима
        # Используем shutil.copy2 для сохранения метаданных
        try:
            logger.info(f"📦 Создание резервной копии: {db_file_path} -> {backup_path}")

            # Для SQLite с WAL режимом можно безопасно копировать файл
            # Но лучше использовать checkpoint для гарантии консистентности
            # Однако, для простоты используем прямое копирование
            # Если база заблокирована, это вызовет исключение

            # Пытаемся скопировать файл
            shutil.copy2(db_file_path, backup_path)
            logger.info(f"✅ Резервная копия создана: {backup_path}")

            # Проверяем размер файла
            backup_size = os.path.getsize(backup_path)
            if backup_size == 0:
                logger.error("❌ Резервная копия пуста!")
                os.remove(backup_path)
                return False

            logger.info(
                f"📊 Размер резервной копии: {backup_size / 1024 / 1024:.2f} MB"
            )

        except PermissionError as e:
            logger.error(f"❌ Ошибка доступа к файлу базы данных: {e}")
            if admin_id and bot_instance:
                try:
                    await bot_instance.send_message(
                        admin_id,
                        f"❌ Ошибка резервного копирования: файл базы данных заблокирован\n"
                        f"Ошибка: {str(e)[:200]}",
                    )
                except Exception:
                    pass
            return False
        except Exception as e:
            logger.exception(f"❌ Ошибка при создании резервной копии: {e}")
            if admin_id and bot_instance:
                try:
                    await bot_instance.send_message(
                        admin_id, f"❌ Ошибка резервного копирования: {str(e)[:200]}"
                    )
                except Exception:
                    pass
            return False

        # Отправляем файл администратору через Telegram
        if admin_id and bot_instance:
            try:
                from aiogram.types import FSInputFile

                logger.info(
                    f"📤 Отправка резервной копии администратору (ID: {admin_id})"
                )

                # Отправляем документ
                await bot_instance.send_document(
                    chat_id=admin_id,
                    document=FSInputFile(backup_path),
                    caption="📦 Daily Database Backup",
                )

                logger.info("✅ Резервная копия успешно отправлена администратору")

            except Exception as e:
                logger.exception(f"❌ Ошибка при отправке резервной копии: {e}")
                # Не удаляем файл, если не удалось отправить - может быть временная проблема
                if admin_id and bot_instance:
                    try:
                        await bot_instance.send_message(
                            admin_id,
                            f"⚠️ Резервная копия создана, но не отправлена\n"
                            f"Ошибка: {str(e)[:200]}\n"
                            f"Файл сохранен: {backup_path}",
                        )
                    except Exception:
                        pass
                return False

        # Удаляем локальный файл резервной копии после успешной отправки
        try:
            if os.path.exists(backup_path):
                os.remove(backup_path)
                logger.info(f"🗑️ Локальный файл резервной копии удален: {backup_path}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось удалить локальный файл резервной копии: {e}")
            # Это не критическая ошибка, файл можно удалить вручную

        return True

    except Exception as e:
        logger.exception(f"❌ Критическая ошибка в create_backup: {e}")
        if admin_id and bot_instance:
            try:
                await bot_instance.send_message(
                    admin_id,
                    f"❌ Критическая ошибка резервного копирования: {str(e)[:200]}",
                )
            except Exception:
                pass
        return False


async def backup_worker(
    admin_id: int,
    bot_instance,
    db_file_path: Optional[str] = None,
    interval_hours: int = 24,
):
    """
    Фоновый воркер для периодического создания резервных копий.

    Args:
        admin_id: ID администратора в Telegram
        bot_instance: Экземпляр бота (aiogram Bot)
        db_file_path: Путь к файлу базы данных
        interval_hours: Интервал между резервными копиями в часах (по умолчанию 24)
    """
    import asyncio

    logger.info(f"🔄 Backup worker запущен (интервал: {interval_hours} часов)")

    # Ждем немного перед первой резервной копией, чтобы бот успел запуститься
    await asyncio.sleep(60)  # 1 минута

    while True:
        try:
            logger.info("📦 Запуск запланированного резервного копирования...")
            success = await create_backup(admin_id, bot_instance, db_file_path)

            if success:
                logger.info(
                    "✅ Запланированное резервное копирование завершено успешно"
                )
            else:
                logger.warning(
                    "⚠️ Запланированное резервное копирование завершилось с ошибкой"
                )

        except Exception as e:
            logger.exception(f"❌ Ошибка в backup_worker: {e}")

        # Ждем указанный интервал перед следующей резервной копией
        await asyncio.sleep(interval_hours * 3600)  # Конвертируем часы в секунды













