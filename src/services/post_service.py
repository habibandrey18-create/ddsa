"""
Post Service - создание и отправка постов
"""

import os
import asyncio
import logging
import csv
from typing import Dict, Any, Optional, Tuple
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import src.config as config
from src.services.formatting_service import get_formatting_service

logger = logging.getLogger(__name__)


def is_product_valid(product) -> tuple[bool, list]:
    """
    Проверяет товар по качественным фильтрам.
    Возвращает (is_valid, reasons)
    """
    reasons = []

    # Всегда проверяем цену
    if getattr(product, 'price', 0) == 0:
        reasons.append("Нет цены")

    # Если валидатор не строгий, пропускаем остальные проверки
    if not getattr(config, 'VALIDATOR_STRICT', False):
        is_valid = len(reasons) == 0
        if not is_valid:
            logger.info(f"Пропуск товара '{getattr(product, 'title', '')}': {', '.join(reasons)}")
        return is_valid, reasons

    # Строгие проверки
    if getattr(product, 'discount', 0) < config.DISCOUNT_THRESHOLD:
        reasons.append("Слишком маленькая скидка")
    if getattr(product, 'rating', 0) < config.RATING_THRESHOLD:
        reasons.append("Рейтинг ниже порога")
    if getattr(product, 'reviews', 0) < config.REVIEWS_THRESHOLD:
        reasons.append("Недостаточно отзывов")

    # Логируем причины отказа
    if reasons:
        logger.info(f"Пропуск товара '{getattr(product, 'title', '')}': {', '.join(reasons)}")
        # Сохраняем в CSV файл отклонений
        try:
            with open('rejections.csv', 'a', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    getattr(product, 'title', ''),
                    getattr(product, 'url', ''),
                    getattr(product, 'price', 0),
                    '; '.join(reasons)
                ])
        except Exception as e:
            logger.error(f"Failed to save rejection to CSV: {e}")

    return len(reasons) == 0, reasons


async def create_link_only_post(
    url: str, chat_id: Optional[int], correlation_id: str
) -> Dict[str, Any]:
    """
    Создаёт минимальные данные для поста только со ссылкой

    Args:
        url: Партнёрская cc-ссылка
        chat_id: ID чата для уведомлений
        correlation_id: ID для корреляции логов

    Returns:
        Словарь с данными для поста
    """
    return {
        "title": "Товар Яндекс.Маркета",
        "price": "Цена уточняется",
        "url": url,
        "ref_link": url,
        "product_url": url,
        "has_ref": True,
        "flags": ["cc_url_direct", "scrape_failed", "link_only"],
        "description": "",
    }


async def send_post_to_channel(
    bot: Bot,
    data: Dict[str, Any],
    photo_path: Optional[str] = None,
    retry_count: int = 3,
    chat_id: Optional[int] = None,
    correlation_id: Optional[str] = None,
    disable_notification: bool = True,
) -> Tuple[bool, Optional[int]]:
    """
    Отправляет пост в канал с ретраями

    Args:
        bot: Экземпляр бота
        data: Данные товара
        photo_path: Путь к файлу изображения
        retry_count: Количество попыток
        chat_id: ID чата для уведомлений об ошибках
        correlation_id: ID для корреляции логов
        disable_notification: Если False, отправляет с уведомлением (громко)

    Returns:
        Tuple (success: bool, message_id: Optional[int])
    """
    correlation_id = correlation_id or "unknown"

    # Extract and validate required variables at the beginning
    price = data.get("price", "Цена уточняется")
    old_price = data.get("old_price")
    discount_percent = data.get("discount_percent", 0)
    product_url = data.get("product_url") or data.get("url") or ""

    # Validate that we have essential data
    if not price or price == "Цена уточняется":
        logger.error(f"No valid price found for product: {data.get('title', 'Unknown')}")
        return False, None

    # Use the new simplified formatting service
    try:
        formatting_service = get_formatting_service()
        caption = await formatting_service.format_product_post(data)
        data["template_type"] = "new_ai_format"  # New template type for analytics
        logger.info(f"Using new AI formatting service for: {data.get('title', '')[:50]}")
    except Exception as e:
        logger.error(f"New formatting service failed, using basic fallback: {e}")
        # Basic fallback formatting
        title = data.get("title", "").strip()
        formatted_price = price
        if isinstance(price, (int, float)):
            formatted_price = f"{price} ₽"
        elif isinstance(price, str) and not price.endswith('₽'):
            formatted_price = f"{price} ₽"

        caption = f"🔥 {title}\n\n💰 Цена: {formatted_price} (цена может отличаться)\n\n✍️ Качественный товар с хорошими отзывами покупателей.\n\n👉 Смотреть на Маркете ({product_url})\n\n#покупки"
        data["template_type"] = "basic_fallback"

    logger.info(
        f"Sending post to channel {config.CHANNEL_ID} (correlation_id={correlation_id})"
    )

    # Ensure price is properly formatted for display
    display_price = price
    if isinstance(price, (int, float)):
        display_price = f"{price} ₽"
    elif isinstance(price, str) and not price.endswith('₽'):
        display_price = price.replace('₽₽', '₽').strip()
        if not display_price.endswith('₽'):
            display_price = f"{display_price} ₽"

    # Ensure discount_percent is properly typed
    if isinstance(discount_percent, str):
        try:
            discount_percent = int(discount_percent)
        except (ValueError, TypeError):
            discount_percent = 0
    elif not isinstance(discount_percent, (int, float)):
        discount_percent = 0

    # Create enhanced inline keyboard with multiple action buttons
    try:
        from src.services.button_service import create_purchase_buttons

        has_discount = bool(old_price) or (isinstance(discount_percent, (int, float)) and discount_percent > 0)
        keyboard = create_purchase_buttons(
            product_url=product_url,
            price=display_price,
            old_price=str(old_price) if old_price else None,
            has_discount=has_discount
        )
        logger.debug("Created enhanced inline keyboard with purchase buttons")
    except Exception as e:
        logger.warning(f"Enhanced keyboard creation failed, using simple button: {e}")
        # Fallback to simple keyboard
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"🛒 Купить за {display_price}",
                        url=product_url,
                    )
                ]
            ]
        )

    send_success = False
    message_id = None

    for attempt in range(retry_count):
        try:
            if photo_path and os.path.exists(photo_path):
                logger.info(
                    f"Sending photo post (attempt {attempt + 1}/{retry_count}, correlation_id={correlation_id})"
                )
                photo = types.FSInputFile(photo_path)
                sent_message = await bot.send_photo(
                    chat_id=config.CHANNEL_ID,
                    photo=photo,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    disable_notification=disable_notification,
                    reply_markup=keyboard,
                )
                message_id = sent_message.message_id
                logger.info(
                    f"Photo post sent successfully (message_id: {message_id}, correlation_id={correlation_id})"
                )
            else:
                logger.info(
                    f"Sending text post (attempt {attempt + 1}/{retry_count}, correlation_id={correlation_id})"
                )
                sent_message = await bot.send_message(
                    chat_id=config.CHANNEL_ID,
                    text=caption,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False,
                    disable_notification=disable_notification,
                    reply_markup=keyboard,
                )
                message_id = sent_message.message_id
                logger.info(
                    f"Text post sent successfully (message_id: {message_id}, correlation_id={correlation_id})"
                )

            send_success = True

            # Записываем affiliate-ссылку для трекинга
            try:
                from src.services.affiliate_tracking_service import record_affiliate_link_sent

                market_id = data.get('market_id', data.get('id', ''))
                erid = data.get('erid', '')
                affiliate_url = data.get('ref_link', product_url)
                original_url = data.get('product_url', data.get('url', ''))

                if affiliate_url and erid:
                    link_id = record_affiliate_link_sent(
                        market_id=market_id,
                        erid=erid,
                        affiliate_url=affiliate_url,
                        original_url=original_url,
                        channel_id=str(config.CHANNEL_ID),
                        message_id=str(message_id) if message_id else None
                    )
                    logger.debug(f"Recorded affiliate link for tracking: {link_id}")
                else:
                    logger.debug("No affiliate link or ERID found for tracking")
            except Exception as e:
                logger.warning(f"Failed to record affiliate link for tracking: {e}")

            # после успешной публикации сохраняй ключ
            try:
                title = data.get('title', '')
                vendor = data.get('vendor', '')
                offerid = data.get('offerid')
                url = data.get('url', product_url)

                product_key = db.make_product_key(title=title, vendor=vendor, offerid=offerid, url=url)
                db = get_db_instance()
                db.add_posted_product(product_key=product_key, url=url)
                logger.debug(f"Recorded posted product key: {product_key}")
            except Exception as e:
                logger.warning(f"Failed to record posted product key: {e}")

            break

        except Exception as e:
            logger.warning(
                f"Send attempt {attempt + 1}/{retry_count} failed (correlation_id={correlation_id}): {e}"
            )
            if attempt < retry_count - 1:
                await asyncio.sleep(2**attempt)
            else:
                logger.error(
                    f"Error sending post after {retry_count} attempts (correlation_id={correlation_id}): {e}",
                    exc_info=True,
                )
                if chat_id:
                    try:
                        await bot.send_message(
                            chat_id,
                            f"❌ Ошибка отправки после {retry_count} попыток: {str(e)[:200]}",
                        )
                    except Exception:
                        pass  # Игнорируем ошибки уведомления
                return False, None

    if not send_success:
        return False, None

    return True, message_id
