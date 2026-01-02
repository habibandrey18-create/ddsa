# utils/text_gen.py
import random

# Import settings - handle the case where BOT_TOKEN might not be set
try:
    from src.config import settings
except (ImportError, RuntimeError) as e:
    # If settings import fails, create a minimal settings object with defaults
    import sys
    import os

    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import importlib.util

    config_py_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.py"
    )
    spec = importlib.util.spec_from_file_location("config_py", config_py_path)
    config_py = importlib.util.module_from_spec(spec)
    # Execute only up to the Settings class definition, not the instantiation
    config_code = ""
    with open(config_py_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        # Read until the settings = Settings() line
        for line in lines:
            if line.strip().startswith("settings = Settings()"):
                break
            config_code += line
    exec(config_code, config_py.__dict__)

    # Create settings object manually with minimal required fields
    class MinimalSettings:
        ANCHOR_TEXT = "Яндекс.Маркет"
        # Add other defaults as needed

    settings = MinimalSettings()


def get_emoji_by_category(title: str) -> str:
    t = title.lower()
    if any(x in t for x in ["шоколад", "конфет", "снек"]):
        return "🍫"
    if any(x in t for x in ["кофе", "чай"]):
        return "☕️"
    if any(x in t for x in ["наушник", "гарнитур", "смартфон", "телефон"]):
        return "📱"
    if any(x in t for x in ["одежд", "рубаш", "куртк"]):
        return "👕"
    if any(x in t for x in ["игрушк", "lego", "конструктор"]):
        return "🧸"
    if any(x in t for x in ["ноутбук", "компьютер", "пк"]):
        return "💻"
    if any(x in t for x in ["книг", "учебник"]):
        return "📚"
    if any(x in t for x in ["обувь", "кроссовк", "ботинк"]):
        return "👟"
    if any(x in t for x in ["мебель", "стол", "стул", "диван"]):
        return "🪑"
    if any(x in t for x in ["косметик", "крем", "шампунь"]):
        return "💄"
    return "🔥"


def get_reasons_by_category(title: str, description: str = "") -> list:
    """Возвращает релевантные причины покупки для категории товара"""
    t = (title + " " + description).lower()
    reasons_map = {
        "food": [
            "Премиум качество ингредиентов",
            "Невероятный вкус и свежесть",
            "Проверенный временем производитель",
            "Натуральный состав без консервантов",
            "Идеально для подарка",
            "Лучшая цена на рынке",
            "Ограниченная серия",
            "Популярный выбор покупателей",
        ],
        "tech": [
            "Последние технологии 2025",
            "Максимальная надежность",
            "Лучшее соотношение цена/качество",
            "Премиум сборка и материалы",
            "Долгий срок службы",
            "Современный дизайн",
            "Высокая производительность",
            "Проверенные отзывами",
        ],
        "clothing": [
            "Премиум материалы",
            "Стильный и актуальный дизайн",
            "Максимальный комфорт",
            "Долговечность и качество",
            "Универсальность стиля",
            "Идеальная посадка",
            "Модный тренд сезона",
            "Проверено покупателями",
        ],
        "toys": [
            "Безопасность для детей",
            "Развивающий потенциал",
            "Высокое качество изготовления",
            "Сертифицировано по ГОСТ",
            "Долговечность игрушки",
            "Развивает воображение",
            "Популярный выбор родителей",
            "Идеальный подарок",
        ],
        "books": [
            "Актуальная информация",
            "Проверенный автор",
            "Полезные знания",
            "Бестселлер категории",
            "Высокий рейтинг читателей",
            "Актуальная тема",
            "Качественное издание",
            "Рекомендуют эксперты",
        ],
        "cosmetics": [
            "Натуральные компоненты",
            "Проверенная эффективность",
            "Безопасный состав",
            "Премиум формула",
            "Видимый результат",
            "Гипоаллергенно",
            "Популярный выбор",
            "Профессиональное качество",
        ],
        "default": [
            "Отличная цена",
            "Быстрая доставка",
            "Высокий рейтинг покупателей",
            "Проверенный продавец",
            "Гарантия качества",
            "Хит продаж",
            "Ограниченная партия",
            "Лучшее предложение",
            "Популярный выбор",
            "Премиум качество",
            "Идеальное соотношение цена/качество",
            "Рекомендуют эксперты",
        ],
    }

    # Определяем категорию
    if any(
        x in t for x in ["шоколад", "конфет", "снек", "кофе", "чай", "еда", "продукт"]
    ):
        category = "food"
    elif any(
        x in t
        for x in [
            "наушник",
            "смартфон",
            "телефон",
            "ноутбук",
            "компьютер",
            "пк",
            "техник",
        ]
    ):
        category = "tech"
    elif any(x in t for x in ["одежд", "рубаш", "куртк", "обувь", "кроссовк"]):
        category = "clothing"
    elif any(x in t for x in ["игрушк", "lego", "конструктор"]):
        category = "toys"
    elif any(x in t for x in ["книг", "учебник"]):
        category = "books"
    elif any(x in t for x in ["косметик", "крем", "шампунь"]):
        category = "cosmetics"
    else:
        category = "default"

    return reasons_map.get(category, reasons_map["default"])


LLM_PROMPT = """
Ты — генератор коротких рекламных постов для телеграм-канала @marketi_tochka.
На основе данных: title, price, old_price, package, image_url, product_url, source_anchor.
Сделай русский текст 4–8 коротких строк, без воды.
В заголовке — точное название (title).
Укажи упаковку/кол-во, если есть.
Добавь 2-3 буллета почему брать.
В конце вставь: "👉 Ссылка: {ANCHOR_TEXT}" (HTML ссылка).
Не добавляй лишних хэштегов.
Подбери эмодзи по категории.
""".strip()


def generate_post_caption(data: dict) -> str:
    # Check for flash sale info (priority over price drop)
    flash_sale_info = data.get("flash_sale_info")
    flash_sale_tag = ""
    if flash_sale_info:
        discount_percent = flash_sale_info.get("discount_percent", 0)
        flash_sale_tag = (
            f"🚨 <b>Резкое падение цены! (-{discount_percent:.0f}%)</b>\n\n"
        )

    # Check for price drop info (if not flash sale)
    price_drop_info = data.get("price_drop_info")
    price_drop_tag = ""
    if not flash_sale_info and price_drop_info:
        old_price = price_drop_info.get("old_price", 0)
        current_price = price_drop_info.get("current_price", 0)
        drop_percent = price_drop_info.get("price_drop_percent", 0)
        price_drop_tag = f"📉 <b>Price Drop Alert!</b> {old_price:.0f} ₽ → {current_price:.0f} ₽ (-{drop_percent:.1f}%)\n\n"

    emoji = get_emoji_by_category(data.get("title", ""))
    title = data.get("title", "").strip()
    desc = (data.get("description") or "").strip()
    price = data.get("price", "Цена уточняется")
    sku = data.get("sku") or ""
    promo_text = data.get("promo_text")  # Текст промокода/скидки

    # Получаем релевантные причины для категории
    category_reasons = get_reasons_by_category(title, desc)
    # Улучшенное описание - каждый раз разное, с акцентом на пользу для пользователя
    import random
    import re

    short_desc = ""
    if desc:
        # Дополнительная фильтрация рекламных текстов (на случай, если они все еще попали)
        if re.search(
            r"закажите прямо сейчас|на сайте или в приложении|купить.*прямо сейчас|📲",
            desc,
            re.I,
        ):
            desc = ""  # Отбрасываем описание с рекламными текстами
        else:
            # Берем случайное предложение из описания для разнообразия
            sentences = [s.strip() for s in desc.split(".") if s.strip()]
            if sentences:
                # Берем случайное предложение, но предпочитаем более информативные
                # Фильтруем слишком короткие предложения (меньше 20 символов)
                # И фильтруем рекламные тексты
                meaningful_sentences = [
                    s
                    for s in sentences
                    if len(s) > 20
                    and not re.search(
                        r"закажите прямо сейчас|на сайте или в приложении|купить.*прямо сейчас|📲",
                        s,
                        re.I,
                    )
                ]
                if meaningful_sentences:
                    chosen_sentence = random.choice(meaningful_sentences)
                else:
                    # Если все предложения содержат рекламу, берем первое без рекламы
                    non_ad_sentences = [
                        s
                        for s in sentences
                        if not re.search(
                            r"закажите прямо сейчас|на сайте или в приложении|купить.*прямо сейчас|📲",
                            s,
                            re.I,
                        )
                    ]
                    if non_ad_sentences:
                        chosen_sentence = random.choice(non_ad_sentences)
                    else:
                        chosen_sentence = None

                if chosen_sentence:
                    if len(chosen_sentence) > 150:
                        short_desc = chosen_sentence[:147] + "..."
                    else:
                        short_desc = chosen_sentence
    if not short_desc:
        # Новогодние варианты описания с разнообразием эмодзи
        default_descs = [
            "❄️ Отличное предложение на Яндекс.Маркете!",
            "🎄 Выгодная покупка с быстрой доставкой!",
            "🎁 Топовое предложение дня!",
            "✨ Не упустите эту возможность!",
            "🌟 Лучшая цена на рынке!",
            "🎅 Проверенное качество и надежность!",
            "🎊 Популярный выбор покупателей!",
            "❄️ Высокое качество по доступной цене!",
            "🎁 Идеально подходит для наших пользователей!",
            "✨ Проверенное качество и надежность!",
            "🌟 Отличное соотношение цена/качество!",
            "🎄 Отличная возможность для покупки!",
            "❄️ Лучшее предложение сезона!",
            "🎁 Высокое качество по доступной цене!",
            "✨ Топовое предложение дня!",
            "🌟 Не упустите эту возможность!",
            "🎅 Проверенное качество и надежность!",
            "🎊 Популярный выбор покупателей!",
        ]
        short_desc = random.choice(default_descs)

    # Каждый раз генерируем новый уникальный пост
    # Используем случайный выбор шаблона + случайные причины
    import random

    # Случайный выбор шаблона каждый раз (не стабильный - каждый раз новый!)
    template_index = random.randint(0, 5)

    # Перемешиваем причины для большего разнообразия каждый раз
    shuffled_reasons = random.sample(category_reasons, min(len(category_reasons), 5))
    chosen = shuffled_reasons[:3]

    # Новогодние вариации текста
    call_to_actions = [
        "Подпишись на ❄️ @marketi_tochka — мы находим самое выгодное",
        "❄️ @marketi_tochka — лучшие предложения каждый день",
        "Подписывайся на 🎄 @marketi_tochka за лучшими скидками!",
        "🎁 @marketi_tochka — не упусти выгоду!",
        "Подпишись на ✨ @marketi_tochka и будь в курсе лучших предложений",
        "🌟 @marketi_tochka — акции и скидки каждый день",
        "Следи за 🎅 @marketi_tochka — только лучшие цены!",
        "🎊 @marketi_tochka — лучшие предложения каждый день!",
    ]

    price_variants = [
        f"💰 <b>Цена: {price}</b>",
        f"💸 <b>Всего: {price}</b>",
        f"💵 Цена: <b>{price}</b>",
        f"💎 <b>{price}</b>",
        f"💰 {price}",
        f"💵 <b>Цена: {price}</b>",
    ]

    link_variants = [
        f"👉 Ссылка: <a href='{data.get('url')}'>{settings.ANCHOR_TEXT}</a>",
        f"🔗 <a href='{data.get('url')}'>{settings.ANCHOR_TEXT}</a>",
        f"👉 <a href='{data.get('url')}'>{settings.ANCHOR_TEXT}</a>",
        f"🔗 Ссылка: <a href='{data.get('url')}'>{settings.ANCHOR_TEXT}</a>",
    ]

    # Подготовка артикула (чтобы избежать проблемы с \n в f-string)
    sku_line = f"📦 Артикул: {sku}\n" if sku else ""
    sku_line_simple = f"📦 {sku}\n" if sku else ""
    # Подготовка строки с промокодом
    promo_line = f"🎁 {promo_text}\n\n" if promo_text else ""
    newline = "\n"

    # Случайные варианты для каждого элемента
    cta = random.choice(call_to_actions)
    price_text = random.choice(price_variants)
    link_text = random.choice(link_variants)

    # Новогодние маркеры для списка причин
    list_markers = [
        ("❄️", "❄️", "❄️"),
        ("🎄", "🎄", "🎄"),
        ("🎁", "🎁", "🎁"),
        ("✨", "✨", "✨"),
        ("🌟", "🌟", "🌟"),
        ("🎅", "🎅", "🎅"),
        ("🎊", "🎊", "🎊"),
        ("⭐", "⭐", "⭐"),
        ("💎", "💎", "💎"),
        ("✓", "✓", "✓"),
        ("•", "•", "•"),
    ]

    marker1, marker2, marker3 = random.choice(list_markers)

    # Новогодние заголовки для секций "почему купить"
    section_headers = [
        ("❄️", "Что делает это предложение особенным:"),
        ("🎄", "Почему это отличный выбор:"),
        ("🎁", "Топ-причины купить прямо сейчас:"),
        ("✨", "Ключевые особенности:"),
        ("🌟", "Почему выбирают именно это:"),
        ("🎅", "Главные преимущества:"),
        ("🎊", "Почему стоит купить:"),
        ("⭐", "Что делает это предложение особенным:"),
        ("💎", "Преимущества:"),
    ]

    # Выбираем случайный заголовок
    header_emoji, header_text = random.choice(section_headers)

    templates = [
        # Шаблон 1: Классический
        (
            f"{flash_sale_tag}{price_drop_tag}{emoji} <b>{title}</b>{newline}{newline}"
            f"{short_desc}{newline}{newline}"
            f"{header_emoji} <b>{header_text}</b>{newline}"
            f"{marker1} {chosen[0]}{newline}"
            f"{marker2} {chosen[1]}{newline}"
            f"{marker3} {chosen[2]}{newline}{newline}"
            f"{sku_line}"
            f"{price_text}{newline}"
            f"{link_text}{newline}{newline}"
            f"{cta}"
        ),
        # Шаблон 2: С акцентом на цену
        (
            f"{flash_sale_tag}{price_drop_tag}{emoji} <b>{title}</b>{newline}{newline}"
            f"{price_text}{newline}{newline}"
            f"{short_desc}{newline}{newline}"
            f"{promo_line}"
            f"{header_emoji} <b>{header_text}</b>{newline}"
            f"{marker1} {chosen[0]}{newline}"
            f"{marker2} {chosen[1]}{newline}"
            f"{marker3} {chosen[2]}{newline}{newline}"
            f"{sku_line}"
            f"{link_text}{newline}{newline}"
            f"{cta}"
        ),
        # Шаблон 3: Эмоциональный
        (
            f"{flash_sale_tag}{price_drop_tag}{emoji} <b>{title}</b>{newline}{newline}"
            f"💡 {short_desc}{newline}{newline}"
            f"{header_emoji} <b>{header_text}</b>{newline}"
            f"{marker1} {chosen[0]}{newline}"
            f"{marker2} {chosen[1]}{newline}"
            f"{marker3} {chosen[2]}{newline}{newline}"
            f"{sku_line}"
            f"{price_text}{newline}"
            f"{link_text}{newline}{newline}"
            f"{cta}"
        ),
        # Шаблон 4: Минималистичный
        (
            f"{flash_sale_tag}{price_drop_tag}{emoji} <b>{title}</b>{newline}{newline}"
            f"{short_desc}{newline}{newline}"
            f"{promo_line}"
            f"{marker1} {chosen[0]}{newline}"
            f"{marker2} {chosen[1]}{newline}"
            f"{marker3} {chosen[2]}{newline}{newline}"
            f"{sku_line_simple}"
            f"{price_text}{newline}"
            f"{link_text}{newline}{newline}"
            f"{cta}"
        ),
        # Шаблон 5: С акцентом на срочность
        (
            f"{flash_sale_tag}{price_drop_tag}{emoji} <b>{title}</b>{newline}{newline}"
            f"{short_desc}{newline}{newline}"
            f"{promo_line}"
            f"{header_emoji} <b>{header_text}</b>{newline}"
            f"{marker1} {chosen[0]}{newline}"
            f"{marker2} {chosen[1]}{newline}"
            f"{marker3} {chosen[2]}{newline}{newline}"
            f"{sku_line}"
            f"{price_text}{newline}"
            f"{link_text}{newline}{newline}"
            f"{cta}"
        ),
        # Шаблон 6: Детальный
        (
            f"{flash_sale_tag}{price_drop_tag}{emoji} <b>{title}</b>{newline}{newline}"
            f"📝 {short_desc}{newline}{newline}"
            f"{promo_line}"
            f"{header_emoji} <b>{header_text}</b>{newline}"
            f"{marker1} {chosen[0]}{newline}"
            f"{marker2} {chosen[1]}{newline}"
            f"{marker3} {chosen[2]}{newline}{newline}"
            f"{sku_line}"
            f"{price_text}{newline}"
            f"{link_text}{newline}{newline}"
            f"{cta}"
        ),
    ]

    # Случайный выбор шаблона каждый раз (не стабильный)
    caption = templates[template_index]
    return caption


def generate_short_description(data: dict, max_length: int = 100) -> str:
    """Генерирует короткое описание (мини-версия)"""
    title = data.get("title", "").strip()
    desc = (data.get("description") or "").strip()
    price = data.get("price", "Цена уточняется")

    if desc:
        short = desc.split(".")[0].strip()
        if len(short) > max_length:
            short = short[: max_length - 3] + "..."
    else:
        short = f"{title[:50]}..."

    return f"{short}\n💰 {price}"


def generate_long_description(data: dict) -> str:
    """Генерирует длинное описание"""
    title = data.get("title", "").strip()
    desc = (data.get("description") or "").strip()
    price = data.get("price", "Цена уточняется")
    sku = data.get("sku") or ""

    category_reasons = get_reasons_by_category(title, desc)
    chosen = random.sample(category_reasons, min(5, len(category_reasons)))

    text = f"<b>{title}</b>\n\n"
    if desc:
        text += f"{desc}\n\n"
    text += f"<b>Ключевые преимущества:</b>\n"
    for reason in chosen:
        text += f"• {reason}\n"
    text += f"\n💰 Цена: {price}\n"
    if sku:
        text += f"📦 Артикул: {sku}\n"

    return text


def generate_hashtags(title: str, description: str = "") -> str:
    """Генерирует умные хэштеги на основе товара"""
    text = (title + " " + description).lower()
    hashtags = []

    # Категории
    if any(x in text for x in ["шоколад", "конфет", "снек"]):
        hashtags.extend(["#сладости", "#еда", "#вкусно"])
    if any(x in text for x in ["кофе", "чай"]):
        hashtags.extend(["#напитки", "#кофе", "#чай"])
    if any(x in text for x in ["наушник", "смартфон", "телефон"]):
        hashtags.extend(["#техника", "#гаджеты", "#электроника"])
    if any(x in text for x in ["одежд", "рубаш", "куртк"]):
        hashtags.extend(["#одежда", "#мода", "#стиль"])
    if any(x in text for x in ["игрушк", "lego"]):
        hashtags.extend(["#игрушки", "#детям", "#подарок"])

    # Общие
    hashtags.extend(["#яндексмаркет", "#выгодно", "#скидки"])

    # Ограничиваем количество
    return " ".join(hashtags[:5])


def generate_post_variations(data: dict, count: int = 3) -> list:
    """Генерирует несколько вариаций поста"""
    variations = []
    for _ in range(count):
        variations.append(generate_post_caption(data))
    return variations
