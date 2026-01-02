# services/circuit_breaker.py
"""
Circuit Breaker for Link Generation Service
Protects against repeated failures (404s, captcha, throttling)
"""
import asyncio
import time
import logging
from enum import Enum
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

from config.link_generation_config import (
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CIRCUIT_BREAKER_OPEN_DURATION,
)

# Circuit Breaker config (from config module)
FAILURE_THRESHOLD = CIRCUIT_BREAKER_FAILURE_THRESHOLD
OPEN_DURATION = CIRCUIT_BREAKER_OPEN_DURATION
PROBE_TIMEOUT = 30  # Timeout for probe job


class CBState(Enum):
    """Circuit Breaker states"""

    CLOSED = "CLOSED"  # Normal operation
    OPEN = "OPEN"  # Rejecting all requests
    HALF_OPEN = "HALF_OPEN"  # Allowing one probe request


class CircuitBreaker:
    """
    Circuit Breaker pattern implementation.

    States:
    - CLOSED: Normal operation, allowing all requests
    - OPEN: Rejecting all requests after threshold failures
    - HALF_OPEN: Allowing one probe request to test recovery
    """

    def __init__(
        self,
        failure_threshold: int = FAILURE_THRESHOLD,
        open_duration: int = OPEN_DURATION,
        name: str = "link_generation",
    ):
        """
        Initialize Circuit Breaker.

        Args:
            failure_threshold: Number of consecutive failures before opening
            open_duration: Duration in seconds to stay OPEN before HALF_OPEN
            name: Name identifier for this breaker (for logging)
        """
        self.failure_threshold = failure_threshold
        self.open_duration = open_duration
        self.name = name

        # State
        self._state = CBState.CLOSED
        self._consecutive_failures = 0
        self._opened_at: Optional[float] = None
        self._lock = asyncio.Lock()
        self._alert_sent = False  # Ensure admin alerted only once per trip
        self._probe_allowed = False  # Flag for HALF_OPEN probe

    def _is_failure_type(self, exc: Exception) -> bool:
        """
        Determine if exception should count as a failure for circuit breaker.

        Only network errors, captcha, throttling, and 4xx/5xx should trip the breaker.
        Parser errors, validation errors, etc. should not.

        Args:
            exc: Exception to check

        Returns:
            True if this exception should count as a failure
        """
        error_str = str(exc).lower()
        error_type = type(exc).__name__

        # Network-related failures
        network_keywords = [
            "404",
            "403",
            "429",
            "500",
            "502",
            "503",
            "504",
            "timeout",
            "connection",
            "network",
            "http",
            "captcha",
            "капча",
            "throttl",
            "rate limit",
            "blocked",
            "banned",
            "forbidden",
            "unauthorized",
        ]

        if any(keyword in error_str for keyword in network_keywords):
            return True

        # Exception types that indicate external service issues
        network_exception_types = [
            "TimeoutError",
            "ConnectionError",
            "HTTPError",
            "HTTPStatusError",
            "PlaywrightTimeout",
        ]

        if any(etype in error_type for etype in network_exception_types):
            return True

        # Parser/validation errors should NOT trip the breaker
        ignore_keywords = [
            "parse",
            "validation",
            "invalid url",
            "syntax",
            "attribute",
            "keyerror",
            "indexerror",
        ]

        if any(keyword in error_str for keyword in ignore_keywords):
            return False

        # Default: count as failure if it's a runtime/execution error
        return True

    async def before_job(self) -> bool:
        """
        Call before enqueueing / starting a job.

        Returns:
            True if job can proceed, False if rejected

        Raises:
            RuntimeError: If circuit is OPEN and duration hasn't expired
        """
        async with self._lock:
            now = time.time()

            if self._state == CBState.OPEN:
                # Check if open duration expired, move to HALF_OPEN
                if self._opened_at and (now - self._opened_at) >= self.open_duration:
                    self._state = CBState.HALF_OPEN
                    self._consecutive_failures = 0
                    self._alert_sent = False
                    self._probe_allowed = True
                    logger.info(
                        f"🔓 Circuit breaker {self.name} moved to HALF_OPEN (probe allowed)"
                    )
                    return True

                # Still OPEN, reject immediately
                raise RuntimeError("CircuitBreakerOpen")

            elif self._state == CBState.HALF_OPEN:
                # Only allow one probe job
                if self._probe_allowed:
                    self._probe_allowed = False
                    logger.info(f"🔍 Circuit breaker {self.name} allowing probe job")
                    return True
                else:
                    # Another job tried while probe is in progress
                    raise RuntimeError("CircuitBreakerHalfOpen")

            # CLOSED: allow job to proceed
            return True

    async def on_success(self):
        """Call when a job succeeds. Resets breaker to CLOSED."""
        async with self._lock:
            self._consecutive_failures = 0
            self._state = CBState.CLOSED
            self._opened_at = None
            self._alert_sent = False
            self._probe_allowed = False
            logger.info(f"✅ Circuit breaker {self.name} reset to CLOSED (success)")

    async def on_failure(self, exc: Optional[Exception] = None):
        """
        Call when a job fails.
        Prevents unsafe retry loops by tracking consecutive failures.

        Args:
            exc: Optional exception to check if it should count as failure
        """
        async with self._lock:
            # Check if this failure type should count
            if exc and not self._is_failure_type(exc):
                logger.debug(
                    f"⚠️ Failure ignored by circuit breaker (not network-related): {exc}"
                )
                return

            # Prevent retry loops: if already at threshold, don't increment further
            if (
                self._consecutive_failures >= self.failure_threshold
                and self._state == CBState.CLOSED
            ):
                # Already at threshold, trip immediately
                self._trip()
                return

            self._consecutive_failures += 1
            logger.warning(
                f"⚠️ Circuit breaker {self.name}: failure {self._consecutive_failures}/{self.failure_threshold} "
                f"(state: {self._state.value})"
            )

            # If we were half-open and a failure occurs, go back to OPEN immediately
            # This prevents retry loops in HALF_OPEN state
            if self._state == CBState.HALF_OPEN:
                logger.error(
                    f"❌ Circuit breaker {self.name}: probe failed, moving back to OPEN "
                    f"(prevents retry loop)"
                )
                self._trip()
                return

            # Check if threshold reached (only in CLOSED state)
            if (
                self._state == CBState.CLOSED
                and self._consecutive_failures >= self.failure_threshold
            ):
                logger.error(
                    f"🚨 Circuit breaker {self.name}: threshold reached "
                    f"({self._consecutive_failures}/{self.failure_threshold}), tripping to OPEN"
                )
                self._trip()
                return

            # Safety check: if failures exceed threshold significantly, force OPEN
            if self._consecutive_failures > self.failure_threshold * 2:
                logger.critical(
                    f"🚨 Circuit breaker {self.name}: excessive failures "
                    f"({self._consecutive_failures}), forcing OPEN to prevent retry loop"
                )
                self._trip()

    def _trip(self):
        """Trip the circuit breaker to OPEN state."""
        self._state = CBState.OPEN
        self._opened_at = time.time()
        self._probe_allowed = False

        logger.error(
            f"🚨 Circuit breaker {self.name} TRIPPED to OPEN "
            f"(failures: {self._consecutive_failures}, duration: {self.open_duration}s)"
        )

        # Admin alert should be triggered once (outside lock or via async task)
        if not self._alert_sent:
            self._alert_sent = True
            try:
                # Fire-and-forget alert
                asyncio.create_task(
                    send_admin_alert(
                        f"🚨 Circuit breaker '{self.name}' TRIPPED at {time.ctime(self._opened_at)}\n"
                        f"Consecutive failures: {self._consecutive_failures}\n"
                        f"Will retry after {self.open_duration}s"
                    )
                )
            except Exception as e:
                logger.error(f"Failed to send admin alert: {e}")

    def get_status(self) -> Dict[str, Any]:
        """
        Get current circuit breaker status for introspection.

        Returns:
            Dict with state, failures, timing info
        """
        now = time.time()
        time_until_retry = 0

        if self._opened_at:
            elapsed = now - self._opened_at
            time_until_retry = max(0, self.open_duration - elapsed)

        return {
            "name": self.name,
            "state": self._state.value,
            "consecutive_failures": self._consecutive_failures,
            "failure_threshold": self.failure_threshold,
            "opened_at": self._opened_at,
            "time_until_retry": int(time_until_retry),
            "open_duration": self.open_duration,
            "is_available": self._state == CBState.CLOSED
            or (self._state == CBState.HALF_OPEN and self._probe_allowed),
        }

    def get_user_message(self) -> str:
        """
        Get user-friendly message based on current state.

        Returns:
            User-friendly error message
        """
        if self._state == CBState.OPEN:
            time_until = int(self.get_status()["time_until_retry"])
            if time_until > 0:
                minutes = time_until // 60
                return f"Сервис временно перегружен. Повторите попытку через {minutes} мин."
            else:
                return "Сервис временно перегружен. Повторите попытку позже."
        elif self._state == CBState.HALF_OPEN:
            return "Сервис проверяется. Повторите попытку через несколько секунд."
        else:
            return "Сервис доступен."


# Global circuit breaker instance
_circuit_breaker: Optional[CircuitBreaker] = None


def get_circuit_breaker() -> CircuitBreaker:
    """Get or create global circuit breaker instance."""
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = CircuitBreaker()
    return _circuit_breaker


async def send_admin_alert(message: str):
    """
    Send alert to administrator(s).

    Replace this with your actual notification mechanism:
    - Telegram bot message to admin
    - Email
    - Webhook
    - etc.
    """
    try:
        # Try to import bot and send to admin
        import config
        from bot import bot

        if config.ADMIN_ID:
            try:
                await bot.send_message(
                    config.ADMIN_ID,
                    f"🚨 **Circuit Breaker Alert**\n\n{message}",
                    parse_mode="Markdown",
                )
                logger.info(f"✅ Admin alert sent to {config.ADMIN_ID}")
            except Exception as e:
                logger.warning(f"Failed to send Telegram alert: {e}")
                # Fallback to console
                print(f"[ADMIN ALERT] {message}")
        else:
            # No admin ID configured, just log
            logger.warning(f"[ADMIN ALERT] {message}")
            print(f"[ADMIN ALERT] {message}")
    except Exception as e:
        # Fallback if bot not available
        logger.error(f"Failed to send admin alert: {e}")
        print(f"[ADMIN ALERT] {message}")
