# services/link_generation_service.py
"""
Link Generation Service - asyncio.Queue + worker implementation
Non-blocking job submission with result polling
Anti-detection: stealth plugin, UA rotation, storage state persistence
"""
import asyncio
import uuid
import logging
import json
import random
from pathlib import Path
from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from services.circuit_breaker import get_circuit_breaker

logger = logging.getLogger(__name__)

# Debug directory
DEBUG_DIR = Path("debug")
DEBUG_DIR.mkdir(exist_ok=True)

# Storage state directory (for cookie/session persistence)
STORAGE_STATE_DIR = Path("storage_states")
STORAGE_STATE_DIR.mkdir(exist_ok=True)

# User-Agent rotation list (up-to-date real browser UAs)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
]

# In-memory result store (replace with Redis/DB for production)
results: Dict[str, Dict[str, Any]] = {}

# Queue for incoming jobs
job_queue: asyncio.Queue = asyncio.Queue()

# Configuration
MAX_WORKERS = 2  # Number of concurrent Playwright instances
JOB_TIMEOUT = 60  # Seconds
CLEANUP_INTERVAL = 3600  # Clean old results every hour
RESULT_TTL = 3600  # Keep results for 1 hour


class LinkGenerationService:
    """
    Service for generating Yandex Market partner links.
    Uses asyncio.Queue + ThreadPoolExecutor to run Playwright without blocking event loop.
    """

    def __init__(self, max_workers: int = MAX_WORKERS):
        self.max_workers = max_workers
        self.executor: Optional[ThreadPoolExecutor] = None
        self.worker_task: Optional[asyncio.Task] = None
        self.cleanup_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """Start the service (workers and cleanup)."""
        if self._running:
            logger.warning("Service already running")
            return

        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.worker_task = asyncio.create_task(self._worker_main())
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._running = True
        logger.info(f"✅ LinkGenerationService started with {self.max_workers} workers")

    async def stop(self):
        """Stop the service gracefully."""
        self._running = False

        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass

        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass

        if self.executor:
            self.executor.shutdown(wait=True)

        logger.info("✅ LinkGenerationService stopped")

    async def submit_job(
        self,
        url: str,
        cookies: Optional[list] = None,
        timeout: int = JOB_TIMEOUT,
        headless: bool = True,
        debug: bool = True,
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

        Returns:
            job_id: Unique job identifier
        """
        job_id = str(uuid.uuid4())

        job = {
            "id": job_id,
            "url": url,
            "cookies": cookies,
            "timeout": timeout,
            "headless": headless,
            "debug": debug,
            "reuse_storage_state": reuse_storage_state,
            "created_at": datetime.now().isoformat(),
        }

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

        Returns:
            Dict with status, result, error, or None if job not found
        """
        return results.get(job_id)

    async def _worker_main(self):
        """Main worker loop - consumes jobs from queue."""
        logger.info("🔄 Worker started")

        while self._running:
            try:
                # Get job with timeout to allow checking _running flag
                try:
                    job = await asyncio.wait_for(job_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                job_id = job["id"]
                url = job["url"]

                logger.info(f"🔄 Processing job: {job_id}")

                # Check circuit breaker before processing
                circuit_breaker = get_circuit_breaker()
                try:
                    await circuit_breaker.before_job()
                except RuntimeError as e:
                    # Circuit breaker is OPEN or HALF_OPEN (probe in progress)
                    user_message = circuit_breaker.get_user_message()
                    results[job_id]["status"] = "error"
                    results[job_id]["error"] = user_message
                    results[job_id]["completed_at"] = datetime.now().isoformat()
                    logger.warning(
                        f"⚠️ Job {job_id} rejected by circuit breaker: {user_message}"
                    )
                    job_queue.task_done()
                    continue

                results[job_id]["status"] = "running"
                results[job_id]["started_at"] = datetime.now().isoformat()

                try:
                    # STEP 2: Try XHR reproduction first (if XHR info was saved from previous run)
                    # This is a fast path - try direct HTTP request before full browser
                    xhr_reproduced = False
                    try:
                        from utils.xhr_reproducer import (
                            reproduce_xhr_directly,
                            extract_short_url_from_response,
                        )

                        # Check if we have saved XHR info from previous successful capture
                        xhr_path = DEBUG_DIR / f"last_xhr.json"
                        if xhr_path.exists():
                            with open(xhr_path, "r", encoding="utf-8") as f:
                                xhr_info = json.load(f)

                            # Convert cookies to dict
                            cookies_dict = None
                            if job.get("cookies"):
                                cookies_dict = {
                                    c.get("name", ""): c.get("value", "")
                                    for c in job.get("cookies")
                                    if c.get("name")
                                }

                            # Try to reproduce XHR
                            response_data = await reproduce_xhr_directly(
                                xhr_info, cookies_dict, timeout=10
                            )
                            if response_data:
                                link = extract_short_url_from_response(response_data)
                                if link:
                                    logger.info(
                                        f"✅ Link obtained via XHR reproduction: {link}"
                                    )
                                    results[job_id]["status"] = "done"
                                    results[job_id]["result"] = link
                                    results[job_id][
                                        "completed_at"
                                    ] = datetime.now().isoformat()

                                    # Cache product after successful CC generation
                                    await _cache_product_after_link_generation(
                                        url, link
                                    )

                                    xhr_reproduced = True
                    except Exception as e:
                        logger.debug(f"XHR reproduction attempt failed: {e}")

                    if not xhr_reproduced:
                        # Run blocking Playwright work off the event loop
                        link = await asyncio.wait_for(
                            asyncio.get_event_loop().run_in_executor(
                                self.executor,
                                _sync_run_playwright,
                                job_id,
                                url,
                                job.get("cookies"),
                                job.get("timeout", JOB_TIMEOUT),
                                job.get("headless", True),
                                job.get("debug", True),
                                job.get("reuse_storage_state"),
                            ),
                            timeout=job.get("timeout", JOB_TIMEOUT)
                            + 10,  # Extra 10s buffer
                        )

                    results[job_id]["status"] = "done"
                    results[job_id]["result"] = link
                    results[job_id]["completed_at"] = datetime.now().isoformat()
                    logger.info(f"✅ Job completed: {job_id} -> {link[:100]}")

                    # Cache product after successful CC generation
                    await _cache_product_after_link_generation(url, link)

                    # Record success in circuit breaker
                    await circuit_breaker.on_success()

                except asyncio.TimeoutError:
                    error_msg = f"Job timeout after {job.get('timeout', JOB_TIMEOUT)}s"
                    results[job_id]["status"] = "error"
                    results[job_id]["error"] = error_msg
                    results[job_id]["completed_at"] = datetime.now().isoformat()
                    logger.error(f"❌ Job timeout: {job_id}")

                    # Record failure in circuit breaker
                    timeout_exc = TimeoutError(error_msg)
                    await circuit_breaker.on_failure(timeout_exc)

                except Exception as e:
                    error_msg = str(e)
                    results[job_id]["status"] = "error"
                    results[job_id]["error"] = error_msg
                    results[job_id]["completed_at"] = datetime.now().isoformat()
                    logger.exception(f"❌ Job failed: {job_id} - {error_msg}")

                    # Record failure in circuit breaker
                    await circuit_breaker.on_failure(e)

                finally:
                    job_queue.task_done()

            except asyncio.CancelledError:
                logger.info("🔄 Worker cancelled")
                break
            except Exception as e:
                logger.exception(f"❌ Worker error: {e}")
                await asyncio.sleep(1.0)  # Prevent tight loop on errors

    async def _cleanup_loop(self):
        """Periodically clean old results."""
        while self._running:
            try:
                await asyncio.sleep(CLEANUP_INTERVAL)

                now = datetime.now()
                expired_jobs = []

                for job_id, result in list(results.items()):
                    created_at_str = result.get("created_at")
                    if not created_at_str:
                        continue

                    try:
                        created_at = datetime.fromisoformat(created_at_str)
                        if (now - created_at).total_seconds() > RESULT_TTL:
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


async def _cache_product_after_link_generation(url: str, cc_link: str) -> None:
    """
    Cache product data after successful CC generation.
    Scrapes product data and caches it if validation passes.

    Args:
        url: Product URL
        cc_link: Generated CC link
    """
    try:
        from models.cached_product import CachedProduct
        from database import Database
        from utils.scraper import scrape_yandex_market

        # Scrape product data
        scraper_data = await scrape_yandex_market(url)

        # Create CachedProduct from scraper data
        cached_product = CachedProduct.from_scraper_data(
            url=url, scraper_data=scraper_data, cc_link=cc_link
        )

        if cached_product:
            # Cache in database
            db = Database()
            success = db.cache_product(cached_product)
            if success:
                logger.info(
                    f"✅ Cached product: {cached_product.product_id} - {cached_product.title[:50]}"
                )
            else:
                logger.debug(f"Failed to cache product: {cached_product.product_id}")
        else:
            logger.debug(f"Product validation failed, skipping cache for: {url}")
    except Exception as e:
        logger.warning(f"Failed to cache product after link generation: {e}")


async def _async_run_link_generation(
    job_id: str,
    url: str,
    cookies: Optional[list] = None,
    timeout: int = JOB_TIMEOUT,
    headless: bool = True,
    debug: bool = True,
    reuse_storage_state: Optional[str] = None,
) -> str:
    """
    Async wrapper for YandexMarketLinkGen.generate().
    This runs in the event loop (non-blocking).
    """
    from utils.yandex_market_link_gen import YandexMarketLinkGen, RefLinkGenerationError

    generator = YandexMarketLinkGen(
        headless=headless, timeout=timeout, max_retries=3, debug=debug
    )

    try:
        link = await generator.generate(
            url=url, job_id=job_id, reuse_state_path=reuse_storage_state
        )
        return link
    except RefLinkGenerationError as e:
        # Re-raise with same exception type
        raise
    except Exception as e:
        # Wrap other exceptions
        raise RefLinkGenerationError(
            f"Link generation failed: {e}", debug_path=str(DEBUG_DIR / job_id)
        ) from e


def _sync_run_playwright(
    job_id: str,
    url: str,
    cookies: Optional[list] = None,
    timeout: int = JOB_TIMEOUT,
    headless: bool = True,
    debug: bool = True,
    reuse_storage_state: Optional[str] = None,
) -> str:
    """
    DEPRECATED: Use _async_run_link_generation instead.
    Kept for backward compatibility.
    """
    """
    Blocking function - runs Playwright sync API.
    Implements YandexMarketLinkGen behavior:
    - Network interception listening for JSON with shortUrl or redirects containing /cc/
    - Fallback to clicking "Share" with retries
    - On error saves debug/<job_id>.png and debug/<job_id>.html
    
    Args:
        job_id: Job identifier for debug artifacts
        url: Product URL
        cookies: Optional cookies
        timeout: Timeout in seconds
        headless: Run in headless mode
        debug: Enable debug artifacts
        
    Returns:
        Clean partner link (https://market.yandex.ru/cc/XXXXX)
        
    Raises:
        Exception: If link cannot be generated
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    page = None
    browser = None

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=headless and not debug,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--lang=ru-RU,ru",
                ],
            )

            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                locale="ru-RU",
            )

            page = context.new_page()

            # Anti-bot measures
            page.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """
            )

            # Add cookies if provided
            if cookies:
                try:
                    context.add_cookies(cookies)
                except Exception as e:
                    logger.warning(f"Failed to add cookies: {e}")

            # Check if URL already contains /cc/
            import re

            cc_match = re.search(r"/cc/([A-Za-z0-9_-]+)", url)
            if cc_match:
                cc_code = cc_match.group(1)
                return f"https://market.yandex.ru/cc/{cc_code}"

            # Network interception - captured link and XHR info
            captured = {
                "link": None,
                "response_data": None,
                "xhr_info": None,  # For XHR reproduction
            }

            def on_request(request):
                """Capture XHR requests for reproduction."""
                try:
                    url_str = request.url
                    method = request.method

                    # Capture promising XHR requests (API endpoints)
                    if (
                        "market.yandex.ru/api/" in url_str
                        or "platform-api.yandex.ru" in url_str
                        or "/share" in url_str
                    ) and method in ("POST", "GET", "PUT"):
                        # Capture request info for reproduction
                        headers = request.headers
                        post_data = request.post_data

                        captured["xhr_info"] = {
                            "method": method,
                            "url": url_str,
                            "headers": dict(headers),
                            "body": post_data,
                        }
                        logger.info(f"📡 Captured XHR: {method} {url_str[:100]}...")
                except Exception as e:
                    logger.debug(f"Request capture error: {e}")

            def on_response(resp):
                """Handle network responses - PRIMARY METHOD."""
                try:
                    url_str = resp.url

                    # Check if response URL contains /cc/
                    if "/cc/" in url_str:
                        cc_match = re.search(
                            r"https?://market\.yandex\.ru/cc/[A-Za-z0-9_-]+", url_str
                        )
                        if cc_match:
                            captured["link"] = cc_match.group(0).split("?")[0]
                            logger.info(
                                f"🌐 Found /cc/ link in response URL: {captured['link']}"
                            )
                            return

                    # Check API responses
                    if (
                        "market.yandex.ru/api/" in url_str
                        or "platform-api.yandex.ru" in url_str
                        or "/share" in url_str
                    ) and resp.status == 200:
                        try:
                            content_type = resp.headers.get("content-type", "")
                            if "application/json" in content_type:
                                data = resp.json()
                                captured["response_data"] = data

                                # Look for shortUrl
                                if isinstance(data, dict):
                                    short_url = (
                                        data.get("shortUrl")
                                        or data.get("short_url")
                                        or data.get("url")
                                        or data.get("link")
                                        or data.get("data", {}).get("shortUrl")
                                        or data.get("result", {}).get("shortUrl")
                                    )

                                    if short_url:
                                        cc_match = re.search(
                                            r"https?://market\.yandex\.ru/cc/[A-Za-z0-9_-]+",
                                            short_url,
                                        )
                                        if cc_match:
                                            captured["link"] = cc_match.group(0).split(
                                                "?"
                                            )[0]
                                            logger.info(
                                                f"🌐 Found shortUrl in JSON: {captured['link']}"
                                            )
                                            return

                                    # Search recursively
                                    def search_dict(d, depth=0):
                                        if depth > 10:
                                            return
                                        if isinstance(d, dict):
                                            for v in d.values():
                                                if isinstance(v, str):
                                                    cc_match = re.search(
                                                        r"https?://market\.yandex\.ru/cc/[A-Za-z0-9_-]+",
                                                        v,
                                                    )
                                                    if cc_match:
                                                        captured["link"] = (
                                                            cc_match.group(0).split(
                                                                "?"
                                                            )[0]
                                                        )
                                                        return
                                                elif isinstance(v, (dict, list)):
                                                    search_dict(v, depth + 1)
                                        elif isinstance(d, list):
                                            for item in d:
                                                search_dict(item, depth + 1)

                                    search_dict(data)
                        except Exception:
                            pass

                    # Check redirects
                    if 300 <= resp.status < 400:
                        location = resp.headers.get("location", "")
                        if location and "/cc/" in location:
                            cc_match = re.search(
                                r"https?://market\.yandex\.ru/cc/[A-Za-z0-9_-]+",
                                location,
                            )
                            if cc_match:
                                captured["link"] = cc_match.group(0).split("?")[0]
                                logger.info(
                                    f"🌐 Found /cc/ link in redirect: {captured['link']}"
                                )

                except Exception as e:
                    logger.debug(f"Response handler error: {e}")

            page.on("request", on_request)
            page.on("request", on_request)
            page.on("response", on_response)

            # Navigate to page
            logger.info(f"📄 Navigating to: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            page.wait_for_timeout(1000)  # Wait for initial load

            # Check if we already got the link
            if captured["link"]:
                return captured["link"]

            # FALLBACK: Try clicking Share button
            logger.info(
                "🔄 Network interception didn't find link, trying button click..."
            )

            share_selectors = [
                'button:has-text("Поделиться")',
                'button[aria-label*="Поделиться"]',
                'button[aria-label="Поделиться"]',
                '[data-testid*="share"]',
            ]

            share_button = None
            for selector in share_selectors:
                try:
                    share_button = page.query_selector(selector)
                    if share_button:
                        logger.info(f"✅ Found share button: {selector}")
                        break
                except Exception:
                    continue

            if not share_button:
                raise RuntimeError("Share button not found")

            # Try clicking with retries (human-like interaction)
            for attempt in range(3):
                if captured["link"]:
                    break

                try:
                    # Human-like interaction: hover first, then click
                    share_button.scroll_into_view_if_needed()
                    page.wait_for_timeout(random.randint(200, 500))  # Random delay

                    # Try hover before click (more human-like)
                    try:
                        share_button.hover()
                        page.wait_for_timeout(random.randint(100, 300))
                    except Exception:
                        pass

                    share_button.click(timeout=5000)
                    page.wait_for_timeout(
                        random.randint(1500, 2500)
                    )  # Wait for API response
                except Exception as e:
                    logger.warning(f"Click attempt {attempt + 1} failed: {e}")
                    # Try alternative: mouse movement + click
                    try:
                        box = share_button.bounding_box()
                        if box:
                            page.mouse.move(
                                box["x"] + box["width"] / 2,
                                box["y"] + box["height"] / 2,
                            )
                            page.wait_for_timeout(random.randint(100, 200))
                            page.mouse.click(
                                box["x"] + box["width"] / 2,
                                box["y"] + box["height"] / 2,
                            )
                            page.wait_for_timeout(random.randint(1500, 2500))
                    except Exception:
                        pass

                # Check if link was captured
                if captured["link"]:
                    return captured["link"]

            # Final check
            if captured["link"]:
                # Save storage state for future reuse (successful session)
                try:
                    storage_state_path = STORAGE_STATE_DIR / f"{job_id}_success.json"
                    context.storage_state(path=str(storage_state_path))
                    logger.info(f"💾 Saved storage state: {storage_state_path}")
                except Exception as e:
                    logger.warning(f"Failed to save storage state: {e}")

                # Save XHR info for future reproduction (fast path)
                if captured.get("xhr_info"):
                    try:
                        xhr_save_path = DEBUG_DIR / "last_xhr.json"
                        with open(xhr_save_path, "w", encoding="utf-8") as f:
                            json.dump(
                                captured["xhr_info"], f, indent=2, ensure_ascii=False
                            )
                        logger.info(
                            f"💾 Saved XHR info for future reproduction: {xhr_save_path}"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to save XHR info: {e}")

                return captured["link"]

            raise RuntimeError("No link captured after all attempts")

    except Exception as exc:
        # Save debug artifacts on error
        if debug and page:
            try:
                html_path = DEBUG_DIR / f"{job_id}.html"
                png_path = DEBUG_DIR / f"{job_id}.png"

                try:
                    page_content = page.content()
                    html_path.write_text(page_content, encoding="utf-8")
                    logger.info(f"💾 Saved HTML: {html_path}")
                except Exception as e:
                    logger.warning(f"Failed to save HTML: {e}")

                try:
                    page.screenshot(path=str(png_path), full_page=True)
                    logger.info(f"💾 Saved screenshot: {png_path}")
                except Exception as e:
                    logger.warning(f"Failed to save screenshot: {e}")

                # Save network response data if available
                if captured.get("response_data"):
                    try:
                        network_path = DEBUG_DIR / f"{job_id}_network.json"
                        with open(network_path, "w", encoding="utf-8") as f:
                            json.dump(
                                captured["response_data"],
                                f,
                                indent=2,
                                ensure_ascii=False,
                            )
                        logger.info(f"💾 Saved network data: {network_path}")
                    except Exception:
                        pass

            except Exception as e:
                logger.warning(f"Failed to save debug artifacts: {e}")

        raise
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass


# Global service instance
_service: Optional[LinkGenerationService] = None


def get_link_generation_service() -> LinkGenerationService:
    """Get or create global service instance."""
    global _service
    if _service is None:
        _service = LinkGenerationService()
    return _service
