# services/file_service.py
"""Сервис для работы с файлами"""
import os
import shutil
from pathlib import Path
from typing import List
import logging

logger = logging.getLogger(__name__)


def cleanup_old_files(
    directory: str, max_age_days: int = 7, pattern: str = "*.jpg"
) -> int:
    """Удаляет старые файлы из директории"""
    try:
        from datetime import datetime, timedelta

        cutoff = datetime.now() - timedelta(days=max_age_days)
        deleted = 0

        for file_path in Path(directory).glob(pattern):
            if file_path.is_file():
                file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_time < cutoff:
                    file_path.unlink()
                    deleted += 1

        return deleted
    except Exception as e:
        logger.error("cleanup_old_files error: %s", e)
        return 0


def get_directory_size(directory: str) -> int:
    """Возвращает размер директории в байтах"""
    total = 0
    try:
        for dirpath, dirnames, filenames in os.walk(directory):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if os.path.exists(filepath):
                    total += os.path.getsize(filepath)
    except Exception as e:
        logger.error("get_directory_size error: %s", e)
    return total


def remove_empty_directories(directory: str) -> int:
    """Удаляет пустые директории"""
    removed = 0
    try:
        for dirpath, dirnames, filenames in os.walk(directory, topdown=False):
            if not dirnames and not filenames:
                os.rmdir(dirpath)
                removed += 1
    except Exception as e:
        logger.error("remove_empty_directories error: %s", e)
    return removed


def check_disk_space(path: str = ".") -> dict:
    """Проверяет свободное место на диске"""
    try:
        import shutil

        total, used, free = shutil.disk_usage(path)
        return {
            "total": total,
            "used": used,
            "free": free,
            "percent_used": (used / total) * 100,
        }
    except Exception as e:
        logger.error("check_disk_space error: %s", e)
        return {}
