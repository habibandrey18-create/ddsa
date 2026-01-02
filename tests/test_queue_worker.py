# tests/test_queue_worker.py
"""Тесты для queue_worker"""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, call
import asyncio
from datetime import datetime


class TestQueueWorker(unittest.TestCase):
    """Тесты для queue_worker"""

    def setUp(self):
        """Настройка перед каждым тестом"""
        self.db_mock = MagicMock()
        self.bot_mock = MagicMock()
        self.global_settings_mock = MagicMock()

    def test_queue_worker_auto_publish_disabled(self):
        """Тест: queue_worker не публикует когда автопубликация отключена"""

        async def run_test():
            with patch("bot.db", self.db_mock):
                with patch(
                    "bot.get_global_settings", return_value=self.global_settings_mock
                ):
                    with patch(
                        "bot.process_and_publish", new_callable=AsyncMock
                    ) as mock_publish:
                        self.global_settings_mock.get_auto_publish_enabled.return_value = (
                            False
                        )
                        self.global_settings_mock.get_schedule_settings.return_value = {
                            "enabled": False
                        }

                        # Импортируем queue_worker
                        from bot import queue_worker

                        # Создаем задачу которая завершится через короткое время
                        async def stop_after_delay():
                            await asyncio.sleep(0.1)
                            # Останавливаем worker через исключение (симуляция)
                            raise KeyboardInterrupt()

                        # Запускаем worker и останавливаем его
                        try:
                            await asyncio.wait_for(queue_worker(), timeout=0.2)
                        except (asyncio.TimeoutError, KeyboardInterrupt):
                            pass

                        # Проверяем что process_and_publish не вызывался
                        mock_publish.assert_not_called()

        asyncio.run(run_test())

    def test_queue_worker_processes_queue_item(self):
        """Тест: queue_worker обрабатывает элемент из очереди"""

        async def run_test():
            with patch("bot.db", self.db_mock):
                with patch(
                    "bot.get_global_settings", return_value=self.global_settings_mock
                ):
                    with patch(
                        "bot.process_and_publish", new_callable=AsyncMock
                    ) as mock_publish:
                        with patch("bot.config", MagicMock(ADMIN_ID=123)):
                            # Настраиваем моки
                            self.global_settings_mock.get_auto_publish_enabled.return_value = (
                                True
                            )
                            self.global_settings_mock.get_schedule_settings.return_value = {
                                "enabled": False,
                                "interval": 1,
                            }

                            # Мокируем очередь: первый вызов возвращает задачу, второй - None
                            call_count = [0]

                            def get_next_side_effect():
                                call_count[0] += 1
                                if call_count[0] == 1:
                                    return (
                                        1,
                                        "https://market.yandex.ru/product/123456",
                                    )
                                return None

                            self.db_mock.get_next_from_queue.side_effect = (
                                get_next_side_effect
                            )
                            self.db_mock.mark_as_done = MagicMock()
                            mock_publish.return_value = True

                            # Импортируем queue_worker
                            from bot import queue_worker

                            # Запускаем worker на короткое время
                            try:
                                await asyncio.wait_for(queue_worker(), timeout=0.5)
                            except (asyncio.TimeoutError, KeyboardInterrupt):
                                pass

                            # Проверяем что process_and_publish был вызван
                            self.assertTrue(mock_publish.called)
                            # Проверяем что задача была помечена как выполненная
                            self.db_mock.mark_as_done.assert_called_once_with(1)

        asyncio.run(run_test())

    def test_queue_worker_handles_publish_error(self):
        """Тест: queue_worker обрабатывает ошибки публикации"""

        async def run_test():
            with patch("bot.db", self.db_mock):
                with patch(
                    "bot.get_global_settings", return_value=self.global_settings_mock
                ):
                    with patch(
                        "bot.process_and_publish", new_callable=AsyncMock
                    ) as mock_publish:
                        with patch("bot.config", MagicMock(ADMIN_ID=123)):
                            # Настраиваем моки
                            self.global_settings_mock.get_auto_publish_enabled.return_value = (
                                True
                            )
                            self.global_settings_mock.get_schedule_settings.return_value = {
                                "enabled": False,
                                "interval": 1,
                            }

                            # Мокируем очередь
                            call_count = [0]

                            def get_next_side_effect():
                                call_count[0] += 1
                                if call_count[0] == 1:
                                    return (
                                        1,
                                        "https://market.yandex.ru/product/123456",
                                    )
                                return None

                            self.db_mock.get_next_from_queue.side_effect = (
                                get_next_side_effect
                            )
                            self.db_mock.mark_as_error = MagicMock()
                            mock_publish.return_value = False  # Публикация не удалась

                            # Импортируем queue_worker
                            from bot import queue_worker

                            # Запускаем worker на короткое время
                            try:
                                await asyncio.wait_for(queue_worker(), timeout=0.5)
                            except (asyncio.TimeoutError, KeyboardInterrupt):
                                pass

                            # Проверяем что задача была помечена как ошибка
                            self.db_mock.mark_as_error.assert_called_once_with(1)

        asyncio.run(run_test())

    def test_queue_worker_handles_exception(self):
        """Тест: queue_worker обрабатывает исключения при публикации"""

        async def run_test():
            with patch("bot.db", self.db_mock):
                with patch(
                    "bot.get_global_settings", return_value=self.global_settings_mock
                ):
                    with patch(
                        "bot.process_and_publish", new_callable=AsyncMock
                    ) as mock_publish:
                        with patch("bot.config", MagicMock(ADMIN_ID=123)):
                            # Настраиваем моки
                            self.global_settings_mock.get_auto_publish_enabled.return_value = (
                                True
                            )
                            self.global_settings_mock.get_schedule_settings.return_value = {
                                "enabled": False,
                                "interval": 1,
                            }

                            # Мокируем очередь
                            call_count = [0]

                            def get_next_side_effect():
                                call_count[0] += 1
                                if call_count[0] == 1:
                                    return (
                                        1,
                                        "https://market.yandex.ru/product/123456",
                                    )
                                return None

                            self.db_mock.get_next_from_queue.side_effect = (
                                get_next_side_effect
                            )
                            self.db_mock.mark_as_error = MagicMock()
                            mock_publish.side_effect = Exception("Test error")

                            # Импортируем queue_worker
                            from bot import queue_worker

                            # Запускаем worker на короткое время
                            try:
                                await asyncio.wait_for(queue_worker(), timeout=0.5)
                            except (asyncio.TimeoutError, KeyboardInterrupt):
                                pass

                            # Проверяем что задача была помечена как ошибка
                            self.db_mock.mark_as_error.assert_called_once_with(1)

        asyncio.run(run_test())

    def test_queue_worker_schedule_check(self):
        """Тест: queue_worker проверяет расписание"""

        async def run_test():
            with patch("bot.db", self.db_mock):
                with patch(
                    "bot.get_global_settings", return_value=self.global_settings_mock
                ):
                    with patch(
                        "bot.process_and_publish", new_callable=AsyncMock
                    ) as mock_publish:
                        # Настраиваем моки
                        self.global_settings_mock.get_auto_publish_enabled.return_value = (
                            True
                        )

                        # Расписание включено, но текущий час не в списке разрешенных
                        now = datetime.now()
                        current_hour = now.hour
                        allowed_hours = [(current_hour + 1) % 24]  # Следующий час

                        self.global_settings_mock.get_schedule_settings.return_value = {
                            "enabled": True,
                            "hours": allowed_hours,
                            "interval": 1,
                        }

                        self.db_mock.get_next_from_queue.return_value = None

                        # Импортируем queue_worker
                        from bot import queue_worker

                        # Запускаем worker на короткое время
                        try:
                            await asyncio.wait_for(queue_worker(), timeout=0.2)
                        except (asyncio.TimeoutError, KeyboardInterrupt):
                            pass

                        # Проверяем что process_and_publish не вызывался (не время для публикации)
                        mock_publish.assert_not_called()

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
