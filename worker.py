# worker.py
"""
Async Worker for Link Generation
Non-blocking job processing using asyncio.Queue
"""
import asyncio
import uuid
import logging
from typing import Dict, Optional, Any
from datetime import datetime

from config.link_generation_config import (
    WORKER_MAX_WORKERS,
    WORKER_JOB_TIMEOUT,
    WORKER_CLEANUP_INTERVAL,
    WORKER_RESULT_TTL,
    DEFAULT_DEBUG,
)
from services.circuit_breaker import get_circuit_breaker
from exceptions.link_generation_exceptions import (
    LinkGenerationError,
    NetworkError,
    TimeoutError as LinkTimeoutError,
    HTTPError,
    CaptchaError,
    ThrottlingError,
    ConfigurationError,
)

logger = logging.getLogger(__name__)

# In-memory result store (replace with Redis/DB for production)
# Protected by lock for thread-safety
results: Dict[str, Dict[str, Any]] = {}
results_lock = asyncio.Lock()  # Protects results dict from race conditions

# Queue for incoming jobs (asyncio.Queue is already thread-safe)
job_queue: asyncio.Queue = asyncio.Queue()


class LinkGenerationWorker:
    """
    Async worker for generating Yandex Market partner links.
    Uses asyncio.Queue + async YandexMarketLinkGen (non-blocking).
    """

    def __init__(self, max_workers: int = WORKER_MAX_WORKERS):
        self.max_workers = max_workers
        self.worker_tasks: list = []
        self.cleanup_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """Start the worker (multiple worker tasks and cleanup)."""
        if self._running:
            logger.warning("Worker already running")
            return

        self._running = True

        # Start multiple worker tasks
        for i in range(self.max_workers):
            task = asyncio.create_task(self._worker_main(f"worker-{i}"))
            self.worker_tasks.append(task)

        # Start cleanup task
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())

        logger.info(f"✅ LinkGenerationWorker started with {self.max_workers} workers")

    async def stop(self):
        """Stop the worker gracefully."""
        self._running = False

        # Cancel worker tasks
        for task in self.worker_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Cancel cleanup task
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("✅ LinkGenerationWorker stopped")

    async def submit_job(
        self,
        url: str,
        cookies: Optional[list] = None,
        timeout: int = WORKER_JOB_TIMEOUT,
        headless: bool = True,
        debug: bool = True,
        reuse_storage_state: Optional[str] = None,
    ) -> str:
        """
        Submit a job to generate partner link.
        Returns immediately with job_id (non-blocking).

        Args:
            url: Product URL
            cookies: Optional cookies for authentication
            timeout: Job timeout in seconds
            headless: Run browser in headless mode
            debug: Enable debug artifacts
            reuse_storage_state: Path to storage state file to reuse

        Returns:
            job_id: Unique job identifier
        """
        job_id = str(uuid.uuid4())

        job = {
            "id": job_id,
            "url": url,
            "cookies": cookies,
            "timeout": timeout or WORKER_JOB_TIMEOUT,
            "headless": headless,
            "debug": debug,
            "reuse_storage_state": reuse_storage_state,
            "created_at": datetime.now().isoformat(),
        }

        # Thread-safe result storage
        async with results_lock:
            results[job_id] = {
                "status": "pending",
                "created_at": datetime.now().isoformat(),
            }

        await job_queue.put(job)
        logger.info(f"📝 Job submitted: {job_id} for URL: {url[:100]}")

        return job_id

    def get_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get job result by job_id.
        Thread-safe read operation.

        Returns:
            Dict with status, result, error, or None if job not found
        """
        # Read is safe without lock (dict.get is atomic in CPython)
        # But for consistency and future-proofing, we could use lock
        # For now, direct access is fine for reads
        return results.get(job_id)

    async def _worker_main(self, worker_name: str):
        """Main worker loop - consumes jobs from queue."""
        logger.info(f"🔄 {worker_name} started")

        while self._running:
            try:
                # Get job with timeout to allow checking _running flag
                try:
                    job = await asyncio.wait_for(job_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                job_id = job["id"]
                url = job["url"]

                logger.info(f"🔄 {worker_name} processing job: {job_id}")

                # Check circuit breaker before processing
                circuit_breaker = get_circuit_breaker()
                try:
                    await circuit_breaker.before_job()
                except RuntimeError:
                    # Circuit breaker is OPEN or HALF_OPEN (probe in progress)
                    user_message = circuit_breaker.get_user_message()
                    async with results_lock:
                        if job_id in results:
                            results[job_id]["status"] = "error"
                            results[job_id]["error"] = user_message
                            results[job_id]["completed_at"] = datetime.now().isoformat()
                    logger.warning(
                        f"⚠️ Job {job_id} rejected by circuit breaker: {user_message}"
                    )
                    job_queue.task_done()
                    continue

                # Thread-safe status update
                async with results_lock:
                    if job_id in results:
                        results[job_id]["status"] = "running"
                        results[job_id]["started_at"] = datetime.now().isoformat()

                try:
                    # Validate inputs before processing
                    from utils.input_validators import validate_url

                    is_valid, error = validate_url(url)
                    if not is_valid:
                        raise ConfigurationError(
                            f"Invalid URL provided: {error}", debug_path=None
                        )

                    # Create generator
                    from utils.yandex_market_link_gen import YandexMarketLinkGen

                    timeout = job.get("timeout", WORKER_JOB_TIMEOUT)
                    # Validate timeout
                    if timeout < 5 or timeout > 300:
                        timeout = WORKER_JOB_TIMEOUT
                        logger.warning(
                            f"⚠️ Invalid timeout in job {job_id}, using default: {WORKER_JOB_TIMEOUT}s"
                        )

                    generator = YandexMarketLinkGen(
                        headless=job.get("headless", True),
                        timeout=timeout,
                        max_retries=min(job.get("max_retries", 3), 10),  # Cap at 10
                        debug=job.get("debug", DEFAULT_DEBUG),
                    )

                    # Create cancellation token for this job
                    cancellation_event = asyncio.Event()

                    # Generate link (async, non-blocking) with timeout and cancellation
                    try:
                        link = await asyncio.wait_for(
                            generator.generate(
                                url=url,
                                job_id=job_id,
                                reuse_state_path=job.get("reuse_storage_state"),
                                cancellation_token=None,  # Can be set if job is cancelled
                            ),
                            timeout=timeout + 10,  # Extra 10s buffer
                        )
                    except asyncio.CancelledError:
                        logger.info(f"🛑 Job {job_id} cancelled")
                        raise
                    except asyncio.TimeoutError:
                        raise LinkTimeoutError(
                            f"Job timeout after {timeout + 10}s", debug_path=None
                        )

                    # Thread-safe result update
                    async with results_lock:
                        if job_id in results:
                            results[job_id]["status"] = "done"
                            results[job_id]["result"] = link
                            results[job_id]["completed_at"] = datetime.now().isoformat()
                    logger.info(f"✅ Job completed: {job_id} -> {link[:100]}")

                    # Record success in circuit breaker
                    await circuit_breaker.on_success()

                except asyncio.TimeoutError:
                    error_msg = (
                        f"Job timeout after {job.get('timeout', WORKER_JOB_TIMEOUT)}s"
                    )
                    await self._handle_job_error(
                        job_id, error_msg, LinkTimeoutError(error_msg), circuit_breaker
                    )

                except (LinkGenerationError, NetworkError) as e:
                    # Link generation errors (network, timeout, etc.)
                    await self._handle_job_error(
                        job_id,
                        str(e),
                        e,
                        circuit_breaker,
                        debug_path=getattr(e, "debug_path", None),
                    )

                except Exception as e:
                    # Unexpected errors
                    error_msg = f"Unexpected error: {e}"
                    await self._handle_job_error(job_id, error_msg, e, circuit_breaker)

                finally:
                    job_queue.task_done()

            except asyncio.CancelledError:
                logger.info(f"🔄 {worker_name} cancelled")
                break
            except Exception as e:
                logger.exception(f"❌ {worker_name} error: {e}")
                await asyncio.sleep(1.0)  # Prevent tight loop on errors

    async def _handle_job_error(
        self,
        job_id: str,
        error_msg: str,
        exception: Exception,
        circuit_breaker,
        debug_path: Optional[str] = None,
    ):
        """
        Unified error handling for job failures.
        Ensures Circuit Breaker prevents unsafe retry loops.
        Thread-safe result updates.

        Args:
            job_id: Job identifier
            error_msg: Error message
            exception: Exception object
            circuit_breaker: Circuit breaker instance
            debug_path: Optional path to debug artifacts
        """
        # Thread-safe result update
        async with results_lock:
            if job_id in results:
                results[job_id]["status"] = "error"
                results[job_id]["error"] = error_msg
                results[job_id]["completed_at"] = datetime.now().isoformat()
                results[job_id]["error_type"] = type(exception).__name__

                if debug_path:
                    results[job_id]["debug_path"] = debug_path

        # Enhanced logging with context
        logger.error(
            f"❌ Job failed: {job_id} - {error_msg}",
            extra={
                "job_id": job_id,
                "error_type": type(exception).__name__,
                "error_msg": error_msg,
                "debug_path": debug_path,
            },
            exc_info=exception,
        )

        # Record failure in circuit breaker (prevents retry loops)
        # Await to ensure it completes (prevents race conditions)
        try:
            await circuit_breaker.on_failure(exception)
        except Exception as e:
            logger.error(
                f"Failed to record failure in circuit breaker: {e}", exc_info=True
            )

    async def _cleanup_loop(self):
        """Periodically clean old results."""
        while self._running:
            try:
                await asyncio.sleep(WORKER_CLEANUP_INTERVAL)

                now = datetime.now()
                expired_jobs = []

                # Thread-safe cleanup
                async with results_lock:
                    for job_id, result in list(results.items()):
                        created_at_str = result.get("created_at")
                        if not created_at_str:
                            continue

                        try:
                            created_at = datetime.fromisoformat(created_at_str)
                            if (now - created_at).total_seconds() > WORKER_RESULT_TTL:
                                expired_jobs.append(job_id)
                        except Exception:
                            expired_jobs.append(job_id)

                    for job_id in expired_jobs:
                        results.pop(job_id, None)

                if expired_jobs:
                    logger.info(f"🧹 Cleaned up {len(expired_jobs)} old results")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"❌ Cleanup error: {e}")

    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """
        Get circuit breaker status for introspection.

        Returns:
            Dict with circuit breaker state and metrics
        """
        circuit_breaker = get_circuit_breaker()
        return circuit_breaker.get_status()


# Global worker instance
_worker: Optional[LinkGenerationWorker] = None


def get_worker() -> LinkGenerationWorker:
    """Get or create global worker instance."""
    global _worker
    if _worker is None:
        _worker = LinkGenerationWorker()
    return _worker
