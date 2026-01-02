"""
Structured Logging Helper - Улучшенное логирование с correlation_id
Согласно требованиям: structured logging с correlation_id во всех логах
"""

import logging
from typing import Optional, Dict, Any
from src.utils.correlation_id import get_correlation_id, set_correlation_id

logger = logging.getLogger(__name__)


def log_with_context(
    level: str,
    message: str,
    correlation_id: Optional[str] = None,
    **kwargs
):
    """
    Структурированное логирование с correlation_id и дополнительными полями
    
    Args:
        level: Уровень логирования ('info', 'warning', 'error', 'debug')
        message: Сообщение для логирования
        correlation_id: Correlation ID (если не передан, берется из контекста)
        **kwargs: Дополнительные поля для логирования
    """
    # Получаем correlation_id из контекста если не передан
    if correlation_id is None:
        correlation_id = get_correlation_id() or "unknown"
    
    # Формируем структурированное сообщение
    extra_fields = {k: v for k, v in kwargs.items() if v is not None}
    
    if extra_fields:
        # Структурированное логирование с дополнительными полями
        fields_str = ", ".join(f"{k}={v}" for k, v in extra_fields.items())
        structured_message = f"[{correlation_id}] {message} | {fields_str}"
    else:
        structured_message = f"[{correlation_id}] {message}"
    
    # Логируем с правильным уровнем
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.log(log_level, structured_message, extra={'correlation_id': correlation_id})


def log_product_event(
    event_type: str,
    product_id: Optional[str] = None,
    product_url: Optional[str] = None,
    message: str = "",
    correlation_id: Optional[str] = None,
    **kwargs
):
    """
    Специализированное логирование событий продуктов
    
    Args:
        event_type: Тип события ('found', 'published', 'rejected', 'error')
        product_id: ID товара
        product_url: URL товара
        message: Дополнительное сообщение
        correlation_id: Correlation ID
        **kwargs: Дополнительные поля
    """
    event_messages = {
        'found': f"Product found: {product_id or 'unknown'}",
        'published': f"Product published: {product_id or 'unknown'}",
        'rejected': f"Product rejected: {product_id or 'unknown'}",
        'error': f"Product error: {product_id or 'unknown'}"
    }
    
    base_message = event_messages.get(event_type, f"Product event: {event_type}")
    if message:
        base_message += f" - {message}"
    
    log_with_context(
        level='info' if event_type != 'error' else 'error',
        message=base_message,
        correlation_id=correlation_id,
        product_id=product_id,
        product_url=product_url[:100] if product_url else None,  # Ограничиваем длину URL
        **kwargs
    )


def log_affiliate_event(
    event_type: str,
    erid: Optional[str] = None,
    link: Optional[str] = None,
    message: str = "",
    correlation_id: Optional[str] = None
):
    """
    Специализированное логирование событий affiliate ссылок
    
    Args:
        event_type: Тип события ('generated', 'clicked', 'error')
        erid: ERID ссылки
        link: Ссылка (первые 100 символов)
        message: Дополнительное сообщение
        correlation_id: Correlation ID
    """
    event_messages = {
        'generated': f"Affiliate link generated: erid={erid or 'unknown'}",
        'clicked': f"Affiliate link clicked: erid={erid or 'unknown'}",
        'error': f"Affiliate link error: erid={erid or 'unknown'}"
    }
    
    base_message = event_messages.get(event_type, f"Affiliate event: {event_type}")
    if message:
        base_message += f" - {message}"
    
    log_with_context(
        level='info' if event_type != 'error' else 'error',
        message=base_message,
        correlation_id=correlation_id,
        erid=erid,
        link=link[:100] if link else None
    )

