# services/notification_service.py
"""Сервис для уведомлений"""
import asyncio
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, bot, admin_id: int):
        self.bot = bot
        self.admin_id = admin_id
        self.notification_queue = asyncio.Queue()
        self._worker_task = None

    async def send_notification(self, message: str, is_error: bool = False):
        """Отправляет уведомление администратору"""
        if self.admin_id:
            try:
                prefix = (
                    "🚨 КРИТИЧЕСКАЯ ОШИБКА:\n\n" if is_error else "ℹ️ Уведомление:\n\n"
                )
                await self.bot.send_message(self.admin_id, f"{prefix}{message}")
            except Exception as e:
                logger.error("Failed to send notification: %s", e)

    async def send_daily_summary(self, stats: dict):
        """Отправляет ежедневную сводку"""
        message = (
            f"📊 <b>Ежедневная сводка</b>\n\n"
            f"✅ Опубликовано: {stats.get('published', 0)}\n"
            f"⏳ В очереди: {stats.get('pending', 0)}\n"
            f"❌ Ошибок: {stats.get('errors', 0)}\n"
            f"🔄 Успешных сегодня: {stats.get('today', 0)}"
        )
        await self.send_notification(message)
