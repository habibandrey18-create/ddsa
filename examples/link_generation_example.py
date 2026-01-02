# examples/link_generation_example.py
"""
Example usage of LinkGenerationService
Demonstrates non-blocking job submission and result polling
"""
import asyncio
import logging
from services.link_generation_service import get_link_generation_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def example_bot_handler(url: str):
    """
    Example bot handler that submits a job and returns job_id immediately.
    """
    service = get_link_generation_service()

    # Start service if not running
    if not service._running:
        await service.start()

    # Submit job (non-blocking)
    job_id = await service.submit_job(url=url, headless=True, debug=True, timeout=60)

    logger.info(f"✅ Job submitted: {job_id}")
    return job_id


async def poll_result(job_id: str, max_wait: int = 120) -> dict:
    """
    Poll for job result.

    Args:
        job_id: Job identifier
        max_wait: Maximum time to wait in seconds

    Returns:
        Result dict with status, result, or error
    """
    service = get_link_generation_service()

    for _ in range(max_wait):
        result = service.get_result(job_id)

        if not result:
            logger.warning(f"Job {job_id} not found")
            return {"status": "not_found"}

        status = result.get("status")

        if status == "done":
            logger.info(f"✅ Job completed: {result.get('result')}")
            return result
        elif status == "error":
            logger.error(f"❌ Job failed: {result.get('error')}")
            return result
        elif status in ("pending", "running"):
            logger.info(f"⏳ Job {status}, waiting...")
            await asyncio.sleep(2)
        else:
            logger.warning(f"Unknown status: {status}")
            await asyncio.sleep(2)

    logger.warning(f"⏱ Timeout waiting for job {job_id}")
    return {"status": "timeout"}


async def example_usage():
    """Example of using the service."""
    service = get_link_generation_service()

    # Start service
    await service.start()

    try:
        # Example URL
        test_url = "https://market.yandex.ru/product/123456"

        # Submit job (non-blocking)
        job_id = await example_bot_handler(test_url)

        # Poll for result
        result = await poll_result(job_id)

        if result.get("status") == "done":
            link = result.get("result")
            print(f"✅ Generated link: {link}")
        else:
            error = result.get("error", "Unknown error")
            print(f"❌ Failed: {error}")

    finally:
        # Stop service
        await service.stop()


if __name__ == "__main__":
    asyncio.run(example_usage())
