"""
Catalog Scoring Service - Умный выбор каталогов на основе производительности
Приоритизация каталогов по метрикам: CTR, конверсия, качество товаров
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import json
import os

logger = logging.getLogger(__name__)


class CatalogScoringService:
    """Сервис для оценки и приоритизации каталогов"""
    
    def __init__(self):
        self.catalog_stats = defaultdict(lambda: {
            'products_found': 0,
            'products_published': 0,
            'total_clicks': 0,
            'total_views': 0,
            'last_parsed': None,
            'shadow_ban_count': 0,
            'avg_price': 0,
            'avg_discount': 0
        })
        self._load_stats()
    
    def _load_stats(self):
        """Загрузка статистики из файла"""
        stats_file = "catalog_stats.json"
        try:
            if os.path.exists(stats_file):
                with open(stats_file, 'r') as f:
                    loaded_stats = json.load(f)
                    # Конвертируем обратно в defaultdict
                    for catalog, stats in loaded_stats.items():
                        self.catalog_stats[catalog] = stats
                logger.info(f"Loaded stats for {len(self.catalog_stats)} catalogs")
        except Exception as e:
            logger.warning(f"Failed to load catalog stats: {e}")
    
    def _save_stats(self):
        """Сохранение статистики в файл"""
        stats_file = "catalog_stats.json"
        try:
            with open(stats_file, 'w') as f:
                json.dump(dict(self.catalog_stats), f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Failed to save catalog stats: {e}")
    
    def record_parse(self, catalog_url: str, products_found: int):
        """
        Записать результаты парсинга каталога
        
        Args:
            catalog_url: URL каталога
            products_found: Количество найденных товаров
        """
        stats = self.catalog_stats[catalog_url]
        stats['products_found'] += products_found
        stats['last_parsed'] = datetime.utcnow().isoformat()
        self._save_stats()
    
    def record_publish(self, catalog_url: str, product_data: Dict[str, Any]):
        """
        Записать публикацию товара из каталога
        
        Args:
            catalog_url: URL каталога
            product_data: Данные товара
        """
        stats = self.catalog_stats[catalog_url]
        stats['products_published'] += 1
        
        # Обновляем средние метрики
        price = product_data.get('price', 0)
        discount = product_data.get('discount_percent', 0)
        
        if price:
            current_avg = stats['avg_price']
            count = stats['products_published']
            stats['avg_price'] = (current_avg * (count - 1) + price) / count
        
        if discount:
            current_avg = stats['avg_discount']
            count = stats['products_published']
            stats['avg_discount'] = (current_avg * (count - 1) + discount) / count
        
        self._save_stats()
    
    def record_click(self, catalog_url: str):
        """
        Записать клик по товару из каталога
        
        Args:
            catalog_url: URL каталога
        """
        stats = self.catalog_stats[catalog_url]
        stats['total_clicks'] += 1
        self._save_stats()
    
    def record_view(self, catalog_url: str):
        """
        Записать просмотр товара из каталога
        
        Args:
            catalog_url: URL каталога
        """
        stats = self.catalog_stats[catalog_url]
        stats['total_views'] += 1
        self._save_stats()
    
    def record_shadow_ban(self, catalog_url: str):
        """
        Записать shadow-ban для каталога
        
        Args:
            catalog_url: URL каталога
        """
        stats = self.catalog_stats[catalog_url]
        stats['shadow_ban_count'] += 1
        self._save_stats()
    
    def calculate_score(self, catalog_url: str) -> float:
        """
        Рассчитать score каталога (0-100)
        
        Факторы:
        - CTR (click-through rate)
        - Количество публикаций
        - Средняя скидка
        - Частота shadow-ban
        - Свежесть данных
        
        Args:
            catalog_url: URL каталога
            
        Returns:
            Score от 0 до 100
        """
        stats = self.catalog_stats[catalog_url]
        
        score = 50.0  # Базовый score для новых каталогов
        
        # CTR (0-30 баллов)
        if stats['total_views'] > 0:
            ctr = stats['total_clicks'] / stats['total_views']
            ctr_score = min(ctr * 100, 30)  # Max 30 баллов
            score += ctr_score
        
        # Количество публикаций (0-20 баллов)
        publications = stats['products_published']
        pub_score = min(publications / 10, 20)  # 1 публикация = 2 балла, max 20
        score += pub_score
        
        # Средняя скидка (0-15 баллов)
        discount_score = min(stats['avg_discount'] / 10, 15)  # 10% скидка = 1.5 балла
        score += discount_score
        
        # Штраф за shadow-ban (-5 баллов за каждый)
        shadow_ban_penalty = stats['shadow_ban_count'] * 5
        score -= shadow_ban_penalty
        
        # Штраф за устаревшие данные (-10 баллов если не парсили > 7 дней)
        if stats['last_parsed']:
            try:
                last_parsed = datetime.fromisoformat(stats['last_parsed'])
                days_since_parse = (datetime.utcnow() - last_parsed).days
                if days_since_parse > 7:
                    score -= 10
            except:
                pass
        
        # Бонус за свежие данные (+10 баллов если парсили < 1 дня назад)
        if stats['last_parsed']:
            try:
                last_parsed = datetime.fromisoformat(stats['last_parsed'])
                hours_since_parse = (datetime.utcnow() - last_parsed).total_seconds() / 3600
                if hours_since_parse < 24:
                    score += 10
            except:
                pass
        
        # Ограничиваем score в диапазоне 0-100
        return max(0, min(100, score))
    
    def get_ranked_catalogs(self, catalog_urls: List[str]) -> List[Dict[str, Any]]:
        """
        Получить список каталогов отсортированных по score
        
        Args:
            catalog_urls: Список URL каталогов
            
        Returns:
            Список словарей с URL и score, отсортированный по убыванию score
        """
        ranked = []
        for url in catalog_urls:
            score = self.calculate_score(url)
            ranked.append({
                'url': url,
                'score': score,
                'stats': self.catalog_stats[url]
            })
        
        # Сортируем по score (убывание)
        ranked.sort(key=lambda x: x['score'], reverse=True)
        return ranked
    
    def get_top_catalogs(self, catalog_urls: List[str], top_n: int = 5) -> List[str]:
        """
        Получить top N каталогов по score
        
        Args:
            catalog_urls: Список URL каталогов
            top_n: Количество топ каталогов
            
        Returns:
            Список URL топ каталогов
        """
        ranked = self.get_ranked_catalogs(catalog_urls)
        return [item['url'] for item in ranked[:top_n]]
    
    def get_stats(self, catalog_url: str) -> Dict[str, Any]:
        """
        Получить статистику для каталога
        
        Args:
            catalog_url: URL каталога
            
        Returns:
            Словарь со статистикой
        """
        stats = dict(self.catalog_stats[catalog_url])
        stats['score'] = self.calculate_score(catalog_url)
        return stats
    
    def reset_stats(self, catalog_url: str):
        """
        Сбросить статистику для каталога
        
        Args:
            catalog_url: URL каталога
        """
        if catalog_url in self.catalog_stats:
            del self.catalog_stats[catalog_url]
            self._save_stats()


# Singleton instance
_scoring_service: Optional[CatalogScoringService] = None


def get_scoring_service() -> CatalogScoringService:
    """Получить глобальный экземпляр CatalogScoringService"""
    global _scoring_service
    if _scoring_service is None:
        _scoring_service = CatalogScoringService()
    return _scoring_service

