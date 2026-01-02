# utils/partner_link_builder.py
"""
Partner Link Builder - Official Yandex Distribution method
Builds partner links using affiliate_clid and affiliate_vid
"""
import logging
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from typing import Optional

logger = logging.getLogger(__name__)


def build_partner_link(
    page_url: str,
    affiliate_clid: str,
    affiliate_vid: str,
    utm_source: str = "distribution",
    utm_medium: str = "cpa",
) -> str:
    """
    Build partner link using the manual template from Yandex Distribution docs:
    <page_url>?...&affiliate_clid={affiliate_clid}&affiliate_vid={affiliate_vid}&utm_source=distribution&utm_medium=cpa

    Args:
        page_url: Target page URL (e.g., https://market.yandex.ru/product/...)
        affiliate_clid: Partner CLID from Yandex Distribution
        affiliate_vid: Partner VID from Yandex Distribution
        utm_source: UTM source (default: "distribution")
        utm_medium: UTM medium (default: "cpa")

    Returns:
        Partner link with affiliate parameters
    """
    try:
        parts = urlparse(page_url)
        q = dict(parse_qsl(parts.query, keep_blank_values=True))

        # Add affiliate params (preserve existing query)
        q.update(
            {
                "affiliate_clid": affiliate_clid,
                "affiliate_vid": affiliate_vid,
                "utm_source": utm_source,
                "utm_medium": utm_medium,
            }
        )

        new_query = urlencode(q, doseq=True)
        partner_link = urlunparse(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                parts.params,
                new_query,
                parts.fragment,
            )
        )

        logger.info(
            f"✅ Built partner link via Distribution method: {partner_link[:100]}..."
        )
        return partner_link

    except Exception as e:
        logger.error(f"❌ Failed to build partner link: {e}")
        raise


def check_distribution_available() -> tuple[bool, Optional[str], Optional[str]]:
    """
    Check if Yandex Distribution credentials are available in config.

    Returns:
        Tuple of (is_available, affiliate_clid, affiliate_vid)
    """
    try:
        import os

        # Check environment variables first (recommended for production)
        clid = os.getenv("YANDEX_AFFILIATE_CLID") or os.getenv("AFFILIATE_CLID")
        vid = os.getenv("YANDEX_AFFILIATE_VID") or os.getenv("AFFILIATE_VID")

        # Fallback to config module
        if not (clid and vid):
            try:
                import config

                clid = (
                    clid
                    or getattr(config, "YANDEX_AFFILIATE_CLID", None)
                    or getattr(config, "AFFILIATE_CLID", None)
                )
                vid = (
                    vid
                    or getattr(config, "YANDEX_AFFILIATE_VID", None)
                    or getattr(config, "AFFILIATE_VID", None)
                )
            except ImportError:
                pass

        if clid and vid:
            logger.info("✅ Yandex Distribution credentials found")
            return True, clid, vid
        else:
            logger.debug("⚠️ Yandex Distribution credentials not found")
            return False, None, None

    except Exception as e:
        logger.debug(f"Failed to check Distribution credentials: {e}")
        return False, None, None
