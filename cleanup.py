#!/usr/bin/env python3
"""
cleanup.py - Удаление мусора из проекта
Безопасно удаляет только ненужные файлы
"""
import os
import shutil
from pathlib import Path


# ✅ ФАЙЛЫ/ПАПКИ КОТОРЫЕ НУЖНО УДАЛИТЬ
JUNK_PATTERNS = {
    # Документация/объяснения (кроме важных)
    "*.md": [
        "README.md",
        "CHANGELOG.md",
        "TODO.md",
        "NOTES.md",
        "DEBUG.md",
        "FIXES.md",
    ],
    # Отчеты/логи/дебаг
    "debug_*": True,  # Все файлы debug_*
    "report_*": True,
    "*.log": True,
    ".log": True,
    # Временные файлы
    "__pycache__": True,
    ".pytest_cache": True,
    ".coverage": True,
    "*.pyc": True,
    "*.pyo": True,
    ".DS_Store": True,
    "Thumbs.db": True,
    # IDE мусор
    ".vscode": True,
    ".idea": True,
    "*.swp": True,
    "*.swo": True,
    # Скриншоты/медиа дебаг
    "screenshot_*.jpg": True,
    "modal_html_*.html": True,
    "debug_ref_link_*": True,
}


# ❌ ФАЙЛЫ/ПАПКИ КОТОРЫЕ НЕ ТРОГАТЬ (ВАЖНОЕ)
KEEP_SAFE = {
    "bot.py",
    "main.py",
    "app.py",
    "config.py",
    "database.py",
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    ".env",
    ".env.example",
    "cookies.json",
    "logging_config.json",
    "utils",
    "services",
    "handlers",
    "models",
    "database",
    "data",
    "config",
    ".git",
    ".gitignore",
    "venv",
    "env",
    "migrations",
    "alembic",
    "tests",
    "test_",
    "run_browser_once.py",
    "check_bot.py",
    "cleanup.py",
    "handlers_admin.py",
    "handlers_user.py",
    "worker.py",
}


def should_keep(path: str) -> bool:
    """Проверка что файл/папка важные"""
    path_lower = path.lower()
    name = os.path.basename(path_lower)

    # Абсолютный путь для проверки
    abs_path = os.path.abspath(path_lower)

    for keep in KEEP_SAFE:
        keep_lower = keep.lower()
        # Проверка по имени файла/папки
        if name == keep_lower or name.startswith(keep_lower):
            return True
        # Проверка по пути
        if keep_lower in abs_path.replace("\\", "/"):
            return True

    return False


def cleanup(root_dir: str = "."):
    """Удаляет мусор"""
    removed = []
    skipped = []
    errors = []

    root_dir = os.path.abspath(root_dir)

    print(f"📁 Очистка директории: {root_dir}")
    print()

    for root, dirs, files in os.walk(root_dir):
        # Пропусти важные папки
        dirs[:] = [d for d in dirs if not should_keep(os.path.join(root, d))]

        # Удали файлы
        for file in files:
            full_path = os.path.join(root, file)

            # Пропусти если это важный файл
            if should_keep(full_path):
                skipped.append(full_path)
                continue

            # Проверка по паттернам
            should_remove = False

            # *.md файлы (кроме важных)
            if file.endswith(".md"):
                important_md = [
                    "readme.md",
                    "changelog.md",
                    "start_bot.md",
                    "bot_status.md",
                    "quick_start.md",
                    "instructions_after_cookies.md",
                    "clean_fixes_applied.md",
                ]
                if file.lower() not in [f.lower() for f in important_md]:
                    should_remove = True

            # debug_* файлы
            if file.startswith("debug_"):
                should_remove = True

            # screenshot_* файлы
            if file.startswith("screenshot_"):
                should_remove = True

            # modal_html_* файлы
            if file.startswith("modal_html_"):
                should_remove = True

            # .log файлы
            if file.endswith(".log"):
                should_remove = True

            # report_* файлы
            if file.startswith("report_"):
                should_remove = True

            # *.pyc файлы
            if file.endswith(".pyc"):
                should_remove = True

            # *.pyo файлы
            if file.endswith(".pyo"):
                should_remove = True

            if should_remove:
                try:
                    os.remove(full_path)
                    removed.append(full_path)
                    print(f"🗑️  Удален: {full_path}")
                except Exception as e:
                    errors.append((full_path, str(e)))
                    print(f"❌ Ошибка удаления {full_path}: {e}")

    # Удали папки __pycache__ и .pytest_cache
    for root, dirs, files in os.walk(root_dir):
        for dir_name in dirs[:]:
            dir_path = os.path.join(root, dir_name)

            if dir_name == "__pycache__" or dir_name == ".pytest_cache":
                if not should_keep(dir_path):
                    try:
                        shutil.rmtree(dir_path)
                        removed.append(dir_path)
                        print(f"🗑️  Удалена папка: {dir_path}")
                    except Exception as e:
                        errors.append((dir_path, str(e)))
                        print(f"❌ Ошибка удаления папки {dir_path}: {e}")

    # Итоги
    print()
    print("=" * 60)
    print(f"✅ Удалено файлов/папок: {len(removed)}")
    print(f"⏭️  Пропущено (важные): {len(skipped)}")
    if errors:
        print(f"❌ Ошибок: {len(errors)}")
    print("=" * 60)


if __name__ == "__main__":
    print("=" * 60)
    print("🧹 CLEANUP - Удаление мусора из проекта")
    print("=" * 60)
    print()
    print("⚠️  ВНИМАНИЕ: Будут удалены:")
    print("   - Файлы .md (кроме важных)")
    print("   - Папки __pycache__")
    print("   - Файлы .log")
    print("   - Файлы debug_*, report_*, screenshot_*")
    print("   - Временные файлы")
    print()

    response = input("Продолжить? (yes/no): ").strip().lower()
    if response not in ["yes", "y", "да", "д"]:
        print("❌ Отменено пользователем")
        exit(0)

    print()
    cleanup()

    print()
    print("=" * 60)
    print("✅ Cleanup завершен!")
    print("=" * 60)
