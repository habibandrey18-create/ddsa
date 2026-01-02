# bot_integration_link_gen.py
"""
Minimal Bot Integration for Link Generation
Clean integration point for Telegram bot
"""
import asyncio
import logging
from typing import Optional, Dict, Any

from worker import get_worker, job_queue
from exceptions.link_generation_exceptions import (
    LinkGenerationError,
    TimeoutError,
    HTTPError,
    CaptchaError,
    ThrottlingError,
    ConfigurationError,
)

# Alias for convenience
LinkTimeoutError = TimeoutError

logger = logging.getLogger(__name__)


async def generate_partner_link(url: str, timeout: int = 60, debug: bool = True) -> str:
    """
    High-level function to generate partner link.
    Non-blocking: submits job and polls for result.

    Args:
        url: Yandex Market product URL
        timeout: Maximum time to wait for result (seconds)
        debug: Enable debug artifacts

    Returns:
        Partner link (https://market.yandex.ru/cc/XXXXX)

    Raises:
        LinkGenerationError: If link cannot be generated
        LinkTimeoutError: If operation times out
        ConfigurationError: If inputs are invalid
    """
    worker = get_worker()

    # Ensure worker is running
    if not worker._running:
        await worker.start()

    # Submit job (non-blocking)
    job_id = await worker.submit_job(url=url, timeout=timeout, debug=debug)

    logger.info(f"📝 Link generation job submitted: {job_id}")

    # Poll for result (with timeout)
    poll_interval = 0.5  # Check every 500ms
    elapsed = 0.0

    while elapsed < timeout:
        result = worker.get_result(job_id)

        if not result:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            continue

        status = result.get("status")

        if status == "done":
            link = result.get("result")
            if link:
                logger.info(f"✅ Link generated: {link[:100]}...")
                return link
            else:
                raise LinkGenerationError(
                    "Job completed but no link in result", job_id=job_id, url=url
                )

        elif status == "error":
            error_msg = result.get("error", "Unknown error")
            error_type = result.get("error_type", "LinkGenerationError")

            # Classify error
            if "timeout" in error_msg.lower():
                raise LinkTimeoutError(error_msg, job_id=job_id, url=url)
            elif "404" in error_msg or "403" in error_msg:
                raise HTTPError(
                    error_msg,
                    status_code=404 if "404" in error_msg else 403,
                    job_id=job_id,
                    url=url,
                )
            elif "captcha" in error_msg.lower():
                raise CaptchaError(error_msg, job_id=job_id, url=url)
            elif "throttl" in error_msg.lower():
                raise ThrottlingError(error_msg, job_id=job_id, url=url)
            else:
                raise LinkGenerationError(error_msg, job_id=job_id, url=url)

        elif status == "running":
            # Still processing, wait
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            continue

        # Status is "pending" or unknown, wait
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    # Timeout reached
    raise LinkTimeoutError(
        f"Link generation timed out after {timeout}s", job_id=job_id, url=url
    )


async def get_link_generation_status() -> Dict[str, Any]:
    """
    Get status of link generation service.

    Returns:
        Dict with worker status, circuit breaker status, queue size
    """
    worker = get_worker()
    cb_status = worker.get_circuit_breaker_status()

    return {
        "worker_running": worker._running,
        "worker_count": len(worker.worker_tasks),
        "circuit_breaker": cb_status,
        "queue_size": job_queue.qsize(),
    }


# Example usage in bot handler:
"""
from bot_integration_link_gen import generate_partner_link

@dp.message(Command("link"))
async def cmd_generate_link(message: types.Message):
    url = message.get_args()
    if not url:
        await message.answer("❌ Укажите URL товара")
        return
    
    try:
        # Show "processing" message
        status_msg = await message.answer("⏳ Генерирую партнёрскую ссылку...")
        
        # Generate link (non-blocking, but we wait for result)
        link = await generate_partner_link(url, timeout=60)
        
        # Update status message
        await status_msg.edit_text(f"✅ Партнёрская ссылка:\n{link}")
        
    except LinkTimeoutError:
        await message.answer("⏱️ Превышено время ожидания. Попробуйте позже.")
    except CaptchaError:
        await message.answer("🤖 Обнаружена капча. Требуется ручное вмешательство.")
    except HTTPError as e:
        await message.answer(f"❌ HTTP ошибка: {e.status_code}")
    except LinkGenerationError as e:
        await message.answer(f"❌ Ошибка генерации ссылки: {e}")
"""
