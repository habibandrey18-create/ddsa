# services/state_service.py
"""Сервис для управления состоянием бота через FSM"""
from typing import Dict, Optional, Any
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import BaseStorage
import logging

logger = logging.getLogger(__name__)


class BotStates(StatesGroup):
    """Состояния бота"""

    waiting_for_url = State()
    waiting_for_search_query = State()
    waiting_for_n_value = State()
    waiting_for_qr_url = State()
    waiting_for_schedule_hours = State()
    waiting_for_schedule_interval = State()


class StateService:
    """Сервис для управления состоянием бота"""

    def __init__(self, storage: BaseStorage):
        self.storage = storage

    async def set_user_state(
        self, user_id: int, state: State, data: Optional[Dict[str, Any]] = None
    ):
        """Устанавливает состояние пользователя"""
        try:
            key = self.storage.resolve_key(user_id=user_id)
            await self.storage.set_state(key=key, state=state)
            if data:
                await self.storage.set_data(key=key, data=data)
        except Exception as e:
            logger.error(f"Failed to set user state: {e}")

    async def get_user_state(self, user_id: int) -> Optional[State]:
        """Получает состояние пользователя"""
        try:
            key = self.storage.resolve_key(user_id=user_id)
            state = await self.storage.get_state(key=key)
            return state
        except Exception as e:
            logger.error(f"Failed to get user state: {e}")
            return None

    async def get_user_data(self, user_id: int) -> Dict[str, Any]:
        """Получает данные пользователя"""
        try:
            key = self.storage.resolve_key(user_id=user_id)
            data = await self.storage.get_data(key=key)
            return data or {}
        except Exception as e:
            logger.error(f"Failed to get user data: {e}")
            return {}

    async def clear_user_state(self, user_id: int):
        """Очищает состояние пользователя"""
        try:
            key = self.storage.resolve_key(user_id=user_id)
            await self.storage.set_state(key=key, state=None)
            await self.storage.set_data(key=key, data={})
        except Exception as e:
            logger.error(f"Failed to clear user state: {e}")


# Глобальные настройки с сохранением в БД
class GlobalSettings:
    """Класс для хранения глобальных настроек с сохранением в БД"""

    def __init__(self, db=None):
        self.db = db
        self._auto_publish_enabled: Optional[bool] = None
        self._schedule_settings: Optional[Dict[str, Any]] = None
        self._load_from_db()

    def _load_from_db(self):
        """Загружает настройки из БД"""
        if not self.db:
            # Если БД не предоставлена, используем значения по умолчанию
            self._auto_publish_enabled = True
            self._schedule_settings = {
                "enabled": False,
                "hours": [],
                "one_per_day": False,
                "interval": 3600,
            }
            return

        try:
            # Загружаем автопубликацию
            auto_pub = self.db.get_setting("auto_publish_enabled", "True")
            self._auto_publish_enabled = auto_pub.lower() in ("true", "1", "yes")

            # Загружаем настройки расписания
            import json

            schedule_json = self.db.get_setting("schedule_settings", "{}")
            try:
                self._schedule_settings = json.loads(schedule_json)
            except (json.JSONDecodeError, TypeError):
                self._schedule_settings = {
                    "enabled": False,
                    "hours": [],
                    "one_per_day": False,
                    "interval": 3600,
                }
        except Exception as e:
            logger.error(f"Failed to load settings from DB: {e}")
            # Используем значения по умолчанию
            self._auto_publish_enabled = True
            self._schedule_settings = {
                "enabled": False,
                "hours": [],
                "one_per_day": False,
                "interval": 3600,
            }

    def get_auto_publish_enabled(self) -> bool:
        """Получить статус автопубликации"""
        if self._auto_publish_enabled is None:
            self._load_from_db()
        return self._auto_publish_enabled or False

    def set_auto_publish_enabled(self, value: bool):
        """Установить статус автопубликации"""
        self._auto_publish_enabled = value
        if self.db:
            try:
                self.db.set_setting("auto_publish_enabled", str(value))
                logger.info(f"Saved auto_publish_enabled to DB: {value}")
            except Exception as e:
                logger.error(f"Failed to save auto_publish_enabled to DB: {e}")

    def get_schedule_settings(self) -> Dict[str, Any]:
        """Получить настройки расписания"""
        if self._schedule_settings is None:
            self._load_from_db()
        return self._schedule_settings.copy() if self._schedule_settings else {}

    def update_schedule_settings(self, **kwargs):
        """Обновить настройки расписания"""
        if self._schedule_settings is None:
            self._load_from_db()

        self._schedule_settings.update(kwargs)

        if self.db:
            try:
                import json

                self.db.set_setting(
                    "schedule_settings", json.dumps(self._schedule_settings)
                )
                logger.info(f"Saved schedule_settings to DB: {kwargs}")
            except Exception as e:
                logger.error(f"Failed to save schedule_settings to DB: {e}")


# Глобальный экземпляр
_global_settings: Optional[GlobalSettings] = None


def get_global_settings(db=None) -> GlobalSettings:
    """Получить глобальный экземпляр настроек

    Args:
        db: Экземпляр Database для сохранения настроек в БД
    """
    global _global_settings
    if _global_settings is None:
        _global_settings = GlobalSettings(db=db)
    elif db and _global_settings.db is None:
        # Обновляем БД если она была предоставлена позже
        _global_settings.db = db
        _global_settings._load_from_db()
    return _global_settings
