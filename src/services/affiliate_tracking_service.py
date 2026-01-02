"""
Affiliate Tracking Service - Трекинг affiliate-ссылок и ERID
Логирует отправленные ссылки и сохраняет статистику переходов
"""

import logging
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class AffiliateLinkRecord:
    """Запись о отправленной affiliate-ссылке"""
    link_id: str  # Уникальный ID ссылки
    market_id: str  # ID товара в Яндекс.Маркете
    erid: str  # ERID токен
    affiliate_url: str  # Affiliate ссылка
    original_url: str  # Оригинальная ссылка товара
    sent_at: float  # Время отправки
    channel_id: str  # ID канала/чата
    message_id: Optional[str] = None  # ID сообщения (если доступно)
    clicks_count: int = 0  # Количество переходов
    last_click_at: Optional[float] = None  # Последний переход


class AffiliateTrackingService:
    """
    Сервис для трекинга affiliate-ссылок и ERID
    Сохраняет статистику отправленных ссылок и переходов по ним
    """

    def __init__(self):
        self.records: Dict[str, AffiliateLinkRecord] = {}
        self.max_records = 10000  # Максимум записей в памяти
        self.cleanup_interval = 86400  # Очистка старых записей раз в сутки

        # Автоматическая очистка старых записей
        self._schedule_cleanup()

    def _schedule_cleanup(self):
        """Запланировать автоматическую очистку"""
        import asyncio

        async def cleanup_old_records():
            while True:
                await asyncio.sleep(self.cleanup_interval)
                self._cleanup_old_records()

        # Запускаем в фоне
        import threading
        def run_cleanup():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(cleanup_old_records())

        thread = threading.Thread(target=run_cleanup, daemon=True)
        thread.start()

    def _cleanup_old_records(self):
        """Очистить старые записи (старше 30 дней)"""
        cutoff_time = time.time() - (30 * 24 * 60 * 60)  # 30 дней
        old_keys = [
            key for key, record in self.records.items()
            if record.sent_at < cutoff_time and record.clicks_count == 0
        ]

        for key in old_keys:
            del self.records[key]

        if old_keys:
            logger.info(f"Cleaned up {len(old_keys)} old affiliate tracking records")

    def _generate_link_id(self, market_id: str, erid: str, channel_id: str) -> str:
        """Сгенерировать уникальный ID для ссылки"""
        content = f"{market_id}:{erid}:{channel_id}:{time.time()}"
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def record_affiliate_link(
        self,
        market_id: str,
        erid: str,
        affiliate_url: str,
        original_url: str,
        channel_id: str,
        message_id: Optional[str] = None
    ) -> str:
        """
        Записать отправку affiliate-ссылки

        Args:
            market_id: ID товара в Яндекс.Маркете
            erid: ERID токен
            affiliate_url: Affiliate ссылка
            original_url: Оригинальная ссылка товара
            channel_id: ID канала/чата
            message_id: ID сообщения

        Returns:
            Уникальный ID ссылки
        """
        link_id = self._generate_link_id(market_id, erid, channel_id)

        record = AffiliateLinkRecord(
            link_id=link_id,
            market_id=market_id,
            erid=erid,
            affiliate_url=affiliate_url,
            original_url=original_url,
            sent_at=time.time(),
            channel_id=channel_id,
            message_id=message_id
        )

        self.records[link_id] = record

        # Ограничиваем количество записей
        if len(self.records) > self.max_records:
            # Удаляем самые старые записи без кликов
            old_records = sorted(
                [(k, v) for k, v in self.records.items() if v.clicks_count == 0],
                key=lambda x: x[1].sent_at
            )
            if old_records:
                del self.records[old_records[0][0]]

        # Сохраняем в постоянное хранилище
        self._persist_record(record)

        logger.debug(f"Recorded affiliate link: {link_id} for market_id {market_id}")
        return link_id

    def record_click(self, link_id: str, user_id: Optional[str] = None) -> bool:
        """
        Записать переход по affiliate-ссылке

        Args:
            link_id: ID ссылки
            user_id: ID пользователя (опционально)

        Returns:
            True если запись найдена и обновлена
        """
        if link_id not in self.records:
            logger.warning(f"Click recorded for unknown link_id: {link_id}")
            return False

        record = self.records[link_id]
        record.clicks_count += 1
        record.last_click_at = time.time()

        # Обновляем в постоянном хранилище
        self._update_record_click(record)

        logger.info(f"Click recorded for link {link_id}: total clicks {record.clicks_count}")
        return True

    def get_link_stats(self, link_id: str) -> Optional[Dict[str, Any]]:
        """
        Получить статистику по ссылке

        Args:
            link_id: ID ссылки

        Returns:
            Статистика или None
        """
        if link_id not in self.records:
            return None

        record = self.records[link_id]
        return {
            'link_id': record.link_id,
            'market_id': record.market_id,
            'erid': record.erid,
            'affiliate_url': record.affiliate_url,
            'original_url': record.original_url,
            'sent_at': record.sent_at,
            'channel_id': record.channel_id,
            'message_id': record.message_id,
            'clicks_count': record.clicks_count,
            'last_click_at': record.last_click_at,
            'days_since_sent': (time.time() - record.sent_at) / (24 * 60 * 60)
        }

    def get_erid_stats(self, erid: str) -> Dict[str, Any]:
        """
        Получить статистику по ERID

        Args:
            erid: ERID токен

        Returns:
            Статистика по ERID
        """
        erid_records = [r for r in self.records.values() if r.erid == erid]

        if not erid_records:
            return {
                'erid': erid,
                'total_links': 0,
                'total_clicks': 0,
                'click_through_rate': 0.0
            }

        total_links = len(erid_records)
        total_clicks = sum(r.clicks_count for r in erid_records)
        ctr = (total_clicks / total_links * 100) if total_links > 0 else 0

        return {
            'erid': erid,
            'total_links': total_links,
            'total_clicks': total_clicks,
            'click_through_rate': ctr,
            'avg_clicks_per_link': total_clicks / total_links if total_links > 0 else 0
        }

    def get_channel_stats(self, channel_id: str, days: int = 7) -> Dict[str, Any]:
        """
        Получить статистику по каналу за период

        Args:
            channel_id: ID канала
            days: Период в днях

        Returns:
            Статистика по каналу
        """
        cutoff_time = time.time() - (days * 24 * 60 * 60)
        channel_records = [
            r for r in self.records.values()
            if r.channel_id == channel_id and r.sent_at >= cutoff_time
        ]

        total_links = len(channel_records)
        total_clicks = sum(r.clicks_count for r in channel_records)
        ctr = (total_clicks / total_links * 100) if total_links > 0 else 0

        return {
            'channel_id': channel_id,
            'period_days': days,
            'total_links': total_links,
            'total_clicks': total_clicks,
            'click_through_rate': ctr,
            'avg_clicks_per_link': total_clicks / total_links if total_links > 0 else 0
        }

    def get_overall_stats(self, days: int = 7) -> Dict[str, Any]:
        """
        Получить общую статистику за период

        Args:
            days: Период в днях

        Returns:
            Общая статистика
        """
        cutoff_time = time.time() - (days * 24 * 60 * 60)
        recent_records = [
            r for r in self.records.values()
            if r.sent_at >= cutoff_time
        ]

        total_links = len(recent_records)
        total_clicks = sum(r.clicks_count for r in recent_records)
        ctr = (total_clicks / total_links * 100) if total_links > 0 else 0

        # Статистика по ERID
        erid_stats = {}
        for record in recent_records:
            if record.erid not in erid_stats:
                erid_stats[record.erid] = {'links': 0, 'clicks': 0}
            erid_stats[record.erid]['links'] += 1
            erid_stats[record.erid]['clicks'] += record.clicks_count

        top_erids = sorted(
            erid_stats.items(),
            key=lambda x: x[1]['clicks'],
            reverse=True
        )[:5]

        return {
            'period_days': days,
            'total_links': total_links,
            'total_clicks': total_clicks,
            'overall_ctr': ctr,
            'top_erids': [
                {
                    'erid': erid,
                    'links': stats['links'],
                    'clicks': stats['clicks'],
                    'ctr': (stats['clicks'] / stats['links'] * 100) if stats['links'] > 0 else 0
                }
                for erid, stats in top_erids
            ]
        }

    def _persist_record(self, record: AffiliateLinkRecord):
        """Сохранить запись в постоянное хранилище"""
        try:
            # Сохраняем в Redis если доступен
            import src.config as config
            if config.USE_REDIS:
                from src.core.redis_cache import get_redis_cache
                redis = get_redis_cache()

                key = f"affiliate_link:{record.link_id}"
                data = {
                    'market_id': record.market_id,
                    'erid': record.erid,
                    'affiliate_url': record.affiliate_url,
                    'original_url': record.original_url,
                    'sent_at': record.sent_at,
                    'channel_id': record.channel_id,
                    'message_id': record.message_id,
                    'clicks_count': record.clicks_count,
                    'last_click_at': record.last_click_at
                }

                import json
                redis.client.set(key, json.dumps(data, ensure_ascii=False))
                # Устанавливаем TTL 90 дней
                redis.client.expire(key, 90 * 24 * 60 * 60)

        except Exception as e:
            logger.debug(f"Failed to persist affiliate record: {e}")

    def _update_record_click(self, record: AffiliateLinkRecord):
        """Обновить клики в постоянном хранилище"""
        try:
            import src.config as config
            if config.USE_REDIS:
                from src.core.redis_cache import get_redis_cache
                redis = get_redis_cache()

                key = f"affiliate_clicks:{record.link_id}"
                redis.client.incr(key)
                # Устанавливаем TTL 90 дней
                redis.client.expire(key, 90 * 24 * 60 * 60)

                # Также обновляем last_click_at
                last_click_key = f"affiliate_last_click:{record.link_id}"
                redis.client.set(last_click_key, str(time.time()))
                redis.client.expire(last_click_key, 90 * 24 * 60 * 60)

        except Exception as e:
            logger.debug(f"Failed to update affiliate click: {e}")

    def load_from_persistence(self):
        """Загрузить данные из постоянного хранилища"""
        try:
            import src.config as config
            if config.USE_REDIS:
                from src.core.redis_cache import get_redis_cache
                redis = get_redis_cache()

                # Получаем все ключи affiliate ссылок
                keys = redis.client.keys("affiliate_link:*")
                for key in keys[:1000]:  # Ограничиваем для производительности
                    try:
                        data_json = redis.client.get(key)
                        if data_json:
                            import json
                            data = json.loads(data_json)
                            link_id = key.split(":", 1)[1]

                            record = AffiliateLinkRecord(
                                link_id=link_id,
                                market_id=data['market_id'],
                                erid=data['erid'],
                                affiliate_url=data['affiliate_url'],
                                original_url=data['original_url'],
                                sent_at=data['sent_at'],
                                channel_id=data['channel_id'],
                                message_id=data.get('message_id'),
                                clicks_count=data.get('clicks_count', 0),
                                last_click_at=data.get('last_click_at')
                            )

                            self.records[link_id] = record

                    except Exception as e:
                        logger.debug(f"Failed to load affiliate record {key}: {e}")

                logger.info(f"Loaded {len(self.records)} affiliate records from Redis")

        except Exception as e:
            logger.debug(f"Failed to load affiliate records from persistence: {e}")


# Глобальный экземпляр
_affiliate_tracking_service = None


def get_affiliate_tracking_service() -> AffiliateTrackingService:
    """Получить глобальный экземпляр сервиса трекинга"""
    global _affiliate_tracking_service
    if _affiliate_tracking_service is None:
        _affiliate_tracking_service = AffiliateTrackingService()
        # Загружаем данные из постоянного хранилища
        _affiliate_tracking_service.load_from_persistence()
    return _affiliate_tracking_service


# Вспомогательные функции
def record_affiliate_link_sent(market_id: str, erid: str, affiliate_url: str,
                              original_url: str, channel_id: str, message_id: str = None) -> str:
    """
    Записать отправку affiliate-ссылки

    Returns:
        ID ссылки для будущего трекинга кликов
    """
    service = get_affiliate_tracking_service()
    return service.record_affiliate_link(
        market_id=market_id,
        erid=erid,
        affiliate_url=affiliate_url,
        original_url=original_url,
        channel_id=channel_id,
        message_id=message_id
    )


def record_affiliate_click(link_id: str, user_id: str = None) -> bool:
    """
    Записать клик по affiliate-ссылке

    Returns:
        True если ссылка найдена
    """
    service = get_affiliate_tracking_service()
    return service.record_click(link_id, user_id)
