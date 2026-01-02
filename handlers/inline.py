# handlers/inline.py
"""Обработчики inline режима бота"""
import logging
import time
from typing import Dict, List, Optional
from aiogram import Bot, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import (
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChosenInlineResult,
)
import config
from services.auto_search_service import AutoSearchService
from services.url_service import add_affiliate_params

logger = logging.getLogger(__name__)

# Кэш для результатов поиска (query -> (results, timestamp))
_search_cache: Dict[str, tuple[List[Dict], float]] = {}
CACHE_TTL = 300  # 300 секунд (5 минут)


def get_cached_results(query: str) -> Optional[List[Dict]]:
    """Получает закэшированные результаты поиска"""
    if query not in _search_cache:
        return None

    results, timestamp = _search_cache[query]
    if time.time() - timestamp > CACHE_TTL:
        # Кэш истек
        del _search_cache[query]
        return None

    return results


def cache_results(query: str, results: List[Dict]):
    """Кэширует результаты поиска"""
    _search_cache[query] = (results, time.time())
    logger.debug(f"Cached {len(results)} results for query: {query[:50]}")


def format_product_card(product: Dict, affiliate_url: str) -> str:
    """Форматирует карточку товара для отправки"""
    title = product.get("title", "Товар")
    url = affiliate_url or product.get("url", "")
    price = product.get("price", "")
    channel_username = config.CHANNEL_ID.lstrip("@")

    # Формируем текст сообщения
    text = f"🛍 <b>{title}</b>\n\n"

    if price:
        text += f"💰 <b>Цена: {price}</b>\n\n"

    text += f"👉 Ссылка: <a href='{url}'>{config.ANCHOR_TEXT}</a>\n\n"
    text += f"📢 <a href='https://t.me/{channel_username}'>Подписаться на канал</a> — лучшие предложения каждый день!"

    return text


# Глобальная переменная для auto_search_service (будет инициализирована при первом использовании)
_auto_search_service: Optional[AutoSearchService] = None


def get_auto_search_service(db, bot: Bot) -> AutoSearchService:
    """Получает или создает экземпляр AutoSearchService"""
    global _auto_search_service
    if _auto_search_service is None:
        _auto_search_service = AutoSearchService(db, bot)
    return _auto_search_service


def register_inline_handlers(dp, bot: Bot, db):
    """Регистрирует обработчики inline режима"""

    @dp.inline_query()
    async def handle_inline_query(inline_query: types.InlineQuery):
        """Обрабатывает inline запросы (@botname query)"""
        query = inline_query.query.strip()

        # Если запрос пустой, показываем подсказку
        if not query:
            await inline_query.answer(
                results=[],
                switch_pm_text="Введите запрос для поиска товаров",
                switch_pm_parameter="help",
                cache_time=1,
            )
            return

        try:
            # Проверяем кэш
            cached_results = get_cached_results(query)
            if cached_results:
                logger.info(f"Using cached results for query: {query[:50]}")
                products = cached_results
            else:
                # Выполняем поиск
                logger.info(f"Searching products for query: {query[:50]}")
                auto_search_service = get_auto_search_service(db, bot)
                products = await auto_search_service.search_products(
                    query=query, max_results=20  # Максимум результатов для inline
                )

                # Кэшируем результаты
                if products:
                    cache_results(query, products)

            # Формируем результаты для inline режима
            results = []
            for idx, product in enumerate(
                products[:10]
            ):  # Telegram ограничивает до 50 результатов
                product_url = product.get("url", "")
                title = product.get("title", "Товар")[:64]  # Ограничение Telegram
                price = product.get("price", "")

                # Добавляем партнерские параметры к URL
                affiliate_url = add_affiliate_params(product_url)

                # Формируем описание для превью
                description = f"💰 {price}" if price else "Товар на Яндекс.Маркете"

                # Создаем результат
                # Сохраняем данные продукта в ID для использования в chosen_inline_result
                product_data = f"{idx}|{product_url}|{affiliate_url}"

                result = InlineQueryResultArticle(
                    id=product_data,
                    title=title,
                    description=description,
                    input_message_content=InputTextMessageContent(
                        message_text=format_product_card(product, affiliate_url),
                        parse_mode=ParseMode.HTML,
                    ),
                )
                results.append(result)

            # Если результатов нет
            if not results:
                results.append(
                    InlineQueryResultArticle(
                        id="no_results",
                        title="Товары не найдены",
                        description=f"Попробуйте другой запрос",
                        input_message_content=InputTextMessageContent(
                            message_text="❌ Товары по запросу не найдены. Попробуйте изменить запрос.",
                            parse_mode=ParseMode.HTML,
                        ),
                    )
                )

            # Отправляем результаты
            await inline_query.answer(
                results=results,
                cache_time=60,  # Кэш на стороне Telegram (60 секунд)
                is_personal=False,  # Результаты не персонализированы
            )

            logger.info(f"Sent {len(results)} inline results for query: {query[:50]}")

        except Exception as e:
            logger.error(
                f"Error handling inline query '{query[:50]}': {e}", exc_info=True
            )
            # Отправляем ошибку пользователю
            await inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id="error",
                        title="Ошибка поиска",
                        description="Попробуйте позже",
                        input_message_content=InputTextMessageContent(
                            message_text="❌ Произошла ошибка при поиске товаров. Попробуйте позже.",
                            parse_mode=ParseMode.HTML,
                        ),
                    )
                ],
                cache_time=1,
            )

    @dp.chosen_inline_result()
    async def handle_chosen_inline_result(chosen_result: ChosenInlineResult):
        """Обрабатывает выбор результата inline запроса"""
        query = chosen_result.query
        result_id = chosen_result.result_id

        logger.info(
            f"User {chosen_result.from_user.id} chose inline result: {result_id} for query: {query[:50]}"
        )

        # Здесь можно добавить аналитику или дополнительную обработку
        # Например, сохранение статистики выбора товаров
        try:
            # Можно добавить логику для отслеживания популярных запросов
            pass
        except Exception as e:
            logger.error(f"Error handling chosen inline result: {e}", exc_info=True)
