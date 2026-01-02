#!/usr/bin/env python3
"""
Final Comprehensive Test Suite
Runs all tests to verify the bot is production-ready
"""

import sys
import os
import asyncio

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

def run_sync_tests():
    """Run synchronous tests"""
    print('1. Testing all service imports...')
    try:
        from services import affiliate_service, shadow_ban_service, smart_search_service
        from services import session_manager, health_endpoint, db_batch_service, catalog_scoring_service
        from services import http_client, structured_logging
        from database import Database
        from services.post_service import send_post_to_channel
        from services.scrape_service import safe_scrape_with_retry
        print('   ✅ All imports successful')
        return True
    except Exception as e:
        print(f'   ❌ Imports failed: {e}')
        return False

def run_affiliate_tests():
    """Test affiliate service"""
    print('2. Testing affiliate service...')
    try:
        erid = affiliate_service.generate_erid()
        link, erid2 = affiliate_service.get_affiliate_link('https://market.yandex.ru/product/12345')
        assert erid.startswith('tg-')
        assert 'clid=' in link and 'erid=' in link
        print('   ✅ Affiliate service works')
        return True
    except Exception as e:
        print(f'   ❌ Affiliate failed: {e}')
        return False

def run_shadow_ban_tests():
    """Test shadow-ban service"""
    print('3. Testing shadow-ban service...')
    try:
        from services.shadow_ban_service import ShadowBanService
        service = ShadowBanService()
        assert service.is_shadow_banned(2, 600_000) == True
        assert service.is_shadow_banned(20, 300_000) == False
        print('   ✅ Shadow-ban detection works')
        return True
    except Exception as e:
        print(f'   ❌ Shadow-ban failed: {e}')
        return False

def run_product_key_tests():
    """Test product key generation"""
    print('4. Testing product key generation...')
    try:
        from services.validator_service import ProductValidator
        validator = ProductValidator()
        product = {'title': 'Test', 'vendor': 'Test'}
        key1 = validator._generate_product_key(product)
        key2 = validator._generate_product_key(product)
        assert key1 == key2
        assert len(key1) == 40
        print('   ✅ Product key generation works')
        return True
    except Exception as e:
        print(f'   ❌ Product key failed: {e}')
        return False

def run_session_manager_tests():
    """Test session management"""
    print('5. Testing session management...')
    try:
        manager = session_manager.get_session_manager()
        assert manager is not None
        print('   ✅ Session manager works')
        return True
    except Exception as e:
        print(f'   ❌ Session manager failed: {e}')
        return False

def run_health_tests():
    """Test health endpoint"""
    print('6. Testing health endpoint...')
    try:
        health = health_endpoint.get_health_service()
        assert health is not None
        print('   ✅ Health service works')
        return True
    except Exception as e:
        print(f'   ❌ Health endpoint failed: {e}')
        return False

def run_db_batch_tests():
    """Test DB batching"""
    print('7. Testing DB batching...')
    try:
        batch = db_batch_service.get_batch_service()
        assert batch is not None
        stats = batch.get_stats()
        assert 'products_pending' in stats
        print('   ✅ DB batching works')
        return True
    except Exception as e:
        print(f'   ❌ DB batching failed: {e}')
        return False

def run_catalog_scoring_tests():
    """Test catalog scoring"""
    print('8. Testing catalog scoring...')
    try:
        scoring = catalog_scoring_service.get_scoring_service()
        score = scoring.calculate_score('https://test.com')
        assert 0 <= score <= 100
        print('   ✅ Catalog scoring works')
        return True
    except Exception as e:
        print(f'   ❌ Catalog scoring failed: {e}')
        return False

def run_database_tests():
    """Test database connection"""
    print('9. Testing database connection...')
    try:
        db = Database()
        db.cursor.execute('SELECT 1')
        print('   ✅ Database connection works')
        return True
    except Exception as e:
        print(f'   ❌ Database failed: {e}')
        return False

def run_core_services_tests():
    """Test core services"""
    print('10. Testing core services...')
    try:
        # Just import check
        assert send_post_to_channel is not None
        assert safe_scrape_with_retry is not None
        print('   ✅ Core services available')
        return True
    except Exception as e:
        print(f'   ❌ Core services failed: {e}')
        return False

async def run_async_tests():
    """Run asynchronous tests"""
    print('11. Testing async functionality...')

    try:
        # Test batch service async operations
        batch = db_batch_service.get_batch_service(batch_size=5)

        # Mock flush to avoid DB operations
        async def mock_flush():
            batch._product_batch.clear()
            return
        batch._flush_products = mock_flush
        batch._flush_metrics = mock_flush

        # Test batching
        for i in range(3):
            product = {'product_key': f'test_{i}', 'title': f'Product {i}'}
            await batch.add_product(product)

        stats = batch.get_stats()
        assert stats['products_pending'] == 3

        await batch.flush_all()
        stats = batch.get_stats()
        assert stats['products_pending'] == 0

        print('   ✅ Async batching works')
        return True
    except Exception as e:
        print(f'   ❌ Async tests failed: {e}')
        return False

def main():
    """Main test function"""
    print('🎯 FINAL COMPREHENSIVE TEST SUITE')
    print('=' * 50)

    test_results = []

    # Run sync tests
    test_results.append(('Imports', run_sync_tests()))
    test_results.append(('Affiliate', run_affiliate_tests()))
    test_results.append(('Shadow-ban', run_shadow_ban_tests()))
    test_results.append(('Product Key', run_product_key_tests()))
    test_results.append(('Session Manager', run_session_manager_tests()))
    test_results.append(('Health Endpoint', run_health_tests()))
    test_results.append(('DB Batching', run_db_batch_tests()))
    test_results.append(('Catalog Scoring', run_catalog_scoring_tests()))
    test_results.append(('Database', run_database_tests()))
    test_results.append(('Core Services', run_core_services_tests()))

    # Run async tests
    async_result = asyncio.run(run_async_tests())
    test_results.append(('Async Operations', async_result))

    print('\n' + '=' * 50)
    print('📊 FINAL TEST RESULTS:')
    print('=' * 50)

    passed = 0
    total = len(test_results)

    for name, result in test_results:
        status = 'PASS' if result else 'FAIL'
        print(f'{name:15} | {status}')
        if result:
            passed += 1

    print('=' * 50)
    print(f'SUMMARY: {passed}/{total} tests passed')

    if passed == total:
        print('🎉 ALL TESTS PASSED! Bot is production-ready!')
        print('🚀 Ready to launch!')
        return 0
    else:
        print('❌ Some tests failed. Please check the errors above.')
        return 1

if __name__ == '__main__':
    sys.exit(main())
