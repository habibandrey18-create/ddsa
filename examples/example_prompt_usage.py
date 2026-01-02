"""
Примеры использования генератора промптов
"""

from utils.prompt_generator import generate_prompt, generate_prompt_from_diff


def example_debug():
    """Пример генерации промпта для дебага"""
    code = """
async def process_and_publish(url: str, chat_id: int = None):
    data = await scrape_yandex_market(url)
    if data["title"]:
        await send_message(chat_id, data["title"])
    return data["ref_link"]
"""

    prompt = generate_prompt(
        code=code,
        mode="auto-debug",
        context="Функция падает с KeyError если 'title' или 'ref_link' отсутствуют в data",
        file_path="bot.py",
    )

    print("=" * 80)
    print("ПРОМПТ ДЛЯ АВТО-ДЕБАГА:")
    print("=" * 80)
    print(prompt)
    print("=" * 80)


def example_refactor():
    """Пример генерации промпта для рефакторинга"""
    code = """
def get_price(data):
    return data.get('price', '0')

def process_url(url):
    result = url.split('/')
    return result[-1]
"""

    prompt = generate_prompt(
        code=code,
        mode="auto-refactor",
        context="Добавь type hints, docstring, проверки на None и обработку ошибок",
    )

    print("=" * 80)
    print("ПРОМПТ ДЛЯ АВТО-РЕФАКТОРИНГА:")
    print("=" * 80)
    print(prompt)
    print("=" * 80)


def example_diff():
    """Пример генерации промпта из diff"""
    diff = """
diff --git a/bot.py b/bot.py
@@ -100,7 +100,7 @@ async def process_data(url):
-    data = await fetch_data(url)
+    data = await fetch_data(url) if url else None
     return data["result"]
"""

    prompt = generate_prompt_from_diff(
        diff=diff,
        mode="auto-debug",
        context="Проверь, не сломалась ли логика после изменений. data может быть None.",
    )

    print("=" * 80)
    print("ПРОМПТ ДЛЯ АНАЛИЗА DIFF:")
    print("=" * 80)
    print(prompt)
    print("=" * 80)


if __name__ == "__main__":
    print("\nПример 1: Авто-дебаг\n")
    example_debug()

    print("\n\nПример 2: Авто-рефакторинг\n")
    example_refactor()

    print("\n\nПример 3: Анализ diff\n")
    example_diff()
