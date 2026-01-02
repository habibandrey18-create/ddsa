# utils/xhr_reproducer.py
"""
XHR Reproducer - Direct HTTP reproduction of captured XHR requests
PRIMARY METHOD: Pure HTTP client with httpx, no browser rendering needed
Network-first approach: capture XHR in Playwright, reproduce via httpx
"""
import logging
import json
import random
from typing import Dict, Optional, Any, List
from urllib.parse import urlparse
import httpx

from src.config.link_generation_config import (
    USER_AGENTS, XHR_REPRODUCTION_TIMEOUT, XHR_HEADERS_TO_REMOVE
)

logger = logging.getLogger(__name__)

# Global httpx client pool for connection reuse
_http_client: Optional[httpx.AsyncClient] = None


def get_http_client() -> httpx.AsyncClient:
    """Get or create global httpx client for connection pooling."""
    global _http_client
    if _http_client is None:
        # Try to enable HTTP/2 if h2 package is available
        try:
            import h2
            http2_enabled = True
        except ImportError:
            http2_enabled = False
            logger.debug("HTTP/2 not available (h2 package not installed), using HTTP/1.1")
        
        _http_client = httpx.AsyncClient(
            timeout=XHR_REPRODUCTION_TIMEOUT,
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            http2=http2_enabled  # Enable HTTP/2 if available
        )
    return _http_client


async def close_http_client():
    """Close global httpx client (call on shutdown)."""
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None


def prepare_headers(
    xhr_info: Dict[str, Any],
    product_url: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Dict[str, str]:
    """
    Prepare headers for XHR reproduction with anti-detection measures.
    Copies all relevant headers including cookies, referrer, and user-agent.
    
    Args:
        xhr_info: Captured XHR information
        product_url: Original product URL (for Referer header)
        user_agent: User-Agent string (if not in xhr_info)
        
    Returns:
        Prepared headers dict
    """
    # Start with captured headers
    headers = dict(xhr_info.get("headers", {}))
    
    # CRITICAL: Preserve all anti-detection headers
    # Keep Origin, Referer, User-Agent, Accept-Language, etc.
    
    # Set User-Agent (use provided, or from xhr_info, or random from pool)
    if user_agent:
        headers["User-Agent"] = user_agent
    elif "User-Agent" not in headers:
        headers["User-Agent"] = random.choice(USER_AGENTS)
    
    # Set Referer if product_url provided and not already set
    if product_url and "Referer" not in headers:
        headers["Referer"] = product_url
    
    # Set Origin if not present (derive from Referer or URL)
    if "Origin" not in headers:
        if "Referer" in headers:
            parsed = urlparse(headers["Referer"])
            headers["Origin"] = f"{parsed.scheme}://{parsed.netloc}"
        elif product_url:
            parsed = urlparse(product_url)
            headers["Origin"] = f"{parsed.scheme}://{parsed.netloc}"
    
    # Set Accept headers if not present
    if "Accept" not in headers:
        headers["Accept"] = "application/json, text/plain, */*"
    
    if "Accept-Language" not in headers:
        headers["Accept-Language"] = "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
    
    if "Accept-Encoding" not in headers:
        headers["Accept-Encoding"] = "gzip, deflate, br"
    
    # Set Content-Type for POST/PUT requests if body present
    if xhr_info.get("method") in ("POST", "PUT", "PATCH"):
        if "Content-Type" not in headers and xhr_info.get("body"):
            # Try to detect content type from body
            body = xhr_info.get("body", "")
            if isinstance(body, str):
                try:
                    json.loads(body)
                    headers["Content-Type"] = "application/json"
                except (json.JSONDecodeError, TypeError):
                    headers["Content-Type"] = "application/x-www-form-urlencoded"
    
    # Remove hop-by-hop headers that httpx will set automatically
    for header in XHR_HEADERS_TO_REMOVE:
        headers.pop(header, None)
    
    # Remove headers that httpx sets automatically
    headers.pop("Content-Length", None)  # httpx calculates this
    headers.pop("Host", None)  # httpx sets this from URL
    headers.pop("Connection", None)  # hop-by-hop header
    
    # Keep all other headers (especially anti-detection ones)
    # This includes: X-Requested-With, X-CSRF-Token, etc.
    
    return headers


def prepare_cookies(
    xhr_info: Dict[str, Any],
    additional_cookies: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """
    Prepare cookies for XHR reproduction.
    Extracts cookies from xhr_info headers and merges with additional cookies.
    
    Args:
        xhr_info: Captured XHR information
        additional_cookies: Additional cookies to merge
        
    Returns:
        Cookies dict
    """
    cookies = {}
    
    # Extract cookies from Cookie header if present
    cookie_header = xhr_info.get("headers", {}).get("Cookie", "")
    if cookie_header:
        # Parse Cookie header: "name1=value1; name2=value2"
        for cookie_pair in cookie_header.split(";"):
            cookie_pair = cookie_pair.strip()
            if "=" in cookie_pair:
                name, value = cookie_pair.split("=", 1)
                cookies[name.strip()] = value.strip()
    
    # Merge with additional cookies (additional_cookies take precedence)
    if additional_cookies:
        cookies.update(additional_cookies)
    
    return cookies


async def reproduce_xhr_directly(
    xhr_info: Dict[str, Any],
    cookies: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
    product_url: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Reproduce XHR request directly via httpx (PRIMARY METHOD - no browser needed).
    Pure HTTP client that replays exact API call without rendering page.
    
    Args:
        xhr_info: Captured XHR information with method, url, headers, body
        cookies: Optional additional cookies dict (merged with cookies from headers)
        timeout: Request timeout in seconds (default: XHR_REPRODUCTION_TIMEOUT)
        product_url: Original product URL (for Referer header)
        user_agent: User-Agent string (if not in xhr_info)
        
    Returns:
        Parsed JSON response or None if failed
    """
    if timeout is None:
        timeout = XHR_REPRODUCTION_TIMEOUT
    
    try:
        method = xhr_info.get("method", "GET")
        url = xhr_info.get("url")
        
        if not url:
            logger.warning("⚠️ XHR info missing URL")
            return None
        
        # Prepare headers with anti-detection measures
        headers = prepare_headers(xhr_info, product_url=product_url, user_agent=user_agent)
        
        # Prepare cookies (merge from headers and additional cookies)
        cookies_dict = prepare_cookies(xhr_info, additional_cookies=cookies)
        
        # Prepare body
        body = xhr_info.get("body")
        if body:
            if isinstance(body, str):
                body = body.encode('utf-8')
            elif not isinstance(body, bytes):
                # Try to serialize as JSON
                try:
                    body = json.dumps(body).encode('utf-8')
                except (TypeError, ValueError):
                    body = str(body).encode('utf-8')
        
        logger.info(f"🔄 Reproducing XHR (PRIMARY METHOD): {method} {url[:100]}...")
        logger.debug(f"   Headers: {len(headers)} headers, Cookies: {len(cookies_dict)} cookies")
        
        # Use global client for connection pooling
        client = get_http_client()
        
        resp = await client.request(
            method=method,
            url=url,
            headers=headers,
            content=body if body else None,
            cookies=cookies_dict if cookies_dict else None
        )
        
        resp.raise_for_status()
        
        # Attempt to parse JSON
        try:
            data = resp.json()
            logger.info(f"✅ XHR reproduced successfully, got JSON response ({len(str(data))} chars)")
            return data
        except Exception:
            # Return text if not JSON
            text = resp.text
            logger.info(f"✅ XHR reproduced successfully, got text response ({len(text)} chars)")
            return {"_text": text, "_status": resp.status_code}
                
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        logger.warning(f"⚠️ XHR reproduction failed with status {status_code}: {url[:100]}")
        # Log response body for debugging
        try:
            error_body = e.response.text[:200]
            logger.debug(f"   Error response: {error_body}")
        except Exception:
            pass
        return None
    except httpx.TimeoutException:
        logger.warning(f"⚠️ XHR reproduction timed out after {timeout}s: {url[:100]}")
        return None
    except httpx.RequestError as e:
        logger.warning(f"⚠️ XHR reproduction request error: {e}")
        return None
    except Exception as e:
        logger.warning(f"⚠️ XHR reproduction failed: {e}", exc_info=True)
        return None


def extract_short_url_from_response(response_data: Dict[str, Any]) -> Optional[str]:
    """
    Extract shortUrl or /cc/ link from XHR response data.
    Enhanced recursive search with better pattern matching.
    
    Args:
        response_data: Parsed JSON response or dict
        
    Returns:
        Partner link or None
    """
    import re
    
    if not response_data:
        return None
    
    # CC link pattern
    cc_pattern = re.compile(r'https?://market\.yandex\.ru/cc/[A-Za-z0-9_-]+')
    
    # Check for shortUrl in common locations (direct fields)
    short_url = (
        response_data.get('shortUrl') or
        response_data.get('short_url') or
        response_data.get('url') or
        response_data.get('link') or
        response_data.get('data', {}).get('shortUrl') or
        response_data.get('result', {}).get('shortUrl') or
        response_data.get('payload', {}).get('shortUrl') or
        response_data.get('response', {}).get('shortUrl') or
        response_data.get('body', {}).get('shortUrl') if isinstance(response_data.get('body'), dict) else None
    )    
    if short_url:
        # Extract /cc/ link if present
        cc_match = cc_pattern.search(str(short_url))
        if cc_match:
            result = cc_match.group(0).split('?')[0]            return result
        # Return as-is if it's a valid URL
        if isinstance(short_url, str) and short_url.startswith(('http://', 'https://')):            return short_url
    
    # Deep recursive search in all string values
    def search_dict(d, depth=0, max_depth=15):
        if depth >= max_depth:
            return None
        if isinstance(d, dict):
            # Check key names for hints
            for key, value in d.items():
                if isinstance(key, str) and any(hint in key.lower() for hint in ['url', 'link', 'short', 'cc', 'ref']):
                    if isinstance(value, str):
                        cc_match = cc_pattern.search(value)
                        if cc_match:
                            return cc_match.group(0).split('?')[0]
                # Recursively search values
                if isinstance(value, (dict, list, str)):
                    result = search_dict(value, depth + 1, max_depth)
                    if result:
                        return result
        elif isinstance(d, list):
            for item in d:
                result = search_dict(item, depth + 1, max_depth)
                if result:
                    return result
        elif isinstance(d, str):
            # Check if string contains CC link
            cc_match = cc_pattern.search(d)
            if cc_match:
                return cc_match.group(0).split('?')[0]
        return None
    
    return search_dict(response_data)


def extract_xhr_from_network_dump(
    network_dump_path: str,
    product_url: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Extract XHR information from network dump JSON file.
    Finds the API call that returned the CC link.
    
    Args:
        network_dump_path: Path to network dump JSON file
        product_url: Original product URL (for context)
        
    Returns:
        XHR info dict (method, url, headers, body) or None
    """
    try:
        with open(network_dump_path, 'r', encoding='utf-8') as f:
            dump_data = json.load(f)
        
        responses = dump_data.get("responses", [])
        
        # Find response that contains CC link
        for response in responses:
            if response.get("cc_link_found", False):
                # This response had a CC link, but we need the REQUEST info
                # Network dump should include request info, but if not, we'll need to reconstruct
                url = response.get("url")
                if url and any(pattern in url for pattern in ["/api/", "/share", "platform-api"]):
                    # Try to find corresponding request in dump
                    # For now, return basic info - in production, dump should include full request
                    return {
                        "method": "POST",  # Most share APIs are POST
                        "url": url,
                        "headers": {},  # Should be in dump
                        "body": None  # Should be in dump
                    }
        
        # If no CC link found, return first API response
        for response in responses:
            url = response.get("url")
            if url and any(pattern in url for pattern in ["/api/", "/share", "platform-api"]):
                return {
                    "method": "POST",
                    "url": url,
                    "headers": {},
                    "body": None
                }
        
        logger.warning(f"⚠️ No API response found in network dump: {network_dump_path}")
        return None
        
    except Exception as e:
        logger.warning(f"⚠️ Failed to extract XHR from network dump: {e}")
        return None

