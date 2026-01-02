# bot_integration_example.py
"""
Minimal example showing Telegram bot integration with link generation worker.
Demonstrates job submission and result polling.
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode

from worker import get_worker
from exceptions.link_generation_exceptions import LinkGenerationError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize bot (replace with your actual bot token)
BOT_TOKEN = "YOUR_BOT_TOKEN"
ADMIN_ID = 123456789  # Replace with your admin ID

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Initialize worker
worker = get_worker()


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Start command handler."""
    await message.answer(
        "👋 Привет! Отправь ссылку на товар Яндекс.Маркета для получения партнёрской ссылки."
    )


@dp.message(Command("get_link"))
async def handle_get_link(message: types.Message):
    """
    Example handler for getting partner link.
    Demonstrates non-blocking job submission and result polling.
    """
    # Extract URL from command or message text
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❌ Укажите URL товара: /get_link <url>")
        return

    url = args[1]

    # Submit job (non-blocking, returns immediately)
    try:
        job_id = await worker.submit_job(url=url, headless=True, debug=True, timeout=60)

        # Immediately acknowledge with job_id
        await message.answer(
            f"✅ Задача принята!\n" f"📋 ID: `{job_id}`\n" f"⏳ Обработка...",
            parse_mode=ParseMode.MARKDOWN,
        )

        # Start background task to poll for result
        asyncio.create_task(poll_and_notify(message.chat.id, job_id, url))

    except Exception as e:
        logger.exception(f"Failed to submit job: {e}")
        await message.answer(f"❌ Ошибка при создании задачи: {e}")


async def poll_and_notify(chat_id: int, job_id: str, url: str):
    """
    Background task that polls for job result and notifies user.

    Args:
        chat_id: Telegram chat ID to send result to
        job_id: Job identifier
        url: Original URL (for context)
    """
    max_wait = 120  # Maximum time to wait (2 minutes)
    poll_interval = 2  # Check every 2 seconds

    for _ in range(max_wait // poll_interval):
        result = worker.get_result(job_id)

        if not result:
            logger.warning(f"Job {job_id} not found")
            await bot.send_message(chat_id, f"❌ Задача {job_id} не найдена")
            return

        status = result.get("status")

        if status == "done":
            link = result.get("result")
            await bot.send_message(
                chat_id,
                f"✅ **Готово!**\n\n"
                f"🔗 Партнёрская ссылка:\n`{link}`\n\n"
                f"📋 ID задачи: `{job_id}`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        elif status == "error":
            error = result.get("error", "Unknown error")
            debug_path = result.get("debug_path")

            error_msg = f"❌ **Ошибка**\n\n{error}"
            if debug_path:
                error_msg += f"\n\n💾 Debug артефакты: `{debug_path}`"

            await bot.send_message(chat_id, error_msg, parse_mode=ParseMode.MARKDOWN)
            return

        # Still pending or running, wait
        await asyncio.sleep(poll_interval)

    # Timeout
    await bot.send_message(
        chat_id,
        f"⏱ Превышено время ожидания для задачи `{job_id}`",
        parse_mode=ParseMode.MARKDOWN,
    )


@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    """Show worker and circuit breaker status (admin only)."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Доступ запрещён")
        return

    try:
        # Get circuit breaker status
        cb_status = worker.get_circuit_breaker_status()

        state_emoji = {"CLOSED": "✅", "OPEN": "🚨", "HALF_OPEN": "🔍"}

        emoji = state_emoji.get(cb_status["state"], "❓")

        status_text = (
            f"{emoji} **Worker Status**\n\n"
            f"**Circuit Breaker:**\n"
            f"• State: {cb_status['state']}\n"
            f"• Failures: {cb_status['consecutive_failures']}/{cb_status['failure_threshold']}\n"
            f"• Available: {'✅ Yes' if cb_status['is_available'] else '❌ No'}\n"
        )

        if cb_status["state"] == "OPEN":
            minutes = cb_status["time_until_retry"] // 60
            seconds = cb_status["time_until_retry"] % 60
            status_text += f"• Retry in: {minutes}m {seconds}s\n"

        await message.answer(status_text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logger.exception(f"Error getting status: {e}")
        await message.answer(f"❌ Ошибка: {e}")


async def main():
    """Main function - start bot and worker."""
    # Start worker
    await worker.start()
    logger.info("✅ Worker started")

    try:
        # Start bot
        logger.info("✅ Bot starting...")
        await dp.start_polling(bot)
    finally:
        # Stop worker on shutdown
        await worker.stop()
        logger.info("✅ Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
