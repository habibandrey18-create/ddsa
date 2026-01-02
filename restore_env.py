#!/usr/bin/env python3
"""
Script to restore/create .env file with default configuration
"""
import os


def create_env_file():
    """Create .env file with default configuration"""

    env_content = """# Telegram Bot Configuration
BOT_TOKEN=846192345:AAEXAMPLE_TOKEN_HERE_REPLACE_WITH_REAL
ADMIN_ID=123456789

# Database
DB_FILE=bot_database.db

# Channel Configuration
CHANNEL_ID=@marketi_tochka

# Link Generation
ANCHOR_TEXT=Яндекс.Маркет
REF_CODE=
UTM_SOURCE=telegram
UTM_MEDIUM=bot
UTM_CAMPAIGN=marketi_tochka

# Auto Search Settings
AUTO_SEARCH_ENABLED=true
AUTO_SEARCH_INTERVAL_MINUTES=30
AUTO_MAIN_PAGE_ENABLED=true

# Posting Settings
POST_INTERVAL=3600
MIN_PRICE=0
MAX_PRICE=0
MIN_DISCOUNT=0
SKIP_NO_PRICE=true

# Image Settings
IMAGE_MAX_MB=5

# Night Mode
NIGHT_START=22
NIGHT_END=8

# Analytics
ANALYTICS_ENABLED=true

# Webhook (optional)
USE_WEBHOOK=false
WEBHOOK_URL=
WEBHOOK_PATH=/webhook

# Schedule (optional)
SCHEDULE_ENABLED=false
SCHEDULE_HOURS=
SCHEDULE_ONE_PER_DAY=false

# Backup
BACKUP_ENABLED=true
BACKUP_INTERVAL_HOURS=24

# Cleaner
CLEANER_ENABLED=true
CLEANER_INTERVAL_HOURS=6

# Digest
DIGEST_FREQUENCY=10
DIGEST_MAX_ITEMS=20
DIGEST_MIN_ITEMS=5

# Logging
LOG_LEVEL=INFO

# Performance
MAX_WORKERS=4
REQUEST_TIMEOUT=30
CACHE_ENABLED=true
CACHE_TTL=3600
"""

    with open(".env", "w", encoding="utf-8") as f:
        f.write(env_content)

    print("Created .env file with default configuration")
    print("IMPORTANT: Replace BOT_TOKEN with your actual Telegram bot token!")
    print("Get it from @BotFather on Telegram")


if __name__ == "__main__":
    create_env_file()
