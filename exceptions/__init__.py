# exceptions/__init__.py
"""Exception classes for Yandex Market Bot"""

from exceptions.link_generation_exceptions import (
    LinkGenerationError,
    NetworkError,
    TimeoutError,
    HTTPError,
    CaptchaError,
    ThrottlingError,
    ParsingError,
    ButtonNotFoundError,
    ConfigurationError,
    RefLinkGenerationError,  # Backward compatibility
)

__all__ = [
    "LinkGenerationError",
    "NetworkError",
    "TimeoutError",
    "HTTPError",
    "CaptchaError",
    "ThrottlingError",
    "ParsingError",
    "ButtonNotFoundError",
    "ConfigurationError",
    "RefLinkGenerationError",
]
