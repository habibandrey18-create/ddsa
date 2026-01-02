# services/image_service.py
"""Сервис для работы с изображениями"""
import os
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import logging

logger = logging.getLogger(__name__)


def remove_exif(image_bytes: bytes) -> bytes:
    """Удаляет EXIF данные из изображения"""
    try:
        img = Image.open(BytesIO(image_bytes))
        # Создаем новое изображение без EXIF
        output = BytesIO()
        img.save(output, format=img.format or "JPEG", quality=95)
        return output.getvalue()
    except Exception as e:
        logger.warning("remove_exif error: %s", e)
        return image_bytes


def check_image_quality(image_bytes: bytes) -> tuple[bool, str]:
    """Проверяет качество изображения. Возвращает (is_good, reason)"""
    try:
        img = Image.open(BytesIO(image_bytes))
        width, height = img.size

        # Проверка размера
        if width < 100 or height < 100:
            return False, "Слишком маленькое изображение"

        # Проверка соотношения сторон (слишком вытянутое)
        ratio = max(width, height) / min(width, height)
        if ratio > 5:
            return False, "Слишком вытянутое изображение"

        # Проверка на монохромность (может быть плохое качество)
        if img.mode == "L":  # Grayscale
            # Проверяем, не слишком ли темное
            pixels = list(img.getdata())
            avg_brightness = sum(pixels) / len(pixels) / 255
            if avg_brightness < 0.1:
                return False, "Слишком темное изображение"

        return True, "OK"
    except Exception as e:
        logger.warning("check_image_quality error: %s", e)
        return False, f"Ошибка проверки: {str(e)[:50]}"


def improve_image(image_bytes: bytes) -> bytes:
    """Улучшает качество изображения (базовые улучшения)"""
    try:
        img = Image.open(BytesIO(image_bytes))

        # Конвертируем в RGB если нужно
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Базовое улучшение контраста и яркости
        from PIL import ImageEnhance

        # Улучшаем контраст
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.1)  # +10% контраста

        # Улучшаем резкость
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(1.1)  # +10% резкости

        # Сохраняем
        output = BytesIO()
        img.save(output, format="JPEG", quality=95, optimize=True)
        return output.getvalue()
    except Exception as e:
        logger.warning("improve_image error: %s", e)
        return image_bytes


def add_price_overlay(
    image_bytes: bytes, price: str, discount_percent: float = 0, old_price: str = None
) -> bytes:
    """
    Добавляет профессиональные оверлеи на изображение товара:
    - Ценовой тег в левом нижнем углу
    - Бейдж скидки в правом верхнем углу (если скидка > 10%)

    Args:
        image_bytes: Исходное изображение в байтах
        price: Текущая цена (например, "15 990 ₽")
        discount_percent: Процент скидки (0-100)
        old_price: Старая цена для перечеркивания (опционально)

    Returns:
        Обработанное изображение в байтах (BytesIO buffer)
    """
    try:
        from PIL import ImageDraw, ImageFont

        # Открываем изображение
        img = Image.open(BytesIO(image_bytes))

        # Конвертируем в RGB если нужно
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Оптимизация размера для Telegram (макс 1024px ширина)
        max_width = 1024
        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
            logger.debug(
                f"Resized image from {img.width}x{img.height} to {max_width}x{new_height}"
            )

        width, height = img.size

        # Создаем объект для рисования
        draw = ImageDraw.Draw(img)

        # Загружаем шрифты (пробуем разные варианты)
        try:
            # Пробуем системные шрифты
            font_large = ImageFont.truetype("arial.ttf", 36)
            font_medium = ImageFont.truetype("arial.ttf", 28)
            font_small = ImageFont.truetype("arial.ttf", 20)
        except:
            try:
                # Windows fallback
                font_large = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 36)
                font_medium = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 28)
                font_small = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 20)
            except:
                # Default font
                font_large = ImageFont.load_default()
                font_medium = ImageFont.load_default()
                font_small = ImageFont.load_default()

        # 1. Ценовой тег в левом нижнем углу
        if price:
            # Подготовка текста цены
            price_text = str(price).strip()
            if not price_text.endswith("₽"):
                price_text += " ₽"

            # Размеры текста
            bbox = draw.textbbox((0, 0), price_text, font=font_large)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            # Отступы от краев
            padding = 15
            tag_padding = 12

            # Позиция тега (левый нижний угол)
            tag_x = padding
            tag_y = height - padding - text_height - tag_padding * 2

            # Рисуем полупрозрачный фон для цены
            tag_width = text_width + tag_padding * 2
            tag_height = text_height + tag_padding * 2

            # Создаем полупрозрачный слой
            overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)

            # Черный фон с прозрачностью 80%
            overlay_draw.rectangle(
                [tag_x, tag_y, tag_x + tag_width, tag_y + tag_height],
                fill=(0, 0, 0, 204),  # 80% прозрачности
                outline=(255, 255, 255, 255),
                width=2,
            )

            # Объединяем слои
            img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
            draw = ImageDraw.Draw(img)

            # Рисуем цену белым цветом
            draw.text(
                (tag_x + tag_padding, tag_y + tag_padding),
                price_text,
                fill=(255, 255, 255),
                font=font_large,
            )

            # Если есть старая цена - рисуем перечеркнутую
            if old_price:
                old_price_text = str(old_price).strip()
                if not old_price_text.endswith("₽"):
                    old_price_text += " ₽"

                # Старая цена выше новой, серым цветом
                old_bbox = draw.textbbox((0, 0), old_price_text, font=font_medium)
                old_text_width = old_bbox[2] - old_bbox[0]
                old_text_height = old_bbox[3] - old_bbox[1]

                old_x = tag_x + tag_padding
                old_y = tag_y - old_text_height - 5

                # Рисуем перечеркнутую цену
                draw.text(
                    (old_x, old_y),
                    old_price_text,
                    fill=(150, 150, 150),
                    font=font_medium,
                )

                # Линия зачеркивания
                line_y = old_y + old_text_height // 2
                draw.line(
                    [(old_x, line_y), (old_x + old_text_width, line_y)],
                    fill=(200, 0, 0),
                    width=2,
                )

        # 2. Бейдж скидки в правом верхнем углу (если скидка > 10%)
        if discount_percent > 10:
            discount_text = f"-{int(discount_percent)}%"

            # Размеры текста
            bbox = draw.textbbox((0, 0), discount_text, font=font_medium)
            badge_width = bbox[2] - bbox[0] + 20
            badge_height = bbox[3] - bbox[1] + 12

            # Позиция бейджа (правый верхний угол)
            badge_x = width - padding - badge_width
            badge_y = padding

            # Создаем красный бейдж
            overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)

            # Красный фон с белой рамкой
            overlay_draw.ellipse(
                [badge_x, badge_y, badge_x + badge_width, badge_y + badge_height],
                fill=(220, 20, 60, 240),  # Красный цвет
                outline=(255, 255, 255, 255),
                width=2,
            )

            # Объединяем слои
            img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
            draw = ImageDraw.Draw(img)

            # Рисуем текст скидки белым цветом
            text_x = badge_x + (badge_width - (bbox[2] - bbox[0])) // 2
            text_y = badge_y + (badge_height - (bbox[3] - bbox[1])) // 2
            draw.text(
                (text_x, text_y), discount_text, fill=(255, 255, 255), font=font_medium
            )

        # Сохраняем в буфер
        output = BytesIO()
        img.save(output, format="JPEG", quality=90, optimize=True)
        output.seek(0)

        logger.info(f"Added price overlay: {price}, discount: {discount_percent}%")
        return output.getvalue()

    except Exception as e:
        logger.exception(f"Error adding price overlay: {e}")
        # В случае ошибки возвращаем оригинальное изображение
        return image_bytes


def add_watermark(image_bytes: bytes, watermark_text: str = None) -> bytes:
    """
    Добавляет водяной знак на изображение.

    Args:
        image_bytes: Исходное изображение в байтах
        watermark_text: Текст водяного знака (если None, берется из config.CHANNEL_ID)

    Returns:
        Изображение с водяным знаком в байтах
    """
    try:
        import config

        # Получаем текст водяного знака
        if watermark_text is None:
            watermark_text = config.CHANNEL_ID or "@marketi_tochka"
            # Убираем @ если есть, так как мы добавим его сами
            if watermark_text.startswith("@"):
                watermark_text = watermark_text[1:]
            watermark_text = f"@{watermark_text}"

        # Открываем изображение
        img = Image.open(BytesIO(image_bytes))

        # Конвертируем в RGBA для поддержки прозрачности
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        width, height = img.size

        # Создаем объект для рисования
        draw = ImageDraw.Draw(img)

        # Загружаем шрифт (пробуем разные варианты)
        font_size = max(24, min(width, height) // 20)  # Адаптивный размер шрифта
        font = None

        # Пробуем загрузить системные шрифты
        font_paths = [
            "arial.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibri.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]

        for font_path in font_paths:
            try:
                if os.path.exists(font_path):
                    font = ImageFont.truetype(font_path, font_size)
                    break
            except Exception:
                continue

        # Если не удалось загрузить шрифт, используем default
        if font is None:
            try:
                # Пробуем использовать default font с увеличенным размером
                font = ImageFont.load_default()
            except Exception:
                font = None

        # Вычисляем размер текста
        if font:
            bbox = draw.textbbox((0, 0), watermark_text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        else:
            # Примерная оценка размера для default font
            text_width = len(watermark_text) * 8
            text_height = 20

        # Позиция водяного знака: правый нижний угол с отступом 10px
        padding = 10
        x = width - text_width - padding
        y = height - text_height - padding

        # Создаем полупрозрачный слой для водяного знака
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)

        # Рисуем текст белым цветом с 50% прозрачностью (alpha=128 из 255)
        if font:
            overlay_draw.text(
                (x, y),
                watermark_text,
                fill=(255, 255, 255, 128),  # Белый с 50% прозрачностью
                font=font,
            )
        else:
            overlay_draw.text((x, y), watermark_text, fill=(255, 255, 255, 128))

        # Объединяем слои
        img = Image.alpha_composite(img, overlay)

        # Конвертируем обратно в RGB для сохранения
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Сохраняем в буфер
        output = BytesIO()
        img.save(output, format="JPEG", quality=90, optimize=True)
        output.seek(0)

        logger.debug(f"Added watermark: {watermark_text}")
        return output.getvalue()

    except Exception as e:
        logger.warning(f"Error adding watermark: {e}")
        # В случае ошибки возвращаем оригинальное изображение
        return image_bytes


def process_image(image_bytes: bytes, watermark_text: str = None) -> bytes:
    """
    Обрабатывает изображение: улучшение + водяной знак.
    Универсальная функция для обработки изображений с водяным знаком.

    Args:
        image_bytes: Исходное изображение в байтах
        watermark_text: Текст водяного знака (если None, берется из config.CHANNEL_ID)

    Returns:
        Обработанное изображение в байтах
    """
    try:
        # Шаг 1: Улучшение изображения
        improved = improve_image(image_bytes)

        # Шаг 2: Добавление водяного знака
        final = add_watermark(improved, watermark_text)

        return final
    except Exception as e:
        logger.exception(f"Error processing image: {e}")
        # В случае ошибки возвращаем оригинальное изображение
        return image_bytes


async def process_product_image(
    image_bytes: bytes, price: str, discount_percent: float = 0, old_price: str = None
) -> bytes:
    """
    Полная обработка изображения товара: улучшение + оверлеи + водяной знак.

    Args:
        image_bytes: Исходное изображение
        price: Текущая цена
        discount_percent: Процент скидки
        old_price: Старая цена (опционально)

    Returns:
        Обработанное изображение
    """
    try:
        # Шаг 1: Улучшение изображения
        improved = improve_image(image_bytes)

        # Шаг 2: Добавление оверлеев (цена и скидка)
        with_overlays = add_price_overlay(improved, price, discount_percent, old_price)

        # Шаг 3: Добавление водяного знака
        final = add_watermark(with_overlays)
        return final
    except Exception as e:
        logger.exception(f"Error processing product image: {e}")
        return image_bytes
