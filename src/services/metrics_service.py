# services/metrics_service.py - Система метрик и CTR
import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse
import src.config as config
from src.core.database import get_postgres_db
from src.core.redis_cache import get_redis_cache

logger = logging.getLogger(__name__)

class MetricsService:
    """Сервис для сбора и анализа метрик"""

    def __init__(self):
        self.db = get_postgres_db() if config.USE_POSTGRES else None
        self.redis = get_redis_cache() if config.USE_REDIS else None

        # Файловое хранилище метрик для работы без базы данных
        self.metrics_file = "metrics_cache.json"
        self.metrics_cache = {
            'posts': {},  # post_id -> metrics
            'daily_stats': {}  # date -> stats
        }
        self._load_metrics_cache()

    def record_click(self, click_data: Dict) -> bool:
        """
        Записать клик по посту

        Args:
            click_data: Данные о клике (post_id, user_id, timestamp, etc.)

        Returns:
            bool: Успешно ли записано
        """
        try:
            post_id = click_data.get('post_id')
            if not post_id:
                logger.warning("No post_id in click data")
                return False

            # Используем базу данных если доступна, иначе файловый кэш
            if self.db:
                self.db.increment_clicks(post_id)
            else:
                self.record_click_file(post_id)

            # Логируем детальную информацию о клике
            logger.info(f"Click recorded: post_id={post_id}, user={click_data.get('user_id', 'unknown')}")

            return True

        except Exception as e:
            logger.error(f"Failed to record click: {e}")
            return False

    def record_impression(self, impression_data: Dict) -> bool:
        """
        Записать показ поста

        Args:
            impression_data: Данные о показе

        Returns:
            bool: Успешно ли записано
        """
        try:
            post_id = impression_data.get('post_id')
            if not post_id:
                logger.warning("No post_id in impression data")
                return False

            # Используем базу данных если доступна, иначе файловый кэш
            if self.db:
                self.db.increment_impressions(post_id)
            else:
                self.record_impression_file(post_id)

            # Логируем с пониженной частотой (не каждый показ)
            if impression_data.get('log_impression', False):
                logger.debug(f"Impression recorded: post_id={post_id}")

            return True

        except Exception as e:
            logger.error(f"Failed to record impression: {e}")
            return False

    def _load_metrics_cache(self):
        """Загрузить метрики из файла"""
        try:
            import json
            with open(self.metrics_file, 'r', encoding='utf-8') as f:
                self.metrics_cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.metrics_cache = {'posts': {}, 'daily_stats': {}}

    def _save_metrics_cache(self):
        """Сохранить метрики в файл"""
        try:
            import json
            with open(self.metrics_file, 'w', encoding='utf-8') as f:
                json.dump(self.metrics_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save metrics cache: {e}")

    def record_click_file(self, post_id: int) -> bool:
        """Записать клик в файловый кэш"""
        try:
            post_key = str(post_id)
            if post_key not in self.metrics_cache['posts']:
                self.metrics_cache['posts'][post_key] = {
                    'clicks': 0,
                    'impressions': 0,
                    'post_id': post_id
                }

            self.metrics_cache['posts'][post_key]['clicks'] += 1
            self._save_metrics_cache()
            return True
        except Exception as e:
            logger.error(f"Failed to record click in file cache: {e}")
            return False

    def record_impression_file(self, post_id: int) -> bool:
        """Записать показ в файловый кэш"""
        try:
            post_key = str(post_id)
            if post_key not in self.metrics_cache['posts']:
                self.metrics_cache['posts'][post_key] = {
                    'clicks': 0,
                    'impressions': 0,
                    'post_id': post_id
                }

            self.metrics_cache['posts'][post_key]['impressions'] += 1
            self._save_metrics_cache()
            return True
        except Exception as e:
            logger.error(f"Failed to record impression in file cache: {e}")
            return False

    def _get_file_metrics_summary(self, days: int) -> Dict:
        """Получить сводку метрик из файлового кэша"""
        try:
            total_posts = len(self.metrics_cache.get('posts', {}))
            total_clicks = sum(p.get('clicks', 0) for p in self.metrics_cache.get('posts', {}).values())
            total_impressions = sum(p.get('impressions', 0) for p in self.metrics_cache.get('posts', {}).values())

            return {
                'total_posts': total_posts,
                'total_clicks': total_clicks,
                'total_impressions': total_impressions,
                'overall_ctr': round((total_clicks / total_impressions * 100) if total_impressions > 0 else 0, 2),
                'brand_ctr': [],  # Не поддерживается в файловом режиме
                'template_ctr': []  # Не поддерживается в файловом режиме
            }
        except Exception as e:
            logger.error(f"Failed to get file metrics summary: {e}")
            return {
                'total_posts': 0,
                'total_clicks': 0,
                'total_impressions': 0,
                'overall_ctr': 0,
                'brand_ctr': [],
                'template_ctr': []
            }

    def get_post_metrics(self, post_id: int) -> Optional[Dict]:
        """Получить метрики конкретного поста"""
        try:
            post_key = str(post_id)

            # Сначала пробуем базу данных
            if self.db:
                metrics = self.db.get_post_metrics(post_id)
                if metrics:
                    # Вычисляем CTR
                    clicks = metrics.get('clicks', 0)
                    impressions = metrics.get('impressions', 0)
                    ctr = (clicks / impressions * 100) if impressions > 0 else 0

                    return {
                        'post_id': post_id,
                        'clicks': clicks,
                        'impressions': impressions,
                        'ctr': round(ctr, 2),
                        'brand': metrics.get('brand'),
                        'price': metrics.get('price'),
                        'template_used': metrics.get('template_used'),
                        'cta_used': metrics.get('cta_used'),
                        'published_at': metrics.get('published_at')
                    }

            # Если база недоступна, используем файловый кэш
            if post_key in self.metrics_cache.get('posts', {}):
                metrics = self.metrics_cache['posts'][post_key]
                clicks = metrics.get('clicks', 0)
                impressions = metrics.get('impressions', 0)
                ctr = (clicks / impressions * 100) if impressions > 0 else 0

                return {
                    'post_id': post_id,
                    'clicks': clicks,
                    'impressions': impressions,
                    'ctr': round(ctr, 2),
                    'brand': None,  # Не поддерживается в файловом режиме
                    'price': None,
                    'template_used': None,
                    'cta_used': None,
                    'published_at': None
                }

            return None

        except Exception as e:
            logger.error(f"Failed to get post metrics for {post_id}: {e}")
            return None

    def get_performance_report(self, days: int = 7) -> Dict:
        """
        Получить отчёт о производительности

        Args:
            days: Период анализа в днях

        Returns:
            Dict: Отчёт с метриками
        """
        try:
            # Проверяем доступность базы данных
            if not self.db:
                return {
                    'period_days': days,
                    'generated_at': datetime.utcnow().isoformat(),
                    'error': 'Database not available (Postgres disabled)',
                    'overall': {'total_posts': 0, 'total_clicks': 0, 'total_impressions': 0, 'overall_ctr': 0},
                    'insights': ['База данных недоступна - используйте старую архитектуру'],
                    'recommendations': ['Включите Postgres для полной функциональности метрик']
                }

            # Получаем общую статистику
            overall_stats = self.db.get_metrics_summary(days=days)
        except Exception as e:
            logger.error(f"Failed to get database metrics: {e}")
            # Используем файловый кэш как fallback
            overall_stats = self._get_file_metrics_summary(days=days)

            # Добавляем дополнительные метрики
            report = {
                'period_days': days,
                'generated_at': datetime.utcnow().isoformat(),
                'overall': overall_stats,
                'insights': self._generate_insights(overall_stats),
                'recommendations': self._generate_recommendations(overall_stats)
            }

            return report

        except Exception as e:
            logger.error(f"Failed to generate performance report: {e}")
            return {}

    def _generate_insights(self, stats: Dict) -> List[str]:
        """Сгенерировать инсайты на основе статистики"""
        insights = []

        try:
            # Анализ CTR по брендам
            brand_ctr = stats.get('brand_ctr', [])
            if brand_ctr:
                top_brand = max(brand_ctr, key=lambda x: x['ctr'])
                worst_brand = min(brand_ctr, key=lambda x: x['ctr'])

                insights.append(f"Лучший CTR по бренду: {top_brand['brand']} ({top_brand['ctr']}%)")
                insights.append(f"Худший CTR по бренду: {worst_brand['brand']} ({worst_brand['ctr']}%)")

            # Анализ CTR по шаблонам
            template_ctr = stats.get('template_ctr', [])
            if template_ctr:
                top_template = max(template_ctr, key=lambda x: x['ctr'])
                insights.append(f"Лучший CTR по шаблону: {top_template['template']} ({top_template['ctr']}%)")

            # Общий CTR
            overall_ctr = stats.get('overall_ctr', 0)
            if overall_ctr > 5:
                insights.append(f"Отличный общий CTR: {overall_ctr}%")
            elif overall_ctr > 2:
                insights.append(f"Хороший общий CTR: {overall_ctr}%")
            elif overall_ctr > 1:
                insights.append(f"Средний CTR: {overall_ctr}%")
            else:
                insights.append(f"Низкий CTR: {overall_ctr}% - требуется оптимизация")

        except Exception as e:
            logger.error(f"Failed to generate insights: {e}")

        return insights

    def _generate_recommendations(self, stats: Dict) -> List[str]:
        """Сгенерировать рекомендации на основе статистики"""
        recommendations = []

        try:
            overall_ctr = stats.get('overall_ctr', 0)

            # Рекомендации по CTR
            if overall_ctr < 1:
                recommendations.append("Критически низкий CTR. Рекомендуется:")
                recommendations.append("- Проверить качество изображений")
                recommendations.append("- Улучшить описания товаров")
                recommendations.append("- Протестировать разные CTA")
            elif overall_ctr < 2:
                recommendations.append("Низкий CTR. Возможные улучшения:")
                recommendations.append("- Оптимизировать время публикаций")
                recommendations.append("- Добавить больше скидочных предложений")
                recommendations.append("- Проверить валидность affiliate ссылок")

            # Анализ брендов
            brand_ctr = stats.get('brand_ctr', [])
            if len(brand_ctr) > 1:
                low_performing_brands = [b for b in brand_ctr if b['ctr'] < overall_ctr * 0.7]
                if low_performing_brands:
                    brands_list = ", ".join([b['brand'] for b in low_performing_brands])
                    recommendations.append(f"Рассмотреть уменьшение публикаций брендов: {brands_list}")

            # Анализ шаблонов
            template_ctr = stats.get('template_ctr', [])
            if template_ctr:
                best_template = max(template_ctr, key=lambda x: x['ctr'])
                recommendations.append(f"Увеличить использование шаблона: {best_template['template']}")

        except Exception as e:
            logger.error(f"Failed to generate recommendations: {e}")

        return recommendations

    def track_conversion(self, conversion_data: Dict) -> bool:
        """
        Отследить конверсию (покупку)

        Args:
            conversion_data: Данные о конверсии

        Returns:
            bool: Успешно ли записано
        """
        try:
            # TODO: Реализовать отслеживание конверсий
            # Это может включать вебхуки от affiliate сети или API calls
            logger.info(f"Conversion tracked: {conversion_data}")
            return True

        except Exception as e:
            logger.error(f"Failed to track conversion: {e}")
            return False

    def get_audience_analytics(self) -> Dict:
        """Получить аналитику аудитории"""
        try:
            # TODO: Добавить сбор данных о пользователях
            # clicks per user, geographic distribution, etc.
            return {
                'total_unique_users': 0,  # TODO
                'avg_clicks_per_user': 0,  # TODO
                'top_regions': [],  # TODO
                'engagement_rate': 0  # TODO
            }
        except Exception as e:
            logger.error(f"Failed to get audience analytics: {e}")
            return {}

    def create_click_tracking_url(self, post_id: int, original_url: str) -> str:
        """
        Создать URL для отслеживания кликов

        Args:
            post_id: ID поста
            original_url: Оригинальный URL товара

        Returns:
            str: URL с трекингом кликов
        """
        try:
            # Создаём трекинг URL через наш API endpoint
            tracking_url = f"{config.WEBHOOK_URL}/click/{post_id}"

            # Добавляем оригинальный URL как параметр
            params = {
                'url': original_url,
                'post_id': post_id,
                'ts': int(time.time())
            }

            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            return f"{tracking_url}?{query_string}"

        except Exception as e:
            logger.error(f"Failed to create tracking URL: {e}")
            return original_url

    def process_click_tracking(self, tracking_data: Dict) -> Optional[str]:
        """
        Обработать трекинг клика

        Args:
            tracking_data: Данные из трекинг URL

        Returns:
            Optional[str]: Финальный URL для редиректа или None при ошибке
        """
        try:
            post_id = tracking_data.get('post_id')
            original_url = tracking_data.get('url')

            if not post_id or not original_url:
                logger.warning("Invalid tracking data")
                return None

            # Записываем клик
            self.record_click({
                'post_id': int(post_id),
                'user_id': tracking_data.get('user_id'),
                'timestamp': datetime.utcnow(),
                'user_agent': tracking_data.get('user_agent'),
                'ip': tracking_data.get('ip')
            })

            # Возвращаем оригинальный URL для редиректа
            return original_url

        except Exception as e:
            logger.error(f"Failed to process click tracking: {e}")
            return None

    def get_ab_test_results(self, test_name: str, days: int = 7) -> Dict:
        """
        Получить результаты A/B тестирования

        Args:
            test_name: Название теста
            days: Период анализа

        Returns:
            Dict: Результаты теста
        """
        try:
            # TODO: Реализовать A/B тестирование для шаблонов, CTA, etc.
            return {
                'test_name': test_name,
                'period_days': days,
                'variants': {},
                'winner': None,
                'confidence': 0
            }
        except Exception as e:
            logger.error(f"Failed to get A/B test results: {e}")
            return {}

    def export_metrics_csv(self, days: int = 30, file_path: str = None) -> Optional[str]:
        """
        Экспортировать метрики в CSV

        Args:
            days: Период для экспорта
            file_path: Путь к файлу (если None, генерируется автоматически)

        Returns:
            Optional[str]: Путь к созданному файлу
        """
        try:
            import csv
            from pathlib import Path

            if not file_path:
                file_path = f"metrics_export_{int(time.time())}.csv"

            stats = self.db.get_metrics_summary(days=days)

            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)

                # Заголовки
                writer.writerow(['Metric', 'Value'])

                # Общая статистика
                writer.writerow(['Period (days)', days])
                writer.writerow(['Total Posts', stats.get('total_posts', 0)])
                writer.writerow(['Total Clicks', stats.get('total_clicks', 0)])
                writer.writerow(['Total Impressions', stats.get('total_impressions', 0)])
                writer.writerow(['Overall CTR (%)', stats.get('overall_ctr', 0)])

                # CTR по брендам
                writer.writerow([])
                writer.writerow(['Brand CTR'])
                for brand in stats.get('brand_ctr', []):
                    writer.writerow([brand['brand'], f"{brand['ctr']}%"])

                # CTR по шаблонам
                writer.writerow([])
                writer.writerow(['Template CTR'])
                for template in stats.get('template_ctr', []):
                    writer.writerow([template['template'], f"{template['ctr']}%"])

            logger.info(f"Metrics exported to {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"Failed to export metrics: {e}")
            return None

# Глобальный экземпляр
_metrics_service = None

def get_metrics_service() -> MetricsService:
    """Get global metrics service instance"""
    global _metrics_service
    if _metrics_service is None:
        _metrics_service = MetricsService()
    return _metrics_service
