# utils/correlation_id.py
"""Утилита для correlation_id в логах"""
import uuid
import contextvars
import logging
from typing import Optional

# Context variable для хранения correlation_id
correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)


def get_correlation_id() -> str:
    """Получает текущий correlation_id"""
    return correlation_id_var.get()


def set_correlation_id(cid: Optional[str] = None) -> str:
    """Устанавливает correlation_id (генерирует новый если не передан)"""
    if cid is None:
        cid = str(uuid.uuid4())[:8]  # Короткий ID
    correlation_id_var.set(cid)
    return cid


class CorrelationIDFilter(logging.Filter):
    """Фильтр для добавления correlation_id в логи"""

    def filter(self, record):
        correlation_id = get_correlation_id()
        if correlation_id:
            record.correlation_id = correlation_id
        else:
            record.correlation_id = "N/A"
        return True
