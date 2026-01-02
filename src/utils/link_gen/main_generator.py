# utils/link_gen/main_generator.py
"""
Main Yandex Market Link Generator class.
Combines all mixins and implements the main generation logic.
"""
import asyncio
import logging
from typing import Optional, Dict, Any

from .browser_setup import BrowserSetupMixin
from .link_extraction import LinkExtractionMixin
from .storage_manager import StorageManagerMixin
from src.config.link_generation_config import (
    NETWORK_RESPONSE_TIMEOUT, NETWORK_API_PATTERNS
)

logger = logging.getLogger(__name__)


class YandexMarketLinkGen(BrowserSetupMixin, LinkExtractionMixin, StorageManagerMixin):
    """
    Production-ready async Yandex Market Link Generator.

    Strategy:
    1. Official Distribution method (if credentials available)
    2. Network-first: Intercept responses for shortUrl or /cc/
    3. XHR reproduction via httpx (if XHR captured)
    4. Fallback: Click "Share" button with retries
    """

    async def _try_distribution_method(self, url: str) -> Optional[str]:
        """
        Try official Yandex Distribution method.

        Returns:
            Partner link if successful, None otherwise
        """
        try:
            from src.utils.partner_link_builder import check_distribution_available, build_partner_link

            is_available, clid, vid = check_distribution_available()
            if is_available and clid and vid:
                logger.info("✅ Using official Yandex Distribution method")
                try:
                    partner_link = build_partner_link(url, clid, vid)
                    return partner_link
                except Exception as e:
                    logger.warning(f"⚠️ Distribution method failed: {e}, falling back to browser")
        except Exception as e:
            logger.debug(f"Distribution check failed: {e}")

        return None

    async def _save_network_dump(self, captured: Dict[str, Any], job_id: Optional[str] = None):
        """Save network dump to file for debugging."""
        try:
            if not job_id or not captured.get("network_dump"):
                return

            DEBUG_DIR = __import__('src.config.link_generation_config', fromlist=['DEBUG_DIR']).DEBUG_DIR
            DEBUG_DIR.mkdir(exist_ok=True, parents=True)

            dump_path = DEBUG_DIR / f"{job_id}_network_dump.json"
            with open(dump_path, "w", encoding="utf-8") as f:
                json.dump(captured["network_dump"], f, indent=2, ensure_ascii=False)

            logger.info(f"💾 Saved network dump: {dump_path}")
        except Exception as e:
            logger.warning(f"Failed to save network dump: {e}")

    def _setup_network_interception(self, page, captured: Dict[str, Any], job_id: Optional[str] = None):
        """
        Setup network request/response interception with structured dump.
        Network interception is enabled BEFORE Share button click.
        """
        # Initialize network dump storage
        if "network_dump" not in captured:
            captured["network_dump"] = []

        def on_request(request):
            """Capture XHR requests for reproduction."""
            try:
                url_str = request.url
                method = request.method

                if any(pattern in url_str for pattern in NETWORK_API_PATTERNS) and method in ("POST", "GET", "PUT"):
                    headers = request.headers
                    # Don't log sensitive headers
                    safe_headers = {k: v for k, v in headers.items()
                                  if k.lower() not in ('authorization', 'cookie', 'x-csrf-token')}

                    captured["network_dump"].append({
                        "type": "request",
                        "url": url_str,
                        "method": method,
                        "headers": safe_headers,
                        "timestamp": asyncio.get_event_loop().time()
                    })
            except Exception as e:
                logger.debug(f"Request capture error: {e}")

        async def on_response(response):
            """Capture responses with CC links."""
            try:
                url_str = response.url
                status = response.status

                # Check for successful responses from relevant endpoints
                if (status == 200 and
                    any(pattern in url_str for pattern in NETWORK_API_PATTERNS)):

                    try:
                        # Try to get response text with timeout
                        text = await asyncio.wait_for(
                            response.text(),
                            timeout=NETWORK_RESPONSE_TIMEOUT
                        )

                        # Check if response contains CC link
                        cc_link = self._extract_cc_link(text)
                        if cc_link:
                            captured["cc_link"] = cc_link
                            logger.info(f"🎯 Found CC link in network response: {cc_link}")
                            return

                        # Also check JSON responses recursively
                        try:
                            json_data = json.loads(text)
                            cc_link = self._search_cc_link_recursive(json_data)
                            if cc_link:
                                captured["cc_link"] = cc_link
                                logger.info(f"🎯 Found CC link in JSON response: {cc_link}")
                                return
                        except json.JSONDecodeError:
                            pass  # Not JSON, continue

                        # Store response for potential XHR reproduction
                        safe_headers = {k: v for k, v in response.headers.items()
                                      if k.lower() not in ('set-cookie', 'authorization')}

                        captured["network_dump"].append({
                            "type": "response",
                            "url": url_str,
                            "status": status,
                            "headers": dict(safe_headers),
                            "content": text[:5000],  # Limit content size
                            "timestamp": asyncio.get_event_loop().time()
                        })

                    except asyncio.TimeoutError:
                        logger.debug(f"Response read timeout for {url_str}")
                    except Exception as e:
                        logger.debug(f"Response processing error for {url_str}: {e}")

            except Exception as e:
                logger.debug(f"Response capture error: {e}")

        # Attach listeners
        page.on("request", on_request)
        page.on("response", on_response)

    async def generate(self, url: str, reuse_state_path: Optional[str] = None) -> Optional[str]:
        """
        Generate CC link from product URL.

        Args:
            url: Product URL to generate link for
            reuse_state_path: Optional path to browser state file for reuse

        Returns:
            CC link if successful, None otherwise
        """
        # Reset state
        self._link_found = False

        # Try distribution method first
        distribution_link = await self._try_distribution_method(url)
        if distribution_link:
            self._link_found = True
            return distribution_link

        # Fall back to browser-based method
        logger.info("🔄 Using browser-based link generation")

        # Implementation continues in next part...
        # This is a placeholder for the full implementation
        return None
