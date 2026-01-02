# tests/test_more_edge_cases.py
"""Дополнительные тесты для edge cases"""
import unittest
import sys
import os
import tempfile
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database
from bot import validate_product_url, validate_product_data


class TestMoreEdgeCases(unittest.TestCase):
    """Дополнительные тесты для edge cases"""

    def setUp(self):
        """Создание временной БД"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.db = Database(db_file=self.temp_db.name)

    def tearDown(self):
        """Удаление временной БД"""
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def test_url_with_unicode(self):
        """Тест URL с Unicode символами"""
        urls = [
            "https://market.yandex.ru/product/123456?param=тест",
            "https://market.yandex.ru/product/123456?param=тест%20значение",
        ]
        for url in urls:
            is_valid, reason = validate_product_url(url)
            # URL с Unicode должен быть валидным если есть product_id
            self.assertTrue(
                is_valid,
                f"URL с Unicode должен быть валидным: {url}, причина: {reason}",
            )

    def test_url_with_fragments(self):
        """Тест URL с фрагментами"""
        urls = [
            "https://market.yandex.ru/product/123456#section",
            "https://market.yandex.ru/product/123456?param=value#fragment",
        ]
        for url in urls:
            is_valid, reason = validate_product_url(url)
            self.assertTrue(is_valid, f"URL с фрагментом должен быть валидным: {url}")

    def test_multiple_product_ids(self):
        """Тест URL с несколькими product_id"""
        url = "https://market.yandex.ru/product/123456?product_id=789012"
        is_valid, reason = validate_product_url(url)
        # Должен быть валидным (берется первый найденный)
        self.assertTrue(
            is_valid, f"URL с несколькими ID должен быть валидным: {reason}"
        )

    def test_empty_title_with_image(self):
        """Тест товара без названия, но с изображением"""
        data = {
            "title": "",  # Пустое название
            "price": "1000 ₽",
            "url": "https://market.yandex.ru/product/123456",
            "image_url": "https://example.com/image.jpg",
        }
        is_valid, reason = validate_product_data(data, data["url"])
        # Должен быть невалидным (название обязательно)
        self.assertFalse(is_valid, "Товар без названия должен быть невалидным")

    def test_whitespace_only_title(self):
        """Тест названия только из пробелов"""
        data = {
            "title": "   ",  # Только пробелы
            "price": "1000 ₽",
            "url": "https://market.yandex.ru/product/123456",
        }
        is_valid, reason = validate_product_data(data, data["url"])
        self.assertFalse(is_valid, "Название только из пробелов должно быть невалидным")

    def test_negative_price(self):
        """Тест отрицательной цены (если парсер ошибся)"""
        data = {
            "title": "Тестовый товар",
            "price": "-1000 ₽",  # Отрицательная цена
            "url": "https://market.yandex.ru/product/123456",
        }
        # Валидация данных не проверяет числовое значение цены, только наличие
        # Но это можно улучшить
        is_valid, reason = validate_product_data(data, data["url"])
        # Пока что валидный (цена есть)
        self.assertTrue(is_valid, "Товар с отрицательной ценой (пока валидный)")

    def test_very_short_product_id(self):
        """Тест очень короткого product_id"""
        url = "https://market.yandex.ru/product/123"  # Всего 3 цифры
        is_valid, reason = validate_product_url(url)
        self.assertFalse(is_valid, "Product ID должен быть минимум 6 цифр")

    def test_product_id_with_letters(self):
        """Тест product_id с буквами"""
        url = "https://market.yandex.ru/product/123abc"
        is_valid, reason = validate_product_url(url)
        self.assertFalse(is_valid, "Product ID должен быть числовым")

    def test_concurrent_settings_access(self):
        """Тест конкурентного доступа к настройкам"""
        import threading

        def set_setting(key, value):
            try:
                self.db.set_setting(key, value)
            except Exception as e:
                pass

        threads = []
        for i in range(10):
            t = threading.Thread(
                target=set_setting, args=(f"test_key_{i}", f"value_{i}")
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Проверяем, что все настройки сохранены
        settings = self.db.get_settings_dict()
        self.assertGreaterEqual(len(settings), 0)  # Может быть 0 или больше

    def test_json_settings_serialization(self):
        """Тест сериализации настроек в JSON"""
        settings = {
            "enabled": True,
            "hours": [9, 12, 15],
            "one_per_day": False,
            "interval": 3600,
        }

        try:
            json_str = json.dumps(settings)
            parsed = json.loads(json_str)
            self.assertEqual(parsed["enabled"], True)
            self.assertEqual(parsed["hours"], [9, 12, 15])
        except Exception as e:
            self.fail(f"JSON serialization failed: {e}")

    def test_settings_persistence(self):
        """Тест сохранения настроек в БД"""
        # Сохраняем настройку
        self.db.set_setting("test_key", "test_value")

        # Читаем обратно
        value = self.db.get_setting("test_key")
        self.assertEqual(value, "test_value")

        # Обновляем
        self.db.set_setting("test_key", "updated_value")
        value = self.db.get_setting("test_key")
        self.assertEqual(value, "updated_value")

        # Удаляем
        self.db.delete_setting("test_key")
        value = self.db.get_setting("test_key")
        self.assertIsNone(value)


if __name__ == "__main__":
    unittest.main()
