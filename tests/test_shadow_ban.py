"""
Unit tests for shadow-ban detection service
Tests for shadow-ban detection logic and auto-pause functionality
"""

import unittest
from datetime import datetime, timedelta
from services.shadow_ban_service import ShadowBanService


class TestShadowBanService(unittest.TestCase):
    """Тесты для shadow-ban service"""

    def setUp(self):
        """Настройка перед каждым тестом"""
        self.service = ShadowBanService()

    def test_is_shadow_banned_few_products_large_html(self):
        """Тест детекции: мало товаров + большой HTML"""
        # < 5 товаров и HTML > 500KB → shadow-ban
        result = self.service.is_shadow_banned(products_count=3, html_size=600_000)
        self.assertTrue(result)

    def test_is_shadow_banned_no_products_large_html(self):
        """Тест детекции: 0 товаров + большой HTML"""
        # 0 товаров и HTML > 100KB → shadow-ban
        result = self.service.is_shadow_banned(products_count=0, html_size=200_000)
        self.assertTrue(result)

    def test_is_not_shadow_banned_normal(self):
        """Тест что нормальный парсинг не детектируется как shadow-ban"""
        # Много товаров и нормальный HTML
        result = self.service.is_shadow_banned(products_count=20, html_size=300_000)
        self.assertFalse(result)
        
        # Мало товаров но маленький HTML
        result = self.service.is_shadow_banned(products_count=3, html_size=50_000)
        self.assertFalse(result)

    def test_record_shadow_ban_sets_pause(self):
        """Тест что record_shadow_ban устанавливает паузу"""
        self.service.record_shadow_ban(
            catalog_url="https://market.yandex.ru/catalog--test/",
            products_count=2,
            html_size=600_000
        )
        
        # Пауза должна быть установлена
        self.assertIsNotNone(self.service.pause_until)
        self.assertGreater(self.service.pause_until, datetime.utcnow())

    def test_can_continue_parsing_without_pause(self):
        """Тест что можно продолжать когда паузы нет"""
        result = self.service.can_continue_parsing()
        self.assertTrue(result)

    def test_can_continue_parsing_with_active_pause(self):
        """Тест что нельзя продолжать когда пауза активна"""
        # Устанавливаем паузу на будущее
        self.service.pause_until = datetime.utcnow() + timedelta(hours=1)
        
        result = self.service.can_continue_parsing()
        self.assertFalse(result)

    def test_can_continue_parsing_after_pause_expires(self):
        """Тест что можно продолжать после истечения паузы"""
        # Устанавливаем паузу в прошлом
        self.service.pause_until = datetime.utcnow() - timedelta(minutes=1)
        
        result = self.service.can_continue_parsing()
        self.assertTrue(result)
        # Пауза должна быть сброшена
        self.assertIsNone(self.service.pause_until)

    def test_get_status(self):
        """Тест получения статуса"""
        status = self.service.get_status()
        
        self.assertIn('paused', status)
        self.assertIn('pause_until', status)
        self.assertIn('can_continue', status)
        self.assertFalse(status['paused'])
        self.assertTrue(status['can_continue'])


if __name__ == '__main__':
    unittest.main()

