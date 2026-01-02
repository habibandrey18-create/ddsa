"""
Affiliate Service - Генерация affiliate ссылок с уникальными ERID
Согласно требованиям: формат market.yandex.ru/cc/<code> с параметрами clid, vid, erid, UTM
"""

import uuid
import logging
from datetime import datetime
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


def generate_erid() -> str:
    """
    Генерирует уникальный ERID для поста по правилам Yandex.
    Формат: tg-YYYYMMDD-XXXXXX (где XXXXXX - 6 символов UUID)
    
    Returns:
        Уникальный ERID строка
    """
    date = datetime.utcnow().strftime("%Y%m%d")
    uid = uuid.uuid4().hex[:6]
    return f"tg-{date}-{uid}"
    return f"tg-{date}-{uid}"


def get_affiliate_link(product_url: str, correlation_id: Optional[str] = None) -> Tuple[str, str]:
    """
    Возвращает аффилиатную ссылку на товар с уникальным ERID и параметрами.
    
    Согласно требованиям:
    - Использует urllib.parse для парсинга URL
    - Удаляет существующие query параметры
    - Добавляет clid, vid, erid, UTM параметры
    - Если clid не установлен, возвращает чистый URL
    
    Args:
        product_url: Оригинальный URL товара
        correlation_id: Correlation ID для логирования (опционально)
        
    Returns:
        Tuple (affiliate_link, unique_erid)
    """
    try:
        from utils.correlation_id import get_correlation_id
        correlation_id = correlation_id or get_correlation_id() or "unknown"
        
        import config
        
        # Получаем параметры из config
        clid = getattr(config, 'YANDEX_REF_CLID', None) or getattr(config, 'AFFILIATE_CLID', None)
        vid = getattr(config, 'YANDEX_REF_VID', None) or getattr(config, 'AFFILIATE_VID', None)
        
        # Если clid не установлен - возвращаем чистый URL
        if not clid:
            logger.debug(f"[{correlation_id}] AFFILIATE_CLID not set, returning clean URL")
            return product_url, ""
        
        # Генерируем уникальный ERID для этого поста
        unique_erid = generate_erid()
        logger.debug(f"[{correlation_id}] Generated ERID: {unique_erid} for URL: {product_url[:50]}...")
        
        # Парсим URL
        parsed = urlparse(product_url)
        
        # Удаляем существующие query параметры и создаем новые
        # Согласно требованиям: "strip existing query params and append affiliate parameters"
        query_params = {}
        
        # Добавляем affiliate параметры
        query_params['clid'] = clid
        if vid:
            query_params['vid'] = vid
        query_params['erid'] = unique_erid
        
        # Добавляем UTM параметры
        utm_source = getattr(config, 'UTM_SOURCE', 'telegram')
        utm_medium = getattr(config, 'UTM_MEDIUM', 'bot')
        utm_campaign = getattr(config, 'UTM_CAMPAIGN', 'marketi_tochka')
        
        query_params['utm_source'] = utm_source
        query_params['utm_medium'] = utm_medium
        query_params['utm_campaign'] = utm_campaign
        
        # Формируем новую query строку
        new_query = urlencode(query_params)
        
        # Собираем новый URL (удаляем fragment тоже)
        affiliate_link = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            '',  # params
            new_query,
            ''   # fragment - удаляем
        ))
        
        logger.info(f"[{correlation_id}] Generated affiliate link with ERID {unique_erid}")
        return affiliate_link, unique_erid
        
    except Exception as e:
        from utils.correlation_id import get_correlation_id
        correlation_id = correlation_id or get_correlation_id() or "unknown"
        logger.error(f"[{correlation_id}] Error generating affiliate link: {e}", exc_info=True)
        # В случае ошибки возвращаем оригинальный URL
        return product_url, ""


def get_ad_marking_text(erid: str) -> str:
    """
    Возвращает текст рекламы с указанным ERID.
    Формат: Реклама. ООО «Яндекс Маркет», ИНН ..., erid: <ERID>
    
    Args:
        erid: ERID для отображения в тексте рекламы
        
    Returns:
        Текст рекламы с ERID
    """
    if not erid:
        return ""
    return f"\n\nРеклама. ООО «Яндекс Маркет», ИНН 9704254424, erid: {erid}"


# Legacy compatibility
class AffiliateService:
    """Legacy compatibility class"""

    def make_affiliate_link(self, url: str) -> Tuple[str, str]:
        """Legacy method - returns tuple (link, erid)"""
        return get_affiliate_link(url)

    def get_ad_marking_text(self, erid: str) -> str:
        """Get ad marking text with specific ERID"""
        return get_ad_marking_text(erid)
    
    def should_add_ad_marking(self) -> bool:
        """Check if ad marking should be added"""
        try:
            import config
            clid = getattr(config, 'YANDEX_REF_CLID', None) or getattr(config, 'AFFILIATE_CLID', None)
            return bool(clid)
        except:
            return False


# Global instance for legacy compatibility
affiliate_service = AffiliateService()


def get_affiliate_service() -> AffiliateService:
    """Get global affiliate service instance"""
    return affiliate_service


# Convenience functions for backward compatibility
def make_affiliate_link(url: str) -> Tuple[str, str]:
    """
    Generate Yandex affiliate link with Erid ad-marking (convenience function).
    
    Args:
        url: Input URL to process
        
    Returns:
        Tuple (affiliate_link, erid)
    """
    return affiliate_service.make_affiliate_link(url)


def should_add_ad_marking() -> bool:
    """
    Check if ad marking text should be added to posts (convenience function).
    
    Returns:
        True if ERID is configured and ad marking should be added
    """
    return affiliate_service.should_add_ad_marking()
