"""
Unit tests for improved affiliate link generation
Tests for ERID generation, URL parsing, and parameter handling
"""

import unittest
from urllib.parse import urlparse, parse_qs
from services.affiliate_service import generate_erid, get_affiliate_link


class TestAffiliateService(unittest.TestCase):
    """Тесты для affiliate service"""

    def test_generate_erid_format(self):
        """Тест формата ERID: tg-YYYYMMDD-XXXXXX"""
        erid = generate_erid()
        
        # Проверяем формат
        self.assertTrue(erid.startswith("tg-"))
        parts = erid.split("-")
        self.assertEqual(len(parts), 3)
        
        # Проверяем дату (YYYYMMDD)
        self.assertEqual(len(parts[1]), 8)
        self.assertTrue(parts[1].isdigit())
        
        # Проверяем UUID часть (6 символов hex)
        self.assertEqual(len(parts[2]), 6)
        self.assertTrue(all(c in '0123456789abcdef' for c in parts[2]))

    def test_generate_erid_unique(self):
        """Тест что ERID уникальны"""
        erid1 = generate_erid()
        erid2 = generate_erid()
        
        # Они должны быть разными (с высокой вероятностью)
        self.assertNotEqual(erid1, erid2)

    def test_affiliate_link_removes_query_params(self):
        """Тест что существующие query параметры удаляются"""
        original_url = "https://market.yandex.ru/product/12345?existing=param&another=value"
        
        # Мокаем config для теста
        import config
        original_clid = getattr(config, 'AFFILIATE_CLID', None)
        config.AFFILIATE_CLID = "test_clid"
        
        try:
            affiliate_link, erid = get_affiliate_link(original_url)
            
            # Парсим результирующую ссылку
            parsed = urlparse(affiliate_link)
            params = parse_qs(parsed.query)
            
            # Старые параметры не должны быть
            self.assertNotIn('existing', params)
            self.assertNotIn('another', params)
            
            # Новые параметры должны быть
            self.assertIn('clid', params)
            self.assertIn('erid', params)
            self.assertEqual(params['clid'][0], "test_clid")
            
        finally:
            # Восстанавливаем оригинальный config
            if original_clid:
                config.AFFILIATE_CLID = original_clid
            else:
                delattr(config, 'AFFILIATE_CLID')

    def test_affiliate_link_adds_utm_params(self):
        """Тест что UTM параметры добавляются"""
        original_url = "https://market.yandex.ru/product/12345"
        
        import config
        original_clid = getattr(config, 'AFFILIATE_CLID', None)
        config.AFFILIATE_CLID = "test_clid"
        
        try:
            affiliate_link, erid = get_affiliate_link(original_url)
            
            parsed = urlparse(affiliate_link)
            params = parse_qs(parsed.query)
            
            # Проверяем UTM параметры
            self.assertIn('utm_source', params)
            self.assertIn('utm_medium', params)
            self.assertIn('utm_campaign', params)
            
        finally:
            if original_clid:
                config.AFFILIATE_CLID = original_clid
            else:
                delattr(config, 'AFFILIATE_CLID')

    def test_affiliate_link_removes_fragment(self):
        """Тест что fragment удаляется"""
        original_url = "https://market.yandex.ru/product/12345#section"
        
        import config
        original_clid = getattr(config, 'AFFILIATE_CLID', None)
        config.AFFILIATE_CLID = "test_clid"
        
        try:
            affiliate_link, erid = get_affiliate_link(original_url)
            
            # Fragment не должен быть в результирующей ссылке
            self.assertNotIn('#', affiliate_link)
            
        finally:
            if original_clid:
                config.AFFILIATE_CLID = original_clid
            else:
                delattr(config, 'AFFILIATE_CLID')

    def test_affiliate_link_no_clid_returns_clean(self):
        """Тест что без clid возвращается чистый URL"""
        original_url = "https://market.yandex.ru/product/12345?existing=param"
        
        import config
        original_clid = getattr(config, 'AFFILIATE_CLID', None)
        # Удаляем clid если есть
        if hasattr(config, 'AFFILIATE_CLID'):
            delattr(config, 'AFFILIATE_CLID')
        if hasattr(config, 'YANDEX_REF_CLID'):
            delattr(config, 'YANDEX_REF_CLID')
        
        try:
            affiliate_link, erid = get_affiliate_link(original_url)
            
            # Должен вернуться оригинальный URL (или близкий к нему)
            self.assertEqual(affiliate_link, original_url)
            self.assertEqual(erid, "")
            
        finally:
            if original_clid:
                config.AFFILIATE_CLID = original_clid


if __name__ == '__main__':
    unittest.main()

