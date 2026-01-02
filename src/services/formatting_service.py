# services/formatting_service.py
"""Service for formatting product posts with AI-generated descriptions"""
import logging
import random
import re
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse, parse_qs

from .ai_content_service import get_ai_content_service
try:
    from src.config import HASHTAG_COUNT
except ImportError:
    HASHTAG_COUNT = 5

logger = logging.getLogger(__name__)

# Типы постов для ротации (чтобы не выглядеть как шаблон)
POST_TYPES = [
    "sell",      # продажный
    "review",    # от лица пользователя
    "compare",   # сравнение
    "tip"        # совет / польза
]

# Шаблоны для каждого типа поста
TEMPLATES = {
    "sell": [
        "🔥 {title}\n💰 Цена: {price} ₽\n⭐ Рейтинг: {rating} ({reviews} отзывов)\n\n👉 Смотреть на Маркете\n{affiliate_link}\n\n{hashtags}",
        "🚀 Успей купить {title}!\n💰 Всего {price} ₽\n⭐ {rating}/5 звезд ({reviews} отзывов)\n\n👉 Смотреть на Маркете\n{affiliate_link}\n\n{hashtags}",
        "⭐ Специальное предложение: {title}\n💰 Цена: {price} ₽\n⭐ Рейтинг {rating} ({reviews} отзывов)\n\n👉 Смотреть на Маркете\n{affiliate_link}\n\n{hashtags}"
    ],
    "review": [
        "Часто спрашивают, стоит ли брать {title}\n\nЕсли коротко:\n— норм сборка\n— рейтинг {rating}\n— за свои деньги ок\n\n💰 Цена: {price} ₽\n\n👉 Проверить цену\n{affiliate_link}\n\n{hashtags}",
        "Решил поделиться мнением о {title}\n\nПлюсы:\n— цена {price} ₽\n— рейтинг {rating}/5\n— {reviews} отзывов\n\n👉 Смотреть на Маркете\n{affiliate_link}\n\n{hashtags}",
        "{title} — что думаю после изучения:\n\nЦена: {price} ₽\nРейтинг: {rating}\nОтзывы: {reviews}\n\n👉 Посмотреть отзывы\n{affiliate_link}\n\n{hashtags}"
    ],
    "compare": [
        "Если выбираешь между {title} и аналогами —\nэтот вариант сейчас выгоднее по цене.\n\n💰 {price} ₽\n⭐ {rating}/5\n\n👉 Смотреть на Маркете\n{affiliate_link}\n\n{hashtags}",
        "Сравнивал {title} с конкурентами.\nЭтот вариант:\n— дешевле на {discount_percent}%\n— рейтинг {rating}\n— цена {price} ₽\n\n👉 Смотреть на Маркете\n{affiliate_link}\n\n{hashtags}",
        "{title} vs аналоги:\n\nПо цене: {price} ₽\nПо рейтингу: {rating}/5\nПо отзывам: {reviews}\n\n👉 Сравнить самому\n{affiliate_link}\n\n{hashtags}"
    ],
    "tip": [
        "Совет: не берите {category} без отзывов < 50.\nЛучше переплатить 200–300 ₽.\n\nСегодня норм вариант попадался 👇\n{affiliate_link}\n\n{hashtags}",
        "Лайфхак: {title} можно найти за {price} ₽\nс рейтингом {rating}.\n\nНе всегда дешево = плохо 👇\n{affiliate_link}\n\n{hashtags}",
        "Топчик по соотношению цена/качество:\n{title}\n💰 {price} ₽\n⭐ {rating}/5\n\n👉 Проверить\n{affiliate_link}\n\n{hashtags}"
    ]
}

# Blacklist нежелательных хэштегов
HASHTAG_BLACKLIST = {"товар", "купить", "цена", "новый", "старый", "б/у", "дешевый", "дорогой", "скидка", "акция", "распродажа"}

# Кэш последнего типа поста для ротации
_last_post_type = None


def generate_hashtags(product_name: str, keywords: list, hashtag_count: int = HASHTAG_COUNT) -> list:
    """
    Генерирует уникальные хэштеги из ключевых слов и названия товара.
    """
    tags = set()

    # Добавляем ключевые слова
    for kw in keywords:
        clean_kw = re.sub(r'[^\w\s-]', '', kw.strip().lower())
        if clean_kw and clean_kw not in HASHTAG_BLACKLIST and len(clean_kw) > 2:
            tags.add(f"#{clean_kw}")

    # Добавляем слова из названия товара
    for word in product_name.split():
        clean_word = re.sub(r'[^\w\s-]', '', word.strip().lower())
        if clean_word and clean_word not in HASHTAG_BLACKLIST and len(clean_word) > 2:
            tags.add(f"#{clean_word}")

    return list(tags)[:hashtag_count]


def format_post_simple(title: str, price: float, affiliate_link: str, product_name: str, keywords: list) -> str:
    """
    Форматирует текст поста, вставляя заголовок, цену, ссылку и хэштеги в шаблон.
    """
    template = random.choice(TEMPLATES)
    hashtags = " ".join(generate_hashtags(product_name, keywords))
    content = template.format(title=title, price=price, affiliate_link=affiliate_link, hashtags=hashtags)
    return content


class FormattingService:
    """Service for formatting product posts"""

    def __init__(self):
        """Initialize the formatting service"""
        pass

    async def format_product_post(self, product_data: Dict[str, Any]) -> str:
        """
        Format a complete product post with AI-generated description and hashtags.

        Args:
            product_data: Dictionary containing product information with keys:
                - title: Product title
                - price: Product price (string or numeric)
                - url: Product URL
                - reviews: Optional list of review texts

        Returns:
            Formatted post text ready for publishing
        """
        try:
            # Extract data with defaults
            title = product_data.get('title', 'Без названия').strip()
            price = product_data.get('price', 'Цена не указана')
            url = product_data.get('url', '').strip()
            reviews = product_data.get('reviews', [])

            # Ensure price is properly formatted
            if isinstance(price, (int, float)):
                price = f"{price} ₽"
            elif isinstance(price, str) and not price.endswith('₽'):
                # Clean up any double ₽ symbols
                price = price.replace('₽₽', '₽').strip()
                if not price.endswith('₽'):
                    price = f"{price} ₽"

            # Get AI-generated description using dynamic strategies
            ai_description = await self._generate_ai_description(product_data)

            # Выбираем тип поста для ротации (чтобы не выглядеть как шаблон)
            global _last_post_type
            available_types = [t for t in POST_TYPES if t != _last_post_type]
            current_post_type = random.choice(available_types) if available_types else random.choice(POST_TYPES)
            _last_post_type = current_post_type

            # Получаем шаблоны для выбранного типа
            type_templates = TEMPLATES.get(current_post_type, TEMPLATES["sell"])
            template = random.choice(type_templates)

            # Подготавливаем данные для шаблона
            rating = product_data.get('rating', 0)
            reviews_count = product_data.get('reviews_count', 0)
            discount_percent = product_data.get('discount_percent', 0)
            category = product_data.get('category', 'товар')

            # Генерируем хэштеги (только 2-4, не больше)
            hashtags = self._generate_hashtags(title, max_hashtags=4)

            # Форматируем пост
            caption = template.format(
                title=title,
                price=price,
                rating=f"{rating:.1f}" if rating > 0 else "N/A",
                reviews=reviews_count,
                discount_percent=discount_percent,
                category=category,
                affiliate_link=url,  # URL уже содержит affiliate параметры
                hashtags=hashtags
            )

            caption = "\n\n".join(post_parts)

            # Add ad marking text with ERID from affiliate link
            erid = product_data.get('erid')
            if erid:
                from .affiliate_service import get_ad_marking_text
                ad_marking = get_ad_marking_text(erid)
                caption += ad_marking

            return caption

        except Exception as e:
            logger.exception(f"❌ Error formatting product post: {e}")
            # Return a basic fallback format
            title = product_data.get('title', 'Без названия')
            url = product_data.get('url', '')
            return f"🔥 {title}\n\n👉 Смотреть на Маркете ({url})"

    async def _generate_ai_description(self, product_data: Dict[str, Any]) -> str:
        """
        Generate AI description using dynamic strategies or fallback text.

        Args:
            product_data: Complete product data dictionary

        Returns:
            AI-generated description or fallback text
        """
        try:
            ai_service = get_ai_content_service()
            if ai_service:
                return await ai_service.generate_dynamic_description(product_data)
            else:
                logger.debug("AI service not available, using fallback description")
                return "Качественный товар с хорошими отзывами покупателей."
        except Exception as e:
            logger.warning(f"Failed to generate AI description, using fallback: {e}")
            return "Качественный товар с хорошими отзывами покупателей."

    def _generate_hashtags(self, title: str, max_hashtags: int = 4) -> str:
        """
        Generate relevant hashtags from product title.

        Args:
            title: Product title
            max_hashtags: Maximum number of hashtags (default 4)

        Returns:
            String of hashtags separated by spaces
        """
        try:
            # Split title into words and filter out short/common words
            words = title.split()
            relevant_words = []

            # Filter words: keep those longer than 2 chars, not numbers
            for word in words[:4]:  # Take first 4 words max
                word = word.lower().strip('.,!?()[]{}')
                if len(word) > 2 and not word.isdigit():
                    relevant_words.append(f"#{word}")

            # Add the general purchase hashtag
            relevant_words.append("#покупки")

            # Limit to max_hashtags total
            hashtags = relevant_words[:max_hashtags]

            return " ".join(hashtags)

        except Exception as e:
            logger.warning(f"Error generating hashtags: {e}")
            return "#покупки"

    def extract_market_link(self, url: str) -> str:
        """
        Extract clean Market link from potentially messy URL.

        Args:
            url: Original URL (potentially with tracking parameters)

        Returns:
            Clean Market URL
        """
        try:
            parsed = urlparse(url)
            if 'market.yandex.ru' in parsed.netloc:
                # Keep only essential parameters for Market URLs
                query_params = parse_qs(parsed.query)
                clean_params = {}

                # Keep important Market parameters
                important_params = ['clid', 'nid', 'lr', 'sku']
                for param in important_params:
                    if param in query_params:
                        clean_params[param] = query_params[param][0]

                if clean_params:
                    from urllib.parse import urlencode
                    query_string = urlencode(clean_params)
                    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{query_string}"
                else:
                    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

            return url  # Return as-is if not a Market URL

        except Exception as e:
            logger.warning(f"Error extracting Market link: {e}")
            return url


# Global instance
formatting_service = FormattingService()


def get_formatting_service() -> FormattingService:
    """Get the global formatting service instance"""
    return formatting_service
