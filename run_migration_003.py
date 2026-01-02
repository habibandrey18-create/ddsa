#!/usr/bin/env python3
"""
Run migration 003 to add UNIQUE constraints
This fixes race conditions in deduplication (Critical Issue #4)
"""
import sqlite3
import sys
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_migration(db_path: str = "bot_database.db"):
    """Run migration 003 to add UNIQUE constraints."""
    
    migration_file = Path("migrations/003_add_unique_constraints.sql")
    
    if not migration_file.exists():
        logger.error(f"Migration file not found: {migration_file}")
        return False
    
    logger.info(f"Running migration 003 on database: {db_path}")
    
    try:
        # Backup first
        import shutil
        from datetime import datetime
        
        backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(db_path, backup_path)
        logger.info(f"✅ Database backed up to: {backup_path}")
        
        # Run migration
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        with open(migration_file, 'r', encoding='utf-8') as f:
            migration_sql = f.read()
        
        # Execute migration
        conn.executescript(migration_sql)
        conn.commit()
        
        # Verify
        cursor = conn.execute("""
            SELECT sql FROM sqlite_master 
            WHERE type='table' AND name='history'
        """)
        table_sql = cursor.fetchone()[0]
        
        if 'UNIQUE' in table_sql and 'normalized_url' in table_sql:
            logger.info("✅ Migration 003 successful!")
            logger.info("✅ UNIQUE constraint added to history.normalized_url")
            logger.info("✅ Race conditions eliminated")
            
            # Check for duplicates that were removed
            cursor = conn.execute("SELECT COUNT(*) FROM history")
            count_after = cursor.fetchone()[0]
            logger.info(f"📊 History table has {count_after} unique URLs")
            
            conn.close()
            return True
        else:
            logger.error("❌ Migration verification failed")
            conn.close()
            return False
            
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        logger.error(f"💡 Restore from backup: {backup_path}")
        return False

if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "bot_database.db"
    
    print("="*60)
    print("🔧 MIGRATION 003: Add UNIQUE Constraints")
    print("="*60)
    print("This fixes: Critical Issue #4 - Race Conditions")
    print("Impact: Eliminates duplicate posts under concurrent load")
    print("="*60)
    
    confirm = input("\n⚠️  This will modify your database. Continue? (yes/no): ")
    
    if confirm.lower() != 'yes':
        print("❌ Migration cancelled")
        sys.exit(0)
    
    success = run_migration(db_path)
    
    if success:
        print("\n✅ Migration complete! Race conditions fixed.")
        print("🎯 Next: Run the bot and test with concurrent workers")
        sys.exit(0)
    else:
        print("\n❌ Migration failed. Check logs above.")
        sys.exit(1)

