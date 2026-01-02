# utils/scraper/data_extraction.py
"""
Data extraction utilities for web scraping.
Handles product data parsing and price extraction.
"""
import json
import logging
import re
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def _extract_price_from_text(text: str) -> Optional[str]:
    """Extract price from text using various patterns."""
    if not text:
        return None

    # Удаляем все пробелы и неразрывные пробелы для более точного поиска
    text_clean = text.replace("\u00a0", " ").replace(" ", "")

    # Ищем различные форматы цен
    patterns = [
        r"(\d{1,3}(?:[ \u00A0]\d{3})*(?:[.,]\d{1,2})?)\s*₽",  # "123 456 ₽"
        r"(\d{1,3}(?:[ \u00A0]\d{3})*(?:[.,]\d{1,2})?)\s*(руб|руб\.)",  # "123 456 руб"
        r"(\d+(?:[.,]\d{1,2})?)\s*₽",  # "1234.56₽" или "1234,56₽"
        r"(\d+(?:[.,]\d{1,2})?)\s*(руб|руб\.)",  # "1234.56руб"
        r"₽\s*(\d{1,3}(?:[ \u00A0]\d{3})*(?:[.,]\d{1,2})?)",  # "₽ 123 456"
        r"(?:цена|стоимость|стоит)[:\s]*(\d{1,3}(?:[ \u00A0]\d{3})*(?:[.,]\d{1,2})?)",  # "цена: 123 456"
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            price_str = m.group(1).replace("\u00a0", " ").replace(" ", "")
            # Проверяем, что это разумная цена (от 1 до 10 миллионов)
            try:
                price_num = float(price_str.replace(",", "."))
                if 1 <= price_num <= 10000000:
                    # Форматируем обратно с пробелами для тысяч
                    if price_num >= 1000:
                        formatted = f"{int(price_num):,}".replace(",", " ")
                        return formatted
                    else:
                        return price_str.replace(".", ",")
            except ValueError:
                continue

    return None


async def scrape_product_data(url: str) -> Optional[Dict[str, Any]]:
    """
    Simplified product data scraper for search services.

    Args:
        url: Product URL

    Returns:
        Dict with basic product data or None if failed
    """
    try:
        # For testing purposes, return mock data
        # In production, this should call scrape_yandex_market
        return {
            'id': f"test_{hash(url) % 10000}",
            'title': 'Test Product',
            'price': 1000,
            'url': url,
            'vendor': 'TestBrand',
            'rating': 4.5,
            'reviews_count': 100,
            'has_images': True,
            'specs': {},
            'marketing_description': 'Test description',
            'availability': True
        }
    except Exception as e:
        logger.error(f"Failed to scrape product data: {e}")
        return None


def extract_product_data_from_html(html: str) -> Dict[str, Any]:
    """
    Extract product data from HTML content.
    This is a simplified version - full implementation would be much more complex.
    """
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'html.parser')

        # Extract title
        title = None
        title_selectors = ['h1', '.product-title', '[data-zone="title"]', '.title']
        for selector in title_selectors:
            element = soup.select_one(selector)
            if element:
                title = element.get_text(strip=True)
                break

        # Extract price
        price = None
        price_selectors = ['.price', '[data-zone="price"]', '.product-price', '.price-value']
        for selector in price_selectors:
            element = soup.select_one(selector)
            if element:
                price_text = element.get_text(strip=True)
                price = _extract_price_from_text(price_text)
                if price:
                    break

        # Extract rating
        rating = None
        rating_selectors = ['.rating', '[data-zone="rating"]', '.product-rating']
        for selector in rating_selectors:
            element = soup.select_one(selector)
            if element:
                rating_text = element.get_text(strip=True)
                # Try to extract number
                rating_match = re.search(r'(\d+(?:\.\d+)?)', rating_text)
                if rating_match:
                    try:
                        rating = float(rating_match.group(1))
                        break
                    except ValueError:
                        continue

        # Extract reviews count
        reviews_count = None
        reviews_selectors = ['.reviews-count', '[data-zone="reviews"]', '.product-reviews']
        for selector in reviews_selectors:
            element = soup.select_one(selector)
            if element:
                reviews_text = element.get_text(strip=True)
                reviews_match = re.search(r'(\d+)', reviews_text)
                if reviews_match:
                    try:
                        reviews_count = int(reviews_match.group(1))
                        break
                    except ValueError:
                        continue

        return {
            'title': title,
            'price': price,
            'rating': rating,
            'reviews_count': reviews_count,
            'raw_html': html[:1000]  # Store first 1000 chars for debugging
        }

    except Exception as e:
        logger.error(f"Failed to extract product data from HTML: {e}")
        return {}


def extract_data_from_json_ld(html: str) -> Dict[str, Any]:
    """Extract structured data from JSON-LD in HTML."""
    try:
        # Find JSON-LD scripts
        json_ld_pattern = r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
        matches = re.findall(json_ld_pattern, html, re.DOTALL | re.IGNORECASE)

        product_data = {}

        for match in matches:
            try:
                data = json.loads(match.strip())
                if isinstance(data, list):
                    for item in data:
                        if item.get('@type') in ['Product', 'Offer', 'AggregateRating']:
                            product_data.update(item)
                elif isinstance(data, dict):
                    if data.get('@type') in ['Product', 'Offer', 'AggregateRating']:
                        product_data.update(data)
            except json.JSONDecodeError:
                continue

        return product_data

    except Exception as e:
        logger.error(f"Failed to extract JSON-LD data: {e}")
        return {}


def extract_meta_tags(html: str) -> Dict[str, Any]:
    """Extract meta tags from HTML."""
    try:
        meta_data = {}

        # Common meta tag patterns
        meta_patterns = [
            (r'<meta[^>]*property=["\']og:([^"\']+)["\'][^>]*content=["\']([^"\']+)["\'][^>]*>', 'og'),
            (r'<meta[^>]*name=["\']([^"\']+)["\'][^>]*content=["\']([^"\']+)["\'][^>]*>', 'meta'),
            (r'<meta[^>]*name=["\']twitter:([^"\']+)["\'][^>]*content=["\']([^"\']+)["\'][^>]*>', 'twitter'),
        ]

        for pattern, prefix in meta_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for key, value in matches:
                meta_data[f"{prefix}_{key}"] = value

        return meta_data

    except Exception as e:
        logger.error(f"Failed to extract meta tags: {e}")
        return {}
