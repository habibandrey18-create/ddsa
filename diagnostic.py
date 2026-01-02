#!/usr/bin/env python3
"""
Диагностический скрипт - проверяет ВСЕ функции бота
Показывает где сломалось и что исправить
"""
import asyncio
import sys
import os
from pathlib import Path

# Добавь путь к проекту
sys.path.insert(0, str(Path(__file__).parent))


class BotDiagnostics:
    """Проверяет ВСЕ критические функции"""

    def __init__(self):
        self.issues = []
        self.success = []
        self.warnings = []

    async def check_all(self):
        """Запуск всех проверок"""
        print("=" * 70)
        print("🔍 ДИАГНОСТИКА БОТА - ПОЛНАЯ ПРОВЕРКА")
        print("=" * 70)
        print()

        # 1. Проверка файлов проекта
        await self.check_files()

        # 2. Проверка конфигурации
        await self.check_config()

        # 3. Проверка базы данных
        await self.check_database()

        # 4. Проверка модулей Python
        await self.check_modules()

        # 5. Проверка функции парсинга
        await self.check_parsing()

        # 6. Проверка cookies
        await self.check_cookies()

        # 7. Проверка обработчиков
        await self.check_handlers()

        # 8. Проверка логирования
        await self.check_logging()

        # 9. Проверка автопубликации
        await self.check_autopublish()

        # 10. Проверка captcha solver
        await self.check_captcha()

        # Итоговый отчет
        self.print_report()

    async def check_files(self):
        """Проверка наличия файлов"""
        print("\n1️⃣ ФАЙЛЫ ПРОЕКТА")
        print("-" * 70)

        required_files = {
            "main.py": "Главный файл запуска",
            "config.py": "Конфигурация",
            "database.py": "База данных",
            "handlers_admin.py": "Обработчики админки",
            "handlers_user.py": "Обработчики пользователей",
            "utils/get_ref_link.py": "Генератор CC ссылок",
            ".env": "Переменные окружения",
        }

        optional_files = {
            "cookies.json": "Cookies для авторизации",
            "logging_config.json": "Конфигурация логирования",
            "run_browser_once.py": "Скрипт получения cookies",
        }

        for file, desc in required_files.items():
            if os.path.exists(file):
                self.success.append(f"✅ {file} найден")
                print(f"✅ {file} - {desc}")
            else:
                self.issues.append(f"❌ {file} НЕ НАЙДЕН!")
                print(f"❌ {file} - {desc} (НЕ НАЙДЕН!)")

        for file, desc in optional_files.items():
            if os.path.exists(file):
                self.success.append(f"✅ {file} найден")
                print(f"✅ {file} - {desc}")
            else:
                self.warnings.append(f"⚠️ {file} не найден (опционально)")
                print(f"⚠️  {file} - {desc} (не найден, но опционально)")

    async def check_config(self):
        """Проверка конфигурации"""
        print("\n2️⃣ КОНФИГУРАЦИЯ")
        print("-" * 70)

        try:
            import config

            # Проверка TOKEN
            if hasattr(config, "TOKEN"):
                if config.TOKEN and config.TOKEN != "":
                    self.success.append("✅ TOKEN установлен")
                    print(f"✅ TOKEN: {config.TOKEN[:10]}...****")
                else:
                    self.issues.append("❌ TOKEN не установлен в .env!")
                    print("❌ TOKEN не установлен в .env!")
            else:
                self.issues.append("❌ TOKEN не найден в config!")
                print("❌ TOKEN не найден в config!")

            # Проверка ADMIN_IDS
            if hasattr(config, "ADMIN_IDS"):
                if config.ADMIN_IDS:
                    self.success.append(f"✅ ADMIN_IDS: {config.ADMIN_IDS}")
                    print(f"✅ ADMIN_IDS: {config.ADMIN_IDS}")
                else:
                    self.warnings.append("⚠️ ADMIN_IDS не установлен")
                    print("⚠️  ADMIN_IDS не установлен")
            else:
                self.warnings.append("⚠️ ADMIN_IDS не найден")
                print("⚠️  ADMIN_IDS не найден")

            # Проверка DB_FILE
            if hasattr(config, "DB_FILE"):
                self.success.append(f"✅ DB_FILE: {config.DB_FILE}")
                print(f"✅ DB_FILE: {config.DB_FILE}")
            else:
                self.warnings.append("⚠️ DB_FILE не найден")
                print("⚠️  DB_FILE не найден")

            # Проверка CAPTCHA
            if hasattr(config, "CAPTCHA_API_KEY"):
                if config.CAPTCHA_API_KEY:
                    self.success.append("✅ CAPTCHA_API_KEY установлен")
                    print(f"✅ CAPTCHA_API_KEY: {config.CAPTCHA_API_KEY[:10]}...")
                else:
                    self.warnings.append(
                        "⚠️ CAPTCHA_API_KEY не установлен (опционально)"
                    )
                    print("⚠️  CAPTCHA_API_KEY не установлен (опционально)")

            if hasattr(config, "CAPTCHA_SERVICE"):
                self.success.append(f"✅ CAPTCHA_SERVICE: {config.CAPTCHA_SERVICE}")
                print(f"✅ CAPTCHA_SERVICE: {config.CAPTCHA_SERVICE}")

        except Exception as e:
            self.issues.append(f"❌ Ошибка загрузки конфига: {e}")
            print(f"❌ Ошибка: {e}")
            import traceback

            traceback.print_exc()

    async def check_database(self):
        """Проверка БД"""
        print("\n3️⃣ БАЗА ДАННЫХ")
        print("-" * 70)

        try:
            import database

            # Проверка инициализации
            if hasattr(database, "init_db"):
                self.success.append("✅ database.init_db существует")
                print("✅ database.init_db существует")
            else:
                self.issues.append("❌ database.init_db не найден!")
                print("❌ database.init_db не найден!")

            # Проверка класса Database
            if hasattr(database, "Database"):
                self.success.append("✅ Database класс найден")
                print("✅ Database класс найден")

                # Попробуем создать экземпляр
                try:
                    import config

                    db = database.Database(
                        config.DB_FILE
                        if hasattr(config, "DB_FILE")
                        else "bot_database.db"
                    )
                    queue_count = db.get_queue_count()
                    self.success.append(f"✅ БД работает (в очереди: {queue_count})")
                    print(f"✅ БД работает (в очереди: {queue_count} элементов)")

                    # Проверка настроек
                    autopublish = db.get_setting("auto_publish_enabled", "False")
                    self.success.append(
                        f"✅ Настройки БД работают (autopublish: {autopublish})"
                    )
                    print(f"✅ Настройки БД работают (autopublish: {autopublish})")
                except Exception as e:
                    self.issues.append(f"❌ Ошибка работы с БД: {e}")
                    print(f"❌ Ошибка работы с БД: {e}")
            else:
                self.warnings.append(
                    "⚠️ Database класс не найден (используются функции)"
                )
                print("⚠️  Database класс не найден (используются функции)")

        except Exception as e:
            self.issues.append(f"❌ Ошибка БД: {e}")
            print(f"❌ Ошибка: {e}")
            import traceback

            traceback.print_exc()

    async def check_modules(self):
        """Проверка модулей Python"""
        print("\n4️⃣ МОДУЛИ PYTHON")
        print("-" * 70)

        modules = {
            "asyncio": "Асинхронность",
            "aiogram": "Telegram Bot API",
            "playwright": "Браузерная автоматизация",
            "dotenv": "Загрузка .env",
            "aiohttp": "HTTP клиент",
            "sqlite3": "SQLite база данных",
        }

        for module, desc in modules.items():
            try:
                __import__(module)
                self.success.append(f"✅ {module} установлен")
                print(f"✅ {module} - {desc}")
            except ImportError:
                self.issues.append(f"❌ {module} НЕ УСТАНОВЛЕН!")
                print(f"❌ {module} - {desc} (НЕ УСТАНОВЛЕН!)")
                if module == "playwright":
                    print(f"   Установи: pip install {module}")
                    print(f"   Затем: python -m playwright install chromium")

    async def check_parsing(self):
        """Проверка парсинга URL и CC ссылок"""
        print("\n5️⃣ ПАРСИНГ URL И CC ССЫЛОК")
        print("-" * 70)

        try:
            from utils.get_ref_link import get_cc_link_by_click

            self.success.append("✅ get_cc_link_by_click импортирован")
            print("✅ get_cc_link_by_click импортирован")

            # Проверка что функция существует
            if callable(get_cc_link_by_click):
                self.success.append("✅ get_cc_link_by_click - функция существует")
                print("✅ get_cc_link_by_click - функция существует")
            else:
                self.issues.append("❌ get_cc_link_by_click не является функцией!")
                print("❌ get_cc_link_by_click не является функцией!")

            # Проверка класса RefLinkService
            try:
                from utils.get_ref_link import RefLinkService

                self.success.append("✅ RefLinkService класс найден")
                print("✅ RefLinkService класс найден")
            except ImportError:
                self.warnings.append(
                    "⚠️ RefLinkService класс не найден (используется функция)"
                )
                print("⚠️  RefLinkService класс не найден (используется функция)")

        except Exception as e:
            self.issues.append(f"❌ Ошибка импорта парсинга: {e}")
            print(f"❌ Ошибка: {e}")
            import traceback

            traceback.print_exc()

    async def check_cookies(self):
        """Проверка cookies"""
        print("\n6️⃣ COOKIES ДЛЯ АВТОРИЗАЦИИ")
        print("-" * 70)

        cookies_file = "cookies.json"
        if os.path.exists(cookies_file):
            try:
                import json

                with open(cookies_file, "r", encoding="utf-8") as f:
                    cookies_data = json.load(f)

                if "cookies" in cookies_data and cookies_data["cookies"]:
                    cookie_count = len(cookies_data["cookies"])
                    self.success.append(
                        f"✅ cookies.json существует ({cookie_count} cookies)"
                    )
                    print(f"✅ cookies.json существует ({cookie_count} cookies)")
                else:
                    self.warnings.append("⚠️ cookies.json пустой или невалидный")
                    print("⚠️  cookies.json пустой или невалидный")
            except Exception as e:
                self.issues.append(f"❌ Ошибка чтения cookies.json: {e}")
                print(f"❌ Ошибка чтения cookies.json: {e}")
        else:
            self.warnings.append(
                "⚠️ cookies.json не найден (запусти run_browser_once.py)"
            )
            print("⚠️  cookies.json не найден")
            print("   Запусти: python run_browser_once.py")

    async def check_handlers(self):
        """Проверка обработчиков"""
        print("\n7️⃣ ОБРАБОТЧИКИ И КОМАНДЫ")
        print("-" * 70)

        try:
            # Проверка handlers_admin
            import handlers_admin

            if hasattr(handlers_admin, "router"):
                self.success.append("✅ handlers_admin.router найден")
                print("✅ handlers_admin.router найден")
            else:
                self.issues.append("❌ handlers_admin.router не найден!")
                print("❌ handlers_admin.router не найден!")

            # Проверка handlers_user
            import handlers_user

            if hasattr(handlers_user, "router"):
                self.success.append("✅ handlers_user.router найден")
                print("✅ handlers_user.router найден")
            else:
                self.issues.append("❌ handlers_user.router не найден!")
                print("❌ handlers_user.router не найден!")

            # Проверка функций админки
            admin_functions = [
                "admin_system_callback",
                "system_toggle_autopublish_callback",
                "admin_queue_callback",
            ]

            for func_name in admin_functions:
                if hasattr(handlers_admin, func_name):
                    self.success.append(f"✅ {func_name} найден")
                    print(f"✅ {func_name} найден")
                else:
                    self.warnings.append(f"⚠️ {func_name} не найден")
                    print(f"⚠️  {func_name} не найден")

        except Exception as e:
            self.issues.append(f"❌ Ошибка проверки handlers: {e}")
            print(f"❌ Ошибка: {e}")
            import traceback

            traceback.print_exc()

    async def check_logging(self):
        """Проверка логирования"""
        print("\n8️⃣ ЛОГИРОВАНИЕ")
        print("-" * 70)

        try:
            import logging

            logger = logging.getLogger("main")

            # Проверка уровня логирования
            level_name = logging.getLevelName(
                logger.level if logger.level else logging.NOTSET
            )
            if logger.level == logging.INFO or logger.level == 0:
                self.success.append("✅ Логирование установлено")
                print(f"✅ Уровень логирования: {level_name}")
            else:
                self.warnings.append(f"⚠️ Уровень логирования: {level_name}")
                print(f"⚠️  Уровень логирования: {level_name}")

            # Проверка обработчиков
            if logger.handlers:
                self.success.append(
                    f"✅ Логирование настроено ({len(logger.handlers)} handler)"
                )
                print(f"✅ Обработчиков: {len(logger.handlers)}")
            else:
                # Проверка root logger
                root_logger = logging.getLogger()
                if root_logger.handlers:
                    self.success.append(
                        f"✅ Root logger настроен ({len(root_logger.handlers)} handler)"
                    )
                    print(f"✅ Root logger обработчиков: {len(root_logger.handlers)}")
                else:
                    self.warnings.append("⚠️ Обработчики логирования не настроены")
                    print(
                        "⚠️  Обработчики не найдены (используется базовое логирование)"
                    )

            # Проверка файла логов
            log_files = ["bot.log", "logs/bot.log"]
            for log_file in log_files:
                if os.path.exists(log_file):
                    size = os.path.getsize(log_file)
                    self.success.append(f"✅ {log_file} существует ({size} байт)")
                    print(f"✅ {log_file}: {size/1024:.1f} KB")
                    break
            else:
                print("⚠️  bot.log еще не создан (будет создан при запуске)")

        except Exception as e:
            self.issues.append(f"❌ Ошибка проверки логирования: {e}")
            print(f"❌ Ошибка: {e}")

    async def check_autopublish(self):
        """Проверка автопубликации"""
        print("\n9️⃣ АВТОПУБЛИКАЦИЯ")
        print("-" * 70)

        try:
            import config
            from database import Database

            db = Database(
                config.DB_FILE if hasattr(config, "DB_FILE") else "bot_database.db"
            )

            # Проверка настройки автопубликации
            autopublish = db.get_setting("auto_publish_enabled", "False")
            autopublish_enabled = autopublish.lower() in ("true", "1", "yes")

            if autopublish_enabled:
                self.success.append("✅ Автопубликация включена")
                print("✅ Автопубликация: ВКЛЮЧЕНА")
            else:
                self.success.append("✅ Автопубликация выключена (по умолчанию)")
                print("✅ Автопубликация: ВЫКЛЮЧЕНА (по умолчанию)")

            # Проверка что можно переключить
            try:
                db.set_setting("auto_publish_enabled", "True")
                test_value = db.get_setting("auto_publish_enabled", "False")
                db.set_setting("auto_publish_enabled", autopublish)  # Вернем обратно

                if test_value.lower() in ("true", "1", "yes"):
                    self.success.append("✅ Переключение автопубликации работает")
                    print("✅ Переключение автопубликации работает")
                else:
                    self.issues.append("❌ Переключение автопубликации не работает!")
                    print("❌ Переключение автопубликации не работает!")
            except Exception as e:
                self.issues.append(f"❌ Ошибка переключения автопубликации: {e}")
                print(f"❌ Ошибка переключения: {e}")

        except Exception as e:
            self.issues.append(f"❌ Ошибка проверки автопубликации: {e}")
            print(f"❌ Ошибка: {e}")
            import traceback

            traceback.print_exc()

    async def check_captcha(self):
        """Проверка captcha solver"""
        print("\n🔟 CAPTCHA SOLVER")
        print("-" * 70)

        try:
            from utils.captcha_solver import CaptchaSolver

            self.success.append("✅ CaptchaSolver импортирован")
            print("✅ CaptchaSolver импортирован")

            # Проверка инициализации
            solver = CaptchaSolver()

            if solver.api_key:
                self.success.append("✅ CAPTCHA API ключ загружен")
                print(f"✅ CAPTCHA API ключ: {solver.api_key[:10]}...")
                print(f"✅ Сервис: {solver.service}")

                # Проверка баланса
                try:
                    balance = await solver.get_balance()
                    if balance is not None:
                        self.success.append(f"✅ Баланс captcha: ${balance:.2f}")
                        print(f"✅ Баланс captcha: ${balance:.2f}")
                    else:
                        self.warnings.append("⚠️ Не удалось получить баланс captcha")
                        print("⚠️  Не удалось получить баланс captcha")
                except Exception as e:
                    self.warnings.append(f"⚠️ Ошибка проверки баланса: {e}")
                    print(f"⚠️  Ошибка проверки баланса: {e}")
            else:
                self.warnings.append("⚠️ CAPTCHA API ключ не установлен (опционально)")
                print("⚠️  CAPTCHA API ключ не установлен (опционально)")

        except ImportError:
            self.warnings.append("⚠️ CaptchaSolver не найден (опционально)")
            print("⚠️  CaptchaSolver не найден (опционально)")
        except Exception as e:
            self.warnings.append(f"⚠️ Ошибка проверки captcha: {e}")
            print(f"⚠️  Ошибка: {e}")

    def print_report(self):
        """Итоговый отчет"""
        print("\n" + "=" * 70)
        print("📋 ИТОГОВЫЙ ОТЧЕТ")
        print("=" * 70)

        print(f"\n✅ УСПЕШНО: {len(self.success)}")
        for item in self.success[:10]:  # Показываем первые 10
            print(f"  {item}")
        if len(self.success) > 10:
            print(f"  ... и еще {len(self.success) - 10} проверок")

        if self.warnings:
            print(f"\n⚠️  ПРЕДУПРЕЖДЕНИЯ: {len(self.warnings)}")
            for warning in self.warnings[:5]:  # Показываем первые 5
                print(f"  {warning}")
            if len(self.warnings) > 5:
                print(f"  ... и еще {len(self.warnings) - 5} предупреждений")

        if self.issues:
            print(f"\n❌ ПРОБЛЕМЫ: {len(self.issues)}")
            for issue in self.issues:
                print(f"  {issue}")

            print("\n🔧 РЕКОМЕНДАЦИИ:")
            if any("TOKEN" in issue for issue in self.issues):
                print("  1. Проверь TOKEN в .env файле")
            if any(
                "БД" in issue or "database" in issue.lower() for issue in self.issues
            ):
                print("  2. Проверь database.py и инициализацию БД")
            if any("handler" in issue.lower() for issue in self.issues):
                print("  3. Убедись что все handler'ы подключены в main.py")
            if any(
                "модуль" in issue.lower() or "import" in issue.lower()
                for issue in self.issues
            ):
                print(
                    "  4. Установи недостающие модули: pip install -r requirements.txt"
                )
            print("  5. Запусти скрипт еще раз после исправлений")
        else:
            print("\n🎉 ВСЕ КРИТИЧЕСКИЕ ПРОВЕРКИ ПРОЙДЕНЫ!")
            print("Бот готов к работе!")

        print("\n" + "=" * 70)


async def main():
    diag = BotDiagnostics()
    await diag.check_all()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Диагностика прервана пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback

        traceback.print_exc()
