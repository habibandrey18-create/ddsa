# tests/test_validation.py
"""Тесты для валидации URL и данных товаров"""
import unittest
import sys
import os

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Импортируем функции валидации из bot.py
# В реальности лучше вынести их в отдельный модуль
from bot import validate_product_url, validate_product_data


class TestValidation(unittest.TestCase):
    """Тесты для функций валидации"""

    def test_valid_product_url(self):
        """Тест валидных URL товаров"""
        valid_urls = [
            "https://market.yandex.ru/product/123456",
            "https://market.yandex.ru/product/123456789",
            "https://market.yandex.ru/card/slug-123456",
            "https://market.yandex.ru/product/123456?param=value",
        ]

        for url in valid_urls:
            is_valid, reason = validate_product_url(url)
            self.assertTrue(
                is_valid, f"URL должен быть валидным: {url}, причина: {reason}"
            )

    def test_invalid_product_url(self):
        """Тест невалидных URL товаров"""
        invalid_urls = [
            "https://market.yandex.ru/card/slug-without-id",
            "https://market.yandex.ru/product/",
            "https://example.com/product/123456",
            "",
            "not-a-url",
        ]

        for url in invalid_urls:
            is_valid, reason = validate_product_url(url)
            self.assertFalse(is_valid, f"URL должен быть невалидным: {url}")

    def test_validate_product_data_valid(self):
        """Тест валидации валидных данных товара"""
        valid_data = {
            "title": "Тестовый товар с длинным названием",
            "price": "1000 ₽",
            "url": "https://market.yandex.ru/product/123456",
            "image_url": "https://example.com/image.jpg",
        }

        is_valid, reason = validate_product_data(valid_data, valid_data["url"])
        self.assertTrue(is_valid, f"Данные должны быть валидными, причина: {reason}")

    def test_validate_product_data_invalid(self):
        """Тест валидации невалидных данных товара"""
        invalid_cases = [
            # Нет названия
            {
                "data": {
                    "price": "1000 ₽",
                    "url": "https://market.yandex.ru/product/123456",
                },
                "expected_reason": "Нет названия",
            },
            # Слишком короткое название
            {
                "data": {
                    "title": "А",
                    "price": "1000 ₽",
                    "url": "https://market.yandex.ru/product/123456",
                },
                "expected_reason": "короткое",
            },
            # Нет цены
            {
                "data": {
                    "title": "Тестовый товар",
                    "url": "https://market.yandex.ru/product/123456",
                },
                "expected_reason": "Нет цены",
            },
            # Пустые данные
            {"data": {}, "expected_reason": "Нет данных"},
        ]

        for case in invalid_cases:
            data = case["data"]
            url = data.get("url", "https://market.yandex.ru/product/123456")
            is_valid, reason = validate_product_data(data, url)
            self.assertFalse(is_valid, f"Данные должны быть невалидными: {data}")
            self.assertIn(
                case["expected_reason"].lower(),
                reason.lower(),
                f"Причина должна содержать '{case['expected_reason']}', получено: {reason}",
            )


if __name__ == "__main__":
    unittest.main()
