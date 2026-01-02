"""
AI Metrics - метрики и мониторинг работы AI
"""

import logging
import time
from typing import Dict, Any, Optional
from collections import defaultdict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AiMetrics:
    """
    Метрики работы AI обогащения
    """

    def __init__(self):
        """Инициализация метрик"""
        self.counters = defaultdict(int)
        self.timings = []
        self.costs = []  # Условная стоимость в токенах/рублях
        self.last_reset = time.time()
        self.hourly_stats = defaultdict(
            lambda: {"ai_ok": 0, "ai_error": 0, "ai_fallback": 0}
        )

    def record_ai_ok(self, tokens: int = 0, cost: float = 0.0):
        """Записать успешное AI обогащение"""
        self.counters["ai_ok"] += 1
        hour_key = datetime.now().strftime("%Y-%m-%d-%H")
        self.hourly_stats[hour_key]["ai_ok"] += 1
        if tokens > 0:
            self.costs.append(
                {"tokens": tokens, "cost": cost, "timestamp": time.time()}
            )

    def record_ai_error(self, error_type: str = "unknown"):
        """Записать ошибку AI"""
        self.counters["ai_error"] += 1
        self.counters[f"ai_error_{error_type}"] += 1
        hour_key = datetime.now().strftime("%Y-%m-%d-%H")
        self.hourly_stats[hour_key]["ai_error"] += 1

    def record_ai_fallback(self, reason: str = "unknown"):
        """Записать fallback на парсер"""
        self.counters["ai_fallback"] += 1
        self.counters[f"ai_fallback_{reason}"] += 1
        hour_key = datetime.now().strftime("%Y-%m-%d-%H")
        self.hourly_stats[hour_key]["ai_fallback"] += 1

    def record_timing(self, duration_ms: float):
        """Записать время выполнения AI запроса"""
        self.timings.append(duration_ms)
        # Храним только последние 1000 записей
        if len(self.timings) > 1000:
            self.timings = self.timings[-1000:]

    def get_stats(self) -> Dict[str, Any]:
        """
        Получить статистику

        Returns:
            Словарь со статистикой
        """
        total_requests = (
            self.counters["ai_ok"]
            + self.counters["ai_error"]
            + self.counters["ai_fallback"]
        )

        # Среднее время ответа
        avg_timing = sum(self.timings) / len(self.timings) if self.timings else 0

        # Общая стоимость за последние 24 часа
        now = time.time()
        recent_costs = [
            c for c in self.costs if now - c["timestamp"] < 86400  # 24 часа
        ]
        total_cost = sum(c["cost"] for c in recent_costs)
        total_tokens = sum(c["tokens"] for c in recent_costs)

        # Статистика за последний час
        current_hour = datetime.now().strftime("%Y-%m-%d-%H")
        hour_stats = self.hourly_stats.get(
            current_hour, {"ai_ok": 0, "ai_error": 0, "ai_fallback": 0}
        )
        hour_total = sum(hour_stats.values())
        hour_ai_ratio = (
            (hour_stats["ai_ok"] / hour_total * 100) if hour_total > 0 else 0
        )

        return {
            "total_requests": total_requests,
            "ai_ok": self.counters["ai_ok"],
            "ai_error": self.counters["ai_error"],
            "ai_fallback": self.counters["ai_fallback"],
            "ai_ok_ratio": (
                (self.counters["ai_ok"] / total_requests * 100)
                if total_requests > 0
                else 0
            ),
            "avg_timing_ms": avg_timing,
            "total_cost_24h": total_cost,
            "total_tokens_24h": total_tokens,
            "hour_stats": hour_stats,
            "hour_ai_ratio": hour_ai_ratio,
        }

    def should_disable_ai(self, daily_cost_limit: float = 100.0) -> bool:
        """
        Проверить, нужно ли отключить AI из-за превышения лимита

        Args:
            daily_cost_limit: Лимит стоимости за сутки

        Returns:
            True если нужно отключить AI
        """
        now = time.time()
        recent_costs = [
            c for c in self.costs if now - c["timestamp"] < 86400  # 24 часа
        ]
        total_cost = sum(c["cost"] for c in recent_costs)

        if total_cost > daily_cost_limit:
            logger.warning(
                f"Daily cost limit exceeded: {total_cost:.2f} > {daily_cost_limit:.2f}"
            )
            return True

        return False

    def reset(self):
        """Сбросить метрики"""
        self.counters.clear()
        self.timings.clear()
        self.costs.clear()
        self.last_reset = time.time()
        logger.info("AI metrics reset")


# Глобальный экземпляр метрик
_ai_metrics: Optional[AiMetrics] = None


def get_ai_metrics() -> AiMetrics:
    """
    Получить глобальный экземпляр метрик

    Returns:
        Экземпляр AiMetrics
    """
    global _ai_metrics
    if _ai_metrics is None:
        _ai_metrics = AiMetrics()
    return _ai_metrics
