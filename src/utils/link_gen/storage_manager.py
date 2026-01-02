# utils/link_gen/storage_manager.py
"""
Storage and state management for Yandex Market Link Generator.
Handles browser storage states, cookies, and debug artifacts.
"""
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urlparse

from src.config.link_generation_config import (
    DEBUG_DIR, STORAGE_STATE_DIR, STORAGE_STATE_HASH_MOD
)

logger = logging.getLogger(__name__)


class StorageManagerMixin:
    """Mixin class for storage and state management."""

    def _get_storage_state_path(self, url: str) -> Optional[Path]:
        """
        Get storage state path for reuse based on URL domain.
        Returns path if exists, None otherwise.
        """
        try:
            # Убеждаемся, что директория существует
            STORAGE_STATE_DIR.mkdir(exist_ok=True, parents=True)
            domain = urlparse(url).netloc
            fingerprint = hash(domain) % STORAGE_STATE_HASH_MOD
            state_path = STORAGE_STATE_DIR / f"{fingerprint}.json"
            if state_path.exists():
                return state_path
        except Exception:
            pass
        return None

    def _get_storage_state_path_for_reuse(self, url: str, reuse_state_path: Optional[str] = None) -> Optional[str]:
        """
        Get storage state path for reuse.

        Returns:
            Path to storage state file or None
        """
        # Убеждаемся, что директория существует
        STORAGE_STATE_DIR.mkdir(exist_ok=True, parents=True)

        if reuse_state_path and reuse_state_path.strip():
            state_file = Path(reuse_state_path)
            if state_file.exists():
                return str(state_file)

        existing_state = self._get_storage_state_path(url)
        if existing_state:
            return str(existing_state)

        return None

    async def _save_debug_artifacts(
        self,
        page,
        job_id: str,
        error_msg: str = "",
        xhr_info: Optional[Dict] = None
    ):
        """
        Save debug artifacts on failure.
        Always attempts to save, even if page is partially initialized.
        """
        if not self.debug:
            return

        saved_artifacts = []

        try:
            # Убеждаемся, что директория существует
            DEBUG_DIR.mkdir(exist_ok=True, parents=True)

            # HTML - try to save even if page is not fully loaded
            html_path = DEBUG_DIR / f"{job_id}.html"
            try:
                if page:
                    html_content = await asyncio.wait_for(
                        page.content(),
                        timeout=5.0
                    )
                    html_path.write_text(html_content, encoding="utf-8")
                    saved_artifacts.append("HTML")
                    logger.info(f"💾 Saved HTML: {html_path}")
            except asyncio.TimeoutError:
                logger.warning(f"⚠️ HTML save timeout for {job_id}")
            except Exception as e:
                logger.warning(f"Failed to save HTML: {e}")

            # Screenshot - try to save even if page is not fully loaded
            screenshot_path = DEBUG_DIR / f"{job_id}.png"
            try:
                if page:
                    await asyncio.wait_for(
                        page.screenshot(path=str(screenshot_path), full_page=True),
                        timeout=5.0
                    )
                    saved_artifacts.append("screenshot")
                    logger.info(f"💾 Saved screenshot: {screenshot_path}")
            except asyncio.TimeoutError:
                logger.warning(f"⚠️ Screenshot save timeout for {job_id}")
            except Exception as e:
                logger.warning(f"Failed to save screenshot: {e}")

            # XHR info - always try to save if available
            if xhr_info:
                xhr_path = DEBUG_DIR / f"{job_id}_xhr.json"
                try:
                    with open(xhr_path, "w", encoding="utf-8") as f:
                        json.dump(xhr_info, f, indent=2, ensure_ascii=False)
                    saved_artifacts.append("XHR")
                    logger.info(f"💾 Saved XHR info: {xhr_path}")
                except Exception as e:
                    logger.warning(f"Failed to save XHR info: {e}")

            # Save error log
            error_log_path = DEBUG_DIR / f"{job_id}_error.txt"
            try:
                error_log_path.write_text(
                    f"Error: {error_msg}\n"
                    f"Job ID: {job_id}\n"
                    f"Timestamp: {time.time()}\n"
                    f"Artifacts saved: {', '.join(saved_artifacts) if saved_artifacts else 'none'}\n",
                    encoding="utf-8"
                )
            except Exception as e:
                logger.warning(f"Failed to save error log: {e}")

        except Exception as e:
            logger.error(f"Failed to save debug artifacts: {e}", exc_info=True)

    async def _get_cookies_from_context(self, context) -> Dict[str, str]:
        """Extract cookies from browser context."""
        try:
            cookies = await context.cookies()
            return {cookie['name']: cookie['value'] for cookie in cookies}
        except Exception as e:
            logger.warning(f"Failed to extract cookies: {e}")
            return {}

    async def _save_storage_state(self, context, url: str, only_if_success: bool = False):
        """Save browser storage state for future reuse."""
        try:
            if only_if_success and not hasattr(self, '_link_found') or not self._link_found:
                return

            # Убеждаемся, что директория существует
            STORAGE_STATE_DIR.mkdir(exist_ok=True, parents=True)

            domain = urlparse(url).netloc
            fingerprint = hash(domain) % STORAGE_STATE_HASH_MOD
            state_path = STORAGE_STATE_DIR / f"{fingerprint}.json"

            storage_state = await context.storage_state()
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(storage_state, f, indent=2, ensure_ascii=False)

            logger.info(f"💾 Saved storage state: {state_path}")

        except Exception as e:
            logger.warning(f"Failed to save storage state: {e}")
