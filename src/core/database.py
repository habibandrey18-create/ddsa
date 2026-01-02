# database_postgres.py - Postgres implementation of the new architecture
import logging
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, Numeric, Float, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql import func
import src.config as config

logger = logging.getLogger(__name__)

Base = declarative_base()

class SearchKey(Base):
    """Таблица для умного автопоиска с offset per keyword"""
    __tablename__ = 'search_keys'

    id = Column(Integer, primary_key=True)
    key_text = Column(Text, unique=True, nullable=False)
    last_page = Column(Integer, default=0)
    last_offset = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Product(Base):
    """Основная таблица товаров"""
    __tablename__ = 'products'

    id = Column(String, primary_key=True)  # market_id
    url = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    vendor = Column(String)
    offerid = Column(String)
    price = Column(Numeric(10, 2))
    old_price = Column(Numeric(10, 2))
    discount_percent = Column(Float)
    rating = Column(Float)
    reviews_count = Column(Integer)
    images = Column(JSONB)  # Список URL изображений
    specs = Column(JSONB)  # Характеристики
    marketing_description = Column(Text)
    availability = Column(Boolean, default=True)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Индексы для производительности
    __table_args__ = (
        Index('idx_products_vendor', 'vendor'),
        Index('idx_products_price', 'price'),
        Index('idx_products_discount', 'discount_percent'),
        Index('idx_products_rating', 'rating'),
        Index('idx_products_last_updated', 'last_updated'),
    )

class PriceHistory(Base):
    """История цен для price alerts"""
    __tablename__ = 'price_history'

    id = Column(Integer, primary_key=True)
    product_id = Column(String, nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    old_price = Column(Numeric(10, 2))
    discount_percent = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_price_history_product_id', 'product_id'),
        Index('idx_price_history_timestamp', 'timestamp'),
    )

class BrandList(Base):
    """Белый/чёрный список брендов"""
    __tablename__ = 'brand_lists'

    brand = Column(String, primary_key=True)
    list_type = Column(String, nullable=False)  # 'whitelist' или 'blacklist'

class PublishedPost(Base):
    """Опубликованные посты"""
    __tablename__ = 'published_posts'

    id = Column(Integer, primary_key=True)
    product_id = Column(String, nullable=False)
    post_text = Column(Text)
    template_used = Column(String)
    cta_used = Column(String)
    brand = Column(String)
    price = Column(Numeric(10, 2))
    discount_percent = Column(Float)
    published_at = Column(DateTime, default=datetime.utcnow)
    channel_message_id = Column(Integer)

    __table_args__ = (
        Index('idx_published_posts_product_id', 'product_id'),
        Index('idx_published_posts_published_at', 'published_at'),
        Index('idx_published_posts_brand', 'brand'),
    )

class PostMetric(Base):
    """Метрики постов"""
    __tablename__ = 'post_metrics'

    id = Column(Integer, primary_key=True)
    post_id = Column(Integer)  # Ссылка на published_posts.id
    product_id = Column(String)
    clicks = Column(Integer, default=0)
    impressions = Column(Integer, default=0)
    brand = Column(String)
    price = Column(Numeric(10, 2))
    template_used = Column(String)
    cta_used = Column(String)
    published_at = Column(DateTime)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_post_metrics_post_id', 'post_id'),
        Index('idx_post_metrics_published_at', 'published_at'),
        Index('idx_post_metrics_brand', 'brand'),
    )

class DatabasePostgres:
    """Postgres database implementation for the new architecture"""

    def __init__(self):
        if not config.USE_POSTGRES:
            raise ValueError("Postgres is not enabled in config")

        # Создаем connection string
        connection_string = f"postgresql://{config.POSTGRES_USER}:{config.POSTGRES_PASSWORD}@{config.POSTGRES_HOST}:{config.POSTGRES_PORT}/{config.POSTGRES_DB}"

        self.engine = create_engine(
            connection_string,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=False  # Set to True for SQL debugging
        )

        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        # Создаем таблицы
        Base.metadata.create_all(bind=self.engine)
        logger.info("Postgres database initialized")

    def get_session(self) -> Session:
        """Get database session"""
        return self.SessionLocal()

    def close_session(self, session: Session):
        """Close database session"""
        session.close()

    # Методы для умного автопоиска
    def get_search_key(self, key_text: str) -> Optional[Dict]:
        """Получить состояние поиска для ключа"""
        with self.get_session() as session:
            key = session.query(SearchKey).filter(SearchKey.key_text == key_text).first()
            if key:
                return {
                    'id': key.id,
                    'key_text': key.key_text,
                    'last_page': key.last_page,
                    'last_offset': key.last_offset,
                    'updated_at': key.updated_at.isoformat() if key.updated_at else None
                }
            return None

    def update_search_key(self, key_text: str, last_page: int = None, last_offset: int = None):
        """Обновить состояние поиска для ключа"""
        with self.get_session() as session:
            key = session.query(SearchKey).filter(SearchKey.key_text == key_text).first()
            if not key:
                key = SearchKey(key_text=key_text)

            if last_page is not None:
                key.last_page = last_page
            if last_offset is not None:
                key.last_offset = last_offset

            session.merge(key)
            session.commit()

    def get_or_create_search_key(self, key_text: str) -> Dict:
        """Получить или создать ключ поиска"""
        key = self.get_search_key(key_text)
        if not key:
            with self.get_session() as session:
                new_key = SearchKey(key_text=key_text)
                session.add(new_key)
                session.commit()
                key = self.get_search_key(key_text)
        return key

    # Методы для работы с товарами
    def save_product(self, product_data: Dict):
        """Сохранить или обновить товар"""
        with self.get_session() as session:
            product_id = product_data['id']

            # Проверяем существует ли товар
            existing = session.query(Product).filter(Product.id == product_id).first()

            if existing:
                # Обновляем существующий
                for key, value in product_data.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
                existing.last_updated = datetime.utcnow()
            else:
                # Создаем новый
                product = Product(**product_data)
                session.add(product)

            session.commit()

    def get_product(self, product_id: str) -> Optional[Dict]:
        """Получить товар по ID"""
        with self.get_session() as session:
            product = session.query(Product).filter(Product.id == product_id).first()
            if product:
                return {
                    'id': product.id,
                    'url': product.url,
                    'title': product.title,
                    'vendor': product.vendor,
                    'offerid': product.offerid,
                    'price': float(product.price) if product.price else None,
                    'old_price': float(product.old_price) if product.old_price else None,
                    'discount_percent': product.discount_percent,
                    'rating': product.rating,
                    'reviews_count': product.reviews_count,
                    'images': product.images,
                    'specs': product.specs,
                    'marketing_description': product.marketing_description,
                    'availability': product.availability,
                    'last_updated': product.last_updated.isoformat() if product.last_updated else None,
                    'created_at': product.created_at.isoformat() if product.created_at else None
                }
            return None

    # Методы для истории цен
    def save_price_history(self, product_id: str, price: float, old_price: float = None, discount_percent: float = None):
        """Сохранить запись в истории цен"""
        with self.get_session() as session:
            history = PriceHistory(
                product_id=product_id,
                price=price,
                old_price=old_price,
                discount_percent=discount_percent
            )
            session.add(history)
            session.commit()

    def get_price_history(self, product_id: str, days: int = 30) -> List[Dict]:
        """Получить историю цен за последние N дней"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        with self.get_session() as session:
            history = session.query(PriceHistory)\
                .filter(PriceHistory.product_id == product_id)\
                .filter(PriceHistory.timestamp >= cutoff_date)\
                .order_by(PriceHistory.timestamp.desc())\
                .all()

            return [{
                'id': h.id,
                'product_id': h.product_id,
                'price': float(h.price),
                'old_price': float(h.old_price) if h.old_price else None,
                'discount_percent': h.discount_percent,
                'timestamp': h.timestamp.isoformat()
            } for h in history]

    def get_min_price_last_days(self, product_id: str, days: int = 30) -> Optional[float]:
        """Получить минимальную цену за последние N дней"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        with self.get_session() as session:
            result = session.query(func.min(PriceHistory.price))\
                .filter(PriceHistory.product_id == product_id)\
                .filter(PriceHistory.timestamp >= cutoff_date)\
                .scalar()

            return float(result) if result else None

    # Методы для брендов
    def add_brand_to_list(self, brand: str, list_type: str):
        """Добавить бренд в список (whitelist/blacklist)"""
        with self.get_session() as session:
            brand_entry = BrandList(brand=brand, list_type=list_type)
            session.merge(brand_entry)  # merge для upsert
            session.commit()

    def remove_brand_from_list(self, brand: str):
        """Удалить бренд из списка"""
        with self.get_session() as session:
            session.query(BrandList).filter(BrandList.brand == brand).delete()
            session.commit()

    def get_brand_list_type(self, brand: str) -> Optional[str]:
        """Получить тип списка для бренда"""
        with self.get_session() as session:
            brand_entry = session.query(BrandList).filter(BrandList.brand == brand).first()
            return brand_entry.list_type if brand_entry else None

    def is_brand_blacklisted(self, brand: str) -> bool:
        """Проверить, находится ли бренд в чёрном списке"""
        return self.get_brand_list_type(brand) == 'blacklist'

    def is_brand_whitelisted(self, brand: str) -> bool:
        """Проверить, находится ли бренд в белом списке"""
        return self.get_brand_list_type(brand) == 'whitelist'

    def get_whitelist_brands(self) -> List[str]:
        """Получить все бренды из белого списка"""
        with self.get_session() as session:
            brands = session.query(BrandList.brand).filter(BrandList.list_type == 'whitelist').all()
            return [b[0] for b in brands]

    # Методы для опубликованных постов
    def save_published_post(self, product_id: str, post_text: str, template_used: str = None,
                          cta_used: str = None, brand: str = None, price: float = None,
                          discount_percent: float = None, channel_message_id: int = None):
        """Сохранить опубликованный пост"""
        with self.get_session() as session:
            post = PublishedPost(
                product_id=product_id,
                post_text=post_text,
                template_used=template_used,
                cta_used=cta_used,
                brand=brand,
                price=price,
                discount_percent=discount_percent,
                channel_message_id=channel_message_id
            )
            session.add(post)
            session.commit()
            return post.id

    def get_recent_posts_by_brand(self, brand: str, limit: int = 10) -> List[Dict]:
        """Получить недавние посты по бренду"""
        with self.get_session() as session:
            posts = session.query(PublishedPost)\
                .filter(PublishedPost.brand == brand)\
                .order_by(PublishedPost.published_at.desc())\
                .limit(limit)\
                .all()

            return [{
                'id': p.id,
                'product_id': p.product_id,
                'post_text': p.post_text,
                'template_used': p.template_used,
                'cta_used': p.cta_used,
                'brand': p.brand,
                'price': float(p.price) if p.price else None,
                'discount_percent': p.discount_percent,
                'published_at': p.published_at.isoformat(),
                'channel_message_id': p.channel_message_id
            } for p in posts]

    # Методы для метрик
    def save_post_metrics(self, post_id: int, product_id: str, brand: str = None,
                         price: float = None, template_used: str = None, cta_used: str = None,
                         published_at: datetime = None):
        """Создать запись метрик для поста"""
        with self.get_session() as session:
            metrics = PostMetric(
                post_id=post_id,
                product_id=product_id,
                brand=brand,
                price=price,
                template_used=template_used,
                cta_used=cta_used,
                published_at=published_at or datetime.utcnow()
            )
            session.add(metrics)
            session.commit()
            return metrics.id

    def increment_clicks(self, post_id: int):
        """Увеличить счетчик кликов"""
        with self.get_session() as session:
            metrics = session.query(PostMetric).filter(PostMetric.post_id == post_id).first()
            if metrics:
                metrics.clicks += 1
                metrics.last_updated = datetime.utcnow()
                session.commit()

    def increment_impressions(self, post_id: int):
        """Увеличить счетчик просмотров"""
        with self.get_session() as session:
            metrics = session.query(PostMetric).filter(PostMetric.post_id == post_id).first()
            if metrics:
                metrics.impressions += 1
                metrics.last_updated = datetime.utcnow()
                session.commit()

    def get_metrics_summary(self, days: int = 30) -> Dict:
        """Получить сводку метрик за период"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        with self.get_session() as session:
            # Общая статистика
            total_posts = session.query(func.count(PublishedPost.id))\
                .filter(PublishedPost.published_at >= cutoff_date)\
                .scalar() or 0

            total_clicks = session.query(func.sum(PostMetric.clicks))\
                .filter(PostMetric.published_at >= cutoff_date)\
                .scalar() or 0

            total_impressions = session.query(func.sum(PostMetric.impressions))\
                .filter(PostMetric.published_at >= cutoff_date)\
                .scalar() or 0

            # CTR по брендам
            brand_stats = session.query(
                PostMetric.brand,
                func.sum(PostMetric.clicks).label('clicks'),
                func.sum(PostMetric.impressions).label('impressions')
            )\
                .filter(PostMetric.published_at >= cutoff_date)\
                .filter(PostMetric.brand.isnot(None))\
                .group_by(PostMetric.brand)\
                .all()

            brand_ctr = []
            for stat in brand_stats:
                ctr = (stat.clicks / stat.impressions * 100) if stat.impressions > 0 else 0
                brand_ctr.append({
                    'brand': stat.brand,
                    'clicks': stat.clicks,
                    'impressions': stat.impressions,
                    'ctr': round(ctr, 2)
                })

            # CTR по шаблонам
            template_stats = session.query(
                PostMetric.template_used,
                func.sum(PostMetric.clicks).label('clicks'),
                func.sum(PostMetric.impressions).label('impressions')
            )\
                .filter(PostMetric.published_at >= cutoff_date)\
                .filter(PostMetric.template_used.isnot(None))\
                .group_by(PostMetric.template_used)\
                .all()

            template_ctr = []
            for stat in template_stats:
                ctr = (stat.clicks / stat.impressions * 100) if stat.impressions > 0 else 0
                template_ctr.append({
                    'template': stat.template_used,
                    'clicks': stat.clicks,
                    'impressions': stat.impressions,
                    'ctr': round(ctr, 2)
                })

            return {
                'total_posts': total_posts,
                'total_clicks': total_clicks,
                'total_impressions': total_impressions,
                'overall_ctr': round((total_clicks / total_impressions * 100) if total_impressions > 0 else 0, 2),
                'brand_ctr': sorted(brand_ctr, key=lambda x: x['ctr'], reverse=True),
                'template_ctr': sorted(template_ctr, key=lambda x: x['ctr'], reverse=True)
            }

# Глобальный экземпляр
_db_postgres = None

def get_postgres_db() -> DatabasePostgres:
    """Get global Postgres database instance"""
    global _db_postgres
    if _db_postgres is None and config.USE_POSTGRES:
        _db_postgres = DatabasePostgres()
    return _db_postgres
