# services/scheduler_service.py
"""Сервис для планирования задач"""
import asyncio
from datetime import datetime, time as dt_time, timedelta
from typing import List, Callable, Optional
import logging

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self):
        self.tasks = []
        self.running = False

    def add_daily_task(self, hour: int, minute: int, callback: Callable):
        """Добавляет ежедневную задачу"""
        self.tasks.append(
            {"type": "daily", "hour": hour, "minute": minute, "callback": callback}
        )

    def add_interval_task(self, interval_seconds: int, callback: Callable):
        """Добавляет задачу с интервалом"""
        self.tasks.append(
            {"type": "interval", "interval": interval_seconds, "callback": callback}
        )

    async def start(self):
        """Запускает планировщик"""
        self.running = True
        while self.running:
            now = datetime.now()

            for task in self.tasks:
                if task["type"] == "daily":
                    target_time = datetime.combine(
                        now.date(), dt_time(task["hour"], task["minute"])
                    )
                    if target_time < now:
                        target_time += timedelta(days=1)

                    if (
                        abs((target_time - now).total_seconds()) < 60
                    ):  # В пределах минуты
                        try:
                            await task["callback"]()
                        except Exception as e:
                            logger.exception("Scheduled task error: %s", e)

            await asyncio.sleep(60)  # Проверяем каждую минуту

    def stop(self):
        """Останавливает планировщик"""
        self.running = False
