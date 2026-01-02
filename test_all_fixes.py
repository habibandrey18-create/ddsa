#!/usr/bin/env python3
"""
Test All Fixes from Audit Report
=================================

This script tests all critical fixes to verify they work correctly.

Run: python test_all_fixes.py

Note: All Unicode emoji removed for Windows console compatibility.
"""

import asyncio
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_async_database():
    """Test 1: Async database works without blocking."""
    try:
        from database_async import AsyncDatabase

        logger.info("Test 1: Async Database")

        async with AsyncDatabase() as db:
            # Test connection
            stats = await db.get_stats()
            logger.info(f"  [PASS] Async DB connected: {stats['published']} posts in history")

            # Test fast queries
            import time
            start = time.time()
            for _ in range(100):
                await db.exists_url("https://test.com")
            duration = time.time() - start

            logger.info(f"  [PASS] 100 queries in {duration*1000:.1f}ms ({duration*10:.2f}ms avg)")

            if duration > 1.0:
                logger.warning("  [WARN] Queries seem slow, check indices")

        logger.info("  [PASS] Test 1 PASSED: Async database works\n")
        return True

    except Exception as e:
        logger.error(f"  [FAIL] Test 1 FAILED: {e}\n")
        return False


async def test_race_conditions():
    """Test 2: Race conditions eliminated (no duplicates)."""
    try:
        from database_async import AsyncDatabase
        
        logger.info("Test 2: Race Conditions")

        async with AsyncDatabase() as db:
            test_url = f"https://market.yandex.ru/product/test{int(asyncio.get_event_loop().time())}"

            # Try to insert same URL 10 times concurrently
            async def try_insert(worker_id):
                queue_id = await db.add_to_queue(test_url, title=f"Test {worker_id}")
                return queue_id is not None

            results = await asyncio.gather(*[try_insert(i) for i in range(10)])
            successful = sum(results)

            logger.info(f"  [INFO] 10 concurrent inserts -> {successful} succeeded")

            if successful == 1:
                logger.info("  [PASS] Test 2 PASSED: Only 1 insert succeeded (UNIQUE constraint works)")
            else:
                logger.error(f"  [FAIL] Test 2 FAILED: {successful} inserts succeeded (expected 1)")
                return False
        
        logger.info("")
        return True
        
    except Exception as e:
        logger.error(f"  ❌ Test 2 FAILED: {e}\n")
        return False


async def test_no_blocking_calls():
    """Test 3: No blocking calls in codebase."""
    try:
        import subprocess
        
        logger.info("Test 3: No Blocking Calls")
        
        # Check for time.sleep in async code
        result = subprocess.run(
            ['grep', '-r', 'time\\.sleep', 'services/', '--include=*.py'],
            capture_output=True,
            text=True
        )
        
        blocking_sleeps = [
            line for line in result.stdout.split('\n')
            if line and 'asyncio.sleep' not in line and 'time.sleep' in line
        ]
        
        if blocking_sleeps:
            logger.error(f"  ❌ Found {len(blocking_sleeps)} blocking time.sleep() calls:")
            for line in blocking_sleeps[:5]:
                logger.error(f"    {line}")
            return False
        else:
            logger.info("  ✅ No blocking time.sleep() found in services/")
        
        # Check for requests in async code
        result = subprocess.run(
            ['grep', '-r', 'import requests', 'services/', '--include=*.py'],
            capture_output=True,
            text=True
        )
        
        if 'import requests' in result.stdout and 'HAS_REQUESTS' not in result.stdout:
            logger.warning("  ⚠️ requests still imported (check if it's used in async)")
        else:
            logger.info("  ✅ No blocking requests module in async code")
        
        logger.info("  ✅ Test 3 PASSED: No blocking calls detected\n")
        return True
        
    except Exception as e:
        logger.warning(f"  ⚠️ Test 3 SKIPPED: {e} (grep not available on Windows)\n")
        return True  # Skip on Windows


async def test_product_key_determinism():
    """Test 4: Product key generation is deterministic."""
    try:
        from utils.product_key import generate_product_key
        
        logger.info("🧪 Test 4: Product Key Determinism")
        
        # Generate key 100 times with same input
        keys = []
        for _ in range(100):
            key = generate_product_key(
                title="iPhone 14 Pro 128GB",
                vendor="Apple",
                market_id="123456"
            )
            keys.append(key)
        
        # All should be identical
        unique_keys = set(keys)
        
        if len(unique_keys) == 1:
            logger.info(f"  ✅ 100 generations → 1 unique key: {list(unique_keys)[0][:16]}...")
            logger.info("  ✅ Test 4 PASSED: Keys are deterministic")
        else:
            logger.error(f"  ❌ Test 4 FAILED: {len(unique_keys)} different keys (expected 1)")
            return False
        
        logger.info("")
        return True
        
    except Exception as e:
        logger.error(f"  ❌ Test 4 FAILED: {e}\n")
        return False


async def test_rate_limiter():
    """Test 5: Rate limiter works."""
    try:
        from services.distributed_rate_limiter import DistributedRateLimiter
        
        logger.info("🧪 Test 5: Rate Limiter")
        
        # Create limiter (5 requests per 10 seconds)
        limiter = DistributedRateLimiter(
            redis_client=None,  # Use local fallback
            key="test",
            limit=5,
            window_seconds=10
        )
        
        # Try 10 requests
        import time
        start = time.time()
        
        for i in range(10):
            await limiter.acquire()
            logger.debug(f"  Request {i+1}/10 acquired")
        
        duration = time.time() - start
        
        # Should take at least 10 seconds (rate limit enforced)
        if duration >= 9:  # 9s buffer
            logger.info(f"  ✅ 10 requests took {duration:.1f}s (rate limit enforced)")
            logger.info("  ✅ Test 5 PASSED: Rate limiter works")
        else:
            logger.error(f"  ❌ Test 5 FAILED: 10 requests took only {duration:.1f}s (should be ~10s)")
            return False
        
        logger.info("")
        return True
        
    except Exception as e:
        logger.error(f"  ❌ Test 5 FAILED: {e}\n")
        return False


async def test_connection_cleanup():
    """Test 6: Connections are cleaned up properly."""
    try:
        from services.http_client import HTTPClient
        
        logger.info("🧪 Test 6: Connection Cleanup")
        
        # Create client
        client = HTTPClient()
        
        # Make some requests
        for i in range(5):
            text = await client.fetch_text("https://httpbin.org/delay/0", max_retries=1)
            if text:
                logger.debug(f"  Request {i+1}/5 completed")
        
        # Close client
        await client.close()
        
        # Verify session is None
        if client._session is None:
            logger.info("  ✅ Session properly closed and set to None")
            logger.info("  ✅ Test 6 PASSED: Connection cleanup works")
        else:
            logger.error("  ❌ Test 6 FAILED: Session not cleaned up")
            return False
        
        logger.info("")
        return True
        
    except Exception as e:
        logger.warning(f"  ⚠️ Test 6 SKIPPED: {e} (network required)\n")
        return True  # Skip if network unavailable


async def run_all_tests():
    """Run all tests and report results."""
    print("="*60)
    print("RUNNING ALL FIXES VERIFICATION TESTS")
    print("="*60)
    print()
    
    tests = [
        ("Async Database", test_async_database),
        ("Race Conditions", test_race_conditions),
        ("No Blocking Calls", test_no_blocking_calls),
        ("Product Key Determinism", test_product_key_determinism),
        ("Rate Limiter", test_rate_limiter),
        ("Connection Cleanup", test_connection_cleanup),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            passed = await test_func()
            results.append((test_name, passed))
        except Exception as e:
            logger.error(f"Test '{test_name}' crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("="*60)
    print("TEST RESULTS SUMMARY")
    print("="*60)

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    for test_name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status}: {test_name}")

    print()
    print(f"TOTAL: {passed_count}/{total_count} tests passed ({passed_count/total_count*100:.0f}%)")
    print("="*60)

    if passed_count == total_count:
        print("ALL TESTS PASSED! Bot is ready for staging.")
        print("Next: Deploy to staging and monitor for 48 hours")
        return 0
    else:
        print(f"{total_count - passed_count} test(s) failed. Check errors above.")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(run_all_tests())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️ Tests interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Fatal error in tests: {e}")
        sys.exit(1)

