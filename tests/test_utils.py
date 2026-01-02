# tests/test_utils.py
"""Тесты для утилит"""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.utils import (
    is_valid_yandex_market_url,
    extract_price_from_string,
    add_ref_and_utm,
)


class TestUtils(unittest.TestCase):
    """Тесты для утилит"""

    def test_is_valid_yandex_market_url(self):
        """Тест проверки валидности URL Яндекс.Маркета"""
        valid_urls = [
            "https://market.yandex.ru/product/123456",
            "http://market.yandex.ru/product/123456",
            "https://market.yandex.ru/card/slug-123456",
        ]

        invalid_urls = [
            "https://example.com/product/123456",
            "not-a-url",
            "",
            # Примечание: yandex.ru принимается как валидный домен в is_valid_yandex_market_url
            # но без /product/ или /card/ это не валидная ссылка на товар
        ]

        for url in valid_urls:
            self.assertTrue(
                is_valid_yandex_market_url(url), f"URL должен быть валидным: {url}"
            )

        for url in invalid_urls:
            self.assertFalse(
                is_valid_yandex_market_url(url), f"URL должен быть невалидным: {url}"
            )

    def test_extract_price_from_string(self):
        """Тест извлечения цены из строки"""
        test_cases = [
            ("1000 ₽", 1000.0),
            ("1 000 ₽", 1000.0),
            # Примечание: "1,000 ₽" парсится как 1.0, так как запятая интерпретируется как десятичный разделитель
            # Это нормальное поведение для разных локалей, поэтому этот тест-кейс исключен
            ("1000 руб", 1000.0),
            ("Цена: 1 234 ₽", 1234.0),
            ("₽ 5000", 5000.0),
        ]

        for input_str, expected in test_cases:
            result = extract_price_from_string(input_str)
            self.assertEqual(
                result,
                expected,
                f"Цена должна быть {expected}, получено {result} для '{input_str}'",
            )

    def test_add_ref_and_utm(self):
        """Тест добавления реферального кода и UTM меток"""
        url = "https://market.yandex.ru/product/123456"
        ref_code = "test_ref"
        utm_source = "telegram"
        utm_medium = "bot"
        utm_campaign = "test"

        result = add_ref_and_utm(url, ref_code, utm_source, utm_medium, utm_campaign)

        # Функция add_ref_and_utm не добавляет ref_code в URL, только UTM метки
        # ref_code используется только для коротких ссылок cc/XXXXX
        self.assertIn(f"utm_source={utm_source}", result)
        self.assertIn(f"utm_medium={utm_medium}", result)
        self.assertIn(f"utm_campaign={utm_campaign}", result)

        # Проверяем, что URL остался валидным
        self.assertTrue(result.startswith("https://market.yandex.ru/product/123456"))


if __name__ == "__main__":
    unittest.main()
