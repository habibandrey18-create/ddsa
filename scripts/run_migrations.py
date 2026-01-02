#!/usr/bin/env python3
"""
SQL Migration Runner - Запуск миграций для Postgres
"""

import os
import sys
import logging
import psycopg2
from pathlib import Path

# Add project root to path so we can import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_db_connection():
    """Получить подключение к БД из env или docker-compose"""
    import config
    
    if config.USE_POSTGRES:
        conn_string = (
            f"postgresql://{config.POSTGRES_USER}:{config.POSTGRES_PASSWORD}"
            f"@{config.POSTGRES_HOST}:{config.POSTGRES_PORT}/{config.POSTGRES_DB}"
        )
    else:
        # Fallback на DATABASE_URL из env
        conn_string = os.getenv(
            'DATABASE_URL',
            'postgresql://bot:secret@localhost:5432/ymarket'
        )
    
    return psycopg2.connect(conn_string)


def run_migration(sql_file: Path):
    """Запустить одну миграцию"""
    logger.info(f"Running migration: {sql_file.name}")
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        sql_content = sql_file.read_text(encoding='utf-8')
        cur.execute(sql_content)
        conn.commit()
        logger.info(f"✅ Migration {sql_file.name} completed successfully")
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Migration {sql_file.name} failed: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def main():
    """Запустить все миграции"""
    migrations_dir = Path(__file__).parent.parent / 'migrations'
    
    if not migrations_dir.exists():
        logger.error(f"Migrations directory not found: {migrations_dir}")
        sys.exit(1)
    
    migration_files = sorted(migrations_dir.glob('*.sql'))
    
    if not migration_files:
        logger.warning("No migration files found")
        return
    
    logger.info(f"Found {len(migration_files)} migration files")
    
    for migration_file in migration_files:
        try:
            run_migration(migration_file)
        except Exception as e:
            logger.error(f"Failed to run migration {migration_file.name}: {e}")
            sys.exit(1)
    
    logger.info("✅ All migrations completed successfully")


if __name__ == '__main__':
    main()

