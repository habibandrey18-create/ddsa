"""
Health Check Endpoint - REST API для мониторинга бота
Для использования с Docker/Kubernetes health checks
"""

import logging
import asyncio
from typing import Dict, Any
from aiohttp import web
import psutil
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class HealthCheckService:
    """Сервис health checks для мониторинга"""
    
    def __init__(self, bot_instance=None):
        self.bot = bot_instance
        self.start_time = time.time()
        self.app = None
        self.runner = None
        self.site = None
        self.health_checks = {
            'db': self._check_database,
            'redis': self._check_redis,
            'bot': self._check_bot,
        }
    
    async def _check_database(self) -> Dict[str, Any]:
        """Проверка подключения к БД"""
        try:
            import config
            if config.USE_POSTGRES:
                from database_postgres import get_postgres_db
                db = get_postgres_db()
                session = db.get_session()
                try:
                    from sqlalchemy import text
                    session.execute(text("SELECT 1"))
                    session.close()
                    return {"status": "healthy", "type": "postgres"}
                except Exception as e:
                    return {"status": "unhealthy", "error": str(e), "type": "postgres"}
            else:
                from database import Database
                db = Database()
                # Простая проверка SQLite
                db.cursor.execute("SELECT 1")
                return {"status": "healthy", "type": "sqlite"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def _check_redis(self) -> Dict[str, Any]:
        """Проверка подключения к Redis"""
        try:
            import config
            if config.USE_REDIS:
                from redis_cache import get_redis_cache
                redis = get_redis_cache()
                if redis and redis.ping():
                    return {"status": "healthy"}
                else:
                    return {"status": "unhealthy", "error": "Redis ping failed"}
            else:
                return {"status": "disabled"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def _check_bot(self) -> Dict[str, Any]:
        """Проверка состояния бота"""
        try:
            if self.bot:
                # Проверяем что бот может получить свою информацию
                bot_info = await self.bot.get_me()
                return {
                    "status": "healthy",
                    "username": bot_info.username,
                    "id": bot_info.id
                }
            else:
                return {"status": "unknown", "error": "Bot instance not provided"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def _get_system_metrics(self) -> Dict[str, Any]:
        """Получить системные метрики"""
        try:
            process = psutil.Process()
            return {
                "cpu_percent": process.cpu_percent(),
                "memory_mb": process.memory_info().rss / 1024 / 1024,
                "threads": process.num_threads(),
                "uptime_seconds": time.time() - self.start_time
            }
        except Exception as e:
            logger.warning(f"Failed to get system metrics: {e}")
            return {}
    
    async def health_handler(self, request: web.Request) -> web.Response:
        """
        GET /health - основной health check endpoint
        
        Returns:
            200: Все системы работают
            503: Есть проблемы
        """
        health_status = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": time.time() - self.start_time,
            "checks": {}
        }
        
        # Запускаем все проверки
        for check_name, check_func in self.health_checks.items():
            try:
                check_result = await check_func()
                health_status["checks"][check_name] = check_result
                
                # Если хотя бы одна проверка unhealthy, общий статус тоже unhealthy
                if check_result.get("status") == "unhealthy":
                    health_status["status"] = "unhealthy"
            except Exception as e:
                health_status["checks"][check_name] = {
                    "status": "error",
                    "error": str(e)
                }
                health_status["status"] = "unhealthy"
        
        status_code = 200 if health_status["status"] == "healthy" else 503
        return web.json_response(health_status, status=status_code)
    
    async def readiness_handler(self, request: web.Request) -> web.Response:
        """
        GET /ready - проверка готовности принимать трафик
        
        Returns:
            200: Готов к работе
            503: Еще не готов
        """
        # Упрощенная проверка - только критичные компоненты
        ready = True
        checks = {}
        
        # Проверяем БД
        db_check = await self._check_database()
        checks["db"] = db_check
        if db_check.get("status") != "healthy":
            ready = False
        
        # Проверяем бота
        if self.bot:
            bot_check = await self._check_bot()
            checks["bot"] = bot_check
            if bot_check.get("status") != "healthy":
                ready = False
        
        response = {
            "ready": ready,
            "checks": checks
        }
        
        status_code = 200 if ready else 503
        return web.json_response(response, status=status_code)
    
    async def liveness_handler(self, request: web.Request) -> web.Response:
        """
        GET /alive - простая проверка что процесс жив
        
        Returns:
            200: Процесс работает
        """
        return web.json_response({
            "alive": True,
            "uptime_seconds": time.time() - self.start_time
        })
    
    async def metrics_handler(self, request: web.Request) -> web.Response:
        """
        GET /metrics - системные метрики для мониторинга
        
        Returns:
            200: JSON с метриками
        """
        metrics = await self._get_system_metrics()
        
        # Добавляем метрики из других сервисов если доступны
        try:
            from services.smart_search_service import SmartSearchService
            search_service = SmartSearchService()
            metrics["search"] = search_service.get_metrics()
        except Exception:
            pass
        
        return web.json_response(metrics)
    
    async def start_server(self, host: str = "0.0.0.0", port: int = 8080):
        """Запуск HTTP сервера для health checks"""
        self.app = web.Application()
        
        # Регистрируем endpoints
        self.app.router.add_get('/health', self.health_handler)
        self.app.router.add_get('/ready', self.readiness_handler)
        self.app.router.add_get('/alive', self.liveness_handler)
        self.app.router.add_get('/metrics', self.metrics_handler)
        
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        self.site = web.TCPSite(self.runner, host, port)
        await self.site.start()
        
        logger.info(f"Health check server started on http://{host}:{port}")
        logger.info(f"  - GET /health - full health check")
        logger.info(f"  - GET /ready - readiness probe")
        logger.info(f"  - GET /alive - liveness probe")
        logger.info(f"  - GET /metrics - system metrics")
    
    async def stop_server(self):
        """Остановка HTTP сервера"""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        logger.info("Health check server stopped")


# Singleton instance
_health_service: HealthCheckService = None


def get_health_service(bot_instance=None) -> HealthCheckService:
    """Получить глобальный экземпляр HealthCheckService"""
    global _health_service
    if _health_service is None:
        _health_service = HealthCheckService(bot_instance)
    return _health_service

