# utils/scraper.py
"""
Main scraper module - combines HTTP utilities and data extraction.
Provides high-level scraping functions for the application.
"""
import logging

from .scraper.http_utils import (
    fetch_with_backoff,
    fetch_text,
    fetch_bytes,
    resolve_final_url,
    fetch_via_api
)
from .scraper.data_extraction import (
    scrape_product_data,
    _extract_price_from_text
)
from .scraper.yandex_market_scraper import scrape_yandex_market

logger = logging.getLogger(__name__)

# Re-export main functions for backward compatibility
__all__ = [
    'fetch_with_backoff',
    'fetch_text',
    'fetch_bytes',
    'resolve_final_url',
    'scrape_product_data',
    'scrape_yandex_market',
    'fetch_via_api',
    '_extract_price_from_text'
]