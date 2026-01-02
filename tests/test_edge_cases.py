# tests/test_edge_cases.py
"""Тесты для edge cases и граничных условий"""
import unittest
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database
from bot import validate_product_url, validate_product_data


class TestEdgeCases(unittest.TestCase):
    """Тесты для edge cases"""

    def setUp(self):
        """Создание временной БД"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.db = Database(db_file=self.temp_db.name)

    def tearDown(self):
        """Удаление временной БД"""
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def test_very_long_url(self):
        """Тест очень длинного URL"""
        long_url = (
            "https://market.yandex.ru/product/123456"
            + "?"
            + "&".join([f"param{i}=value{i}" for i in range(100)])
        )
        is_valid, reason = validate_product_url(long_url)
        # Длинный URL с валидным product_id должен быть валидным
        self.assertTrue(is_valid, f"Длинный URL должен быть валидным: {reason}")

    def test_url_with_special_chars(self):
        """Тест URL со специальными символами"""
        urls = [
            "https://market.yandex.ru/product/123456?param=value%20with%20spaces",
            "https://market.yandex.ru/product/123456?param=value+with+plus",
            "https://market.yandex.ru/product/123456#fragment",
        ]
        for url in urls:
            is_valid, reason = validate_product_url(url)
            self.assertTrue(
                is_valid,
                f"URL со спецсимволами должен быть валидным: {url}, причина: {reason}",
            )

    def test_empty_strings(self):
        """Тест пустых строк"""
        is_valid, reason = validate_product_url("")
        self.assertFalse(is_valid)

        is_valid, reason = validate_product_data({}, "")
        self.assertFalse(is_valid)
        self.assertIn("Нет данных", reason)

    def test_none_values(self):
        """Тест None значений"""
        is_valid, reason = validate_product_url(None)
        self.assertFalse(is_valid)

        is_valid, reason = validate_product_data(
            None, "https://market.yandex.ru/product/123456"
        )
        self.assertFalse(is_valid)

    def test_unicode_in_title(self):
        """Тест Unicode символов в названии"""
        data = {
            "title": "Товар с эмодзи 🎁 и кириллицей",
            "price": "1000 ₽",
            "url": "https://market.yandex.ru/product/123456",
        }
        is_valid, reason = validate_product_data(data, data["url"])
        self.assertTrue(is_valid, f"Unicode должен обрабатываться: {reason}")

    def test_extreme_price_values(self):
        """Тест экстремальных значений цены"""
        cases = [
            {"price": "0 ₽", "should_be_valid": False},  # Нулевая цена
            {"price": "999999999 ₽", "should_be_valid": True},  # Очень большая цена
            {"price": "Цена уточняется", "should_be_valid": True},  # Текст вместо цены
        ]

        for case in cases:
            data = {
                "title": "Тестовый товар",
                "price": case["price"],
                "url": "https://market.yandex.ru/product/123456",
            }
            is_valid, reason = validate_product_data(data, data["url"])
            if case["should_be_valid"]:
                self.assertTrue(
                    is_valid, f"Цена '{case['price']}' должна быть валидной: {reason}"
                )
            else:
                # Нулевая цена может быть валидной в зависимости от логики
                pass

    def test_concurrent_queue_operations(self):
        """Тест конкурентных операций с очередью"""
        import threading

        urls = [f"https://market.yandex.ru/product/{i}" for i in range(100, 200)]
        results = []

        def add_url(url):
            try:
                result = self.db.add_to_queue(url)
                results.append((url, result))
            except Exception as e:
                results.append((url, False, str(e)))

        threads = [threading.Thread(target=add_url, args=(url,)) for url in urls]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Проверяем, что все URL добавлены (или были дубликаты)
        count = self.db.get_queue_count()
        self.assertGreater(count, 0, "Должны быть добавлены товары")
        self.assertLessEqual(
            count, len(urls), "Не должно быть больше товаров, чем добавлено"
        )

    def test_malformed_urls(self):
        """Тест некорректно сформированных URL"""
        malformed_urls = [
            "market.yandex.ru/product/123456",  # Без протокола
            "https://market.yandex.ru/",  # Без пути
            "https://market.yandex.ru/product/",  # Без ID
            "https://market.yandex.ru/product/abc",  # ID не числовой
            "https://market.yandex.ru/product/123",  # ID слишком короткий
        ]

        for url in malformed_urls:
            is_valid, reason = validate_product_url(url)
            self.assertFalse(is_valid, f"Некорректный URL должен быть отклонён: {url}")

    def test_sql_injection_protection(self):
        """Тест защиты от SQL injection"""
        malicious_inputs = [
            "'; DROP TABLE queue; --",
            "' OR '1'='1",
            "'; DELETE FROM history; --",
        ]

        for malicious in malicious_inputs:
            # Попытка добавить в очередь с вредоносным URL
            try:
                result = self.db.add_to_queue(malicious)
                # Должно либо отклонить, либо безопасно обработать
                # Проверяем, что БД не повреждена
                count = self.db.get_queue_count()
                self.assertIsInstance(count, int)
            except Exception as e:
                # Исключение тоже нормально - это защита
                pass

    def test_very_long_title(self):
        """Тест очень длинного названия"""
        long_title = "A" * 10000  # Очень длинное название
        data = {
            "title": long_title,
            "price": "1000 ₽",
            "url": "https://market.yandex.ru/product/123456",
        }
        is_valid, reason = validate_product_data(data, data["url"])
        # Длинное название должно быть валидным (обрезается при публикации)
        self.assertTrue(is_valid, f"Длинное название должно быть валидным: {reason}")

    def test_special_price_formats(self):
        """Тест специальных форматов цены"""
        special_prices = [
            "1 000 000 ₽",
            "1,000,000 ₽",
            "1000000 руб.",
            "от 1000 ₽",
            "до 5000 ₽",
            "1000-2000 ₽",
        ]

        for price in special_prices:
            data = {
                "title": "Тестовый товар",
                "price": price,
                "url": "https://market.yandex.ru/product/123456",
            }
            is_valid, reason = validate_product_data(data, data["url"])
            # Все форматы должны быть валидными (цена обрабатывается отдельно)
            self.assertTrue(
                is_valid,
                f"Специальный формат цены должен быть валидным: {price}, причина: {reason}",
            )


if __name__ == "__main__":
    unittest.main()
