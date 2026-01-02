"""
AI Worker - воркер для асинхронной обработки AI запросов
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime

from services.ai_enrichment_service import get_ai_enrichment_service
from services.ai_result_validator import ValidatedResult

logger = logging.getLogger(__name__)


@dataclass
class AiTask:
    """Задача для AI обогащения"""

    raw_data: Dict[str, Any]
    callback: Optional[Callable] = None
    task_id: Optional[str] = None
    created_at: Optional[datetime] = None


class AiWorker:
    """
    Воркер для обработки AI запросов в фоне
    """

    def __init__(self, max_concurrent: int = 3):
        """
        Инициализация воркера

        Args:
            max_concurrent: Максимальное количество одновременных запросов
        """
        self.max_concurrent = max_concurrent
        self.queue: asyncio.Queue = asyncio.Queue()
        self.running = False
        self.workers: list = []
        self.ai_service = get_ai_enrichment_service()

    async def add_task(
        self,
        raw_data: Dict[str, Any],
        callback: Optional[Callable] = None,
        task_id: Optional[str] = None,
    ) -> None:
        """
        Добавить задачу в очередь

        Args:
            raw_data: Сырые данные для обогащения
            callback: Функция обратного вызова (result, task_id)
            task_id: ID задачи
        """
        task = AiTask(
            raw_data=raw_data,
            callback=callback,
            task_id=task_id,
            created_at=datetime.now(),
        )
        await self.queue.put(task)
        logger.debug(f"AI task added to queue: {task_id}")

    async def _worker(self):
        """Воркер для обработки задач"""
        while self.running:
            try:
                # Получаем задачу с таймаутом
                try:
                    task = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                if not self.ai_service.enabled:
                    logger.debug("AI service disabled, skipping task")
                    if task.callback:
                        try:
                            await task.callback(None, task.task_id)
                        except Exception as e:
                            logger.error(f"Callback error: {e}")
                    continue

                try:
                    # Выполняем обогащение
                    result = await self.ai_service.enrich_product_safe(task.raw_data)

                    # Вызываем callback если есть
                    if task.callback:
                        try:
                            await task.callback(result, task.task_id)
                        except Exception as e:
                            logger.error(f"Callback error: {e}")

                except Exception as e:
                    logger.error(f"AI task error: {e}", exc_info=True)
                    if task.callback:
                        try:
                            await task.callback(None, task.task_id)
                        except Exception as callback_error:
                            logger.error(f"Callback error: {callback_error}")

                finally:
                    self.queue.task_done()

            except Exception as e:
                logger.error(f"Worker error: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def start(self):
        """Запустить воркер"""
        if self.running:
            return

        self.running = True
        self.workers = [
            asyncio.create_task(self._worker()) for _ in range(self.max_concurrent)
        ]
        logger.info(f"AI worker started with {self.max_concurrent} workers")

    async def stop(self):
        """Остановить воркер"""
        if not self.running:
            return

        self.running = False

        # Ждем завершения всех задач
        await self.queue.join()

        # Останавливаем воркеры
        for worker in self.workers:
            worker.cancel()

        await asyncio.gather(*self.workers, return_exceptions=True)
        logger.info("AI worker stopped")

    def get_queue_size(self) -> int:
        """Получить размер очереди"""
        return self.queue.qsize()


# Глобальный экземпляр воркера
_ai_worker: Optional[AiWorker] = None


def get_ai_worker() -> AiWorker:
    """
    Получить глобальный экземпляр воркера

    Returns:
        Экземпляр AiWorker
    """
    global _ai_worker
    if _ai_worker is None:
        _ai_worker = AiWorker()
    return _ai_worker
