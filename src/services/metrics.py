# services/metrics.py
"""Метрики производительности для мониторинга работы бота"""
import time
import logging
from typing import Dict, Optional
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)


class Metrics:
    """Класс для сбора метрик производительности"""

    _instance: Optional["Metrics"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.counters = defaultdict(int)
        self.timers = defaultdict(list)
        self.errors = defaultdict(int)
        self.start_time = time.time()

    def increment(self, metric: str, value: int = 1):
        """Увеличивает счетчик метрики"""
        self.counters[metric] += value

    def record_time(self, metric: str, duration: float):
        """Записывает время выполнения операции"""
        self.timers[metric].append(duration)
        # Храним только последние 1000 значений
        if len(self.timers[metric]) > 1000:
            self.timers[metric] = self.timers[metric][-1000:]

    def record_error(self, metric: str):
        """Записывает ошибку"""
        self.errors[metric] += 1

    def get_stats(self) -> Dict:
        """Возвращает статистику"""
        stats = {
            "uptime_seconds": time.time() - self.start_time,
            "counters": dict(self.counters),
            "errors": dict(self.errors),
            "timers": {},
        }

        for metric, times in self.timers.items():
            if times:
                stats["timers"][metric] = {
                    "count": len(times),
                    "avg": sum(times) / len(times),
                    "min": min(times),
                    "max": max(times),
                    "p95": (
                        sorted(times)[int(len(times) * 0.95)]
                        if len(times) > 20
                        else max(times)
                    ),
                }

        return stats

    def log_summary(self):
        """Логирует сводку метрик"""
        stats = self.get_stats()
        logger.info("=" * 60)
        logger.info("METRICS SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Uptime: {stats['uptime_seconds']:.0f}s")
        logger.info(f"Counters: {stats['counters']}")
        logger.info(f"Errors: {stats['errors']}")
        for metric, timer_stats in stats["timers"].items():
            logger.info(
                f"{metric}: avg={timer_stats['avg']:.2f}s, min={timer_stats['min']:.2f}s, max={timer_stats['max']:.2f}s, p95={timer_stats['p95']:.2f}s"
            )
        logger.info("=" * 60)


class Timer:
    """Контекстный менеджер для измерения времени выполнения"""

    def __init__(self, metric: str, metrics: Optional[Metrics] = None):
        self.metric = metric
        self.metrics = metrics or Metrics()
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = time.time() - self.start_time
            self.metrics.record_time(self.metric, duration)
            if exc_type:
                self.metrics.record_error(self.metric)













