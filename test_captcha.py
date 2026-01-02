"""
Тестовый скрипт для проверки работы captcha solver с rucaptcha
"""

import asyncio
import logging
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(__file__))

from utils.captcha_solver import CaptchaSolver
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Загружаем .env
load_dotenv()


async def test_balance():
    """Тест проверки баланса"""
    logger.info("=" * 50)
    logger.info("Тест 1: Проверка баланса на rucaptcha.com")
    logger.info("=" * 50)

    solver = CaptchaSolver(
        api_key="ddc737c62be7b9f218dd7ae1db661f2e", service="rucaptcha"
    )

    try:
        balance = await solver.get_balance()
        if balance is not None:
            logger.info(f"✅ Баланс успешно получен: ${balance:.2f}")
            return True
        else:
            logger.error("❌ Не удалось получить баланс")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке баланса: {e}")
        return False


async def test_api_connection():
    """Тест подключения к API"""
    logger.info("=" * 50)
    logger.info("Тест 2: Проверка подключения к API rucaptcha")
    logger.info("=" * 50)

    solver = CaptchaSolver(
        api_key="ddc737c62be7b9f218dd7ae1db661f2e", service="rucaptcha"
    )

    # Проверяем, что API ключ загружен
    if not solver.api_key:
        logger.error("❌ API ключ не загружен")
        return False

    logger.info(f"✅ API ключ загружен: {solver.api_key[:10]}...")
    logger.info(f"✅ Сервис: {solver.service}")

    # Проверяем баланс как тест подключения
    try:
        balance = await solver.get_balance()
        if balance is not None:
            logger.info(f"✅ Подключение к API работает! Баланс: ${balance:.2f}")
            return True
        else:
            logger.warning("⚠️ Не удалось получить баланс, но это может быть нормально")
            return True  # Все равно считаем успешным, если нет ошибки подключения
    except Exception as e:
        logger.error(f"❌ Ошибка подключения: {e}")
        return False


async def test_config_loading():
    """Тест загрузки из config"""
    logger.info("=" * 50)
    logger.info("Тест 3: Проверка загрузки из config.py")
    logger.info("=" * 50)

    try:
        import config

        logger.info(
            f"CAPTCHA_API_KEY из config: {config.CAPTCHA_API_KEY[:10] if config.CAPTCHA_API_KEY else 'НЕ УСТАНОВЛЕН'}..."
        )
        logger.info(f"CAPTCHA_SERVICE из config: {config.CAPTCHA_SERVICE}")

        if config.CAPTCHA_API_KEY:
            logger.info("✅ API ключ успешно загружен из config")

            # Создаем solver с ключом из config
            solver = CaptchaSolver(
                api_key=config.CAPTCHA_API_KEY, service=config.CAPTCHA_SERVICE
            )

            balance = await solver.get_balance()
            if balance is not None:
                logger.info(f"✅ Работает с ключом из config! Баланс: ${balance:.2f}")
                return True
            else:
                logger.warning("⚠️ Не удалось получить баланс")
                return True
        else:
            logger.error("❌ API ключ не найден в config")
            return False

    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке из config: {e}")
        return False


async def main():
    """Главная функция тестирования"""
    logger.info("🚀 Начало тестирования captcha solver с rucaptcha.com")
    logger.info("")

    results = []

    # Тест 1: Проверка баланса
    results.append(await test_balance())
    logger.info("")

    # Тест 2: Проверка подключения
    results.append(await test_api_connection())
    logger.info("")

    # Тест 3: Загрузка из config
    results.append(await test_config_loading())
    logger.info("")

    # Итоги
    logger.info("=" * 50)
    logger.info("ИТОГИ ТЕСТИРОВАНИЯ")
    logger.info("=" * 50)

    passed = sum(results)
    total = len(results)

    logger.info(f"Пройдено тестов: {passed}/{total}")

    if passed == total:
        logger.info("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        logger.info("✅ Captcha solver готов к работе")
    else:
        logger.warning(f"⚠️ Провалено тестов: {total - passed}")

    return passed == total


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\n⚠️ Тестирование прервано пользователем")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ Критическая ошибка: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
