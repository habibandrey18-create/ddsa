# exceptions/link_generation_exceptions.py
"""
Link Generation Exceptions
Unified exception hierarchy for link generation errors
"""
from typing import Optional, Dict, Any


class LinkGenerationError(Exception):
    """Base exception for all link generation errors."""

    def __init__(
        self,
        message: str,
        xhr_info: Optional[Dict[str, Any]] = None,
        debug_path: Optional[str] = None,
        original_error: Optional[Exception] = None,
        job_id: Optional[str] = None,
        url: Optional[str] = None,
    ):
        """
        Initialize link generation error.

        Args:
            message: Human-readable error message
            xhr_info: Optional captured XHR request information
            debug_path: Optional path to debug artifacts
            original_error: Optional original exception that caused this error
            job_id: Optional job identifier for tracing
            url: Optional URL that caused the error
        """
        super().__init__(message)
        self.message = message
        self.xhr_info = xhr_info
        self.debug_path = debug_path
        self.original_error = original_error
        self.job_id = job_id
        self.url = url

    def __str__(self) -> str:
        """Return formatted error message with context."""
        msg = self.message

        if self.job_id:
            msg += f" [Job: {self.job_id}]"

        if self.url:
            # Truncate URL for safety
            url_display = self.url[:100] + "..." if len(self.url) > 100 else self.url
            msg += f" [URL: {url_display}]"

        if self.debug_path:
            msg += f" [Debug: {self.debug_path}]"

        if self.original_error:
            original_msg = str(self.original_error)
            if len(original_msg) > 200:
                original_msg = original_msg[:200] + "..."
            msg += f" [Original: {original_msg}]"

        return msg

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for logging/serialization."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "job_id": self.job_id,
            "url": self.url[:200] if self.url else None,  # Truncate for safety
            "debug_path": self.debug_path,
            "has_xhr_info": self.xhr_info is not None,
            "original_error": (
                str(self.original_error)[:200] if self.original_error else None
            ),
        }


class NetworkError(LinkGenerationError):
    """Network-related errors (timeouts, connection failures, HTTP errors)."""

    pass


class TimeoutError(NetworkError):
    """Timeout during link generation."""

    pass


class HTTPError(NetworkError):
    """HTTP error response (4xx, 5xx)."""

    def __init__(self, message: str, status_code: Optional[int] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.status_code = status_code


class CaptchaError(NetworkError):
    """Captcha detected or required."""

    pass


class ThrottlingError(NetworkError):
    """Rate limiting or throttling detected."""

    pass


class ParsingError(LinkGenerationError):
    """Error parsing response or extracting link."""

    pass


class ButtonNotFoundError(LinkGenerationError):
    """Share button not found on page."""

    pass


class ConfigurationError(LinkGenerationError):
    """Configuration or setup error."""

    pass


class RefLinkGenerationError(LinkGenerationError):
    """
    Legacy alias for LinkGenerationError.
    Kept for backward compatibility.
    """

    pass
