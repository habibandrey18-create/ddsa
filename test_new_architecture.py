# test_new_architecture.py - Тестирование новой архитектуры
"""
Тестовый скрипт для проверки компонентов новой архитектуры:
- Postgres + Redis
- Smart Search
- Validator
- Content Service
- Publish Service
- Metrics Service
"""

import asyncio
import logging
import sys
from datetime import datetime
import config

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_database_connections():
    """Тест подключения к базам данных"""
    logger.info("🔍 Testing database connections...")

    # Тест Postgres
    if config.USE_POSTGRES:
        try:
            from database_postgres import get_postgres_db
            db = get_postgres_db()

            # Простой тест
            test_key = db.get_or_create_search_key("test_connection")
            logger.info(f"✅ Postgres OK - Created test key: {test_key}")

        except Exception as e:
            logger.error(f"❌ Postgres test failed: {e}")
            return False
    else:
        logger.info("⚠️ Postgres disabled in config")

    # Тест Redis
    if config.USE_REDIS:
        try:
            from redis_cache import get_redis_cache
            redis = get_redis_cache()

            # Тест записи/чтения
            test_key = f"test:{int(datetime.utcnow().timestamp())}"
            redis.set_counter(test_key, 42)
            value = redis.get_counter(test_key)

            if value == 42:
                logger.info("✅ Redis OK - Counter test passed")
            else:
                logger.error(f"❌ Redis counter test failed: got {value}, expected 42")
                return False

        except Exception as e:
            logger.error(f"❌ Redis test failed: {e}")
            return False
    else:
        logger.info("⚠️ Redis disabled in config")

    return True

async def test_smart_search():
    """Тест умного поиска"""
    logger.info("🔍 Testing smart search service...")

    try:
        from services.smart_search_service import get_smart_search_service
        search_service = get_smart_search_service()

        # Тест поиска с ограниченными параметрами
        result = await search_service.run_smart_search_cycle(
            max_catalogs=2  # Тестируем 2 каталога
        )

        logger.info(f"✅ Smart search test completed: {result}")

        # Закрываем сессию
        await search_service.close_session()

        return True

    except Exception as e:
        logger.error(f"❌ Smart search test failed: {e}")
        return False

async def test_validator():
    """Тест валидатора продуктов"""
    logger.info("🔍 Testing product validator...")

    try:
        from services.validator_service import get_product_validator
        validator = get_product_validator()

        # Тестовый продукт
        test_product = {
            'id': 'test_product_123',
            'title': 'Тестовый товар с длинным названием для проверки валидации',
            'price': 1500,
            'url': 'https://market.yandex.ru/product/123',
            'has_images': True,
            'vendor': 'TestBrand'
        }

        # Тестируем валидацию
        is_valid, errors = validator.validate_product_sync(test_product)

        if is_valid:
            logger.info("✅ Product validator OK - Product passed validation")
        else:
            logger.warning(f"⚠️ Product validator - Product failed validation: {errors}")

        # Закрываем сессию
        await validator.close_session()

        return True

    except Exception as e:
        logger.error(f"❌ Product validator test failed: {e}")
        return False

async def test_content_service():
    """Тест сервиса контента"""
    logger.info("🔍 Testing content service...")

    try:
        from services.content_service import get_content_service
        content_service = get_content_service()

        # Тестовый продукт
        test_product = {
            'title': 'Беспроводные наушники Sony',
            'price': 25000,
            'vendor': 'Sony',
            'rating': 4.8,
            'discount_percent': 15
        }

        # Генерируем контент
        content = content_service.generate_content(test_product)

        logger.info("✅ Content service OK")
        logger.info(f"   Generated post: {content['post_text'][:100]}...")
        logger.info(f"   Template: {content['template_id']}")
        logger.info(f"   CTA: {content['cta_id']}")

        return True

    except Exception as e:
        logger.error(f"❌ Content service test failed: {e}")
        return False

async def test_publish_service():
    """Тест сервиса публикации"""
    logger.info("🔍 Testing publish service...")

    try:
        from services.publish_service import get_publish_service
        publish_service = get_publish_service()

        # Получаем статистику очереди
        queue_stats = publish_service.get_queue_stats()

        logger.info("✅ Publish service OK")
        logger.info(f"   Queue size: {queue_stats.get('queue_size', 0)}")
        logger.info(f"   Publisher running: {queue_stats.get('publisher_running', False)}")

        return True

    except Exception as e:
        logger.error(f"❌ Publish service test failed: {e}")
        return False

async def test_metrics_service():
    """Тест сервиса метрик"""
    logger.info("🔍 Testing metrics service...")

    try:
        from services.metrics_service import get_metrics_service
        metrics_service = get_metrics_service()

        # Получаем тестовый отчёт
        report = metrics_service.get_performance_report(days=1)

        logger.info("✅ Metrics service OK")
        logger.info(f"   Report generated for {report.get('period_days', 0)} days")
        logger.info(f"   Total posts: {report.get('overall', {}).get('total_posts', 0)}")

        return True

    except Exception as e:
        logger.error(f"❌ Metrics service test failed: {e}")
        return False

async def test_full_pipeline():
    """Тест полного пайплайна"""
    logger.info("🔄 Testing full pipeline...")

    try:
        # Создаём тестовый продукт который пройдет валидацию
        test_product = {
            'id': 'pipeline_test_123',
            'title': 'Отличный беспроводной наушник с активным шумоподавлением и высоким качеством звука, идеально подходит для путешествий и работы',
            'price': 15000,  # Выше минимального порога
            'url': 'https://market.yandex.ru/product/test123',
            'vendor': 'Sony',  # Популярный бренд
            'has_images': True,
            'rating': 4.8,  # Выше минимального
            'reviews_count': 200,  # Выше минимального
            'images': ['https://example.com/image1.jpg'],  # Есть изображения
            'marketing_description': 'Это отличные беспроводные наушники с активным шумоподавлением. Они обеспечивают высокое качество звука и комфортную посадку. Идеально подходят для путешествий, работы и повседневного использования. Покупатели отмечают отличное качество сборки и длительное время работы от батареи.',  # Длинное описание
        }

        # 1. Валидируем продукт
        from services.validator_service import get_product_validator
        validator = get_product_validator()

        is_valid, errors = validator.validate_product_sync(test_product)
        if not is_valid:
            logger.warning(f"Product failed validation: {errors}")
            return False

        # 2. Генерируем контент
        from services.content_service import get_content_service
        content_service = get_content_service()

        content = content_service.generate_content(test_product)

        # 3. Добавляем в очередь публикации
        from services.publish_service import get_publish_service
        publish_service = get_publish_service()

        success = publish_service.enqueue_product(test_product)
        if not success:
            logger.error("Failed to enqueue product")
            return False

        logger.info("✅ Full pipeline test completed successfully")
        logger.info(f"   Product validated: {is_valid}")
        logger.info(f"   Content generated: {len(content['post_text'])} chars")
        logger.info(f"   Enqueued for publishing: {success}")

        # Закрываем сессии
        await validator.close_session()

        return True

    except Exception as e:
        logger.error(f"❌ Full pipeline test failed: {e}")
        return False

async def run_all_tests():
    """Запустить все тесты"""
    logger.info("🚀 Starting comprehensive architecture tests...")

    tests = [
        ("Database Connections", test_database_connections),
        ("Smart Search Service", test_smart_search),
        ("Product Validator", test_validator),
        ("Content Service", test_content_service),
        ("Publish Service", test_publish_service),
        ("Metrics Service", test_metrics_service),
        ("Full Pipeline", test_full_pipeline),
    ]

    results = []
    start_time = datetime.utcnow()

    for test_name, test_func in tests:
        logger.info(f"\n{'='*50}")
        logger.info(f"Running: {test_name}")
        logger.info(f"{'='*50}")

        try:
            result = await test_func()
            results.append((test_name, result))
            status = "✅ PASSED" if result else "❌ FAILED"
            logger.info(f"{status}: {test_name}")
        except Exception as e:
            logger.error(f"💥 CRASHED: {test_name} - {e}")
            results.append((test_name, False))

    # Итоги
    duration = datetime.utcnow() - start_time
    passed = sum(1 for _, result in results if result)
    total = len(results)

    logger.info(f"\n{'='*60}")
    logger.info("🏁 TEST RESULTS SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"Total tests: {total}")
    logger.info(f"Passed: {passed}")
    logger.info(f"Failed: {total - passed}")
    logger.info(".2f")
    logger.info(f"Success rate: {(passed/total)*100:.1f}%")

    for test_name, result in results:
        status = "✅" if result else "❌"
        logger.info(f"  {status} {test_name}")

    if passed == total:
        logger.info("\n🎉 ALL TESTS PASSED! Architecture is ready for production.")
        return True
    else:
        logger.error(f"\n⚠️ {total - passed} tests failed. Please check the errors above.")
        return False

async def main():
    """Главная функция"""
    if len(sys.argv) > 1:
        test_name = sys.argv[1].lower()

        # Запуск конкретного теста
        test_map = {
            'db': test_database_connections,
            'search': test_smart_search,
            'validator': test_validator,
            'content': test_content_service,
            'publish': test_publish_service,
            'metrics': test_metrics_service,
            'pipeline': test_full_pipeline,
        }

        if test_name in test_map:
            logger.info(f"Running specific test: {test_name}")
            result = await test_map[test_name]()
            sys.exit(0 if result else 1)
        else:
            logger.error(f"Unknown test: {test_name}")
            logger.info(f"Available tests: {', '.join(test_map.keys())}")
            sys.exit(1)

    else:
        # Запуск всех тестов
        success = await run_all_tests()
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())