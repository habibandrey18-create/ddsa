"""
Monitoring Service - Комплексный мониторинг системы и обнаружение проблем
Отслеживает производительность, ошибки и автоматически реагирует на проблемы
"""

import logging
import time
import asyncio
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque
import statistics

logger = logging.getLogger(__name__)


@dataclass
class MetricPoint:
    """Точка метрики для временного ряда"""
    timestamp: float
    value: float
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class AlertCondition:
    """Условие для алерта"""
    name: str
    condition_func: Callable[[Dict[str, Any]], bool]
    severity: str  # "low", "medium", "high", "critical"
    cooldown_minutes: int = 5
    last_triggered: float = 0


class MonitoringService:
    """
    Сервис комплексного мониторинга с автоматическим обнаружением проблем
    и реагированием на них
    """

    def __init__(self):
        self.metrics: Dict[str, deque] = {}
        self.alerts: List[AlertCondition] = []
        self.max_metric_history = 1000  # Максимум точек на метрику
        self.check_interval = 60  # Секунд между проверками

        # Автоматически настраиваем алерты
        self._setup_default_alerts()

    def _setup_default_alerts(self):
        """Настроить стандартные алерты"""

        # Алерт на низкий success rate парсинга
        self.add_alert(
            AlertCondition(
                name="low_parsing_success_rate",
                condition_func=lambda m: m.get('parsing_success_rate', 100) < 50,
                severity="high",
                cooldown_minutes=10
            )
        )

        # Алерт на большое количество CAPTCHA
        self.add_alert(
            AlertCondition(
                name="high_captcha_rate",
                condition_func=lambda m: m.get('captcha_rate', 0) > 20,
                severity="high",
                cooldown_minutes=5
            )
        )

        # Алерт на HTTP 429 ошибки
        self.add_alert(
            AlertCondition(
                name="high_429_rate",
                condition_func=lambda m: m.get('http_429_rate', 0) > 10,
                severity="medium",
                cooldown_minutes=15
            )
        )

        # Алерт на низкое качество прокси
        self.add_alert(
            AlertCondition(
                name="low_proxy_quality",
                condition_func=lambda m: m.get('avg_proxy_success_rate', 100) < 30,
                severity="medium",
                cooldown_minutes=20
            )
        )

        # Алерт на большой размер очереди
        self.add_alert(
            AlertCondition(
                name="queue_overflow",
                condition_func=lambda m: m.get('queue_size', 0) > 1000,
                severity="medium",
                cooldown_minutes=30
            )
        )

    def add_alert(self, alert: AlertCondition):
        """Добавить алерт"""
        self.alerts.append(alert)
        logger.info(f"Added alert: {alert.name} (severity: {alert.severity})")

    def record_metric(self, name: str, value: float, tags: Dict[str, str] = None):
        """
        Записать метрику

        Args:
            name: Имя метрики
            value: Значение
            tags: Теги для категоризации
        """
        if name not in self.metrics:
            self.metrics[name] = deque(maxlen=self.max_metric_history)

        point = MetricPoint(
            timestamp=time.time(),
            value=value,
            tags=tags or {}
        )

        self.metrics[name].append(point)

    def get_metric_avg(self, name: str, minutes: int = 5) -> Optional[float]:
        """
        Получить среднее значение метрики за период

        Args:
            name: Имя метрики
            minutes: Период в минутах

        Returns:
            Среднее значение или None
        """
        if name not in self.metrics:
            return None

        cutoff_time = time.time() - (minutes * 60)
        recent_points = [
            p.value for p in self.metrics[name]
            if p.timestamp >= cutoff_time
        ]

        return statistics.mean(recent_points) if recent_points else None

    def get_metric_rate(self, name: str, minutes: int = 5) -> Optional[float]:
        """
        Получить rate (скорость) метрики за период

        Args:
            name: Имя метрики
            minutes: Период в минутах

        Returns:
            Rate (значений в минуту) или None
        """
        if name not in self.metrics:
            return None

        cutoff_time = time.time() - (minutes * 60)
        recent_points = [
            p for p in self.metrics[name]
            if p.timestamp >= cutoff_time
        ]

        if len(recent_points) < 2:
            return None

        time_span = recent_points[-1].timestamp - recent_points[0].timestamp
        if time_span == 0:
            return 0

        return len(recent_points) / (time_span / 60)  # per minute

    def get_current_metrics(self) -> Dict[str, Any]:
        """
        Получить текущие метрики системы

        Returns:
            Словарь с метриками
        """
        metrics = {}

        # Метрики парсинга
        parsing_attempts = self.get_metric_rate('parsing_attempt', 5) or 0
        parsing_successes = self.get_metric_rate('parsing_success', 5) or 0

        if parsing_attempts > 0:
            metrics['parsing_success_rate'] = (parsing_successes / parsing_attempts) * 100
        else:
            metrics['parsing_success_rate'] = 100.0

        # Метрики CAPTCHA
        captcha_rate = self.get_metric_rate('captcha_detected', 5) or 0
        metrics['captcha_rate'] = captcha_rate

        # Метрики HTTP ошибок
        http_429_rate = self.get_metric_rate('http_429_error', 5) or 0
        metrics['http_429_rate'] = http_429_rate

        # Метрики прокси
        try:
            from services.proxy_service import get_proxy_service
            proxy_stats = get_proxy_service().get_stats()
            metrics['avg_proxy_success_rate'] = proxy_stats['avg_success_rate']
            metrics['active_proxies'] = proxy_stats['active_proxies']
        except:
            metrics['avg_proxy_success_rate'] = 100.0
            metrics['active_proxies'] = 0

        # Метрики очереди
        try:
            from redis_cache import get_redis_cache
            redis = get_redis_cache()
            metrics['queue_size'] = redis.get_publish_queue_size()
        except:
            metrics['queue_size'] = 0

        # Метрики публикации
        publish_rate = self.get_metric_rate('publish_success', 5) or 0
        metrics['publish_rate'] = publish_rate

        return metrics

    def check_alerts(self) -> List[Dict[str, Any]]:
        """
        Проверить все алерты и вернуть активные

        Returns:
            Список активных алертов
        """
        current_metrics = self.get_current_metrics()
        current_time = time.time()
        active_alerts = []

        for alert in self.alerts:
            # Проверяем cooldown
            if current_time - alert.last_triggered < (alert.cooldown_minutes * 60):
                continue

            # Проверяем условие
            if alert.condition_func(current_metrics):
                alert.last_triggered = current_time
                active_alerts.append({
                    'name': alert.name,
                    'severity': alert.severity,
                    'metrics': current_metrics,
                    'timestamp': current_time
                })

                logger.warning(f"Alert triggered: {alert.name} (severity: {alert.severity})")

                # Автоматические действия при алертах
                self._handle_alert(alert, current_metrics)

        return active_alerts

    def _handle_alert(self, alert: AlertCondition, metrics: Dict[str, Any]):
        """
        Обработать алерт - выполнить автоматические действия

        Args:
            alert: Сработавший алерт
            metrics: Текущие метрики
        """
        if alert.name == "low_parsing_success_rate":
            # При низком успехе парсинга - активировать shadow-ban сервис
            try:
                from services.shadow_ban_service import get_shadow_ban_service
                shadow_ban = get_shadow_ban_service()

                # Имитируем обнаружение shadow-ban
                shadow_ban.record_shadow_ban(
                    catalog_url="auto_detected",
                    products_count=int(metrics.get('parsing_success_rate', 0)),
                    html_size=100000,  # Фиктивный размер
                    error_message=f"Low parsing success rate: {metrics.get('parsing_success_rate', 0):.1f}%"
                )
                logger.info("Activated shadow-ban pause due to low parsing success rate")
            except Exception as e:
                logger.error(f"Failed to handle low_parsing_success_rate alert: {e}")

        elif alert.name == "high_captcha_rate":
            # При высоком количестве CAPTCHA - пауза и смена прокси
            try:
                from services.shadow_ban_service import get_shadow_ban_service
                shadow_ban = get_shadow_ban_service()
                shadow_ban.record_shadow_ban(
                    catalog_url="captcha_detected",
                    products_count=0,
                    html_size=0,
                    error_message=f"High CAPTCHA rate: {metrics.get('captcha_rate', 0):.1f}/min"
                )
                logger.info("Activated shadow-ban pause due to high CAPTCHA rate")
            except Exception as e:
                logger.error(f"Failed to handle high_captcha_rate alert: {e}")

        elif alert.name == "high_429_rate":
            # При HTTP 429 - увеличить задержки
            logger.info("HTTP 429 rate is high, increasing request delays")
            # Здесь можно увеличить глобальные задержки

        elif alert.name == "low_proxy_quality":
            # При низком качестве прокси - протестировать все прокси
            try:
                from services.proxy_service import get_proxy_service
                proxy_service = get_proxy_service()

                # Запускаем тестирование прокси в фоне
                asyncio.create_task(proxy_service.test_all_proxies())
                logger.info("Started proxy testing due to low quality")
            except Exception as e:
                logger.error(f"Failed to handle low_proxy_quality alert: {e}")

    async def monitoring_loop(self):
        """Основной цикл мониторинга"""
        logger.info("Starting monitoring loop")

        while True:
            try:
                # Проверяем алерты
                active_alerts = self.check_alerts()

                # Логируем активные алерты
                for alert in active_alerts:
                    logger.warning(f"Active alert: {alert['name']} (severity: {alert['severity']})")

                # Логируем метрики каждые 5 минут
                if int(time.time()) % 300 == 0:
                    metrics = self.get_current_metrics()
                    logger.info(f"System metrics: parsing_success={metrics.get('parsing_success_rate', 0):.1f}%, "
                              f"captcha_rate={metrics.get('captcha_rate', 0):.1f}/min, "
                              f"queue_size={metrics.get('queue_size', 0)}, "
                              f"active_proxies={metrics.get('active_proxies', 0)}")

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")

            await asyncio.sleep(self.check_interval)

    def get_status(self) -> Dict[str, Any]:
        """Получить статус мониторинга"""
        return {
            'current_metrics': self.get_current_metrics(),
            'active_alerts': self.check_alerts(),
            'metrics_count': {name: len(points) for name, points in self.metrics.items()},
            'alerts_count': len(self.alerts)
        }


# Глобальный экземпляр
_monitoring_service = None


def get_monitoring_service() -> MonitoringService:
    """Получить глобальный экземпляр мониторинга"""
    global _monitoring_service
    if _monitoring_service is None:
        _monitoring_service = MonitoringService()
    return _monitoring_service


# Вспомогательные функции для записи метрик
def record_parsing_attempt(url: str, success: bool = False):
    """Записать попытку парсинга"""
    service = get_monitoring_service()
    service.record_metric('parsing_attempt', 1, {'url': url[:50]})
    if success:
        service.record_metric('parsing_success', 1, {'url': url[:50]})


def record_captcha_detected(url: str):
    """Записать обнаружение CAPTCHA"""
    service = get_monitoring_service()
    service.record_metric('captcha_detected', 1, {'url': url[:50]})


def record_http_error(status_code: int, url: str):
    """Записать HTTP ошибку"""
    service = get_monitoring_service()
    service.record_metric(f'http_{status_code}_error', 1, {'url': url[:50]})


def record_publish_success():
    """Записать успешную публикацию"""
    service = get_monitoring_service()
    service.record_metric('publish_success', 1)
