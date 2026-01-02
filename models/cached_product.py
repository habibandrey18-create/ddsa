# models/cached_product.py
"""
CachedProduct Model
Structured product cache with TTL and validation
"""
import re
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# TTL for product cache (7 days)
PRODUCT_CACHE_TTL_DAYS = 7


@dataclass
class CachedProduct:
    """
    Cached product model with validation and TTL support.

    Fields:
        product_id: Numeric product ID extracted from URL
        title: Product title (required, non-empty)
        price: Product price (required, > 0)
        cc_link: Partner CC link (required)
        discount: Optional discount amount
        category: Optional product category
        rating: Optional product rating
        old_price: Optional old/strikethrough price
        reviews: Optional list of user reviews
        created_at: Cache creation timestamp
    """

    product_id: str
    title: str
    price: float
    cc_link: str
    discount: Optional[float] = None
    category: Optional[str] = None
    rating: Optional[float] = None
    old_price: Optional[float] = None
    reviews: Optional[list[str]] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        """Validate product data after initialization."""
        if not self.created_at:
            self.created_at = datetime.utcnow()

        # Validate required fields
        if not self.title or not self.title.strip():
            raise ValueError("Title must be non-empty")

        if self.price <= 0:
            raise ValueError(f"Price must be > 0, got {self.price}")

        # CC link is now optional - only validate if present
        if self.cc_link and self.cc_link.strip():
            # Validate CC link format
            if not re.search(r"/cc/[A-Za-z0-9_-]+", self.cc_link):
                raise ValueError(f"Invalid CC link format: {self.cc_link}")

    def is_fresh(self, ttl_days: int = PRODUCT_CACHE_TTL_DAYS) -> bool:
        """
        Check if cached product is still fresh (within TTL).

        Args:
            ttl_days: Time-to-live in days (default: 7)

        Returns:
            True if cache is fresh, False if expired
        """
        if not self.created_at:
            return False

        age = datetime.utcnow() - self.created_at
        return age.days < ttl_days

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        data = asdict(self)
        # Convert datetime to ISO string
        if data.get("created_at"):
            data["created_at"] = data["created_at"].isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CachedProduct":
        """Create from dictionary."""
        # Convert ISO string to datetime
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)

    @classmethod
    def extract_product_id(cls, url: str) -> Optional[str]:
        """
        Extract product ID from Yandex Market URL.

        Args:
            url: Product URL

        Returns:
            Product ID or None if not found
        """
        # Try to find numeric ID in path (6+ digits)
        match = re.search(r"/(\d{6,})", url)
        if match:
            return match.group(1)

        # Try to find in /product/ path
        match = re.search(r"/product/[^/]+/(\d+)", url)
        if match:
            return match.group(1)

        return None

    @classmethod
    def from_scraper_data(
        cls, url: str, scraper_data: Dict[str, Any], cc_link: str
    ) -> Optional["CachedProduct"]:
        """
        Create CachedProduct from scraper data.

        Args:
            url: Product URL
            scraper_data: Data from scrape_yandex_market()
            cc_link: Generated CC link

        Returns:
            CachedProduct instance or None if validation fails
        """
        try:
            # Extract product ID
            product_id = cls.extract_product_id(url)
            if not product_id:
                logger.warning(f"Could not extract product_id from URL: {url}")
                return None

            # Extract title
            title = scraper_data.get("title", "").strip()
            if not title:
                logger.warning(f"Empty title in scraper data for URL: {url}")
                return None

            # Extract and parse price
            price_str = scraper_data.get("price", "")
            price = cls._parse_price(price_str)
            if price <= 0:
                logger.warning(f"Invalid price '{price_str}' for URL: {url}")
                return None

            # Extract optional fields
            discount = scraper_data.get("discount")
            discount_percent = scraper_data.get("discount_percent")
            if discount_percent and not discount:
                # Calculate discount from percent if needed
                discount = price * (discount_percent / 100)

            category = scraper_data.get("category")
            rating = scraper_data.get("rating")
            old_price = scraper_data.get("old_price")
            reviews = scraper_data.get("reviews")

            return cls(
                product_id=product_id,
                title=title,
                price=price,
                cc_link=cc_link,
                discount=discount,
                category=category,
                rating=rating,
                old_price=old_price,
                reviews=reviews,
                created_at=datetime.utcnow(),
            )
        except Exception as e:
            logger.warning(f"Failed to create CachedProduct from scraper data: {e}")
            return None

    @staticmethod
    def _parse_price(price_str: str) -> float:
        """
        Parse price string to float.

        Args:
            price_str: Price string (e.g., "123 456 ₽", "1234.56 ₽")

        Returns:
            Price as float, or 0.0 if parsing fails
        """
        if not price_str:
            return 0.0

        # Remove currency symbols and spaces
        price_clean = re.sub(r"[₽руб\s]", "", price_str, flags=re.IGNORECASE)
        # Replace comma with dot
        price_clean = price_clean.replace(",", ".")

        try:
            return float(price_clean)
        except (ValueError, TypeError):
            return 0.0
