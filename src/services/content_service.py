# services/content_service.py - Ротация шаблонов и CTA
import random
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import src.config as config
from src.core.database import get_postgres_db
from src.core.redis_cache import get_redis_cache

logger = logging.getLogger(__name__)

@dataclass
class ContentTemplate:
    """Шаблон контента с метаданными"""
    id: str
    template: str
    category: str  # 'general', 'discount', 'rating', 'new'
    weight: int = 1
    cta_required: bool = True

@dataclass
class CTA:
    """Call-to-Action вариант"""
    id: str
    text: str
    category: str  # 'urgent', 'normal', 'casual'
    emoji: str = ""
    weight: int = 1

class ContentService:
    """Сервис для генерации разнообразного контента"""

    def __init__(self):
        self.db = get_postgres_db() if config.USE_POSTGRES else None
        self.redis = get_redis_cache() if config.USE_REDIS else None

        # Предопределенные шаблоны
        self.templates = self._load_templates()

        # Предопределенные CTA
        self.ctas = self._load_ctas()

    def _load_templates(self) -> List[ContentTemplate]:
        """Загрузить шаблоны контента"""
        return [
            # Общие шаблоны
            ContentTemplate(
                id="general_1",
                template="🔥 {title} — {price} ₽{discount_text}\n\n{description}\n\n👉 {cta}",
                category="general",
                weight=3
            ),
            ContentTemplate(
                id="general_2",
                template="💎 Отличная находка: {title}\n\nЦена: {price} ₽{discount_text}\n{description}\n\n{cta}",
                category="general",
                weight=2
            ),
            ContentTemplate(
                id="general_3",
                template="{title} — топ выбор по цене {price} ₽{discount_text}\n\n{description}\n\n{cta} 🔥",
                category="general",
                weight=2
            ),

            # Шаблоны для скидок
            ContentTemplate(
                id="discount_1",
                template="💰 ВНИМАНИЕ! {title} со скидкой {discount_percent}%!\n\nБыло: {old_price} ₽\nСтало: {price} ₽\n\n{description}\n\n{cta}",
                category="discount",
                weight=4
            ),
            ContentTemplate(
                id="discount_2",
                template="🔥 ГОРЯЧАЯ СКИДКА! {title}\n\nЭкономия: {discount_amount} ₽ ({discount_percent}%)\nИтоговая цена: {price} ₽\n\n{description}\n\n{cta}",
                category="discount",
                weight=3
            ),

            # Шаблоны для товаров с высоким рейтингом
            ContentTemplate(
                id="rating_1",
                template="⭐ Топ-товар с рейтингом {rating}⭐\n\n{title}\nЦена: {price} ₽{discount_text}\n\n{description}\n\n{cta}",
                category="rating",
                weight=2
            ),

            # Шаблоны для новых товаров
            ContentTemplate(
                id="new_1",
                template="🆕 НОВИНКА! {title}\n\n{description}\n\nЦена: {price} ₽{discount_text}\n\n{cta}",
                category="new",
                weight=1
            ),
        ]

    def _load_ctas(self) -> List[CTA]:
        """Загрузить варианты CTA"""
        return [
            # Срочные CTA
            CTA(id="urgent_1", text="Заказать прямо сейчас!", category="urgent", emoji="🚀", weight=3),
            CTA(id="urgent_2", text="Успей забрать по акции!", category="urgent", emoji="⏰", weight=3),
            CTA(id="urgent_3", text="Ограниченное предложение!", category="urgent", emoji="🔥", weight=2),

            # Обычные CTA
            CTA(id="normal_1", text="Посмотреть на Маркете", category="normal", emoji="👀", weight=4),
            CTA(id="normal_2", text="Подробнее о товаре", category="normal", emoji="📋", weight=3),
            CTA(id="normal_3", text="Купить выгодно", category="normal", emoji="💳", weight=3),
            CTA(id="normal_4", text="Добавить в корзину", category="normal", emoji="🛒", weight=2),

            # Неформальные CTA
            CTA(id="casual_1", text="Взять не раздумывая", category="casual", emoji="😎", weight=2),
            CTA(id="casual_2", text="Идеальный вариант", category="casual", emoji="💯", weight=2),
            CTA(id="casual_3", text="Рекомендую к покупке", category="casual", emoji="👍", weight=1),
        ]

    def generate_content(self, product: Dict, description: str = "") -> Dict:
        """
        Сгенерировать контент для товара

        Args:
            product: Данные товара
            description: AI-generated описание (опционально)

        Returns:
            Dict: Сгенерированный контент
        """
        try:
            # Выбираем шаблон
            template = self._select_template(product)

            # Выбираем CTA
            cta = self._select_cta()

            # Подготавливаем переменные
            variables = self._prepare_variables(product, description, cta)

            # Генерируем текст поста
            post_text = template.template.format(**variables)

            # Ограничиваем длину поста
            if len(post_text) > 4000:  # Максимум для Telegram
                post_text = post_text[:3997] + "..."

            return {
                'post_text': post_text,
                'template_id': template.id,
                'template_category': template.category,
                'cta_id': cta.id,
                'cta_category': cta.category,
                'variables': variables
            }

        except Exception as e:
            logger.error(f"Error generating content for product {product.get('title', 'Unknown')}: {e}")
            # Fallback контент
            return self._generate_fallback_content(product)

    def _select_template(self, product: Dict) -> ContentTemplate:
        """Выбрать подходящий шаблон"""
        # Определяем категорию товара
        category = self._determine_product_category(product)

        # Фильтруем шаблоны по категории
        candidates = [t for t in self.templates if t.category == category or t.category == 'general']

        if not candidates:
            candidates = self.templates  # Fallback на все шаблоны

        # Выбираем с учётом весов
        weights = [t.weight for t in candidates]
        selected = random.choices(candidates, weights=weights, k=1)[0]

        return selected

    def _select_cta(self) -> CTA:
        """Выбрать CTA"""
        # Выбираем CTA с учётом весов
        weights = [cta.weight for cta in self.ctas]
        selected = random.choices(self.ctas, weights=weights, k=1)[0]

        return selected

    def _determine_product_category(self, product: Dict) -> str:
        """Определить категорию товара для выбора шаблона"""
        # Проверяем скидку
        discount = product.get('discount_percent', 0)
        if discount >= 20:
            return 'discount'

        # Проверяем рейтинг
        rating = product.get('rating', 0)
        if rating >= 4.5:
            return 'rating'

        # Проверяем новизну (пока просто рандомно)
        if random.random() < 0.1:  # 10% товаров считаем "новинками"
            return 'new'

        return 'general'

    def _prepare_variables(self, product: Dict, description: str, cta: CTA) -> Dict:
        """Подготовить переменные для шаблона"""
        variables = {}

        # Основные поля
        variables['title'] = product.get('title', 'Товар').strip()
        variables['price'] = self._format_price(product.get('price', 0))

        # Скидка
        discount_percent = product.get('discount_percent')
        old_price = product.get('old_price')

        if discount_percent and discount_percent > 0:
            variables['discount_text'] = f" (скидка {discount_percent:.0f}%)"
            variables['discount_percent'] = f"{discount_percent:.0f}"
            if old_price:
                discount_amount = old_price - product.get('price', 0)
                variables['discount_amount'] = f"{discount_amount:.0f}"
                variables['old_price'] = self._format_price(old_price)
        else:
            variables['discount_text'] = ""
            variables['discount_percent'] = "0"
            variables['discount_amount'] = "0"
            variables['old_price'] = variables['price']

        # Рейтинг
        rating = product.get('rating')
        if rating:
            variables['rating'] = f"{rating:.1f}"
        else:
            variables['rating'] = "0.0"

        # Описание
        if description:
            variables['description'] = description.strip()
        else:
            variables['description'] = "Качественный товар с хорошими отзывами покупателей."

        # CTA
        variables['cta'] = f"{cta.emoji} {cta.text}".strip()

        return variables

    def _format_price(self, price: float) -> str:
        """Форматировать цену"""
        if not price:
            return "0"

        try:
            # Форматируем с пробелами для тысяч
            return f"{int(price):,}".replace(",", " ")
        except (ValueError, TypeError):
            return str(price)

    def _generate_fallback_content(self, product: Dict) -> Dict:
        """Сгенерировать fallback контент при ошибке"""
        title = product.get('title', 'Товар')
        price = self._format_price(product.get('price', 0))

        post_text = f"🔥 {title}\n\n💰 Цена: {price} ₽\n\n👉 Посмотреть на Маркете"

        return {
            'post_text': post_text,
            'template_id': 'fallback',
            'template_category': 'fallback',
            'cta_id': 'fallback',
            'cta_category': 'fallback',
            'variables': {}
        }

    def get_template_stats(self) -> Dict:
        """Получить статистику использования шаблонов"""
        if not self.db:
            return {}

        try:
            # Получаем статистику из базы данных
            stats = self.db.get_metrics_summary(days=30)

            # Добавляем информацию о шаблонах
            template_info = {}
            for template in self.templates:
                template_info[template.id] = {
                    'category': template.category,
                    'weight': template.weight
                }

            cta_info = {}
            for cta in self.ctas:
                cta_info[cta.id] = {
                    'category': cta.category,
                    'weight': cta.weight,
                    'text': cta.text,
                    'emoji': cta.emoji
                }

            return {
                'overall_stats': stats,
                'templates': template_info,
                'ctas': cta_info
            }

        except Exception as e:
            logger.error(f"Error getting template stats: {e}")
            return {}

    def add_custom_template(self, template_id: str, template: str, category: str = 'general',
                          weight: int = 1, cta_required: bool = True):
        """Добавить кастомный шаблон"""
        try:
            custom_template = ContentTemplate(
                id=template_id,
                template=template,
                category=category,
                weight=weight,
                cta_required=cta_required
            )

            self.templates.append(custom_template)
            logger.info(f"Added custom template: {template_id}")

        except Exception as e:
            logger.error(f"Error adding custom template: {e}")

    def add_custom_cta(self, cta_id: str, text: str, category: str = 'normal',
                      emoji: str = "", weight: int = 1):
        """Добавить кастомный CTA"""
        try:
            custom_cta = CTA(
                id=cta_id,
                text=text,
                category=category,
                emoji=emoji,
                weight=weight
            )

            self.ctas.append(custom_cta)
            logger.info(f"Added custom CTA: {cta_id}")

        except Exception as e:
            logger.error(f"Error adding custom CTA: {e}")

# Глобальный экземпляр
_content_service = None

def get_content_service() -> ContentService:
    """Get global content service instance"""
    global _content_service
    if _content_service is None:
        _content_service = ContentService()
    return _content_service
