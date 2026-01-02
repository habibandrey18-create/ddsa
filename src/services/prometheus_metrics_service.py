"""
Prometheus Metrics Service - Экспорт метрик для мониторинга
"""

import logging
from typing import Optional

try:
    from prometheus_client import Counter, Histogram, Gauge, start_http_server
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    Counter = Histogram = Gauge = None
    start_http_server = None

import src.config as config

logger = logging.getLogger(__name__)

# Метрики для продуктов (только если prometheus_client доступен)
if PROMETHEUS_AVAILABLE:
    products_found = Counter(
        'ymarket_products_found_total',
        'Total number of products found',
        ['source']
    )

    products_published = Counter(
        'ymarket_products_published_total',
        'Total number of products published',
        ['brand', 'category']
    )

    products_rejected = Counter(
        'ymarket_products_rejected_total',
        'Total number of products rejected',
        ['reason']
    )

    # Метрики для поиска
    search_errors = Counter(
        'ymarket_search_errors_total',
        'Total number of search errors',
        ['error_type']
    )

    search_duration = Histogram(
        'ymarket_search_duration_seconds',
        'Search operation duration',
        ['method']  # 'http' or 'playwright'
    )

    # Метрики для публикации
    publish_errors = Counter(
        'ymarket_publish_errors_total',
        'Total number of publish errors',
        ['error_type']
    )

    publish_duration = Histogram(
        'ymarket_publish_duration_seconds',
        'Publish operation duration'
    )

    # Метрики для очереди
    queue_size = Gauge(
        'ymarket_queue_size',
        'Current queue size'
    )

    # Метрики для кликов/реакций
    clicks_total = Counter(
        'ymarket_clicks_total',
        'Total number of clicks on affiliate links',
        ['brand', 'category']
    )

    # Метрики для shadow-ban detector
    shadow_ban_detected = Counter(
        'ymarket_shadow_ban_detected_total',
        'Total number of shadow-ban detections'
    )

    # Метрики для партнерских ссылок
    affiliate_link_generated = Counter(
        'ymarket_affiliate_link_generated_total',
        'Total number of affiliate links generated',
        ['method']  # 'api' or 'manual'
    )
else:
    # Заглушки если prometheus_client не установлен
    products_found = None
    products_published = None
    products_rejected = None
    search_errors = None
    search_duration = None
    publish_errors = None
    publish_duration = None
    queue_size = None
    clicks_total = None
    shadow_ban_detected = None
    affiliate_link_generated = None


class PrometheusMetricsService:
    """Сервис для работы с Prometheus метриками"""

    def __init__(self):
        self.enabled = getattr(config, 'PROMETHEUS_ENABLED', False)
        self.port = getattr(config, 'PROMETHEUS_PORT', 9100)
        self.server_started = False

    def start_server(self):
        """Запустить HTTP сервер для метрик"""
        if not self.enabled:
            logger.info("Prometheus metrics disabled")
            return

        if not PROMETHEUS_AVAILABLE:
            logger.warning("Prometheus client not available. Install: pip install prometheus_client")
            return

        try:
            start_http_server(self.port)
            self.server_started = True
            logger.info(f"Prometheus metrics server started on port {self.port}")
        except Exception as e:
            logger.error(f"Failed to start Prometheus metrics server: {e}")

    def record_product_found(self, source: str = "search"):
        """Записать найденный продукт"""
        if self.enabled and PROMETHEUS_AVAILABLE and products_found:
            products_found.labels(source=source).inc()

    def record_product_published(self, brand: Optional[str] = None, category: Optional[str] = None):
        """Записать опубликованный продукт"""
        if self.enabled and PROMETHEUS_AVAILABLE and products_published:
            products_published.labels(
                brand=brand or "unknown",
                category=category or "unknown"
            ).inc()

    def record_product_rejected(self, reason: str):
        """Записать отклоненный продукт"""
        if self.enabled and PROMETHEUS_AVAILABLE and products_rejected:
            products_rejected.labels(reason=reason).inc()

    def record_search_error(self, error_type: str):
        """Записать ошибку поиска"""
        if self.enabled and PROMETHEUS_AVAILABLE and search_errors:
            search_errors.labels(error_type=error_type).inc()

    def record_search_duration(self, duration: float, method: str = "http"):
        """Записать длительность поиска"""
        if self.enabled and PROMETHEUS_AVAILABLE and search_duration:
            search_duration.labels(method=method).observe(duration)

    def record_publish_error(self, error_type: str):
        """Записать ошибку публикации"""
        if self.enabled and PROMETHEUS_AVAILABLE and publish_errors:
            publish_errors.labels(error_type=error_type).inc()

    def record_publish_duration(self, duration: float):
        """Записать длительность публикации"""
        if self.enabled and PROMETHEUS_AVAILABLE and publish_duration:
            publish_duration.observe(duration)

    def update_queue_size(self, size: int):
        """Обновить размер очереди"""
        if self.enabled and PROMETHEUS_AVAILABLE and queue_size:
            queue_size.set(size)

    def record_click(self, brand: Optional[str] = None, category: Optional[str] = None):
        """Записать клик по партнерской ссылке"""
        if self.enabled and PROMETHEUS_AVAILABLE and clicks_total:
            clicks_total.labels(
                brand=brand or "unknown",
                category=category or "unknown"
            ).inc()

    def record_shadow_ban(self):
        """Записать обнаружение shadow-ban"""
        if self.enabled and PROMETHEUS_AVAILABLE and shadow_ban_detected:
            shadow_ban_detected.inc()

    def record_affiliate_link(self, method: str = "api"):
        """Записать генерацию партнерской ссылки"""
        if self.enabled and PROMETHEUS_AVAILABLE and affiliate_link_generated:
            affiliate_link_generated.labels(method=method).inc()


# Глобальный экземпляр
_prometheus_service = None


def get_prometheus_service() -> PrometheusMetricsService:
    """Get global Prometheus metrics service instance"""
    global _prometheus_service
    if _prometheus_service is None:
        _prometheus_service = PrometheusMetricsService()
    return _prometheus_service
