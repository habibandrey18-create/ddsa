# services/cleanup_service.py
"""Сервис для очистки старых постов с мертвыми ссылками"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import re

logger = logging.getLogger(__name__)


async def check_url_is_dead(url: str, http_client) -> Tuple[bool, Optional[str]]:
    """
    Проверяет, является ли URL мертвым (404 или "Out of stock").

    Args:
        url: URL для проверки
        http_client: Экземпляр HTTPClient для выполнения запросов

    Returns:
        Tuple (is_dead: bool, reason: Optional[str])
        - is_dead: True если ссылка мертвая
        - reason: Причина (например, "404", "out_of_stock", "timeout")
    """
    try:
        # Выполняем GET запрос
        resp = await http_client.get(url, max_retries=2)

        if resp is None:
            # Не удалось получить ответ (timeout, network error)
            logger.debug(
                f"check_url_is_dead: Failed to fetch {url[:100]} (timeout/network error)"
            )
            return True, "timeout"

        # Проверяем статус код
        if resp.status == 404:
            logger.debug(f"check_url_is_dead: 404 for {url[:100]}")
            resp.close()
            return True, "404"

        # Проверяем содержимое страницы на наличие текста "Out of stock" или "Нет в наличии"
        if resp.status == 200:
            try:
                text = await resp.text()
                resp.close()

                # Проверяем на различные варианты текста "нет в наличии"
                out_of_stock_patterns = [
                    r"нет\s+в\s+наличии",
                    r"out\s+of\s+stock",
                    r"товар\s+закончился",
                    r"товар\s+недоступен",
                    r"распродан",
                    r"снят\s+с\s+продажи",
                    r"не\s+доступен\s+для\s+заказа",
                ]

                text_lower = text.lower()
                for pattern in out_of_stock_patterns:
                    if re.search(pattern, text_lower, re.IGNORECASE):
                        logger.debug(
                            f"check_url_is_dead: Out of stock detected for {url[:100]}"
                        )
                        return True, "out_of_stock"

                # Ссылка живая
                return False, None

            except Exception as e:
                logger.warning(
                    f"check_url_is_dead: Error reading response text for {url[:100]}: {e}"
                )
                resp.close()
                # Если не удалось прочитать текст, считаем ссылку живой (консервативный подход)
                return False, None

        # Другие статус коды (403, 500, etc.) - считаем ссылку живой
        resp.close()
        return False, None

    except Exception as e:
        logger.exception(
            f"check_url_is_dead: Unexpected error checking {url[:100]}: {e}"
        )
        # При ошибке считаем ссылку живой (консервативный подход)
        return False, None


async def cleanup_old_posts(
    db, bot_instance, channel_id: str, hours_threshold: int = 48
) -> Dict[str, int]:
    """
    Очищает старые посты с мертвыми ссылками.

    Args:
        db: Экземпляр Database
        bot_instance: Экземпляр бота (aiogram Bot)
        channel_id: ID канала для удаления сообщений
        hours_threshold: Минимальный возраст поста в часах для проверки (по умолчанию 48)

    Returns:
        Dict с статистикой: {
            'checked': количество проверенных постов,
            'deleted': количество удаленных постов,
            'errors': количество ошибок
        }
    """
    from src.services.http_client import HTTPClient

    stats = {"checked": 0, "deleted": 0, "errors": 0}

    try:
        logger.info(
            f"🧹 Starting cleanup of old posts (threshold: {hours_threshold} hours)"
        )

        # Получаем посты старше указанного порога
        old_posts = db.get_old_posts_for_cleanup(hours_threshold=hours_threshold)

        if not old_posts:
            logger.info("🧹 No old posts found to check")
            return stats

        logger.info(f"🧹 Found {len(old_posts)} old posts to check")

        # Создаем HTTP клиент
        http_client = HTTPClient()

        try:
            for post in old_posts:
                stats["checked"] += 1

                post_id = post["id"]
                url = post["url"]
                message_id = post.get("message_id")
                channel_id_from_db = post.get("channel_id")

                # Пропускаем если нет message_id или channel_id
                if not message_id or not channel_id_from_db:
                    logger.debug(
                        f"🧹 Skipping post {post_id}: missing message_id or channel_id"
                    )
                    continue

                # Используем channel_id из БД, если он есть, иначе используем переданный
                target_channel_id = (
                    channel_id_from_db if channel_id_from_db else channel_id
                )

                logger.debug(f"🧹 Checking post {post_id}: {url[:100]}...")

                # Проверяем, мертвая ли ссылка
                is_dead, reason = await check_url_is_dead(url, http_client)

                if is_dead:
                    logger.info(
                        f"🧹 Dead link detected for post {post_id} (reason: {reason}): {url[:100]}"
                    )

                    # Удаляем сообщение из канала
                    try:
                        await bot_instance.delete_message(
                            chat_id=target_channel_id, message_id=message_id
                        )
                        logger.info(
                            f"✅ Deleted message {message_id} from channel {target_channel_id} "
                            f"(post_id: {post_id})"
                        )
                    except Exception as e:
                        error_msg = str(e)
                        # Игнорируем ошибку если сообщение уже удалено
                        if (
                            "message to delete not found" not in error_msg.lower()
                            and "bad request: message can't be deleted"
                            not in error_msg.lower()
                        ):
                            logger.warning(
                                f"⚠️ Failed to delete message {message_id} from channel {target_channel_id}: {e}"
                            )
                            stats["errors"] += 1
                        else:
                            logger.debug(
                                f"ℹ️ Message {message_id} already deleted or can't be deleted (post_id: {post_id})"
                            )

                    # Помечаем запись как удаленную в истории
                    try:
                        db.mark_history_as_deleted(post_id)
                        stats["deleted"] += 1
                        logger.info(f"✅ Marked history entry {post_id} as deleted")
                    except Exception as e:
                        logger.warning(
                            f"⚠️ Failed to mark history entry {post_id} as deleted: {e}"
                        )
                        stats["errors"] += 1
                else:
                    logger.debug(f"✅ Link is alive for post {post_id}: {url[:100]}")

        finally:
            # Закрываем HTTP клиент
            await http_client.close()

        logger.info(
            f"🧹 Cleanup completed: checked={stats['checked']}, "
            f"deleted={stats['deleted']}, errors={stats['errors']}"
        )

    except Exception as e:
        logger.exception(f"❌ Error in cleanup_old_posts: {e}")
        stats["errors"] += 1

    return stats


async def cleanup_worker(
    db,
    bot_instance,
    channel_id: str,
    interval_hours: int = 24,
    hours_threshold: int = 48,
):
    """
    Фоновый воркер для периодической очистки старых постов.

    Args:
        db: Экземпляр Database
        bot_instance: Экземпляр бота (aiogram Bot)
        channel_id: ID канала для удаления сообщений
        interval_hours: Интервал между запусками очистки в часах (по умолчанию 24)
        hours_threshold: Минимальный возраст поста в часах для проверки (по умолчанию 48)
    """
    import asyncio

    logger.info(
        f"🔄 Cleanup worker запущен "
        f"(интервал: {interval_hours} часов, threshold: {hours_threshold} часов)"
    )

    # Ждем немного перед первой очисткой, чтобы бот успел запуститься
    await asyncio.sleep(3600)  # 1 час

    while True:
        try:
            logger.info("🧹 Запуск запланированной очистки старых постов...")
            stats = await cleanup_old_posts(
                db, bot_instance, channel_id, hours_threshold
            )

            logger.info(
                f"✅ Запланированная очистка завершена: "
                f"проверено={stats['checked']}, удалено={stats['deleted']}, ошибок={stats['errors']}"
            )

        except Exception as e:
            logger.exception(f"❌ Ошибка в cleanup_worker: {e}")

        # Ждем указанный интервал перед следующей очисткой
        await asyncio.sleep(interval_hours * 3600)  # Конвертируем часы в секунды
