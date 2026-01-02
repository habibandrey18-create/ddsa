# services/ai_content_service.py
"""AI content generation service using Groq API with dynamic strategies"""
import logging
import random
from typing import Dict, Any, Optional, List
from groq import AsyncGroq

logger = logging.getLogger(__name__)


class AIContentService:
    """Service for generating dynamic product descriptions using Groq AI with multiple strategies"""

    def __init__(self, groq_api_key: Optional[str] = None):
        """
        Initialize the AI content service.

        Args:
            groq_api_key: Groq API key. If None, service will not work.
        """
        self.api_key = groq_api_key
        self.client = None

        if groq_api_key:
            try:
                self.client = AsyncGroq(api_key=groq_api_key)
                logger.info("✅ AsyncGroq client initialized successfully")
            except Exception as e:
                logger.error(f"❌ Failed to initialize AsyncGroq client: {e}")
                self.client = None
        else:
            logger.warning("⚠️ No Groq API key provided - AI descriptions will be disabled")

    async def generate_dynamic_description(self, product_data: Dict[str, Any]) -> str:
        """
        Generate a dynamic product description using one of four random strategies.

        Args:
            product_data: Dictionary containing product information with keys:
                - title: Product title
                - reviews: Optional list of customer reviews
                - specs: Optional product specifications
                - marketing_description: Optional marketing description

        Returns:
            Dynamic product description, or fallback text if AI fails
        """
        if not self.client:
            logger.debug("Groq client not available, returning fallback description")
            return "Качественный товар с хорошими отзывами покупателей."

        strategies = [
            self._strategy_reviews_summary,
            self._strategy_key_feature,
            self._strategy_buyer_persona,
            self._strategy_human_translation
        ]

        chosen_strategy = random.choice(strategies)
        strategy_name = chosen_strategy.__name__.replace('_strategy_', '')

        try:
            logger.debug(f"Using strategy: {strategy_name} for product: {product_data.get('title', 'Unknown')}")
            description = await chosen_strategy(product_data)
            logger.debug(f"Generated description using {strategy_name}: {description[:100]}...")
            return description
        except Exception as e:
            logger.warning(f"❌ Failed to generate AI description using {strategy_name}: {e}")
            return "Качественный товар с хорошими отзывами покупателей."

    # --- Strategy 1: Reviews Summary ---
    async def _strategy_reviews_summary(self, data: Dict[str, Any]) -> str:
        """Analyze customer reviews and create a summary description."""
        reviews = data.get('reviews', [])
        if not reviews:
            # Fallback to key feature strategy if no reviews
            return await self._strategy_key_feature(data)

        title = data.get('title', 'Товар')
        prompt = f"""
        Проанализируй эти отзывы покупателей о товаре '{title}'. Выдели 1-2 самых частых положительных момента и, если есть, один некритичный недостаток. Сформулируй это в виде одного честного, живого предложения.

        Отзывы:
        {", ".join(reviews[:5])}

        Ответь только одним предложением, без лишних слов.
        """

        return await self._get_ai_response(prompt)

    # --- Strategy 2: Key Feature ---
    async def _strategy_key_feature(self, data: Dict[str, Any]) -> str:
        """Focus on one compelling feature of the product."""
        title = data.get('title', 'Товар')
        specs = data.get('specs', '')

        prompt = f"""
        Проанализируй название товара: '{title}' и его характеристики (если есть): {specs}. Найди одну, самую 'убойную' и интересную фишку. Построй вокруг нее одно яркое, образное предложение.

        Пример: Для 'наушники с активным шумоподавлением', твой ответ может быть: 'Представьте: вы в метро в час пик, а вокруг — полная тишина. Именно за это их и хвалят.'

        Ответь только одним предложением, без лишних слов.
        """

        return await self._get_ai_response(prompt)

    # --- Strategy 3: Buyer Persona ---
    async def _strategy_buyer_persona(self, data: Dict[str, Any]) -> str:
        """Describe the ideal buyer for this product."""
        title = data.get('title', 'Товар')

        prompt = f"""
        Опиши 'портрет' идеального покупателя для товара '{title}' одним-двумя предложениями. Кто этот человек? Что для него важно?

        Пример: Для 'геймерской мыши', твой ответ может быть: 'Идеальный выбор для того, кто проводит ночи в 'CS' и для кого важна каждая миллисекунда. Если это про тебя или твоего друга — присмотрись.'

        Ответь 1-2 предложениями, без лишних слов.
        """

        return await self._get_ai_response(prompt)

    # --- Strategy 4: Human Translation ---
    async def _strategy_human_translation(self, data: Dict[str, Any]) -> str:
        """Make marketing text more human and natural."""
        marketing_description = data.get('marketing_description', '').strip()

        if not marketing_description:
            # Fallback to key feature strategy if no marketing text
            return await self._strategy_key_feature(data)

        prompt = f"""
        'Переведи' скучное маркетинговое описание на живой, человеческий язык. Сохрани суть, но убери всю 'воду' и канцеляризмы. Ответь одним-двумя предложениями.

        Маркетинговый текст: '{marketing_description}'

        Пример: Для 'инновационная технология костной проводимости', твой ответ может быть: 'Короче, эти наушники не вставляются в уши. Они передают звук через кость, и ты слышишь и музыку, и то, что происходит вокруг. Идеально для велика.'

        Ответь 1-2 предложениями, без лишних слов.
        """

        return await self._get_ai_response(prompt)

    # --- Base Method to Call Groq ---
    async def _get_ai_response(self, prompt: str) -> str:
        """Get AI response from Groq API."""
        try:
            completion = await self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=150,  # Increased for potentially longer responses
            )
            response = completion.choices[0].message.content.strip()

            # Clean up the response - ensure it's not too long and ends properly
            if len(response) > 200:
                # If too long, truncate to first sentence or reasonable length
                sentences = response.split('.')
                if len(sentences) > 1:
                    response = sentences[0] + '.'
                else:
                    response = response[:197] + '...'

            return response
        except Exception as e:
            logger.error(f"Error calling Groq API: {e}")
            raise


# Global instance (will be initialized in main bot file)
ai_content_service = None


def get_ai_content_service() -> AIContentService:
    """Get the global AI content service instance"""
    return ai_content_service


def init_ai_content_service(api_key: Optional[str] = None) -> AIContentService:
    """Initialize the global AI content service instance"""
    global ai_content_service
    ai_content_service = AIContentService(api_key)
    return ai_content_service


# Backward compatibility - create a wrapper for the old interface
async def generate_description(title: str, reviews: Optional[List[str]] = None) -> str:
    """
    Backward compatibility wrapper for the old generate_description function.
    Now uses dynamic strategies instead of static prompts.
    """
    if not ai_content_service:
        return "Качественный товар с хорошими отзывами покупателей."

    product_data = {
        'title': title,
        'reviews': reviews or []
    }

    return await ai_content_service.generate_dynamic_description(product_data)
