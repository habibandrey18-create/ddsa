# utils/link_gen/browser_setup.py
"""
Browser setup and configuration for Yandex Market Link Generator.
Handles initialization, stealth plugins, and browser configuration.
"""
import logging
from typing import Optional

from src.config.link_generation_config import (
    DEFAULT_HEADLESS, DEFAULT_TIMEOUT, DEFAULT_MAX_RETRIES, DEFAULT_DEBUG
)

logger = logging.getLogger(__name__)


class BrowserSetupMixin:
    """Mixin class for browser setup and configuration."""

    def __init__(
        self,
        headless: bool = DEFAULT_HEADLESS,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        debug: bool = DEFAULT_DEBUG
    ):
        """
        Initialize browser setup.

        Args:
            headless: Run browser in headless mode
            timeout: Timeout in seconds
            max_retries: Maximum retry attempts for button clicking
            debug: Enable debug artifacts
        """
        self.headless = headless
        self.timeout = timeout
        self.max_retries = max_retries
        self.debug = debug
        self._captcha_solver = None

        # Try to import stealth plugin
        self.stealth_available = False
        self._init_stealth()

        # Initialize CAPTCHA solver
        self._init_captcha_solver()

    def _init_stealth(self):
        """Initialize stealth plugin if available."""
        try:
            from playwright_stealth import stealth_async
            self.stealth_async = stealth_async
            self.stealth_available = True
            logger.info("✅ playwright-stealth available")
        except ImportError:
            try:
                from playwright_stealth.stealth import stealth_async
                self.stealth_async = stealth_async
                self.stealth_available = True
                logger.info("✅ playwright-stealth available (alternative import)")
            except ImportError:
                logger.warning("⚠️ playwright-stealth not installed. Install with: pip install playwright-stealth")

    def _init_captcha_solver(self):
        """Initialize CAPTCHA solver if available."""
        try:
            import sys
            sys.path.append('.')
            from utils.captcha_solver import CaptchaSolver
            self._captcha_solver = CaptchaSolver()
            logger.info("✅ CAPTCHA solver initialized")
        except Exception as e:
            logger.warning(f"⚠️ CAPTCHA solver not available: {e}")
            self._captcha_solver = None
