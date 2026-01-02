# services/config_service.py
"""Сервис для работы с конфигурацией"""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class BotSettings(BaseSettings):
    """Настройки бота через Pydantic"""

    # Основные
    bot_token: str = Field(..., alias="BOT_TOKEN")
    channel_id: str = Field(default="@marketi_tochka", alias="CHANNEL_ID")
    admin_id: int = Field(default=0, alias="ADMIN_ID")

    # Тексты
    anchor_text: str = Field(default="Яндекс.Маркет", alias="ANCHOR_TEXT")

    # API
    use_official_api: bool = Field(default=False, alias="USE_OFFICIAL_API")
    yandex_oauth_token: str = Field(default="", alias="YANDEX_OAUTH_TOKEN")

    # Настройки
    keep_original_url: bool = Field(default=True, alias="KEEP_ORIGINAL_URL")
    image_max_mb: int = Field(default=5, alias="IMAGE_MAX_MB")
    post_interval: int = Field(default=3600, alias="POST_INTERVAL")
    db_file: str = Field(default="bot_database.db", alias="DB_FILE")

    # Фильтры
    min_price: float = Field(default=0, alias="MIN_PRICE")
    max_price: float = Field(default=0, alias="MAX_PRICE")
    min_discount: int = Field(default=0, alias="MIN_DISCOUNT")
    skip_no_price: bool = Field(default=True, alias="SKIP_NO_PRICE")

    # Реф-коды
    ref_code: str = Field(default="", alias="REF_CODE")
    utm_source: str = Field(default="telegram", alias="UTM_SOURCE")
    utm_medium: str = Field(default="bot", alias="UTM_MEDIUM")
    utm_campaign: str = Field(default="marketi_tochka", alias="UTM_CAMPAIGN")

    # Rate limiting
    api_rate_limit: int = Field(default=10, alias="API_RATE_LIMIT")
    api_rate_window: int = Field(default=60, alias="API_RATE_WINDOW")

    # Планирование
    schedule_enabled: bool = Field(default=False, alias="SCHEDULE_ENABLED")
    schedule_hours: str = Field(default="", alias="SCHEDULE_HOURS")
    schedule_one_per_day: bool = Field(default=False, alias="SCHEDULE_ONE_PER_DAY")

    class Config:
        env_file = ".env"
        case_sensitive = False


# Глобальный экземпляр настроек
_settings: Optional[BotSettings] = None


def get_settings() -> BotSettings:
    """Получить настройки (singleton)"""
    global _settings
    if _settings is None:
        _settings = BotSettings()
    return _settings


def reload_settings() -> BotSettings:
    """Перезагрузить настройки из .env"""
    global _settings
    _settings = BotSettings()
    return _settings
