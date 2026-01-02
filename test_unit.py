#!/usr/bin/env python3
"""
Unit tests for critical functions
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

# Mock sample __NEXT_DATA__ for testing
SAMPLE_NEXT_DATA = {
    "props": {
        "pageProps": {
            "initialState": {
                "search": {
                    "results": {
                        "items": [
                            {
                                "id": "12345",
                                "titles": {"raw": "Test Product"},
                                "prices": {"value": 1000, "oldValue": 1200},
                                "rating": 4.5,
                                "reviewsCount": 100
                            }
                        ]
                    }
                }
            }
        }
    }
}

async def test_parse_catalog_products():
    """Test _parse_catalog_products with sample __NEXT_DATA__"""
    from services.smart_search_service import SmartSearchService

    service = SmartSearchService()

    # Create HTML with sample __NEXT_DATA__
    html = f'<html><head><script id="__NEXT_DATA__">{json.dumps(SAMPLE_NEXT_DATA)}</script></head></html>'

    products = service._parse_catalog_products(html)

    assert len(products) == 1
    product = products[0]
    assert product['market_id'] == '12345'
    assert product['title'] == 'Test Product'
    assert product['price'] == 1000
    assert product['old_price'] == 1200
    assert product['rating'] == 4.5
    assert product['reviews_count'] == 100

    print("✅ _parse_catalog_products test passed")

async def test_process_found_products():
    """Test _process_found_products with mocked enqueue"""
    from services.smart_search_service import SmartSearchService

    service = SmartSearchService()

    # Mock methods
    service._validate_product_for_queue = AsyncMock(return_value=(True, []))
    service._mark_product_seen = AsyncMock(return_value=True)
    service._enqueue_product = AsyncMock()

    test_products = [
        {'market_id': 'test1', 'title': 'Product 1'},
        {'market_id': 'test2', 'title': 'Product 2'},
    ]

    added, skipped = await service._process_found_products(test_products, 'test_url')

    assert added == 2
    assert skipped == 0
    assert service._enqueue_product.call_count == 2

    print("✅ _process_found_products test passed")

async def test_cache_logic():
    """Test cache logic (30 min cooldown)"""
    from services.smart_search_service import SmartSearchService
    import time

    service = SmartSearchService()

    # Test initial state
    assert len(service._last_catalog_parse) >= 0

    # Test cache save/load
    service._last_catalog_parse['test_url'] = time.time()
    service._save_parse_cache()

    # Create new instance to test persistence
    service2 = SmartSearchService()
    assert 'test_url' in service2._last_catalog_parse

    print("✅ Cache logic test passed")

async def main():
    """Run all unit tests"""
    print("🧪 Running unit tests...")

    try:
        await test_parse_catalog_products()
        await test_process_found_products()
        await test_cache_logic()

        print("\n🎉 All unit tests passed!")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)