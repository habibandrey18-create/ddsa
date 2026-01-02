-- Migration: Add product_key column and unique indexes for deduplication
-- According to requirements: DB-level dedup with unique index on product_key

-- Add product_key column to products table (if not exists)
ALTER TABLE products ADD COLUMN IF NOT EXISTS product_key TEXT;

-- Create unique index on product_key for products table
CREATE UNIQUE INDEX IF NOT EXISTS idx_products_product_key_unique ON products(product_key);

-- Add product_key column to queue table (if using Postgres)
-- Note: queue table might be in SQLite, check your schema
-- ALTER TABLE queue ADD COLUMN IF NOT EXISTS product_key TEXT;

-- Create unique index on product_key for queue (if table exists)
-- CREATE UNIQUE INDEX IF NOT EXISTS idx_queue_product_key_unique ON queue(product_key);

-- Add product_key column to published_posts table (if exists)
-- Note: Check if this table exists in your schema
-- ALTER TABLE published_posts ADD COLUMN IF NOT EXISTS product_key TEXT;

-- Create unique index on product_key for published_posts (if table exists)
-- CREATE UNIQUE INDEX IF NOT EXISTS idx_published_posts_product_key_unique ON published_posts(product_key);

-- Note: For SQLite (if using), unique constraints are created differently:
-- CREATE UNIQUE INDEX IF NOT EXISTS idx_products_product_key_unique ON products(product_key);
-- For SQLite, we can't use ALTER TABLE ADD COLUMN IF NOT EXISTS, need to check first

