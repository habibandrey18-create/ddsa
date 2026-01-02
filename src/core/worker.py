# main_worker.py - Главный оркестратор новой архитектуры
"""
Main Worker for the Advanced Yandex.Market Bot Architecture

Features:
- Smart search with offset per keyword
- Product validation and quality filtering
- Content generation with templates and CTA rotation
- Publish buffer with Redis queue
- Metrics and CTR tracking
- Price alerts and brand limits
- Postgres + Redis persistence
"""

import asyncio
import logging
import signal
import sys
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import src.config as config

# Services
from src.services.smart_search_service import get_smart_search_service
from src.services.validator_service import get_product_validator
from src.services.content_service import get_content_service
from src.services.publish_service import get_publish_service
from src.services.metrics_service import get_metrics_service
from src.core.database import get_postgres_db
from src.core.redis_cache import get_redis_cache

logger = logging.getLogger(__name__)

class MainWorker:
    """Главный оркестратор всех сервисов бота"""

    def __init__(self):
        self.running = False

        # Инициализируем сервисы
        self.db = get_postgres_db() if config.USE_POSTGRES else None
        self.redis = get_redis_cache() if config.USE_REDIS else None

        self.smart_search = get_smart_search_service()
        self.validator = get_product_validator()
        self.content_service = get_content_service()
        self.publish_service = get_publish_service()
        self.metrics_service = get_metrics_service()

        # Задачи фоновых процессов
        self.tasks: List[asyncio.Task] = []

        # Статистика
        self.stats = {
            'start_time': None,
            'cycles_completed': 0,
            'products_found': 0,
            'products_published': 0,
            'products_rejected': 0,
            'search_errors': 0,
            'publish_errors': 0
        }

    async def start(self):
        """Запустить все сервисы и процессы"""
        if self.running:
            logger.warning("Worker already running")
            return

        self.running = True
        self.stats['start_time'] = datetime.utcnow()

        logger.info("🚀 Starting Advanced Yandex.Market Bot Worker")

        try:
            # Проверяем подключения
            await self._check_connections()

            # Запускаем фоновые сервисы
            await self._start_background_services()

            # Запускаем главный цикл
            await self._main_loop()

        except Exception as e:
            logger.error(f"Critical error in main worker: {e}")
            await self.stop()
            raise
        finally:
            await self.stop()

    async def stop(self):
        """Остановить все сервисы"""
        if not self.running:
            return

        logger.info("🛑 Stopping Advanced Yandex.Market Bot Worker")
        self.running = False

        # Отменяем все задачи
        for task in self.tasks:
            if not task.done():
                task.cancel()

        # Ждём завершения задач
        await asyncio.gather(*self.tasks, return_exceptions=True)

        # Останавливаем сервисы
        try:
            await self.publish_service.stop_publisher()
        except Exception as e:
            logger.error(f"Error stopping publish service: {e}")

        try:
            await self.smart_search.close_session()
        except Exception as e:
            logger.error(f"Error closing smart search session: {e}")

        try:
            await self.validator.close_session()
        except Exception as e:
            logger.error(f"Error closing validator session: {e}")

        self.tasks.clear()
        logger.info("✅ All services stopped")

    async def _check_connections(self):
        """Проверить подключения к базам данных"""
        logger.info("🔍 Checking database connections...")

        # Определяем режим работы (dev/prod)
        is_production = getattr(config, 'ENVIRONMENT', 'dev').lower() == 'prod'
        is_production = is_production or not getattr(config, 'DEBUG_MODE', True)

        # Проверяем Postgres
        if config.USE_POSTGRES:
            try:
                # Простой тестовый запрос
                test_result = self.db.get_search_key("test")
                logger.info("✅ Postgres connection OK")
            except Exception as e:
                logger.error(f"❌ Postgres connection failed: {e}")
                raise

        # Проверяем Redis - обязательно в продакшене
        if config.USE_REDIS:
            try:
                if self.redis.health_check():
                    logger.info("✅ Redis connection OK")
                else:
                    raise Exception("Redis health check failed")
            except Exception as e:
                logger.error(f"❌ Redis connection failed: {e}")
                raise
        elif is_production:
            # В продакшене Redis обязателен
            raise RuntimeError(
                "Redis is required in production environment. "
                "Set USE_REDIS=true and configure Redis connection in your environment variables."
            )
        else:
            logger.warning("⚠️  Redis not enabled - using in-memory queues (not recommended for production)")

        logger.info("✅ All database connections verified")

    async def _start_background_services(self):
        """Запустить фоновые сервисы"""
        logger.info("🔄 Starting background services...")

        # Запускаем publisher
        await self.publish_service.start_publisher()
        logger.info("✅ Publish service started")

        # Создаём задачу для периодического поиска
        search_task = asyncio.create_task(self._search_cycle())
        self.tasks.append(search_task)

        # Создаём задачу для очистки и обслуживания
        maintenance_task = asyncio.create_task(self._maintenance_cycle())
        self.tasks.append(maintenance_task)

        # Создаём задачу для отчётов
        reporting_task = asyncio.create_task(self._reporting_cycle())
        self.tasks.append(reporting_task)

        logger.info("✅ Background services started")

    async def _main_loop(self):
        """Главный цикл работы"""
        logger.info("🔄 Starting main work loop")

        # Настраиваем обработку сигналов
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown")
            asyncio.create_task(self.stop())

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            # Основной цикл - просто ждём завершения
            while self.running:
                await asyncio.sleep(1)

                # Периодически логируем статус
                await self._log_status()

        except asyncio.CancelledError:
            logger.info("Main loop cancelled")
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            raise

    async def _search_cycle(self):
        """Цикл поиска новых товаров"""
        logger.info("🔍 Starting search cycle")

        search_interval = 1800  # 30 минут между циклами поиска
        consecutive_errors = 0
        max_consecutive_errors = 5

        while self.running:
            try:
                start_time = datetime.utcnow()
                logger.info("🌐 Starting smart search cycle...")

                # Выполняем поиск
                result = await self.smart_search.run_smart_search_cycle(max_catalogs=5)

                # Логируем метрики поиска
                metrics = self.smart_search.get_metrics()
                logger.info(f"Search metrics: {metrics}")

                # Обновляем статистику
                self.stats['cycles_completed'] += 1
                self.stats['products_found'] += result.get('total_added', 0)

                duration = (datetime.utcnow() - start_time).total_seconds()
                logger.info(f"✅ Search cycle completed: added={result.get('total_added', 0)}, skipped={result.get('total_skipped', 0)}, time={duration:.1f}s")
                consecutive_errors = 0  # Сбрасываем счетчик ошибок

            except Exception as e:
                consecutive_errors += 1
                self.stats['search_errors'] += 1
                logger.error(f"Search cycle error ({consecutive_errors}/{max_consecutive_errors}): {e}")

                if consecutive_errors >= max_consecutive_errors:
                    logger.error("Too many consecutive search errors, pausing search cycle")
                    await asyncio.sleep(3600)  # Пауза на час
                    consecutive_errors = 0
                    continue

            # Ждём до следующего цикла
            await asyncio.sleep(search_interval)

    async def _maintenance_cycle(self):
        """Цикл обслуживания и очистки"""
        logger.info("🧹 Starting maintenance cycle")

        maintenance_interval = 3600  # 1 час

        while self.running:
            try:
                logger.info("🧹 Running maintenance tasks...")

                # Очищаем старые кэши в Redis
                if self.redis:
                    # Очищаем старые дедупликационные записи (старше 24 часов)
                    # TODO: Добавить метод очистки в redis_cache.py

                    # Проверяем здоровье Redis
                    if not self.redis.health_check():
                        logger.warning("Redis health check failed")

                # Проверяем и пересоздаём индексы в Postgres (если нужно)
                # TODO: Добавить проверки в database_postgres.py

                # Очищаем старые логи метрик (старше 90 дней)
                cutoff_date = datetime.utcnow() - timedelta(days=90)
                # TODO: Добавить метод очистки в database_postgres.py

                logger.info("✅ Maintenance tasks completed")

            except Exception as e:
                logger.error(f"Maintenance cycle error: {e}")

            await asyncio.sleep(maintenance_interval)

    async def _reporting_cycle(self):
        """Цикл создания отчётов"""
        logger.info("📊 Starting reporting cycle")

        report_interval = 86400  # 24 часа

        while self.running:
            try:
                logger.info("📊 Generating performance report...")

                # Получаем отчёт о производительности
                report = self.metrics_service.get_performance_report(days=7)

                # Логируем ключевые метрики
                overall_ctr = report.get('overall', {}).get('overall_ctr', 0)
                total_posts = report.get('overall', {}).get('total_posts', 0)

                logger.info(f"📊 Performance Report (7 days):")
                logger.info(f"   Posts: {total_posts}")
                logger.info(f"   Overall CTR: {overall_ctr:.2f}%")

                # Логируем топ брендов по CTR
                brand_ctr = report.get('overall', {}).get('brand_ctr', [])
                if brand_ctr:
                    top_brand = brand_ctr[0]
                    logger.info(f"   Top Brand: {top_brand['brand']} ({top_brand['ctr']:.2f}%)")

                # Сохраняем отчёт в файл (опционально)
                # self._save_report_to_file(report)

            except Exception as e:
                logger.error(f"Reporting cycle error: {e}")

            await asyncio.sleep(report_interval)

    async def _log_status(self):
        """Логировать текущий статус раз в 5 минут"""
        if not hasattr(self, '_last_status_log'):
            self._last_status_log = datetime.utcnow()

        if (datetime.utcnow() - self._last_status_log).total_seconds() >= 300:  # 5 минут
            uptime = datetime.utcnow() - self.stats['start_time']

            # Получаем статус очереди
            queue_stats = self.publish_service.get_queue_stats()

            logger.info("📈 Status Update:")
            logger.info(f"   Uptime: {uptime}")
            logger.info(f"   Search cycles: {self.stats['cycles_completed']}")
            logger.info(f"   Products found: {self.stats['products_found']}")
            logger.info(f"   Queue size: {queue_stats.get('queue_size', 0)}")
            logger.info(f"   Publisher running: {queue_stats.get('publisher_running', False)}")

            self._last_status_log = datetime.utcnow()

    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику работы"""
        uptime = None
        if self.stats['start_time']:
            uptime = (datetime.utcnow() - self.stats['start_time']).total_seconds()

        return {
            'running': self.running,
            'uptime_seconds': uptime,
            'cycles_completed': self.stats['cycles_completed'],
            'products_found': self.stats['products_found'],
            'products_published': self.stats['products_published'],
            'products_rejected': self.stats['products_rejected'],
            'search_errors': self.stats['search_errors'],
            'publish_errors': self.stats['publish_errors'],
            'queue_stats': self.publish_service.get_queue_stats() if hasattr(self.publish_service, 'get_queue_stats') else {},
            'services_health': self._check_services_health()
        }

    def _check_services_health(self) -> Dict[str, bool]:
        """Проверить здоровье сервисов"""
        health = {}

        # Postgres
        try:
            self.db.get_search_key("health_check")
            health['postgres'] = True
        except:
            health['postgres'] = False

        # Redis
        if self.redis:
            health['redis'] = self.redis.health_check()
        else:
            health['redis'] = None  # Not used

        # Services
        health['smart_search'] = True  # Always available
        health['validator'] = True     # Always available
        health['content_service'] = True  # Always available
        health['publish_service'] = self.publish_service._running if hasattr(self.publish_service, '_running') else False
        health['metrics_service'] = True  # Always available

        return health

    async def manual_search(self, keywords: List[str] = None, max_pages: int = 1) -> Dict:
        """Ручной запуск поиска для тестирования"""
        logger.info(f"🔍 Manual search requested for keywords: {keywords or 'default'}")

        try:
            result = await self.smart_search.run_smart_search_cycle(
                max_catalogs=min(max_pages, 5)  # max_catalogs вместо max_pages
            )

            logger.info(f"✅ Manual search completed: {result}")
            return result

        except Exception as e:
            logger.error(f"❌ Manual search failed: {e}")
            return {'error': str(e)}

    async def force_publish_cycle(self) -> Dict:
        """Принудительно запустить цикл публикации для тестирования"""
        logger.info("🚀 Force publish cycle requested")

        try:
            # Получаем один элемент из очереди
            items = self.redis.dequeue_publish_items(count=1) if self.redis else []

            if not items:
                return {'message': 'No items in queue'}

            result = {'published': 0, 'failed': 0}

            # Публикуем элемент
            for item in items:
                try:
                    # Здесь должна быть логика публикации
                    # Пока просто логируем
                    logger.info(f"Would publish: {item.get('title', 'Unknown')}")
                    result['published'] += 1
                except Exception as e:
                    logger.error(f"Failed to publish item: {e}")
                    result['failed'] += 1

            return result

        except Exception as e:
            logger.error(f"Force publish cycle failed: {e}")
            return {'error': str(e)}

# Глобальный экземпляр
_main_worker = None

def get_main_worker() -> MainWorker:
    """Получить глобальный экземпляр главного worker'а"""
    global _main_worker
    if _main_worker is None:
        _main_worker = MainWorker()
    return _main_worker

async def main():
    """Главная функция для запуска worker'а"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    worker = get_main_worker()

    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Worker failed: {e}")
        sys.exit(1)
    finally:
        await worker.stop()

if __name__ == "__main__":
    # Запуск worker'а
    asyncio.run(main())
