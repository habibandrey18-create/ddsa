"""
Integration Tests - Тесты полного pipeline бота
"""

import unittest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from typing import Dict, Any


class TestFullPipeline(unittest.TestCase):
    """Интеграционные тесты полного pipeline"""
    
    def setUp(self):
        """Настройка перед каждым тестом"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
    
    def tearDown(self):
        """Очистка после каждого теста"""
        self.loop.close()
    
    def test_product_discovery_to_queue(self):
        """Тест: обнаружение товара → добавление в очередь"""
        async def run_test():
            from services.smart_search_service import SmartSearchService
            from services.publish_service import get_publish_service
            
            # Мокаем HTTP запросы
            with patch('aiohttp.ClientSession.get') as mock_get:
                # Мокаем ответ с товарами
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.text = AsyncMock(return_value='<html>Mock HTML</html>')
                mock_get.return_value.__aenter__.return_value = mock_response
                
                search_service = SmartSearchService()
                publish_service = get_publish_service()
                
                # Запускаем поиск
                added, skipped = await search_service.crawl_catalogs(max_catalogs=1)
                
                # Проверяем что товары найдены (или хотя бы попытка была)
                self.assertIsInstance(added, int)
                self.assertIsInstance(skipped, int)
        
        self.loop.run_until_complete(run_test())
    
    def test_affiliate_link_generation_flow(self):
        """Тест: генерация affiliate ссылки → проверка параметров"""
        from services.affiliate_service import get_affiliate_link, generate_erid
        
        # Генерируем ERID
        erid = generate_erid()
        self.assertTrue(erid.startswith("tg-"))
        self.assertEqual(len(erid.split("-")), 3)
        
        # Генерируем affiliate ссылку
        test_url = "https://market.yandex.ru/product/12345"
        
        with patch('config.AFFILIATE_CLID', 'test_clid'):
            affiliate_link, erid = get_affiliate_link(test_url)
            
            # Проверяем что ссылка содержит нужные параметры
            self.assertIn('clid=test_clid', affiliate_link)
            self.assertIn('erid=', affiliate_link)
            self.assertIn('utm_source=', affiliate_link)
    
    def test_shadow_ban_detection_flow(self):
        """Тест: детектирование shadow-ban → установка паузы"""
        from services.shadow_ban_service import ShadowBanService
        
        service = ShadowBanService()
        
        # Симулируем shadow-ban (мало товаров + большой HTML)
        is_banned = service.is_shadow_banned(products_count=2, html_size=600_000)
        self.assertTrue(is_banned)
        
        # Записываем shadow-ban
        service.record_shadow_ban(
            catalog_url="https://market.yandex.ru/catalog--test/",
            products_count=2,
            html_size=600_000
        )
        
        # Проверяем что пауза установлена
        self.assertIsNotNone(service.pause_until)
        self.assertFalse(service.can_continue_parsing())
    
    def test_product_deduplication_flow(self):
        """Тест: генерация product_key → дедупликация"""
        from services.validator_service import ProductValidator
        
        validator = ProductValidator()
        
        product1 = {
            'title': 'Test Product',
            'vendor': 'TestVendor',
            'url': 'https://market.yandex.ru/product/12345'
        }
        
        product2 = {
            'title': 'Test Product',
            'vendor': 'TestVendor',
            'url': 'https://market.yandex.ru/product/12345'
        }
        
        # Генерируем ключи
        key1 = validator._generate_product_key(product1)
        key2 = validator._generate_product_key(product2)
        
        # Ключи должны быть одинаковыми (дедупликация)
        self.assertEqual(key1, key2)
        
        # Ключ должен быть SHA-1 (40 символов hex)
        self.assertEqual(len(key1), 40)
        self.assertTrue(all(c in '0123456789abcdef' for c in key1))
    
    def test_db_batch_operations(self):
        """Тест: batch insert товаров"""
        async def run_test():
            from services.db_batch_service import get_batch_service
            
            batch_service = get_batch_service(batch_size=10)
            
            # Добавляем несколько товаров
            for i in range(5):
                product = {
                    'product_key': f'test_key_{i}',
                    'url': f'https://test.com/product/{i}',
                    'title': f'Test Product {i}',
                    'vendor': 'TestVendor',
                    'price': 1000 + i
                }
                
                flushed = await batch_service.add_product(product)
                # Первые 5 не должны вызвать flush (batch_size=10)
                self.assertFalse(flushed)
            
            # Проверяем статистику
            stats = batch_service.get_stats()
            self.assertEqual(stats['products_pending'], 5)
            
            # Принудительный flush
            await batch_service.flush_all()
            
            stats = batch_service.get_stats()
            self.assertEqual(stats['products_pending'], 0)
        
        self.loop.run_until_complete(run_test())
    
    def test_health_check_endpoints(self):
        """Тест: health check endpoints"""
        async def run_test():
            from services.health_endpoint import HealthCheckService
            from aiohttp import web
            from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
            
            health_service = HealthCheckService()
            
            # Тестируем liveness endpoint
            request = Mock(spec=web.Request)
            response = await health_service.liveness_handler(request)
            
            self.assertEqual(response.status, 200)
            self.assertIn('alive', response.body.decode())
        
        self.loop.run_until_complete(run_test())


class TestSmokeTests(unittest.TestCase):
    """Smoke tests - быстрые проверки что основные компоненты работают"""
    
    def test_imports(self):
        """Smoke test: все модули импортируются"""
        try:
            from services import affiliate_service
            from services import shadow_ban_service
            from services import smart_search_service
            from services import db_batch_service
            from services import health_endpoint
            from services import session_manager
            self.assertTrue(True)
        except ImportError as e:
            self.fail(f"Import failed: {e}")
    
    def test_config_loaded(self):
        """Smoke test: конфигурация загружена"""
        import config
        self.assertTrue(hasattr(config, 'USE_POSTGRES'))
        self.assertTrue(hasattr(config, 'USE_REDIS'))
    
    def test_database_connection(self):
        """Smoke test: подключение к БД"""
        try:
            from database import Database
            db = Database()
            # Простой запрос
            db.cursor.execute("SELECT 1")
            self.assertTrue(True)
        except Exception as e:
            self.fail(f"Database connection failed: {e}")


if __name__ == '__main__':
    unittest.main()
