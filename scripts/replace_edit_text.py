# scripts/replace_edit_text.py
"""Скрипт для массовой замены edit_text на safe_edit_text"""
import re
import os


def replace_edit_text_in_file(file_path: str):
    """Заменяет callback.message.edit_text на safe_edit_callback_message в файле"""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    original_content = content

    # Паттерн для поиска await callback.message.edit_text(...)
    # Учитываем многострочные вызовы
    pattern = r"await\s+callback\.message\.edit_text\s*\("

    # Проверяем, есть ли импорт safe_edit
    has_import = (
        "from utils.safe_edit import" in content or "import utils.safe_edit" in content
    )

    if re.search(pattern, content):
        # Добавляем импорт если его нет
        if not has_import:
            # Ищем место для импорта (после других импортов)
            import_pattern = r"(from\s+utils\.\w+\s+import\s+[^\n]+\n)"
            match = re.search(import_pattern, content)
            if match:
                content = (
                    content[: match.end()]
                    + "from utils.safe_edit import safe_edit_callback_message\n"
                    + content[match.end() :]
                )
            else:
                # Ищем место после импортов aiogram
                aiogram_import = re.search(r"(from aiogram[^\n]+\n)", content)
                if aiogram_import:
                    content = (
                        content[: aiogram_import.end()]
                        + "from utils.safe_edit import safe_edit_callback_message\n"
                        + content[aiogram_import.end() :]
                    )

        # Заменяем вызовы
        # Простая замена для однострочных
        content = re.sub(
            r"await\s+callback\.message\.edit_text\s*\(",
            "await safe_edit_callback_message(callback, ",
            content,
        )

        # Для многострочных нужно более сложная логика, но пока оставим простую замену

    if content != original_content:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ Обновлен: {file_path}")
        return True
    return False


if __name__ == "__main__":
    # Файлы для обработки
    files_to_process = ["bot.py", "handlers/callbacks.py", "handlers/messages.py"]

    updated_count = 0
    for file_path in files_to_process:
        if os.path.exists(file_path):
            if replace_edit_text_in_file(file_path):
                updated_count += 1
        else:
            print(f"⚠️ Файл не найден: {file_path}")

    print(f"\n✅ Обработано файлов: {updated_count}")
