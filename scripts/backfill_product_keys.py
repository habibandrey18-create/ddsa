#!/usr/bin/env python3
"""
Backfill Script - Заполнение product_key для существующих записей
Запустить после миграции 002_add_product_key.sql
"""

import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def backfill_sqlite_product_keys(db_path: str = "bot_database.db"):
    """Backfill product_key для SQLite"""
    try:
        import sqlite3
        from database import Database
        
        logger.info(f"Backfilling product_keys in SQLite database: {db_path}")
        
        db = Database(db_path)
        
        # Проверяем наличие колонки product_key
        try:
            db.cursor.execute("SELECT product_key FROM queue LIMIT 1")
        except sqlite3.OperationalError:
            logger.warning("product_key column not found. Please run migration first.")
            return
        
        # Получаем записи без product_key
        records = db.cursor.execute(
            "SELECT id, url, title FROM queue WHERE product_key IS NULL OR product_key = ''"
        ).fetchall()
        
        logger.info(f"Found {len(records)} records without product_key")
        
        updated = 0
        for record in records:
            try:
                # Генерируем product_key используя метод из database.py
                product_key = db.make_product_key(
                    url=record['url'],
                    title=record.get('title', '')
                )
                
                # Обновляем запись
                db.cursor.execute(
                    "UPDATE queue SET product_key = ? WHERE id = ?",
                    (product_key, record['id'])
                )
                updated += 1
                
                if updated % 100 == 0:
                    logger.info(f"Updated {updated} records...")
                    db.connection.commit()
                    
            except Exception as e:
                logger.warning(f"Failed to update record {record['id']}: {e}")
                continue
        
        db.connection.commit()
        logger.info(f"✅ Backfill complete: {updated} records updated")
        
    except Exception as e:
        logger.error(f"Error during backfill: {e}")
        raise


def backfill_postgres_product_keys():
    """Backfill product_key для Postgres"""
    try:
        import config
        from database_postgres import get_postgres_db
        from database import Database  # Для использования make_product_key
        
        if not config.USE_POSTGRES:
            logger.warning("Postgres not enabled in config")
            return
        
        logger.info("Backfilling product_keys in Postgres database")
        
        db_postgres = get_postgres_db()
        db_sqlite = Database()  # Для метода make_product_key
        
        session = db_postgres.get_session()
        try:
            from sqlalchemy import text
            
            # Получаем записи без product_key
            result = session.execute(text("""
                SELECT id, url, title, vendor, offerid 
                FROM products 
                WHERE product_key IS NULL OR product_key = ''
                LIMIT 1000
            """))
            
            records = result.fetchall()
            logger.info(f"Found {len(records)} records without product_key")
            
            updated = 0
            for record in records:
                try:
                    # Генерируем product_key
                    product_key = db_sqlite.make_product_key(
                        url=record[1] if len(record) > 1 else '',
                        title=record[2] if len(record) > 2 else '',
                        vendor=record[3] if len(record) > 3 else '',
                        offerid=record[4] if len(record) > 4 else ''
                    )
                    
                    # Обновляем запись
                    session.execute(text("""
                        UPDATE products 
                        SET product_key = :key 
                        WHERE id = :id
                    """), {'key': product_key, 'id': record[0]})
                    
                    updated += 1
                    
                    if updated % 100 == 0:
                        session.commit()
                        logger.info(f"Updated {updated} records...")
                        
                except Exception as e:
                    logger.warning(f"Failed to update record {record[0]}: {e}")
                    continue
            
            session.commit()
            logger.info(f"✅ Backfill complete: {updated} records updated")
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Error during Postgres backfill: {e}")
        raise


def main():
    """Main function"""
    import config
    
    try:
        if config.USE_POSTGRES:
            backfill_postgres_product_keys()
        else:
            db_path = getattr(config, 'DB_FILE', 'bot_database.db')
            backfill_sqlite_product_keys(db_path)
            
    except Exception as e:
        logger.error(f"Backfill failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

