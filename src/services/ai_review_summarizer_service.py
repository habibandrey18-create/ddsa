"""
AI Review Summarizer Service - использование OpenAI API для суммирования отзывов пользователей
в маркетинговый текст с ключевыми преимуществами
"""

import logging
import asyncio
from typing import Optional, List, TYPE_CHECKING

import src.config as config

if TYPE_CHECKING:
    from openai import AsyncOpenAI  # type: ignore

logger = logging.getLogger(__name__)

# Инициализация клиента OpenAI (опционально)
_client: Optional["AsyncOpenAI"] = None
_openai_available = False

# Попытка импорта OpenAI
try:
    from openai import AsyncOpenAI  # type: ignore
    _openai_available = True
except ImportError:
    logger.warning("OpenAI package not installed. AI review summarizer service will be disabled.")
    AsyncOpenAI = None  # Для type hints
    _openai_available = False


def _get_client() -> Optional[object]:
    """Получает или создает клиент OpenAI"""
    global _client

    # Check if OpenAI is available
    if not _openai_available:
        logger.debug("OpenAI not available, AI review summarizer service disabled")
        return None

    if _client is None:
        api_key = config.CHATGPT_API_KEY
        if not api_key:
            logger.warning(
                "CHATGPT_API_KEY not found. AI review summarizer service will be disabled."
            )
            return None
        try:
            _client = AsyncOpenAI(api_key=api_key)
        except Exception as e:
            logger.warning(f"Failed to create OpenAI client: {e}. AI review summarizer service disabled.")
            return None
    return _client


async def summarize_reviews_with_openai(reviews: List[str]) -> Optional[str]:
    """
    Суммирует отзывы пользователей через OpenAI API в один убедительный маркетинговый текст.

    Эта функция выполняет следующие действия:
    1. Валидирует входные данные (пустой список или None)
    2. Формирует специальный промпт для маркетингового копирайтера
    3. Отправляет запрос в OpenAI API с таймаутом
    4. Возвращает сгенерированный текст или None при ошибке

    Args:
        reviews: Список строк с отзывами пользователей

    Returns:
        Optional[str]: Суммированный текст с 1-2 ключевыми преимуществами в одном предложении,
                      или None при ошибке/пустом списке/недоступности сервиса
    """
    client = _get_client()
    if not client:
        logger.debug("AI review summarizer service disabled, returning None")
        return None

    # Валидация входных данных
    if not reviews or len(reviews) == 0:
        logger.debug("Empty reviews list provided")
        return None

    # Форматирование отзывов для промпта
    # Каждый отзыв оборачивается в кавычки для четкого разделения
    reviews_formatted: str = "\n".join(f'- "{review}"' for review in reviews)

    # Системный промпт: определяет роль AI как маркетингового копирайтера
    # Фокус на извлечении аутентичных, конкретных преимуществ из отзывов
    # Исключает общие фразы типа "great product", фокусируется на специфике
    system_prompt: str = (
        "As a marketing copywriter, analyze these user reviews for a product. "
        "Extract 1-2 key positive points that sound authentic and human. "
        "Focus on specific benefits mentioned by users (e.g., 'crispy crust', 'quiet operation', 'easy to clean'), "
        "not generic phrases. Combine them into one compelling sentence."
    )

    # Пользовательский промпт: содержит отформатированные отзывы
    user_prompt: str = f"Reviews:\n{reviews_formatted}"

    try:
        # Выполняем асинхронный запрос к OpenAI API с таймаутом 3 секунды
        # Используем asyncio.wait_for для предотвращения зависания
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=config.CHATGPT_MODEL,  # gpt-4o или другая модель из конфига
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=100,  # Ограничение длины ответа
                temperature=0.7,  # Средняя креативность для естественного текста
            ),
            timeout=3.0,  # Таймаут в секундах
        )

        # Проверяем и извлекаем ответ от OpenAI
        if response.choices and len(response.choices) > 0:
            summary: str = response.choices[0].message.content.strip()
            # Валидация ответа: не пустой и не слишком короткий
            if summary and len(summary) > 5:
                logger.debug(f"AI review summary generated successfully: {summary[:100]}...")
                return summary

        # Обработка некорректного ответа от API
        logger.warning("AI returned empty or too short review summary")
        return None

    except asyncio.TimeoutError:
        # Специфическая обработка таймаута API
        logger.warning("AI review summarization timeout (3s) - OpenAI API may be slow or unavailable")
        return None
    except Exception as e:
        # Общая обработка ошибок API (сетевые проблемы, аутентификация, etc.)
        logger.warning(f"AI review summarization error: {e}")
        return None
