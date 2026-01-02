-- Migration 003: Add UNIQUE constraints to prevent race conditions
-- This fixes critical issue #4 from audit report
-- Prevents duplicate posts when bot + worker run concurrently

-- Step 1: Create new history table with UNIQUE constraint
CREATE TABLE IF NOT EXISTS history_new (
    id INTEGER PRIMARY KEY,
    normalized_url TEXT NOT NULL UNIQUE,  -- FIXED: Added UNIQUE constraint
    url TEXT,
    image_hash TEXT,
    date_added TIMESTAMP,
    title TEXT DEFAULT '',
    last_price REAL,
    message_id INTEGER,
    channel_id TEXT,
    template_type TEXT,
    views_24h INTEGER DEFAULT 0,
    deleted BOOLEAN DEFAULT 0
);

-- Step 2: Copy data from old table (handle duplicates)
INSERT OR IGNORE INTO history_new 
SELECT 
    id,
    normalized_url,
    url,
    image_hash,
    date_added,
    title,
    last_price,
    message_id,
    channel_id,
    template_type,
    views_24h,
    deleted
FROM history;

-- Step 3: Drop old table and rename new one
DROP TABLE history;
ALTER TABLE history_new RENAME TO history;

-- Step 4: Recreate indices
CREATE INDEX IF NOT EXISTS idx_history_url ON history(url);
CREATE INDEX IF NOT EXISTS idx_history_image_hash ON history(image_hash);
CREATE INDEX IF NOT EXISTS idx_history_date ON history(date_added);
CREATE INDEX IF NOT EXISTS idx_history_normalized_url ON history(normalized_url);
CREATE INDEX IF NOT EXISTS idx_history_message_id ON history(message_id);
CREATE INDEX IF NOT EXISTS idx_history_channel_id ON history(channel_id);
CREATE INDEX IF NOT EXISTS idx_history_template_type ON history(template_type);

-- Step 5: Create new queue table with UNIQUE constraint
CREATE TABLE IF NOT EXISTS queue_new (
    id INTEGER PRIMARY KEY,
    normalized_url TEXT NOT NULL UNIQUE,  -- FIXED: Added UNIQUE constraint
    url TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP,
    priority INTEGER DEFAULT 0,
    scheduled_time TIMESTAMP NULL
);

-- Step 6: Copy data from old queue table
INSERT OR IGNORE INTO queue_new 
SELECT 
    id,
    normalized_url,
    url,
    status,
    created_at,
    priority,
    scheduled_time
FROM queue;

-- Step 7: Drop old queue and rename
DROP TABLE queue;
ALTER TABLE queue_new RENAME TO queue;

-- Step 8: Recreate queue indices
CREATE INDEX IF NOT EXISTS idx_queue_status ON queue(status);
CREATE INDEX IF NOT EXISTS idx_queue_created ON queue(created_at);
CREATE INDEX IF NOT EXISTS idx_queue_normalized_url ON queue(normalized_url);

-- Migration complete
-- RESULT: Race conditions eliminated, duplicate posts impossible

