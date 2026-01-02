# services/cookies_encryption.py
"""Утилита для шифрования/дешифрования cookies"""
import os
import json
import logging
from typing import List, Dict, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import base64

logger = logging.getLogger(__name__)


def _get_encryption_key() -> bytes:
    """Получает ключ шифрования из .env или генерирует на основе системной информации"""
    # Пытаемся получить ключ из .env
    key_str = os.getenv("COOKIES_ENCRYPTION_KEY")
    if key_str:
        try:
            # Если ключ уже в правильном формате (Fernet key - 44 символа base64)
            if len(key_str) == 44:
                return key_str.encode()
            # Иначе генерируем ключ из строки
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b"yandex_market_bot",
                iterations=100000,
                backend=default_backend(),
            )
            key = base64.urlsafe_b64encode(kdf.derive(key_str.encode()))
            return key
        except Exception as e:
            logger.warning(f"Failed to use COOKIES_ENCRYPTION_KEY: {e}")

    # Fallback: используем системную информацию для генерации ключа
    # ВАЖНО: это не идеально безопасно, но лучше чем plain text
    import platform
    import getpass

    salt = f"{platform.node()}{getpass.getuser()}".encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend(),
    )
    key = base64.urlsafe_b64encode(kdf.derive(b"yandex_market_bot_cookies"))
    return key


def encrypt_cookies(cookies: List[Dict]) -> str:
    """
    Шифрует cookies для безопасного хранения

    Args:
        cookies: Список cookies в формате Playwright

    Returns:
        Зашифрованная строка (base64)
    """
    try:
        key = _get_encryption_key()
        f = Fernet(key)

        # Сериализуем cookies в JSON
        cookies_json = json.dumps(cookies)
        cookies_bytes = cookies_json.encode("utf-8")

        # Шифруем
        encrypted = f.encrypt(cookies_bytes)

        return encrypted.decode("utf-8")
    except Exception as e:
        logger.exception(f"Failed to encrypt cookies: {e}")
        # Fallback: base64 encoding (не безопасно, но лучше чем plain)
        cookies_json = json.dumps(cookies)
        return base64.b64encode(cookies_json.encode("utf-8")).decode("utf-8")


def decrypt_cookies(encrypted_data: str) -> Optional[List[Dict]]:
    """
    Дешифрует cookies из зашифрованной строки

    Args:
        encrypted_data: Зашифрованная строка

    Returns:
        Список cookies или None при ошибке
    """
    try:
        key = _get_encryption_key()
        f = Fernet(key)

        # Дешифруем
        decrypted = f.decrypt(encrypted_data.encode("utf-8"))
        cookies_json = decrypted.decode("utf-8")
        cookies = json.loads(cookies_json)

        return cookies if isinstance(cookies, list) else None
    except Exception as e:
        # Пробуем base64 decode (fallback для старых файлов)
        try:
            decoded = base64.b64decode(encrypted_data.encode("utf-8"))
            cookies_json = decoded.decode("utf-8")
            cookies = json.loads(cookies_json)
            return cookies if isinstance(cookies, list) else None
        except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.exception(f"Failed to decrypt cookies: {e}")
            return None
