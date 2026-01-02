"""
Unified Retry Utilities - единый паттерн для всех retry-обёрток
Ограниченное количество попыток, экспоненциальный backoff, контролируемый возврат
"""

import asyncio
import logging
from typing import TypeVar, Callable, Optional, Tuple, Any
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryConfig:
    """Конфигурация для retry-обёрток"""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        """
        Args:
            max_attempts: Максимальное количество попыток
            base_delay: Базовая задержка в секундах
            max_delay: Максимальная задержка в секундах
            exponential_base: Основание для экспоненциального backoff
            jitter: Добавлять ли случайную задержку для предотвращения thundering herd
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter


DEFAULT_RETRY_CONFIG = RetryConfig(
    max_attempts=3, base_delay=1.0, max_delay=30.0, exponential_base=2.0, jitter=True
)


async def retry_with_backoff(
    func: Callable[..., T],
    *args,
    config: Optional[RetryConfig] = None,
    correlation_id: Optional[str] = None,
    error_context: Optional[str] = None,
    **kwargs,
) -> Tuple[bool, Optional[T], Optional[Exception]]:
    """
    Унифицированная retry-обёртка с экспоненциальным backoff.

    Контракт:
    - Успех: возвращает (True, result, None)
    - Провал: возвращает (False, None, last_error)
    - Никогда не выбрасывает исключения наверх (контролируемый возврат)

    Args:
        func: Асинхронная функция для выполнения
        *args: Позиционные аргументы для функции
        config: Конфигурация retry (по умолчанию DEFAULT_RETRY_CONFIG)
        correlation_id: ID для корреляции логов
        error_context: Контекст ошибки для логирования
        **kwargs: Именованные аргументы для функции

    Returns:
        Tuple (success: bool, result: Optional[T], last_error: Optional[Exception])
    """
    config = config or DEFAULT_RETRY_CONFIG
    correlation_id = correlation_id or "unknown"
    error_context = error_context or "operation"

    # Инициализация переменных результата ДО цикла (защита от UnboundLocalError)
    result: Optional[T] = None
    last_error: Optional[Exception] = None

    for attempt in range(config.max_attempts):
        try:
            result = await func(*args, **kwargs)

            # Проверяем, является ли результат валидным
            # (для функций, которые возвращают None при ошибке)
            if result is not None:
                logger.debug(
                    "retry_with_backoff: success on attempt %d/%d for %s (correlation_id=%s)",
                    attempt + 1,
                    config.max_attempts,
                    error_context,
                    correlation_id,
                )
                return True, result, None

            # Результат None - считаем это ошибкой для следующей попытки
            last_error = ValueError(f"{error_context} returned None")

        except asyncio.TimeoutError as e:
            last_error = e
            logger.warning(
                "retry_with_backoff: timeout on attempt %d/%d for %s (correlation_id=%s): %s",
                attempt + 1,
                config.max_attempts,
                error_context,
                correlation_id,
                str(e)[:200],
            )

        except Exception as e:
            last_error = e
            logger.warning(
                "retry_with_backoff: error on attempt %d/%d for %s (correlation_id=%s): %s",
                attempt + 1,
                config.max_attempts,
                error_context,
                correlation_id,
                str(e)[:200],
            )

        # Exponential backoff перед следующей попыткой
        if attempt < config.max_attempts - 1:
            delay = min(
                config.base_delay * (config.exponential_base**attempt), config.max_delay
            )

            # Добавляем jitter для предотвращения thundering herd
            if config.jitter:
                import random

                delay = delay * (0.5 + random.random() * 0.5)

            await asyncio.sleep(delay)

    # Все попытки исчерпаны - возвращаем контролируемый "фейл"
    logger.warning(
        "retry_with_backoff: failed after %d attempts for %s (correlation_id=%s, error=%s)",
        config.max_attempts,
        error_context,
        correlation_id,
        str(last_error)[:200] if last_error else "unknown",
    )

    return False, None, last_error


def create_retry_wrapper(
    config: Optional[RetryConfig] = None, error_context: Optional[str] = None
):
    """
    Создаёт декоратор для retry-обёртки.

    Usage:
        @create_retry_wrapper(config=RetryConfig(max_attempts=5), error_context="scraping")
        async def my_function(url: str):
            ...
            return result

    Args:
        config: Конфигурация retry
        error_context: Контекст ошибки для логирования

    Returns:
        Декоратор функции
    """

    def decorator(
        func: Callable[..., T],
    ) -> Callable[..., Tuple[bool, Optional[T], Optional[Exception]]]:
        @wraps(func)
        async def wrapper(*args, correlation_id: Optional[str] = None, **kwargs):
            return await retry_with_backoff(
                func,
                *args,
                config=config,
                correlation_id=correlation_id,
                error_context=error_context or func.__name__,
                **kwargs,
            )

        return wrapper

    return decorator
