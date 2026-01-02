"""
DB Batch Service - Bulk inserts и batch операции для оптимизации производительности
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)


class DBBatchService:
    """Сервис для batch операций с БД"""
    
    def __init__(self, batch_size: int = 100):
        self.batch_size = batch_size
        self._product_batch = []
        self._metrics_batch = []
        self._lock = asyncio.Lock()
    
    async def add_product(self, product: Dict[str, Any]) -> bool:
        """
        Добавить продукт в batch
        
        Args:
            product: Данные продукта
            
        Returns:
            True если batch был сброшен, False если еще накапливается
        """
        async with self._lock:
            self._product_batch.append(product)
            
            if len(self._product_batch) >= self.batch_size:
                await self._flush_products()
                return True
            return False
    
    async def add_metric(self, metric: Dict[str, Any]) -> bool:
        """
        Добавить метрику в batch
        
        Args:
            metric: Данные метрики
            
        Returns:
            True если batch был сброшен, False если еще накапливается
        """
        async with self._lock:
            self._metrics_batch.append(metric)
            
            if len(self._metrics_batch) >= self.batch_size:
                await self._flush_metrics()
                return True
            return False
    
    async def _flush_products(self):
        """Сброс batch продуктов в БД"""
        if not self._product_batch:
            return
        
        try:
            import config
            if config.USE_POSTGRES:
                await self._flush_products_postgres()
            else:
                await self._flush_products_sqlite()
            
            logger.info(f"Flushed {len(self._product_batch)} products to DB")
            self._product_batch.clear()
        except Exception as e:
            logger.error(f"Failed to flush products batch: {e}")
            # Не очищаем batch при ошибке, попробуем позже
    
    async def _flush_products_postgres(self):
        """Bulk insert для Postgres"""
        from database_postgres import get_postgres_db
        from sqlalchemy import text
        
        db = get_postgres_db()
        session = db.get_session()
        
        try:
            # Используем executemany для bulk insert
            values = []
            for product in self._product_batch:
                values.append({
                    'product_key': product.get('product_key'),
                    'url': product.get('url'),
                    'title': product.get('title'),
                    'vendor': product.get('vendor'),
                    'price': product.get('price'),
                    'old_price': product.get('old_price'),
                    'discount_percent': product.get('discount_percent', 0),
                    'rating': product.get('rating'),
                    'reviews_count': product.get('reviews_count'),
                    'offerid': product.get('offerid'),
                    'market_id': product.get('market_id'),
                    'added_at': datetime.utcnow()
                })
            
            # Bulk insert с ON CONFLICT DO NOTHING
            stmt = text("""
                INSERT INTO products 
                (product_key, url, title, vendor, price, old_price, discount_percent, 
                 rating, reviews_count, offerid, market_id, added_at)
                VALUES 
                (:product_key, :url, :title, :vendor, :price, :old_price, :discount_percent,
                 :rating, :reviews_count, :offerid, :market_id, :added_at)
                ON CONFLICT (product_key) DO NOTHING
            """)
            
            session.execute(stmt, values)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    async def _flush_products_sqlite(self):
        """Bulk insert для SQLite"""
        from database import Database
        
        db = Database()
        
        try:
            # SQLite executemany для bulk insert
            values = []
            for product in self._product_batch:
                values.append((
                    product.get('product_key'),
                    product.get('url'),
                    product.get('title'),
                    product.get('vendor'),
                    product.get('price'),
                    product.get('old_price'),
                    product.get('discount_percent', 0),
                    product.get('rating'),
                    product.get('reviews_count'),
                    product.get('offerid'),
                    product.get('market_id')
                ))
            
            db.cursor.executemany("""
                INSERT OR IGNORE INTO products 
                (product_key, url, title, vendor, price, old_price, discount_percent,
                 rating, reviews_count, offerid, market_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, values)
            
            db.connection.commit()
        except Exception as e:
            db.connection.rollback()
            raise e
    
    async def _flush_metrics(self):
        """Сброс batch метрик в БД"""
        if not self._metrics_batch:
            return
        
        try:
            import config
            if config.USE_POSTGRES:
                await self._flush_metrics_postgres()
            else:
                await self._flush_metrics_sqlite()
            
            logger.info(f"Flushed {len(self._metrics_batch)} metrics to DB")
            self._metrics_batch.clear()
        except Exception as e:
            logger.error(f"Failed to flush metrics batch: {e}")
    
    async def _flush_metrics_postgres(self):
        """Bulk insert метрик для Postgres"""
        from database_postgres import get_postgres_db
        from sqlalchemy import text
        
        db = get_postgres_db()
        session = db.get_session()
        
        try:
            values = []
            for metric in self._metrics_batch:
                values.append({
                    'product_key': metric.get('product_key'),
                    'metric_type': metric.get('metric_type'),
                    'value': metric.get('value'),
                    'timestamp': datetime.utcnow()
                })
            
            stmt = text("""
                INSERT INTO metrics (product_key, metric_type, value, timestamp)
                VALUES (:product_key, :metric_type, :value, :timestamp)
            """)
            
            session.execute(stmt, values)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    async def _flush_metrics_sqlite(self):
        """Bulk insert метрик для SQLite"""
        from database import Database
        
        db = Database()
        
        try:
            values = []
            for metric in self._metrics_batch:
                values.append((
                    metric.get('product_key'),
                    metric.get('metric_type'),
                    metric.get('value'),
                    datetime.utcnow().isoformat()
                ))
            
            db.cursor.executemany("""
                INSERT INTO metrics (product_key, metric_type, value, timestamp)
                VALUES (?, ?, ?, ?)
            """, values)
            
            db.connection.commit()
        except Exception as e:
            db.connection.rollback()
            raise e
    
    async def flush_all(self):
        """Принудительный сброс всех batch"""
        async with self._lock:
            await self._flush_products()
            await self._flush_metrics()
    
    def get_stats(self) -> Dict[str, int]:
        """Получить статистику batch"""
        return {
            'products_pending': len(self._product_batch),
            'metrics_pending': len(self._metrics_batch),
            'batch_size': self.batch_size
        }


# Singleton instance
_batch_service: Optional[DBBatchService] = None


def get_batch_service(batch_size: int = 100) -> DBBatchService:
    """Получить глобальный экземпляр DBBatchService"""
    global _batch_service
    if _batch_service is None:
        _batch_service = DBBatchService(batch_size)
    return _batch_service

