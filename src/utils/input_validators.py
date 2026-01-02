# utils/input_validators.py
"""
Input Validation - Validate all inputs before processing
Prevents injection attacks, invalid URLs, and resource exhaustion
"""
import re
import logging
from typing import Tuple, Optional
from urllib.parse import urlparse, urlunparse
from src.exceptions.link_generation_exceptions import ConfigurationError

logger = logging.getLogger(__name__)

# URL validation patterns
YANDEX_MARKET_DOMAINS = [
    "market.yandex.ru",
    "market.yandex.com",
    "yandex.ru",
    "yandex.com",
]

# Maximum lengths
MAX_URL_LENGTH = 2048
MAX_JOB_ID_LENGTH = 128
MAX_TIMEOUT = 300  # 5 minutes
MIN_TIMEOUT = 5  # 5 seconds
MAX_RETRIES = 10
MIN_RETRIES = 1

# Job ID pattern (alphanumeric, dashes, underscores)
JOB_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

# Path validation (prevent directory traversal)
PATH_TRAVERSAL_PATTERN = re.compile(r"\.\./|\.\.\\")


def validate_url(url: str) -> Tuple[bool, Optional[str]]:
    """
    Validate URL for Yandex Market link generation.

    Args:
        url: URL to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not url:
        return False, "URL is empty"

    if not isinstance(url, str):
        return False, f"URL must be a string, got {type(url).__name__}"

    if len(url) > MAX_URL_LENGTH:
        return False, f"URL too long (max {MAX_URL_LENGTH} characters)"

    # Check for null bytes or control characters
    if "\x00" in url or any(ord(c) < 32 and c not in "\t\n\r" for c in url):
        return False, "URL contains invalid characters"

    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL format: {e}"

    # Must have scheme
    if not parsed.scheme:
        return False, "URL must have a scheme (http:// or https://)"

    # Must be http or https
    if parsed.scheme not in ("http", "https"):
        return False, f"URL scheme must be http or https, got {parsed.scheme}"

    # Must have netloc
    if not parsed.netloc:
        return False, "URL must have a domain"

    # Check domain (must be Yandex Market)
    domain_lower = parsed.netloc.lower()
    if not any(domain in domain_lower for domain in YANDEX_MARKET_DOMAINS):
        return False, f"URL must be from Yandex Market domain, got {parsed.netloc}"

    # Reconstruct URL to normalize
    try:
        normalized = urlunparse(parsed)
        if normalized != url:
            logger.debug(f"URL normalized: {url} -> {normalized}")
    except Exception as e:
        return False, f"Failed to normalize URL: {e}"

    return True, None


def validate_job_id(job_id: str) -> Tuple[bool, Optional[str]]:
    """
    Validate job ID.

    Args:
        job_id: Job identifier to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not job_id:
        return False, "Job ID is empty"

    if not isinstance(job_id, str):
        return False, f"Job ID must be a string, got {type(job_id).__name__}"

    if len(job_id) > MAX_JOB_ID_LENGTH:
        return False, f"Job ID too long (max {MAX_JOB_ID_LENGTH} characters)"

    # Check pattern
    if not JOB_ID_PATTERN.match(job_id):
        return (
            False,
            "Job ID contains invalid characters (only alphanumeric, dash, underscore allowed)",
        )

    return True, None


def validate_timeout(timeout: int) -> Tuple[bool, Optional[str]]:
    """
    Validate timeout value.

    Args:
        timeout: Timeout in seconds

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(timeout, int):
        return False, f"Timeout must be an integer, got {type(timeout).__name__}"

    if timeout < MIN_TIMEOUT:
        return False, f"Timeout too short (min {MIN_TIMEOUT} seconds)"

    if timeout > MAX_TIMEOUT:
        return False, f"Timeout too long (max {MAX_TIMEOUT} seconds)"

    return True, None


def validate_retries(max_retries: int) -> Tuple[bool, Optional[str]]:
    """
    Validate retry count.

    Args:
        max_retries: Maximum retry attempts

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(max_retries, int):
        return (
            False,
            f"Max retries must be an integer, got {type(max_retries).__name__}",
        )

    if max_retries < MIN_RETRIES:
        return False, f"Max retries too low (min {MIN_RETRIES})"

    if max_retries > MAX_RETRIES:
        return False, f"Max retries too high (max {MAX_RETRIES})"

    return True, None


def validate_storage_state_path(path: Optional[str]) -> Tuple[bool, Optional[str]]:
    """
    Validate storage state file path.

    Args:
        path: Path to storage state file

    Returns:
        Tuple of (is_valid, error_message)
    """
    if path is None:
        return True, None  # Optional parameter

    if not isinstance(path, str):
        return False, f"Storage state path must be a string, got {type(path).__name__}"

    # Check for path traversal
    if PATH_TRAVERSAL_PATTERN.search(path):
        return False, "Storage state path contains directory traversal (../)"

    # Check length
    if len(path) > 512:
        return False, "Storage state path too long (max 512 characters)"

    return True, None


def validate_link_generation_inputs(
    url: str,
    job_id: Optional[str] = None,
    timeout: int = 30,
    max_retries: int = 3,
    reuse_state_path: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Validate all inputs for link generation.

    Args:
        url: Product URL
        job_id: Optional job identifier
        timeout: Timeout in seconds
        max_retries: Maximum retry attempts
        reuse_state_path: Optional storage state path

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Validate URL
    is_valid, error = validate_url(url)
    if not is_valid:
        return False, f"Invalid URL: {error}"

    # Validate job_id if provided
    if job_id:
        is_valid, error = validate_job_id(job_id)
        if not is_valid:
            return False, f"Invalid job_id: {error}"

    # Validate timeout
    is_valid, error = validate_timeout(timeout)
    if not is_valid:
        return False, f"Invalid timeout: {error}"

    # Validate retries
    is_valid, error = validate_retries(max_retries)
    if not is_valid:
        return False, f"Invalid max_retries: {error}"

    # Validate storage state path
    is_valid, error = validate_storage_state_path(reuse_state_path)
    if not is_valid:
        return False, f"Invalid storage_state_path: {error}"

    return True, None
