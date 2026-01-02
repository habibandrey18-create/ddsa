"""
Unified Product Key Generator - Single Source of Truth for Deduplication
=====================================================================

This module provides the ONLY implementation of product key generation.
All other implementations should be removed to prevent deduplication failures.

CRITICAL: Deduplication depends on deterministic key generation.
Different algorithms = same product gets different keys = duplicates in channel!

Author: Senior Backend Engineer
Date: 2026-01-01
"""

import hashlib
import re
import logging
from typing import Optional
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)


def normalize_url(url: str) -> str:
    """
    Normalize Yandex Market URL to canonical form.
    
    Rules (priority order):
    1. If offerid in query → return "offer:offerid"
    2. If market_id in path → return "id:marketid"
    3. If /card/slug → return "card:slug"
    4. Else → return clean path
    
    Args:
        url: Product URL from Yandex Market
    
    Returns:
        Normalized URL string
    
    Examples:
        >>> normalize_url("https://market.yandex.ru/product/123456?offerid=ABC")
        'offer:abc'
        >>> normalize_url("https://market.yandex.ru/product--slug/123456")
        'id:123456'
        >>> normalize_url("https://market.yandex.ru/card/some-product")
        'card:some-product'
    """
    if not url:
        return ""
    
    try:
        # Remove fragment and normalize
        clean = url.split("#")[0].rstrip("/").lower()
        parsed = urlparse(clean)
        
        # Priority 1: offerid parameter (most reliable)
        query = parse_qs(parsed.query)
        if 'offerid' in query and query['offerid']:
            offerid = query['offerid'][0].lower()
            return f"offer:{offerid}"
        
        # Priority 2: Extract market_id from path (6+ digits)
        # Matches: /product/123456, /product--slug/123456, etc.
        match = re.search(r'/(\d{6,})/?', parsed.path)
        if match:
            market_id = match.group(1)
            return f"id:{market_id}"
        
        # Priority 3: /card/ URLs
        match = re.search(r'/card/([^/?]+)', parsed.path)
        if match:
            card_slug = match.group(1)
            return f"card:{card_slug}"
        
        # Fallback: clean path
        clean_path = parsed.path.strip('/').lower()
        if clean_path:
            return f"path:{clean_path}"
        
        return clean
        
    except Exception as e:
        logger.warning(f"Error normalizing URL {url[:100]}: {e}")
        return url.lower()


def generate_product_key(
    *,
    title: str = "",
    vendor: str = "",
    offerid: str = "",
    url: str = "",
    market_id: str = ""
) -> str:
    """
    Generate deterministic product key for deduplication.
    
    This is the SINGLE SOURCE OF TRUTH for product key generation.
    DO NOT create alternative implementations!
    
    Priority (from most to least reliable):
    1. offerid (if available)
    2. market_id (if available)
    3. Normalized URL
    4. title + vendor hash
    
    Args:
        title: Product title
        vendor: Product vendor/brand
        offerid: Yandex offer ID (most reliable)
        url: Product URL
        market_id: Market product ID
    
    Returns:
        SHA-1 hash (40 hex characters) - deterministic across runs
    
    Examples:
        >>> generate_product_key(offerid="ABC123")
        'a1b2c3d4...'  # Always same hash for same offerid
        
        >>> generate_product_key(market_id="123456")
        'x9y8z7...'  # Always same hash for same market_id
        
        >>> generate_product_key(title="iPhone 14", vendor="Apple")
        'p0q9r8...'  # Same hash for same title+vendor
    """
    parts = []
    
    # Priority 1: offerid (most reliable identifier)
    if offerid:
        parts.append(f"offer:{offerid.lower().strip()}")
    
    # Priority 2: market_id (Yandex internal ID)
    if market_id:
        parts.append(f"id:{market_id.strip()}")
    
    # Priority 3: Normalized URL
    if url:
        normalized = normalize_url(url)
        if normalized:
            parts.append(normalized)
    
    # Priority 4: Title (normalized)
    if title:
        # Normalize title: lowercase, remove extra spaces, limit length
        clean_title = re.sub(r'\s+', ' ', title.strip().lower())
        # Truncate to 100 chars to avoid giant keys
        parts.append(f"title:{clean_title[:100]}")
    
    # Priority 5: Vendor (normalized)
    if vendor:
        clean_vendor = vendor.strip().lower()
        parts.append(f"vendor:{clean_vendor}")
    
    # Build base string
    base = "|".join(parts)
    
    # Fallback if all fields are empty
    if not base:
        logger.warning("generate_product_key called with all empty fields")
        base = "empty"
    
    # Generate SHA-1 hash (deterministic, collision-resistant)
    # SHA-1 chosen over MD5 (deprecated) and SHA-256 (overkill)
    key_hash = hashlib.sha1(base.encode("utf-8")).hexdigest()
    
    logger.debug(f"Generated product key: {key_hash} from: {base[:150]}")
    
    return key_hash


def generate_product_key_from_data(data: dict) -> str:
    """
    Generate product key from product data dictionary.
    
    Convenience wrapper around generate_product_key().
    
    Args:
        data: Product data dict with keys: title, vendor, offerid, url, market_id, id
    
    Returns:
        SHA-1 hash string
    """
    return generate_product_key(
        title=data.get("title", ""),
        vendor=data.get("vendor", ""),
        offerid=data.get("offerid", ""),
        url=data.get("url", ""),
        market_id=data.get("market_id") or data.get("id", "")
    )


# Backward compatibility exports
__all__ = [
    'generate_product_key',
    'generate_product_key_from_data',
    'normalize_url'
]

