# tests/test_database.py
"""Тесты для database.py"""
import unittest
import os
import tempfile
from database import Database


class TestDatabase(unittest.TestCase):
    """Тесты для класса Database"""

    def setUp(self):
        """Создание временной БД для тестов"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.db = Database(db_file=self.temp_db.name)

    def tearDown(self):
        """Удаление временной БД"""
        if hasattr(self, "db") and self.db:
            self.db.connection.close()
        if os.path.exists(self.temp_db.name):
            try:
                os.remove(self.temp_db.name)
            except PermissionError:
                # В Windows файл может быть заблокирован, игнорируем
                pass

    def test_add_to_queue(self):
        """Тест добавления в очередь"""
        url = "https://market.yandex.ru/product/123456"
        result = self.db.add_to_queue(url)
        self.assertTrue(result)

        # Проверяем, что товар добавлен
        count = self.db.get_queue_count()
        self.assertEqual(count, 1)

    def test_duplicate_queue(self):
        """Тест дубликата в очереди"""
        url = "https://market.yandex.ru/product/123456"
        self.db.add_to_queue(url)

        # Попытка добавить тот же URL
        result = self.db.add_to_queue(url)
        self.assertFalse(result)

        # Должен быть только один товар
        count = self.db.get_queue_count()
        self.assertEqual(count, 1)

    def test_get_next_from_queue(self):
        """Тест получения следующего товара из очереди"""
        url1 = "https://market.yandex.ru/product/111111"
        url2 = "https://market.yandex.ru/product/222222"

        self.db.add_to_queue(url1, priority=1)
        self.db.add_to_queue(url2, priority=2)

        # Должен вернуться товар с большим приоритетом
        task = self.db.get_next_from_queue()
        self.assertIsNotNone(task)
        task_id, url = task
        self.assertEqual(url, url2)

    def test_history(self):
        """Тест истории публикаций"""
        url = "https://market.yandex.ru/product/123456"
        img_hash = "test_hash_123"
        title = "Test Product"

        self.db.add_post_to_history(url, img_hash, title)

        # Проверяем, что товар в истории
        self.assertTrue(self.db.exists_url(url))
        self.assertTrue(self.db.exists_image(img_hash))

        # Получаем историю
        history = self.db.get_history(limit=10)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["url"], url)
        self.assertEqual(history[0]["title"], title)

    def test_blacklist(self):
        """Тест черного списка"""
        url = "https://market.yandex.ru/product/123456"
        reason = "Test reason"

        self.db.add_to_blacklist(url, reason)

        # Проверяем, что URL в черном списке
        self.assertTrue(self.db.is_blacklisted(url))

        # Получаем черный список
        blacklist = self.db.get_blacklist()
        self.assertEqual(len(blacklist), 1)
        self.assertEqual(blacklist[0]["url"], url)
        self.assertEqual(blacklist[0]["reason"], reason)

        # Удаляем из черного списка
        result = self.db.remove_from_blacklist(url)
        self.assertTrue(result)
        self.assertFalse(self.db.is_blacklisted(url))


if __name__ == "__main__":
    unittest.main()
