# utils/scraper/yandex_market_scraper.py
"""
Yandex Market specific scraping functions.
Contains the main scrape_yandex_market function and related utilities.
"""
import asyncio
import json
import logging
import os
import re
from typing import Dict, Any, Optional, List, Tuple

import aiohttp
from bs4 import BeautifulSoup

import src.config as config
from .http_utils import fetch_bytes, fetch_text, resolve_final_url
from .data_extraction import extract_product_data_from_html, extract_data_from_json_ld, extract_meta_tags, _extract_price_from_text

logger = logging.getLogger(__name__)


async def scrape_yandex_market(
    url: str, use_playwright: bool = False, playwright_page=None
):
    """
    Enhanced scraper with improved HTML parsing:
    returns dict {title, description, price, url, image_bytes, image_url, rating, category, discount, ...}

    Price detection: meta, ld+json, og, twitter, regex on HTML.
    The 'url' returned respects config.KEEP_ORIGINAL_URL.

    Args:
        url: Product URL to scrape
        use_playwright: If True, use Playwright page.content() for dynamically rendered content
        playwright_page: Optional Playwright page object (if use_playwright=True)

    Returns:
        Dict with product data including: title, price, images, rating, category, discount, etc.
    """
    logger.info("scrape_yandex_market: started for %s", url)

    # ПРОВЕРКА 0: Если исходная ссылка уже содержит /cc/, используем её сразу
    cc_match = re.search(r"/cc/([A-Za-z0-9_-]+)", url)
    cc_code = None
    if cc_match:
        cc_code = cc_match.group(1)
        logger.info(f"Found CC code in URL: {cc_code}")

    # Резолвим финальный URL (для cc/... и ya.cc ссылок)
    final_url = await resolve_final_url(url)
    if not final_url:
        logger.warning("Failed to resolve final URL for %s", url)
        return {"_debug": "url_resolution_failed"}

    logger.debug("Final URL: %s", final_url)

    # ПОЛУЧАЕМ HTML
    html = None
    data_source = "unknown"

    if use_playwright and playwright_page:
        try:
            html = await playwright_page.content()
            data_source = "playwright"
            logger.info("Got HTML via Playwright")
        except Exception as e:
            logger.warning("Playwright failed: %s", e)

    if not html:
        # Fallback to aiohttp
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }

            async with aiohttp.ClientSession() as session:
                html, status = await fetch_text(session, final_url, headers)
                if status == 200 and html:
                    data_source = "aiohttp"
                    logger.info("Got HTML via aiohttp")
                else:
                    logger.warning("Failed to fetch HTML: status=%s", status)
                    return {"_debug": "html_fetch_failed", "status": status}

        except Exception as e:
            logger.error("HTML fetch error: %s", e)
            return {"_debug": "html_fetch_error", "error": str(e)}

    if not html:
        return {"_debug": "no_html"}

    # ПАРСИНГ HTML
    try:
        soup = BeautifulSoup(html, 'html.parser')
    except Exception as e:
        logger.error("BeautifulSoup parsing failed: %s", e)
        return {"_debug": "html_parse_failed"}

    # ДОСТАЁМ TITLE
    title = None
    title_selectors = [
        '[data-zone="title"]',
        'h1[data-zone="title"]',
        '.product-title',
        'h1.title',
        'h1',
        'title'
    ]

    for selector in title_selectors:
        element = soup.select_one(selector)
        if element:
            title = element.get_text(strip=True)
            if title and len(title) > 3:  # Минимальная длина
                break

    # ДОСТАЁМ DESCRIPTION
    description = None
    desc_selectors = [
        '[data-zone="description"]',
        '.product-description',
        '.description',
        'meta[name="description"]'
    ]

    for selector in desc_selectors:
        element = soup.select_one(selector)
        if element:
            if element.name == 'meta':
                description = element.get('content', '')
            else:
                description = element.get_text(strip=True)
            if description and len(description) > 10:
                break

    # ДОСТАЁМ SPECS (характеристики)
    specs = {}
    specs_selectors = [
        '[data-zone="specs"]',
        '.product-specs',
        '.specifications',
        '.specs'
    ]

    for selector in specs_selectors:
        spec_elements = soup.select(f'{selector} [data-zone="spec"]')
        if spec_elements:
            for spec in spec_elements:
                name_elem = spec.select_one('[data-zone="spec-name"]')
                value_elem = spec.select_one('[data-zone="spec-value"]')
                if name_elem and value_elem:
                    name = name_elem.get_text(strip=True)
                    value = value_elem.get_text(strip=True)
                    if name and value:
                        specs[name] = value
            if specs:
                break

    # ДОСТАЁМ MARKETING DESCRIPTION (маркетинговое описание)
    marketing_description = None
    marketing_selectors = [
        '[data-zone="marketing-description"]',
        '.marketing-description',
        '.promo-description'
    ]

    for selector in marketing_selectors:
        element = soup.select_one(selector)
        if element:
            marketing_description = element.get_text(strip=True)
            if marketing_description and len(marketing_description) > 20:
                break

    # ДОСТАЁМ PRICE (цена)
    price = None
    price_selectors = [
        '[data-zone="price"]',
        '.product-price',
        '.price',
        'meta[property="product:price:amount"]'
    ]

    for selector in price_selectors:
        element = soup.select_one(selector)
        if element:
            if element.name == 'meta':
                price = element.get('content', '')
            else:
                price_text = element.get_text(strip=True)
                price = _extract_price_from_text(price_text)
            if price:
                break

    # ДОСТАЁМ IMAGES
    image_urls = []
    image_selectors = [
        '[data-zone="images"] img',
        '.product-images img',
        '.gallery img',
        'img[data-src]'
    ]

    for selector in image_selectors:
        img_elements = soup.select(selector)
        for img in img_elements:
            img_url = img.get('src') or img.get('data-src')
            if img_url:
                # Make absolute URL
                if img_url.startswith('//'):
                    img_url = 'https:' + img_url
                elif img_url.startswith('/'):
                    img_url = 'https://market.yandex.ru' + img_url

                if img_url not in image_urls:
                    image_urls.append(img_url)

        if image_urls:
            break

    # Get first image bytes
    image_bytes = None
    image_url = image_urls[0] if image_urls else None

    if image_url:
        try:
            async with aiohttp.ClientSession() as session:
                image_bytes = await fetch_bytes(session, image_url, {"User-Agent": "Mozilla/5.0"})
        except Exception as e:
            logger.debug("Failed to fetch image: %s", e)

    # ДОСТАЁМ RATING (рейтинг)
    rating = None
    rating_selectors = [
        '[data-zone="rating"]',
        '.product-rating',
        '.rating',
        'meta[property="og:rating"]'
    ]

    for selector in rating_selectors:
        element = soup.select_one(selector)
        if element:
            if element.name == 'meta':
                rating = element.get('content', '')
            else:
                rating_text = element.get_text(strip=True)
                # Extract number
                rating_match = re.search(r'(\d+(?:\.\d+)?)', rating_text)
                if rating_match:
                    rating = rating_match.group(1)
            if rating:
                break

    # ДОСТАЁМ RATING COUNT (количество отзывов)
    rating_count = None
    rating_count_selectors = [
        '[data-zone="reviews"]',
        '.reviews-count',
        '.rating-count',
        'meta[property="og:rating_count"]'
    ]

    for selector in rating_count_selectors:
        element = soup.select_one(selector)
        if element:
            if element.name == 'meta':
                rating_count = element.get('content', '')
            else:
                count_text = element.get_text(strip=True)
                count_match = re.search(r'(\d+)', count_text)
                if count_match:
                    rating_count = count_match.group(1)
            if rating_count:
                break

    # ДОСТАЁМ REVIEWS (отзывы)
    reviews = []
    review_selectors = [
        '[data-zone="reviews"] [data-zone="review"]',
        '.reviews .review',
        '.user-reviews .review'
    ]

    for selector in review_selectors:
        review_elements = soup.select(selector)
        for review_elem in review_elements[:15]:  # Limit to 15 reviews
            review_text = review_elem.get_text(strip=True)
            if review_text and len(review_text) > 20:
                reviews.append(review_text)

        if reviews:
            break

    # ДОСТАЁМ CATEGORY (категория)
    category = None
    category_selectors = [
        '[data-zone="category"]',
        '.breadcrumb a:last-child',
        '.category',
        'meta[property="og:type"]'
    ]

    for selector in category_selectors:
        element = soup.select_one(selector)
        if element:
            if element.name == 'meta':
                category = element.get('content', '')
            else:
                category = element.get_text(strip=True)
            if category:
                break

    # ДОСТАЁМ CATEGORIES (список категорий)
    categories = []
    category_list_selectors = [
        '.breadcrumb a',
        '[data-zone="breadcrumb"] a',
        '.categories a'
    ]

    for selector in category_list_selectors:
        cat_elements = soup.select(selector)
        for cat_elem in cat_elements:
            cat_name = cat_elem.get_text(strip=True)
            if cat_name and cat_name not in categories:
                categories.append(cat_name)

        if categories:
            break

    # ДОСТАЁМ DISCOUNT (скидка)
    discount = None
    discount_selectors = [
        '[data-zone="discount"]',
        '.discount',
        '.sale',
        '.promo'
    ]

    for selector in discount_selectors:
        element = soup.select_one(selector)
        if element:
            discount_text = element.get_text(strip=True)
            discount_match = re.search(r'(\d+)', discount_text)
            if discount_match:
                discount = discount_match.group(1)
                break

    # ДОСТАЁМ DISCOUNT PERCENT (процент скидки)
    discount_percent = None
    percent_selectors = [
        '.discount-percent',
        '.sale-percent',
        '[data-zone="discount-percent"]'
    ]

    for selector in percent_selectors:
        element = soup.select_one(selector)
        if element:
            percent_text = element.get_text(strip=True)
            percent_match = re.search(r'(\d+)', percent_text)
            if percent_match:
                discount_percent = percent_match.group(1)
                break

    # ДОСТАЁМ PROMO CODE (промокод)
    promo_code = None
    promo_selectors = [
        '[data-zone="promo-code"]',
        '.promo-code',
        '.coupon-code'
    ]

    for selector in promo_selectors:
        element = soup.select_one(selector)
        if element:
            promo_code = element.get_text(strip=True)
            if promo_code:
                break

    # ДОСТАЁМ PROMO TEXT (текст промо)
    promo_text = None
    promo_text_selectors = [
        '[data-zone="promo-text"]',
        '.promo-text',
        '.promotion-text'
    ]

    for selector in promo_text_selectors:
        element = soup.select_one(selector)
        if element:
            promo_text = element.get_text(strip=True)
            if promo_text:
                break

    # ПОЛУЧАЕМ PARTNER LINK
    ref_link = ""
    product_url = final_url
    has_ref = False
    flags = [data_source]

    # Try to get partner link
    try:
        from src.services.partner_link_service import PartnerLinkService

        partner_service = PartnerLinkService()
        partner_result = await partner_service.get_partner_link(
            url, use_browser=False
        )
        ref_link = partner_result.get("ref_link", "")
        flags.extend(partner_result.get("flags", []))
    except Exception as e:
        logger.warning(f"Failed to get partner link: {e}")
        if (
            "needs_playwright_install" in str(e).lower()
            or "playwright" in str(e).lower()
        ):
            flags.append("needs_playwright_install")
        else:
            flags.append("api_failed")
        flags.append(data_source)

    out_url = url if getattr(config, "KEEP_ORIGINAL_URL", True) else final_url

    return {
        "title": title,
        "description": description or "",
        "specs": specs,
        "marketing_description": marketing_description,
        "price": price,
        "url": out_url,
        "image_bytes": image_bytes,
        "image_url": image_url,
        "image_urls": image_urls[:5] if image_urls else [],  # Up to 5 images
        "rating": float(rating) if rating else None,
        "rating_count": int(rating_count) if rating_count else None,
        "reviews": (
            reviews[:15] if reviews else None
        ),  # Top 15 reviews for AI summarization
        "category": category,
        "categories": categories[:3] if categories else [],  # Top 3 categories
        "discount": float(discount) if discount else None,
        "discount_percent": discount_percent,
        "promo_code": promo_code,
        "promo_text": promo_text,
        "ref_link": ref_link,
        "product_url": product_url,
        "has_ref": has_ref,
        "flags": flags,
        "_debug": "ok_enhanced",
    }
