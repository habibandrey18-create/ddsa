"""
Yandex Market Parser Core - Strict parser that returns minimal product data
"""

import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


def parse_yandex_market_core(html: str, url: str) -> Optional[Dict[str, Any]]:
    """
    Parse Yandex Market HTML and return strict product data dict.

    Args:
        html: Raw HTML content from Yandex Market page
        url: Product URL (for logging purposes)

    Returns:
        Dict with strict structure:
        {
          "title": str,
          "price": int,  # Price in rubles as integer
          "images": list[str],  # List of image URLs
          "url": str  # Product URL
        }
        or None if parsing fails
    """
    try:
        from bs4 import BeautifulSoup
        import re
        import json

        soup = BeautifulSoup(html, "lxml")

        # Extract title
        title = None
        # Priority: h1 > og:title > JSON-LD name
        h1 = soup.find("h1")
        if h1 and h1.text.strip():
            title = h1.text.strip()
        if not title:
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                title = og_title["content"].strip()
        if not title:
            # Try JSON-LD
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string or "{}")
                    if isinstance(data, dict) and data.get("name"):
                        title = data["name"]
                        break
                except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
                    logger.debug(f"Failed to parse JSON-LD title: {e}")
                    continue
                except Exception as e:
                    logger.error(f"Unexpected error parsing JSON-LD title: {e}", exc_info=True)
                    continue

        # Extract price as integer
        price = None
        # Priority: JSON-LD price > meta price > HTML elements
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                if isinstance(data, dict):
                    offers = data.get("offers", {})
                    if isinstance(offers, dict):
                        price_val = offers.get("price")
                    elif isinstance(offers, list) and offers:
                        price_val = offers[0].get("price") if isinstance(offers[0], dict) else None
                    else:
                        price_val = None

                    if price_val:
                        try:
                            # Convert to float first, then to int
                            price_float = float(str(price_val).replace(" ", "").replace(",", "."))
                            price = int(price_float)
                            break
                        except (ValueError, TypeError):
                            continue
            except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
                logger.debug(f"Failed to parse JSON-LD price: {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error parsing JSON-LD price: {e}", exc_info=True)
                continue

        # Fallback: extract from HTML elements
        if price is None:
            # Look for price elements with specific data attributes
            price_elements = soup.find_all(attrs={"data-auto": "snippet-price-current"})
            for elem in price_elements:
                price_span = elem.find("span", class_=re.compile(r"headline-3_bold|ds-text_headline-3_bold"))
                if price_span:
                    price_text = price_span.get_text(strip=True)
                    try:
                        # Clean and convert
                        clean_price = re.sub(r"[^\d.,]", "", price_text.replace(",", "."))
                        price_float = float(clean_price)
                        price = int(price_float)
                        break
                    except (ValueError, TypeError):
                        continue

        # Extract images
        images = []
        # Priority: JSON-LD images > og:image > img tags
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                if isinstance(data, dict):
                    image_data = data.get("image")
                    if isinstance(image_data, list):
                        images.extend(image_data[:5])  # Up to 5 images
                    elif isinstance(image_data, str):
                        images.append(image_data)
                    if images:
                        break
            except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
                logger.debug(f"Failed to parse JSON-LD images: {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error parsing JSON-LD images: {e}", exc_info=True)
                continue

        # Fallback: og:image
        if not images:
            og_image = soup.find("meta", property="og:image")
            if og_image and og_image.get("content"):
                images.append(og_image["content"])

        # Fallback: img tags with product-related src
        if not images:
            img_tags = soup.find_all("img", src=True)
            for img in img_tags:
                src = img.get("src") or img.get("data-src")
                if src and any(keyword in src.lower() for keyword in ["product", "goods", "item"]):
                    if src not in images:
                        images.append(src)
                    if len(images) >= 5:
                        break

        # Extract old price (strikethrough/crossed-out price)
        old_price = None
        # Priority: JSON-LD offers > HTML elements with strikethrough
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                if isinstance(data, dict):
                    offers = data.get("offers", {})
                    if isinstance(offers, dict):
                        price_spec = offers.get("priceSpecification", [])
                        if isinstance(price_spec, list):
                            for spec in price_spec:
                                if isinstance(spec, dict) and spec.get("priceType") == "https://schema.org/ListPrice":
                                    old_price_val = spec.get("price")
                                    if old_price_val:
                                        try:
                                            old_price = float(str(old_price_val).replace(" ", "").replace(",", "."))
                                            break
                                        except (ValueError, TypeError):
                                            continue
                    if old_price:
                        break
            except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
                logger.debug(f"Failed to parse JSON-LD old price: {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error parsing JSON-LD old price: {e}", exc_info=True)
                continue

        # Fallback: look for strikethrough/crossed-out prices in HTML
        if old_price is None:
            # Look for <s>, <del>, or elements with old-price classes
            strikethrough_elements = soup.find_all(['s', 'del', 'strike'])
            for elem in strikethrough_elements:
                text = elem.get_text(strip=True)
                try:
                    clean_price = re.sub(r"[^\d.,]", "", text.replace(",", "."))
                    price_float = float(clean_price)
                    old_price = price_float
                    break
                except (ValueError, TypeError):
                    continue

            # Look for elements with old-price classes
            if old_price is None:
                old_price_elements = soup.find_all(class_=re.compile(r"(old.?price|price.?old|strikethrough|crossed)", re.IGNORECASE))
                for elem in old_price_elements:
                    text = elem.get_text(strip=True)
                    try:
                        clean_price = re.sub(r"[^\d.,]", "", text.replace(",", "."))
                        price_float = float(clean_price)
                        old_price = price_float
                        break
                    except (ValueError, TypeError):
                        continue

        # Extract user reviews
        reviews = []
        # Priority: JSON-LD reviews > HTML review elements
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                if isinstance(data, dict):
                    review_data = data.get("review", [])
                    if isinstance(review_data, list):
                        for review in review_data[:10]:  # Up to 10 reviews
                            if isinstance(review, dict):
                                review_text = review.get("reviewBody") or review.get("description")
                                if review_text and len(review_text.strip()) > 10:
                                    reviews.append(review_text.strip())
                    elif isinstance(review_data, dict):
                        review_text = review_data.get("reviewBody") or review_data.get("description")
                        if review_text and len(review_text.strip()) > 10:
                            reviews.append(review_text.strip())
                    if reviews:
                        break
            except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
                logger.debug(f"Failed to parse JSON-LD reviews: {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error parsing JSON-LD reviews: {e}", exc_info=True)
                continue

        # Fallback: extract from HTML review elements
        if not reviews:
            # Look for review containers
            review_containers = soup.find_all(attrs={"data-auto": re.compile(r"review|comment", re.IGNORECASE)})
            for container in review_containers:
                review_texts = container.find_all(text=True)
                for text in review_texts:
                    text_str = text.strip()
                    # Filter meaningful reviews (longer than 20 chars, not containing URLs)
                    if len(text_str) > 20 and not re.search(r"http[s]?://", text_str):
                        reviews.append(text_str)
                        if len(reviews) >= 10:
                            break
                if len(reviews) >= 10:
                    break

            # Alternative: look for review text in common review classes
            if not reviews:
                review_elements = soup.find_all(class_=re.compile(r"review.?text|comment.?text|user.?review", re.IGNORECASE))
                for elem in review_elements:
                    text = elem.get_text(strip=True)
                    if len(text) > 20 and not re.search(r"http[s]?://", text):
                        reviews.append(text)
                        if len(reviews) >= 10:
                            break

        # Validate required fields
        if not title or price is None or not images:
            logger.warning(
                f"parse_yandex_market_core: missing required fields - title: {bool(title)}, price: {price is not None}, images: {len(images)}"
            )
            return None

        return {
            "title": title,
            "price": price,
            "images": images,
            "url": url,
            "old_price": old_price,
            "reviews": reviews[:10] if reviews else None  # Limit to top 10 reviews
        }

    except Exception as e:
        logger.error(f"parse_yandex_market_core: parsing failed for {url}: {e}")
        return None



