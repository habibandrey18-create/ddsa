#!/usr/bin/env python3
"""
Test script to verify all imports and basic functionality
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

def test_imports():
    """Test all service imports"""
    print("Testing imports...")

    try:
        from services import affiliate_service, shadow_ban_service, smart_search_service
        from services import session_manager, health_endpoint, db_batch_service, catalog_scoring_service
        from services import http_client, structured_logging
        print('✅ All service imports OK')
        return True
    except Exception as e:
        print(f'❌ Import error: {e}')
        import traceback
        traceback.print_exc()
        return False

def test_basic_functionality():
    """Test basic functionality of services"""
    print("\nTesting basic functionality...")

    try:
        # Test affiliate service
        erid = affiliate_service.generate_erid()
        print(f'✅ ERID generation: {erid}')

        # Test session manager
        manager = session_manager.get_session_manager()
        print('✅ Session manager OK')

        # Test batch service
        batch = db_batch_service.get_batch_service()
        print('✅ Batch service OK')

        # Test scoring service
        scoring = catalog_scoring_service.get_scoring_service()
        print('✅ Scoring service OK')

        # Test health service
        health = health_endpoint.get_health_service()
        print('✅ Health service OK')

        # Test affiliate link generation
        test_url = "https://market.yandex.ru/product/12345"
        link, erid = affiliate_service.get_affiliate_link(test_url)
        print(f'✅ Affiliate link: {link[:50]}...')

        print('\n🎉 All basic functionality tests PASSED!')
        return True

    except Exception as e:
        print(f'❌ Functionality error: {e}')
        import traceback
        traceback.print_exc()
        return False

def test_services_integration():
    """Test services integration"""
    print("\nTesting services integration...")

    try:
        # Test shadow-ban service
        shadow_service = shadow_ban_service.ShadowBanService()
        is_banned = shadow_service.is_shadow_banned(products_count=2, html_size=600_000)
        print(f'✅ Shadow-ban detection: {is_banned}')

        # Test catalog scoring
        scoring = catalog_scoring_service.get_scoring_service()
        score = scoring.calculate_score("https://market.yandex.ru/catalog--test/")
        print(f'✅ Catalog scoring: {score}')

        # Test batch service stats
        batch = db_batch_service.get_batch_service()
        stats = batch.get_stats()
        print(f'✅ Batch stats: {stats}')

        print('🎉 All integration tests PASSED!')
        return True

    except Exception as e:
        print(f'❌ Integration error: {e}')
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    print("🚀 Starting comprehensive test suite...\n")

    success = True

    success &= test_imports()
    success &= test_basic_functionality()
    success &= test_services_integration()

    if success:
        print("\n🎯 ALL TESTS PASSED! Bot is ready for production!")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED! Please check the errors above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
