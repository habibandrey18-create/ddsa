#!/usr/bin/env python3
"""Fix database schema issues"""

import sqlite3
import os

def fix_database_schema():
    """Add missing columns to database tables"""

    db_path = "bot_database.db"
    if not os.path.exists(db_path):
        print(f"Database file {db_path} not found!")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Check history table columns
        print("Checking history table schema...")
        cur.execute("PRAGMA table_info(history)")
        history_cols = [r[1] for r in cur.fetchall()]
        print(f"History table columns: {history_cols}")

        if 'deleted' not in history_cols:
            print("Adding 'deleted' column to history table...")
            cur.execute("ALTER TABLE history ADD COLUMN deleted INTEGER DEFAULT 0")
            conn.commit()
            print("✅ Added 'deleted' column to history table")
        else:
            print("✅ 'deleted' column already exists in history table")

        # Check if there are any other missing columns we might need
        required_columns = ['id', 'url', 'image_hash', 'date_added', 'title', 'message_id', 'channel_id', 'deleted']
        missing_columns = [col for col in required_columns if col not in history_cols and col != 'deleted']
        if missing_columns:
            print(f"Warning: Missing columns in history table: {missing_columns}")

        conn.close()
        print("✅ Database schema fixed successfully!")
        return True

    except Exception as e:
        print(f"❌ Error fixing database schema: {e}")
        return False

if __name__ == "__main__":
    print("Fixing database schema...")
    success = fix_database_schema()
    if success:
        print("\nThe database schema has been fixed.")
        print("The cleanup service should now work properly.")
    else:
        print("\nFailed to fix database schema.")