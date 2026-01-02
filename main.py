#!/usr/bin/env python3
"""
Main entry point for Yandex.Market Bot
Запуск основной архитектуры бота с Postgres + Redis
"""

import asyncio
import logging
import sys
import os

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

def check_requirements():
    """Проверка наличия необходимых компонентов"""
    try:
        import config
        # Debug: check config attributes
        print(f"DEBUG: config has USE_POSTGRES: {hasattr(config, 'USE_POSTGRES')}")
        print(f"DEBUG: config.USE_POSTGRES = {getattr(config, 'USE_POSTGRES', 'NOT_FOUND')}")
        print(f"DEBUG: config has USE_REDIS: {hasattr(config, 'USE_REDIS')}")
        print(f"DEBUG: config.USE_REDIS = {getattr(config, 'USE_REDIS', 'NOT_FOUND')}")
        print(f"DEBUG: hasattr config.settings: {hasattr(config, 'settings')}")
        if hasattr(config, 'settings'):
            print(f"DEBUG: config.settings.USE_POSTGRES = {getattr(config.settings, 'USE_POSTGRES', 'NOT_FOUND')}")
            print(f"DEBUG: config.settings.USE_REDIS = {getattr(config.settings, 'USE_REDIS', 'NOT_FOUND')}")
        import main_worker

        # Проверяем основные импорты
        required_modules = [
            'psycopg2',
            'redis',
            'sqlalchemy',
            'aiohttp',
            'aiogram',
            'pydantic'
        ]

        missing_modules = []
        for module in required_modules:
            try:
                __import__(module)
            except ImportError:
                missing_modules.append(module)

        if missing_modules:
            logger.error(f"❌ Missing required modules: {', '.join(missing_modules)}")
            logger.error("Run: pip install -r requirements.txt")
            return False

        logger.info("✅ All required modules are available")

        # Проверка AI провайдеров
        check_ai_providers()

        return True

    except Exception as e:
        logger.error(f"❌ Error checking requirements: {e}")
        return False


def check_ai_providers():
    """Проверить доступные AI провайдеры"""
    try:
        import config

        groq_available = getattr(config, 'GROQ_API_KEY', None)
        openai_available = getattr(config, 'OPENAI_API_KEY', None) or getattr(config, 'CHATGPT_API_KEY', None)

        if groq_available:
            logger.info("🤖 Using Groq AI provider for content generation")
        elif openai_available:
            logger.info("🤖 Using OpenAI provider for content generation")
        else:
            logger.warning("⚠️ No AI provider configured. Content generation may be limited.")

    except Exception as e:
        logger.error(f"Error checking AI providers: {e}")


def check_single_instance():
    """Проверить что запущен только один экземпляр бота"""
    try:
        import psutil
        import os

        current_pid = os.getpid()
        current_process = psutil.Process(current_pid)

        # Ищем другие процессы Python с похожим именем
        python_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] and 'python' in proc.info['name'].lower():
                    cmdline = proc.info['cmdline']
                    if cmdline and any('main.py' in arg or 'main_worker.py' in arg for arg in cmdline):
                        python_processes.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Если есть другие процессы кроме текущего
        other_processes = [pid for pid in python_processes if pid != current_pid]
        if other_processes:
            logger.warning(f"⚠️ Found other bot instances running (PIDs: {other_processes})")
            logger.warning("This may cause TelegramConflictError. Consider stopping other instances.")
        else:
            logger.info("✅ No other bot instances detected")

    except ImportError:
        logger.warning("psutil not available, cannot check for multiple instances")
    except Exception as e:
        logger.error(f"Error checking for multiple instances: {e}")

async def main():
    """Главная функция"""
    logger.info("🚀 Starting Yandex.Market Bot...")

    # Проверка требований
    if not check_requirements():
        logger.error("❌ Requirements check failed. Exiting.")
        sys.exit(1)

    try:
        # Проверка на запущенные экземпляры бота
        check_single_instance()

        # Импорт и запуск главного worker'а
        from main_worker import get_main_worker

        worker = get_main_worker()

        # Режим работы
        if len(sys.argv) > 1:
            command = sys.argv[1].lower()

            if command == 'search':
                # Ручной запуск поиска
                keywords = sys.argv[2:] if len(sys.argv) > 2 else None
                result = await worker.manual_search(keywords=keywords)
                logger.info(f"Manual search result: {result}")

            elif command == 'publish':
                # Принудительная публикация
                result = await worker.force_publish_cycle()
                logger.info(f"Force publish result: {result}")

            elif command == 'status':
                # Показать статус
                status = worker.get_stats()
                logger.info("Bot Status:")
                for key, value in status.items():
                    logger.info(f"  {key}: {value}")

            else:
                logger.error(f"Unknown command: {command}")
                logger.info("Available commands: search, publish, status")
                sys.exit(1)

        else:
            # Основной режим - запуск полного worker'а
            logger.info("Starting full bot operation...")
            await worker.start()

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        logger.info("Bot shutdown complete")

if __name__ == "__main__":
    # Установка правильного event loop policy для Windows
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Запуск
    asyncio.run(main())