"""
Click Learning Service - Обучение на кликах (что реально покупают)
Не ML-магия, а умная статистика по категориям/брендам/ценам/типам постов
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import config

logger = logging.getLogger(__name__)


class ClickLearningService:
    """
    Сервис для обучения на кликах

    Учится:
    - категория
    - бренд
    - цена (bucket)
    - тип поста (sell / review / compare / tip)
    - время публикации

    Применяет:
    - 70% — топ-категории
    - 20% — тест новых
    - 10% — эксперименты
    """

    def __init__(self, learning_days: int = 14):
        self.learning_days = learning_days
        self.min_posts_for_learning = getattr(config, 'LEARNING_MIN_POSTS', 5)
        self.min_clicks_for_blacklist = getattr(config, 'LEARNING_MIN_CLICKS_BLACKLIST', 0.3)

        # Кэш для производительности
        self._category_scores: Optional[Dict[str, float]] = None
        self._brand_blacklist: Optional[List[str]] = None
        self._last_update: Optional[datetime] = None
        self._update_interval = timedelta(hours=6)  # Обновляем кэш каждые 6 часов

    def learn_from_clicks(self, category: str, brand: str, price_bucket: str, 
                          post_type: str, clicks: int, posts: int = 1):
        """
        Обучение на кликах

        Args:
            category: Категория товара
            brand: Бренд
            price_bucket: Бакет цены (например, '0-1000', '1000-5000', '5000+')
            post_type: Тип поста ('sell', 'review', 'compare', 'tip')
            clicks: Количество кликов
            posts: Количество постов
        """
        # В реальной реализации здесь будет запись в БД
        # Для простоты логируем
        logger.debug(
            f"Learning: category={category}, brand={brand}, "
            f"price_bucket={price_bucket}, post_type={post_type}, "
            f"clicks={clicks}, posts={posts}"
        )

    def get_category_score(self, category: str, post_type: str, 
                          price_bucket: str) -> float:
        """
        Получить score категории для выбора товаров

        Args:
            category: Категория
            post_type: Тип поста
            price_bucket: Бакет цены

        Returns:
            Score (чем выше, тем лучше)
        """
        # В реальной реализации будет запрос к БД
        # Для примера возвращаем базовый score
        return 1.0

    def get_top_categories(self, limit: int = 10) -> List[Tuple[str, float]]:
        """
        Получить топ категорий по эффективности

        Returns:
            Список (category, score) отсортированный по score
        """
        # В реальной реализации будет запрос к БД category_performance
        # Для примера возвращаем пустой список
        return []

    def should_blacklist_brand(self, brand: str) -> bool:
        """
        Проверить, нужно ли добавить бренд в blacklist

        Args:
            brand: Бренд для проверки

        Returns:
            True если нужно добавить в blacklist
        """
        if not self._brand_blacklist:
            self._update_brand_blacklist()

        return brand in (self._brand_blacklist or [])

    def _update_brand_blacklist(self):
        """Обновить blacklist брендов из БД"""
        # В реальной реализации будет запрос к БД brand_performance
        # Бренды с avg_clicks_per_post < min_clicks_for_blacklist → в blacklist
        self._brand_blacklist = []

    def get_post_type_preference(self, category: str) -> Dict[str, float]:
        """
        Получить предпочтения по типам постов для категории

        Args:
            category: Категория

        Returns:
            Словарь {post_type: score}
        """
        # В реальной реализации будет запрос к БД category_performance
        # Возвращаем равномерное распределение для примера
        return {
            'sell': 1.0,
            'review': 1.0,
            'compare': 1.0,
            'tip': 1.0
        }

    def get_selection_strategy(self) -> Dict[str, float]:
        """
        Получить стратегию выбора товаров

        Returns:
            Словарь {'top_categories': 0.7, 'new_tests': 0.2, 'experiments': 0.1}
        """
        return {
            'top_categories': 0.7,  # 70% — топ-категории
            'new_tests': 0.2,  # 20% — тест новых
            'experiments': 0.1  # 10% — эксперименты
        }

    def cleanup_stale_data(self, days_to_keep: int = 30):
        """
        Очистка устаревших данных

        Args:
            days_to_keep: Количество дней истории для хранения
        """
        # В реальной реализации будет удаление старых записей из БД
        logger.info(f"Cleaning up stale learning data (keeping {days_to_keep} days)")

    def get_learning_stats(self) -> Dict:
        """Получить статистику обучения"""
        return {
            'top_categories': len(self.get_top_categories()),
            'blacklisted_brands': len(self._brand_blacklist or []),
            'learning_days': self.learning_days,
            'last_update': self._last_update.isoformat() if self._last_update else None
        }


# Глобальный экземпляр
_click_learning_service = None


def get_click_learning_service() -> ClickLearningService:
    """Get global click learning service instance"""
    global _click_learning_service
    if _click_learning_service is None:
        _click_learning_service = ClickLearningService()
    return _click_learning_service

