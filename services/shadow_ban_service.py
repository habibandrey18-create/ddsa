"""
Shadow Ban Service - Управление паузами при обнаружении shadow-ban
Согласно требованиям: автоматическая пауза на 6-12 часов при обнаружении shadow-ban
"""

import logging
from typing import Optional, Dict
from datetime import datetime, timedelta
import random
import config

logger = logging.getLogger(__name__)


class ShadowBanService:
    """
    Сервис для управления shadow-ban детекцией и паузами
    
    Функционал:
    - Детектирование shadow-ban (мало товаров + большой HTML)
    - Автоматическая пауза на 6-12 часов
    - Логирование в БД
    - Проверка, можно ли продолжать парсинг
    """

    def __init__(self):
        self.pause_until: Optional[datetime] = None
        self.min_pause_hours = getattr(config, 'SHADOW_BAN_MIN_PAUSE_HOURS', 6)
        self.max_pause_hours = getattr(config, 'SHADOW_BAN_MAX_PAUSE_HOURS', 12)
        self.html_size_threshold_low = 100_000  # 100KB
        self.html_size_threshold_high = 500_000  # 500KB
        self.products_threshold = 5  # Минимум товаров для нормального парсинга

    def is_shadow_banned(self, products_count: int, html_size: int) -> bool:
        """
        Проверить, обнаружен ли shadow-ban
        
        Согласно требованиям:
        - Если < 5 товаров и HTML size > threshold → shadow-ban
        - Если 0 товаров и HTML size > threshold → shadow-ban
        
        Args:
            products_count: Количество найденных товаров
            html_size: Размер HTML в байтах
            
        Returns:
            True если обнаружен shadow-ban
        """
        # Если мало товаров но большой HTML - возможно bot-safe версия
        if products_count < self.products_threshold and html_size > self.html_size_threshold_high:
            logger.warning(
                f"Shadow-ban detected: {products_count} products, {html_size} bytes HTML"
            )
            return True

        # Если совсем нет товаров - тоже подозрительно
        if products_count == 0 and html_size > self.html_size_threshold_low:
            logger.warning(
                f"Shadow-ban detected: 0 products, {html_size} bytes HTML"
            )
            return True

        return False

    def record_shadow_ban(
        self,
        catalog_url: str,
        products_count: int,
        html_size: int,
        status_code: Optional[int] = None,
        error_message: Optional[str] = None
    ):
        """
        Записать обнаружение shadow-ban и установить паузу
        
        Args:
            catalog_url: URL каталога где обнаружен shadow-ban
            products_count: Количество найденных товаров
            html_size: Размер HTML
            status_code: HTTP статус код (если есть)
            error_message: Сообщение об ошибке (если есть)
        """
        # Генерируем случайную паузу от 6 до 12 часов
        pause_hours = random.randint(self.min_pause_hours, self.max_pause_hours)
        self.pause_until = datetime.utcnow() + timedelta(hours=pause_hours)
        
        logger.warning(
            f"Shadow-ban detected for {catalog_url}. "
            f"Pausing until {self.pause_until.isoformat()} ({pause_hours} hours)"
        )

        # Записываем в БД если доступна
        try:
            if config.USE_POSTGRES:
                from database_postgres import get_postgres_db
                db = get_postgres_db()
                session = db.get_session()
                try:
                    from sqlalchemy import text
                    session.execute(
                        text("""
                            INSERT INTO shadow_ban_log 
                            (catalog_url, parsed_count, status_code, error_message, detected_at)
                            VALUES (:url, :count, :status, :error, :detected_at)
                        """),
                        {
                            'url': catalog_url,
                            'count': products_count,
                            'status': status_code,
                            'error': error_message,
                            'detected_at': datetime.utcnow()
                        }
                    )
                    session.commit()
                except Exception as e:
                    logger.error(f"Failed to log shadow-ban to DB: {e}")
                    session.rollback()
                finally:
                    session.close()
        except Exception as e:
            logger.debug(f"Could not log shadow-ban to DB: {e}")

        # Записываем в Prometheus метрики
        try:
            from services.prometheus_metrics_service import get_prometheus_service
            metrics_service = get_prometheus_service()
            metrics_service.record_shadow_ban()
        except Exception:
            pass

    def can_continue_parsing(self) -> bool:
        """
        Проверить, можно ли продолжать парсинг (пауза истекла)
        
        Returns:
            True если можно продолжать, False если пауза активна
        """
        if self.pause_until is None:
            return True

        if datetime.utcnow() >= self.pause_until:
            logger.info("Shadow-ban pause period expired, resuming parsing")
            self.pause_until = None
            return True

        remaining = (self.pause_until - datetime.utcnow()).total_seconds() / 3600
        logger.debug(f"Shadow-ban pause active, {remaining:.1f} hours remaining")
        return False

    def get_status(self) -> Dict:
        """
        Получить статус shadow-ban сервиса
        
        Returns:
            Словарь с информацией о статусе
        """
        return {
            'paused': self.pause_until is not None,
            'pause_until': self.pause_until.isoformat() if self.pause_until else None,
            'can_continue': self.can_continue_parsing()
        }


# Глобальный экземпляр
_shadow_ban_service = None


def get_shadow_ban_service() -> ShadowBanService:
    """Get global shadow-ban service instance"""
    global _shadow_ban_service
    if _shadow_ban_service is None:
        _shadow_ban_service = ShadowBanService()
    return _shadow_ban_service

