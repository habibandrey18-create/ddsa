# services/automation_service.py
"""Сервис для автоматизации задач бота"""
import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AutomationService:
    """Сервис для автоматизации различных задач"""

    def __init__(self, db, bot=None):
        self.db = db
        self.bot = bot
        self._running = False
        self._tasks = []

    async def start(self):
        """Запуск сервиса автоматизации"""
        if self._running:
            logger.warning("AutomationService already running")
            return

        self._running = True
        logger.info("🚀 AutomationService started")

        # Запускаем фоновые задачи
        self._tasks = [
            asyncio.create_task(self._auto_cleanup_worker()),
            asyncio.create_task(self._health_check_worker()),
        ]

    async def stop(self):
        """Остановка сервиса автоматизации"""
        self._running = False

        # Отменяем все задачи
        for task in self._tasks:
            task.cancel()

        # Ждём завершения
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("🛑 AutomationService stopped")

    async def _auto_cleanup_worker(self):
        """Автоматическая очистка старых данных"""
        while self._running:
            try:
                # Очистка каждые 6 часов
                await asyncio.sleep(6 * 3600)

                if not self._running:
                    break

                logger.info("🧹 Starting auto cleanup...")

                # Очистка старого кэша
                try:
                    self.db.clear_old_cache(max_age_hours=48)
                    logger.info("✅ Old cache cleaned")
                except Exception as e:
                    logger.error(f"❌ Cache cleanup error: {e}")

                # Очистка старых ошибок (старше 7 дней)
                try:
                    cutoff = datetime.utcnow() - timedelta(days=7)
                    # Здесь нужен метод в database.py для очистки старых ошибок
                    # Пока просто логируем
                    logger.debug("Old errors cleanup skipped (method not implemented)")
                except Exception as e:
                    logger.error(f"❌ Errors cleanup error: {e}")

                logger.info("✅ Auto cleanup completed")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"❌ Auto cleanup worker error: {e}")
                await asyncio.sleep(3600)  # Повтор через час при ошибке

    async def _health_check_worker(self):
        """Периодическая проверка здоровья системы"""
        while self._running:
            try:
                # Проверка каждые 30 минут
                await asyncio.sleep(30 * 60)

                if not self._running:
                    break

                logger.debug("❤️ Health check...")

                # Проверка БД
                try:
                    count = self.db.get_queue_count()
                    stats = self.db.get_stats()
                    logger.debug(
                        f"Health: queue={count}, published={stats.get('published', 0)}"
                    )
                except Exception as e:
                    logger.error(f"❌ Health check DB error: {e}")

                # Проверка бота (если доступен)
                if self.bot:
                    try:
                        await self.bot.get_me()
                        logger.debug("✅ Bot is healthy")
                    except Exception as e:
                        logger.error(f"❌ Health check bot error: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"❌ Health check worker error: {e}")
                await asyncio.sleep(600)  # Повтор через 10 минут при ошибке

    async def auto_retry_failed_tasks(self, max_retries: int = 3):
        """Автоматический повтор неудачных задач"""
        try:
            # Получаем задачи со статусом 'error'
            # Здесь нужен метод в database.py для получения ошибок
            # Пока просто логируем
            logger.info("🔄 Auto retry failed tasks (not fully implemented)")
        except Exception as e:
            logger.exception(f"❌ Auto retry error: {e}")


# Глобальный экземпляр
_automation_service: Optional[AutomationService] = None


def get_automation_service(db, bot=None) -> AutomationService:
    """Получить глобальный экземпляр сервиса автоматизации"""
    global _automation_service
    if _automation_service is None:
        _automation_service = AutomationService(db, bot)
    return _automation_service
