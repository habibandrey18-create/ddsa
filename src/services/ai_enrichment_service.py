"""
AI Enrichment Service - использование ChatGPT 5.1 для обогащения данных о товарах
"""

import logging
import json
import os
import time
import asyncio
from typing import Dict, Any, Optional
import aiohttp
from dotenv import load_dotenv

from src.services.ai_result_validator import (
    AiResultValidator,
    ValidatedResult,
    InvalidResult,
)
from src.services.ai_cache import get_ai_cache
from src.services.ai_metrics import get_ai_metrics

load_dotenv()

logger = logging.getLogger(__name__)

# API ключ из .env
CHATGPT_API_KEY = os.getenv("CHATGPT_API_KEY") or os.getenv("OPENAI_API_KEY")
CHATGPT_API_URL = os.getenv(
    "CHATGPT_API_URL", "https://api.openai.com/v1/chat/completions"
)
CHATGPT_MODEL = os.getenv(
    "CHATGPT_MODEL", "gpt-4o"
)  # Можно указать gpt-5.1 когда будет доступен


class AiEnrichmentService:
    """
    Сервис для обогащения данных о товарах через ChatGPT 5.1
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Инициализация сервиса

        Args:
            api_key: API ключ ChatGPT (если не указан, берется из .env)
        """
        self.api_key = api_key or CHATGPT_API_KEY
        self.api_url = CHATGPT_API_URL
        self.model = CHATGPT_MODEL
        self.enabled = bool(self.api_key)
        self.validator = AiResultValidator()
        self.cache = get_ai_cache()
        self.metrics = get_ai_metrics()
        self.request_timeout = 8  # Таймаут 8 секунд
        self.rate_limit_per_minute = 10  # Максимум 10 запросов в минуту
        self._request_times = []  # Временные метки последних запросов

        if not self.enabled:
            logger.warning("ChatGPT API key not found. AI enrichment will be disabled.")

    def _build_prompt(self, raw_data: Dict[str, Any]) -> str:
        """
        Формирует промпт для ChatGPT

        Args:
            raw_data: Сырые данные о товаре

        Returns:
            Текст промпта
        """
        url = raw_data.get("url", "")
        final_url = raw_data.get("final_url", url)
        raw_html = raw_data.get("raw_html", "")
        raw_price = raw_data.get("raw_price", "")
        raw_title = raw_data.get("raw_title", "")
        cc_code = raw_data.get("cc_code", "")
        cc_tail = raw_data.get("cc_tail", "")

        prompt = f"""Ты анализируешь данные товара с Яндекс.Маркета.

Исходные данные:
- URL: {url}
- Финальный URL после редиректов: {final_url}
- Найденный CC код: {cc_code if cc_code else "не найден"}
- Найденный CC хвост: {cc_tail if cc_tail else "не найден"}
- Сырая цена: {raw_price if raw_price else "не найдена"}
- Сырой заголовок: {raw_title if raw_title else "не найден"}

HTML фрагмент карточки товара:
{raw_html[:2000] if raw_html else "не предоставлен"}

Задача:
1. Нормализовать product_url - извлечь чистый URL карточки товара (https://market.yandex.ru/card/... или https://market.yandex.ru/product/...)
2. Если найден CC код или хвост - собрать ref_link вида https://market.yandex.ru/cc/<код> (обрезать хвосты по запятую)
3. Извлечь цену как число (только цифры, без валюты и пробелов)
4. Извлечь название товара (чистый текст, без лишних символов)
5. Определить, валиден ли товар (есть название, цена, корректный URL)

Верни ТОЛЬКО валидный JSON без дополнительного текста:
{{
    "product_url": "https://market.yandex.ru/card/...",
    "ref_link": "https://market.yandex.ru/cc/..." или null,
    "price": 159 или null,
    "title": "Название товара" или null,
    "is_valid": true или false,
    "notes": "Причина если is_valid=false"
}}"""

        return prompt

    def _check_rate_limit(self) -> bool:
        """
        Проверить rate limit

        Returns:
            True если можно делать запрос
        """
        now = time.time()
        # Удаляем запросы старше минуты
        self._request_times = [t for t in self._request_times if now - t < 60]

        if len(self._request_times) >= self.rate_limit_per_minute:
            logger.warning(
                f"Rate limit exceeded: {len(self._request_times)} requests in last minute"
            )
            return False

        return True

    def _record_request(self):
        """Записать время запроса"""
        self._request_times.append(time.time())

    async def enrich_product(
        self, raw_data: Dict[str, Any], use_cache: bool = True
    ) -> Optional[ValidatedResult]:
        """
        Обогащает данные о товаре через ChatGPT с валидацией и кэшированием

        Args:
            raw_data: Сырые данные о товаре
            use_cache: Использовать ли кэш

        Returns:
            ValidatedResult или None при ошибке
        """
        if not self.enabled:
            logger.debug("AI enrichment disabled, skipping")
            return None

        # Проверка лимита стоимости
        if self.metrics.should_disable_ai():
            logger.warning("AI disabled due to cost limit")
            return None

        url = raw_data.get("url", "")
        final_url = raw_data.get("final_url", url)
        product_id = raw_data.get("product_id")

        # Проверка кэша
        if use_cache:
            cached = self.cache.get(final_url, product_id)
            if cached:
                logger.debug("Using cached AI result")
                # Валидируем кэшированный результат
                is_valid, validated, invalid = self.validator.validate(cached, raw_data)
                if is_valid and validated:
                    validated.source = "cache"
                    return validated
                else:
                    logger.warning("Cached result failed validation, will re-request")

        # Проверка rate limit
        if not self._check_rate_limit():
            logger.warning("Rate limit exceeded, skipping AI request")
            return None

        start_time = time.time()

        try:
            # Логируем вход (сокращенно)
            logger.info(
                f"AI request: url={url[:50]}, html_len={len(raw_data.get('raw_html', ''))}, price={raw_data.get('raw_price', '')[:30]}"
            )

            prompt = self._build_prompt(raw_data)

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "Ты эксперт по анализу данных с Яндекс.Маркета. Всегда возвращай только валидный JSON без дополнительного текста.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 500,
            }

            self._record_request()

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.request_timeout),
                ) as response:
                    duration_ms = (time.time() - start_time) * 1000
                    self.metrics.record_timing(duration_ms)

                    if response.status >= 500:
                        # HTTP 5xx - пробуем еще раз
                        logger.warning(
                            f"ChatGPT API 5xx error {response.status}, retrying once..."
                        )
                        await asyncio.sleep(1)
                        async with session.post(
                            self.api_url,
                            headers=headers,
                            json=payload,
                            timeout=aiohttp.ClientTimeout(total=self.request_timeout),
                        ) as retry_response:
                            if retry_response.status != 200:
                                error_text = await retry_response.text()
                                logger.warning(
                                    f"ChatGPT API retry failed {retry_response.status}: {error_text[:200]}"
                                )
                                self.metrics.record_ai_error("http_5xx")
                                return None
                            response = retry_response

                    if response.status != 200:
                        error_text = await response.text()
                        logger.warning(
                            f"ChatGPT API error {response.status}: {error_text[:200]}"
                        )
                        self.metrics.record_ai_error(f"http_{response.status}")
                        return None

                    result = await response.json()

                    # Извлекаем токены для оценки стоимости
                    usage = result.get("usage", {})
                    tokens = usage.get("total_tokens", 0)
                    # Примерная стоимость: $0.01 за 1K токенов для gpt-4o
                    cost = (tokens / 1000) * 0.01

                    # Извлекаем ответ из choices[0].message.content
                    if "choices" not in result or not result["choices"]:
                        logger.warning("ChatGPT API returned no choices")
                        self.metrics.record_ai_error("no_choices")
                        return None

                    content = result["choices"][0]["message"]["content"]

                    # Логируем выход (сокращенно)
                    logger.info(f"AI response: {content[:500]}")

                    # Парсим JSON из ответа
                    content = content.strip()
                    if content.startswith("```json"):
                        content = content[7:]
                    if content.startswith("```"):
                        content = content[3:]
                    if content.endswith("```"):
                        content = content[:-3]
                    content = content.strip()

                    parsed = json.loads(content)

                    # Валидация структуры ответа
                    required_fields = [
                        "product_url",
                        "ref_link",
                        "price",
                        "title",
                        "is_valid",
                    ]
                    if not all(field in parsed for field in required_fields):
                        logger.warning(
                            f"ChatGPT returned incomplete data: {list(parsed.keys())}"
                        )
                        self.metrics.record_ai_error("incomplete_data")
                        return None

                    # Валидация результата
                    is_valid, validated, invalid = self.validator.validate(
                        parsed, raw_data
                    )

                    if is_valid and validated:
                        # Сохраняем в кэш
                        if use_cache:
                            self.cache.set(final_url, parsed, product_id)

                        # Записываем метрики
                        self.metrics.record_ai_ok(tokens, cost)

                        logger.info(
                            f"AI enrichment successful: is_valid={validated.is_valid}, has_ref={bool(validated.ref_link)}"
                        )
                        return validated
                    else:
                        # Валидация не прошла
                        reason = invalid.reason if invalid else "validation_failed"
                        logger.warning(f"AI result validation failed: {reason}")
                        self.metrics.record_ai_fallback(reason)
                        return None

        except asyncio.TimeoutError:
            duration_ms = (time.time() - start_time) * 1000
            self.metrics.record_timing(duration_ms)
            logger.warning(f"ChatGPT API timeout after {duration_ms:.0f}ms")
            self.metrics.record_ai_error("timeout")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse ChatGPT JSON response: {e}")
            self.metrics.record_ai_error("json_parse")
            return None
        except aiohttp.ClientError as e:
            logger.warning(f"ChatGPT API request failed: {e}")
            self.metrics.record_ai_error("client_error")
            return None
        except Exception as e:
            logger.error(f"AI enrichment error: {e}", exc_info=True)
            self.metrics.record_ai_error("unknown")
            return None

    async def enrich_product_safe(
        self, raw_data: Dict[str, Any], use_cache: bool = True
    ) -> Optional[ValidatedResult]:
        """
        Безопасная обертка с таймаутом и обработкой ошибок

        Args:
            raw_data: Сырые данные о товаре
            use_cache: Использовать ли кэш

        Returns:
            ValidatedResult или None
        """
        try:
            return await self.enrich_product(raw_data, use_cache=use_cache)
        except Exception as e:
            logger.debug(f"AI enrichment failed safely: {e}")
            self.metrics.record_ai_error("exception")
            return None


# Глобальный экземпляр сервиса
_ai_service: Optional[AiEnrichmentService] = None


def get_ai_enrichment_service() -> AiEnrichmentService:
    """
    Получить глобальный экземпляр AI сервиса

    Returns:
        Экземпляр AiEnrichmentService
    """
    global _ai_service
    if _ai_service is None:
        _ai_service = AiEnrichmentService()
    return _ai_service
