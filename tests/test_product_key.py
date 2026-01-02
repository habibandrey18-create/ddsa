"""
Unit tests for product_key generation
Tests for SHA-1 hash usage and determinism
"""

import unittest
import hashlib
from services.validator_service import ProductValidator
from services.smart_search_service import SmartSearchService


class TestProductKeyGeneration(unittest.TestCase):
    """Тесты для генерации product_key"""

    def test_product_key_deterministic(self):
        """Тест что product_key детерминированный (одинаковые данные → одинаковый ключ)"""
        validator = ProductValidator()
        
        product1 = {
            'offerid': 'test123',
            'url': 'https://market.yandex.ru/product/12345',
            'title': 'Test Product',
            'vendor': 'TestVendor'
        }
        
        product2 = {
            'offerid': 'test123',
            'url': 'https://market.yandex.ru/product/12345',
            'title': 'Test Product',
            'vendor': 'TestVendor'
        }
        
        key1 = validator._generate_product_key(product1)
        key2 = validator._generate_product_key(product2)
        
        # Ключи должны быть одинаковыми
        self.assertEqual(key1, key2)
        
        # Ключ должен быть SHA-1 hash (40 символов hex)
        self.assertEqual(len(key1), 40)
        self.assertTrue(all(c in '0123456789abcdef' for c in key1))

    def test_product_key_different_for_different_products(self):
        """Тест что разные продукты дают разные ключи"""
        validator = ProductValidator()
        
        product1 = {
            'title': 'Product A',
            'vendor': 'Vendor1'
        }
        
        product2 = {
            'title': 'Product B',
            'vendor': 'Vendor1'
        }
        
        key1 = validator._generate_product_key(product1)
        key2 = validator._generate_product_key(product2)
        
        # Ключи должны быть разными
        self.assertNotEqual(key1, key2)

    def test_product_key_uses_sha1_not_python_hash(self):
        """Тест что используется SHA-1, а не Python hash()"""
        validator = ProductValidator()
        
        product = {
            'title': 'Test',
            'vendor': 'Test'
        }
        
        key = validator._generate_product_key(product)
        
        # SHA-1 всегда 40 символов hex
        self.assertEqual(len(key), 40)
        
        # Python hash() давал бы строку с минусом, SHA-1 всегда hex
        self.assertFalse(key.startswith('-'))
        self.assertTrue(all(c in '0123456789abcdef' for c in key))

    def test_smart_search_product_key_deterministic(self):
        """Тест детерминированности для SmartSearchService"""
        service = SmartSearchService()
        
        product1 = {
            'market_id': '12345',
            'title': 'Test Product',
            'vendor': 'TestVendor',
            'url': 'https://market.yandex.ru/product/12345'
        }
        
        product2 = {
            'market_id': '12345',
            'title': 'Test Product',
            'vendor': 'TestVendor',
            'url': 'https://market.yandex.ru/product/12345'
        }
        
        key1 = service._generate_product_key(product1)
        key2 = service._generate_product_key(product2)
        
        # Ключи должны быть одинаковыми
        self.assertEqual(key1, key2)
        
        # Должен быть SHA-1 (40 символов)
        self.assertEqual(len(key1), 40)


if __name__ == '__main__':
    unittest.main()

