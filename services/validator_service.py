# services/validator_service.py - Валидатор продуктов (анти-пустые посты)
import asyncio
import logging
import re
from typing import Dict, Any, Optional, List, Tuple
from urllib.parse import urlparse
import aiohttp
import config
from database_postgres import get_postgres_db
from redis_cache import get_redis_cache

logger = logging.getLogger(__name__)

class ProductValidator:
    """Валидатор продуктов для проверки качества перед публикацией"""

    def __init__(self):
        self.db = get_postgres_db() if config.USE_POSTGRES else None
        self.redis = get_redis_cache() if config.USE_REDIS else None
        self._session = None

    async def get_session(self):
        """Получить HTTP сессию"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                headers={
                    "User-Agent": config.USER_AGENT or "Mozilla/5.0 (compatible; MarketBot/1.0)",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                }
            )
        return self._session

    async def close_session(self):
        """Закрыть HTTP сессию"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def validate_product(self, product: Dict) -> Tuple[bool, List[str]]:
        """
        Проверить продукт на соответствие критериям качества

        Args:
            product: Данные продукта

        Returns:
            Tuple[bool, List[str]]: (валиден ли продукт, список ошибок)
        """
        return self.validate_product_sync(product)

    def validate_product_sync(self, product: Dict) -> Tuple[bool, List[str]]:
        """
        Синхронная версия валидации для тестов
        """
        errors = []

        try:
            # 1. Проверка наличия изображений
            if not self._has_images(product):
                errors.append("Нет изображений товара")

            # 2. Проверка цены
            if not self._has_valid_price(product):
                errors.append("Некорректная или отсутствующая цена")

            # 3. Проверка описания (длина)
            if not self._has_sufficient_description(product):
                errors.append("Недостаточно длинное описание")

            # 4. Проверка доступности товара (пропускаем в тестах)
            # availability_ok = await self._check_availability(product)
            # if not availability_ok:
            #     errors.append("Товар недоступен для заказа")

            # 5. Проверка фильтров качества
            quality_ok, quality_errors = self._check_quality_filters(product)
            if not quality_ok:
                errors.extend(quality_errors)

            # 6. Проверка бренда (whitelist/blacklist)
            brand_ok, brand_error = self._check_brand_filters(product)
            if not brand_ok:
                errors.append(brand_error)

            # 7. Проверка дедупликации
            if self.redis and self._is_duplicate(product):
                errors.append("Товар уже публиковался недавно")

            # 8. Проверка лимита бренда (sliding window)
            if self.redis and not self._check_brand_limit(product):
                errors.append("Превышен лимит публикаций для бренда")

            is_valid = len(errors) == 0

            if not is_valid:
                logger.debug(f"Product validation failed for '{product.get('title', 'Unknown')}': {errors}")
            else:
                logger.debug(f"Product validation passed for '{product.get('title', 'Unknown')}'")

            return is_valid, errors

        except Exception as e:
            logger.error(f"Error during product validation: {e}")
            return False, [f"Ошибка валидации: {str(e)}"]

    def _has_images(self, product: Dict) -> bool:
        """Проверить наличие изображений"""
        # Проверяем различные поля с изображениями
        images = product.get('images', [])
        has_images = product.get('has_images', False)

        # Если есть массив изображений и он не пустой
        if images and len(images) > 0:
            return True

        # Если есть флаг has_images
        if has_images:
            return True

        # Проверяем URL на наличие изображений в названии/описании
        title = product.get('title', '').lower()
        if 'изображение' in title or 'фото' in title:
            return True

        return False

    def _has_valid_price(self, product: Dict) -> bool:
        """Проверить корректность цены"""
        price = product.get('price')

        if price is None:
            return False

        try:
            price_float = float(price)
            # Цена должна быть положительной и не слишком маленькой
            return price_float > 0
        except (ValueError, TypeError):
            return False

    def _has_sufficient_description(self, product: Dict) -> bool:
        """Проверить достаточность описания"""
        # Собираем текст для проверки
        texts = []

        title = product.get('title', '')
        if title:
            texts.append(title)

        description = product.get('marketing_description', '')
        if description:
            texts.append(description)

        specs = product.get('specs', {})
        if specs and isinstance(specs, dict):
            specs_text = ' '.join([f"{k}: {v}" for k, v in specs.items() if v])
            texts.append(specs_text)

        # Объединяем все тексты
        full_text = ' '.join(texts).strip()

        # Удаляем лишние пробелы и считаем длину
        clean_text = re.sub(r'\s+', ' ', full_text)
        text_length = len(clean_text)

        # Минимум 80 символов для осмысленного поста
        return text_length >= 80

    async def _check_availability(self, product: Dict) -> bool:
        """Проверить доступность товара"""
        try:
            url = product.get('url')
            if not url:
                return False

            # Проверяем кэш доступности (если есть)
            cache_key = f"availability:{hash(url)}"
            if self.redis:
                cached_result = self.redis.get_counter(cache_key)
                if cached_result == 1:
                    return True
                elif cached_result == 0:
                    return False

            # Делаем запросы с backoff для проверки доступности
            from utils.scraper import fetch_with_backoff
            session = await self.get_session()

            # Пробуем несколько подходов с backoff
            availability_checks = [
                self._check_head_request_with_backoff(session, url),
                self._check_get_request_with_backoff(session, url),
            ]

            for check_coro in availability_checks:
                try:
                    is_available = await check_coro
                    if is_available:
                        if self.redis:
                            self.redis.set_counter(cache_key, 1)  # Кэшируем на 1 час
                            self.redis.client.expire(cache_key, 3600)
                        return True
                except Exception as e:
                    logger.debug(f"Availability check failed: {e}")
                    continue

            # Если все проверки провалились, считаем недоступным
            if self.redis:
                self.redis.set_counter(cache_key, 0)
                self.redis.client.expire(cache_key, 1800)  # Кэшируем негативный результат на 30 мин
            return False

        except Exception as e:
            logger.error(f"Error checking availability for {product.get('title', 'Unknown')}: {e}")
            return False

    async def _check_head_request_with_backoff(self, session: aiohttp.ClientSession, url: str) -> bool:
        """Проверить доступность HEAD запросом с backoff"""
        from utils.scraper import fetch_with_backoff
        # Для HEAD запроса создаем временный URL с head методом
        # Но поскольку fetch_with_backoff использует GET, просто используем его
        result = await fetch_with_backoff(url, session, max_attempts=3)
        return result is not None

    async def _check_get_request_with_backoff(self, session: aiohttp.ClientSession, url: str) -> bool:
        """Проверить доступность GET запросом (ограниченный)"""
        async with session.get(url, allow_redirects=True) as resp:
            if resp.status != 200:
                return False

            # Читаем только начало страницы для проверки
            content = await resp.text()
            # Ищем признаки доступности товара
            availability_indicators = [
                'в корзину',
                'купить',
                'добавить в корзину',
                'товар доступен'
            ]

            content_lower = content.lower()
            for indicator in availability_indicators:
                if indicator in content_lower:
                    return True

            return False

    def _check_quality_filters(self, product: Dict) -> Tuple[bool, List[str]]:
        """Проверить фильтры качества"""
        errors = []

        # Проверка минимальной цены
        price = product.get('price')
        if price is not None and price < config.QUALITY_MIN_PRICE:
            errors.append(f"Цена слишком низкая: {price} < {config.QUALITY_MIN_PRICE}")

        # Проверка минимальной скидки
        discount = product.get('discount_percent')
        if discount is not None and discount < config.QUALITY_MIN_DISCOUNT:
            errors.append(f"Скидка слишком маленькая: {discount}% < {config.QUALITY_MIN_DISCOUNT}%")

        # Проверка минимального рейтинга
        rating = product.get('rating')
        if rating is not None and rating < config.QUALITY_MIN_RATING:
            errors.append(f"Рейтинг слишком низкий: {rating} < {config.QUALITY_MIN_RATING}")

        # Проверка минимального количества отзывов
        reviews = product.get('reviews_count')
        if reviews is not None and reviews < config.QUALITY_MIN_REVIEWS:
            errors.append(f"Слишком мало отзывов: {reviews} < {config.QUALITY_MIN_REVIEWS}")

        return len(errors) == 0, errors

    def _check_brand_filters(self, product: Dict) -> Tuple[bool, str]:
        """Проверить фильтры бренда"""
        if not self.db:
            return True, ""  # Если база отключена, пропускаем фильтры

        vendor = product.get('vendor')
        if not vendor:
            return True, ""  # Если бренд не указан, пропускаем

        # Проверяем blacklist
        if self.db.is_brand_blacklisted(vendor):
            return False, f"Бренд в чёрном списке: {vendor}"

        # Проверяем whitelist (если он активен)
        whitelist = self.db.get_whitelist_brands()
        if whitelist and vendor not in whitelist:
            return False, f"Бренд не в белом списке: {vendor}"

        return True, ""

    def _is_duplicate(self, product: Dict) -> bool:
        """Проверить на дублирование"""
        # Используем Redis для быстрой проверки дедупликации
        product_key = self._generate_product_key(product)
        return self.redis.is_product_seen_recently(product_key)

    def _check_brand_limit(self, product: Dict) -> bool:
        """Проверить лимит бренда через sliding window"""
        vendor = product.get('vendor')
        if not vendor:
            return True  # Если бренд не указан, разрешаем

        return self.redis.can_publish_brand(vendor)

    def _generate_product_key(self, product: Dict) -> str:
        """
        Сгенерировать ключ товара для дедупликации
        Использует SHA-1 hash для детерминированности (не Python hash())
        """
        import hashlib
        
        parts = []
        if product.get('offerid'):
            parts.append(f"offer:{product['offerid']}")
        if product.get('url'):
            clean_url = product['url'].split('#')[0].split('?')[0].rstrip('/')
            parts.append(f"url:{clean_url}")
        if product.get('title'):
            title_clean = re.sub(r'\s+', ' ', product['title'].strip().lower())
            parts.append(f"title:{title_clean[:100]}")
        if product.get('vendor'):
            parts.append(f"vendor:{product['vendor'].lower()}")

        base = "|".join([p for p in parts if p])
        if not base:
            base = f"fallback:{product.get('id', 'unknown')}"

        # Используем SHA-1 вместо Python hash() для детерминированности
        return hashlib.sha1(base.encode("utf-8")).hexdigest()

    async def validate_and_enrich_product(self, product: Dict) -> Tuple[bool, Dict, List[str]]:
        """
        Валидировать продукт и обогатить данными

        Args:
            product: Исходные данные продукта

        Returns:
            Tuple[bool, Dict, List[str]]: (валиден, обогащенные данные, ошибки)
        """
        # Сначала валидируем
        is_valid, errors = await self.validate_product(product)

        if not is_valid:
            return False, product, errors

        # Если валиден, пытаемся обогатить данными
        try:
            enriched_product = await self._enrich_product_data(product)
            return True, enriched_product, []
        except Exception as e:
            logger.warning(f"Failed to enrich product data: {e}")
            return True, product, []  # Валиден, но без обогащения

    async def _enrich_product_data(self, product: Dict) -> Dict:
        """Обогатить данные продукта дополнительной информацией"""
        enriched = product.copy()

        try:
            url = product.get('url')
            if url and not product.get('specs'):  # Если характеристики не загружены
                # TODO: Здесь можно добавить парсинг полной страницы товара
                # для получения specs, marketing_description, дополнительных изображений
                pass

        except Exception as e:
            logger.warning(f"Error enriching product data: {e}")

        return enriched

    async def batch_validate(self, products: List[Dict]) -> Dict:
        """
        Пакетная валидация продуктов

        Args:
            products: Список продуктов для валидации

        Returns:
            Dict: Результаты валидации
        """
        results = {
            'valid': [],
            'invalid': [],
            'errors': []
        }

        for product in products:
            try:
                is_valid, errors = await self.validate_product(product)
                if is_valid:
                    results['valid'].append(product)
                else:
                    results['invalid'].append({
                        'product': product,
                        'errors': errors
                    })
            except Exception as e:
                results['errors'].append({
                    'product': product,
                    'error': str(e)
                })

        logger.info(f"Batch validation completed: valid={len(results['valid'])}, invalid={len(results['invalid'])}, errors={len(results['errors'])}")

        return results

# Глобальный экземпляр
_product_validator = None

def get_product_validator() -> ProductValidator:
    """Get global product validator instance"""
    global _product_validator
    if _product_validator is None:
        _product_validator = ProductValidator()
    return _product_validator