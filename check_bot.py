# check_bot.py
"""Скрипт для проверки инициализации бота"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def check_bot():
    """Проверяет инициализацию бота"""
    print("=" * 60)
    print("ПРОВЕРКА ИНИЦИАЛИЗАЦИИ БОТА")
    print("=" * 60)

    try:
        # Проверка конфигурации
        print("\n[1/5] Проверка конфигурации...")
        import config

        print(
            f"   ✅ BOT_TOKEN: {'установлен' if config.BOT_TOKEN else 'НЕ УСТАНОВЛЕН'}"
        )
        print(
            f"   ✅ CHANNEL_ID: {'установлен' if config.CHANNEL_ID else 'НЕ УСТАНОВЛЕН'}"
        )
        print(f"   ✅ ADMIN_ID: {'установлен' if config.ADMIN_ID else 'НЕ УСТАНОВЛЕН'}")

        # Проверка базы данных
        print("\n[2/5] Проверка базы данных...")
        from database import Database

        db = Database()
        print(f"   ✅ База данных инициализирована")
        queue_count = db.get_queue_count()
        print(f"   📊 Товаров в очереди: {queue_count}")

        # Проверка бота
        print("\n[3/5] Проверка бота...")
        from bot import bot, dp

        print(f"   ✅ Bot создан")
        print(f"   ✅ Dispatcher создан")

        # Проверка подключения к Telegram
        print("\n[4/5] Проверка подключения к Telegram...")
        try:
            bot_info = await bot.get_me()
            print(f"   ✅ Бот подключен: @{bot_info.username}")
            print(f"   ✅ ID бота: {bot_info.id}")
            print(f"   ✅ Имя: {bot_info.first_name}")
        except Exception as e:
            print(f"   ❌ Ошибка подключения: {e}")
            return False

        # Проверка webhook
        print("\n[5/5] Проверка webhook...")
        try:
            webhook_info = await bot.get_webhook_info()
            if webhook_info.url:
                print(f"   ⚠️ Webhook установлен: {webhook_info.url}")
                print(f"   ℹ️ Бот будет использовать webhook, а не polling")
            else:
                print(f"   ✅ Webhook не установлен (будет использован polling)")
        except Exception as e:
            print(f"   ⚠️ Не удалось проверить webhook: {e}")

        print("\n" + "=" * 60)
        print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ УСПЕШНО")
        print("=" * 60)
        print("\nБот готов к запуску!")
        print("Для запуска используйте: python bot.py")
        return True

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        try:
            await bot.session.close()
        except:
            pass


if __name__ == "__main__":
    result = asyncio.run(check_bot())
    sys.exit(0 if result else 1)
