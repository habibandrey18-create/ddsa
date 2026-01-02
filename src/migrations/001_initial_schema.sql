-- SQL Migration for Yandex.Market Bot
-- Products table (dedup)
CREATE TABLE IF NOT EXISTS products (
  market_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  price NUMERIC(10, 2),
  brand TEXT,
  vendor TEXT,
  offerid TEXT,
  old_price NUMERIC(10, 2),
  discount_percent FLOAT,
  rating FLOAT,
  reviews_count INTEGER,
  images JSONB,
  specs JSONB,
  marketing_description TEXT,
  availability BOOLEAN DEFAULT TRUE,
  added_at TIMESTAMP DEFAULT now(),
  last_updated TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand);
CREATE INDEX IF NOT EXISTS idx_products_price ON products(price);
CREATE INDEX IF NOT EXISTS idx_products_rating ON products(rating);
CREATE INDEX IF NOT EXISTS idx_products_added_at ON products(added_at);

-- Metrics table for affiliate tracking
CREATE TABLE IF NOT EXISTS metrics (
  id SERIAL PRIMARY KEY,
  market_id TEXT,
  erid TEXT,
  link TEXT,
  brand TEXT,
  price NUMERIC(10, 2),
  category TEXT,
  post_type TEXT,
  clicks INTEGER DEFAULT 0,
  ctr FLOAT DEFAULT 0,
  revenue NUMERIC(10, 2) DEFAULT 0,
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_metrics_market_id ON metrics(market_id);
CREATE INDEX IF NOT EXISTS idx_metrics_erid ON metrics(erid);
CREATE INDEX IF NOT EXISTS idx_metrics_created_at ON metrics(created_at);
CREATE INDEX IF NOT EXISTS idx_metrics_brand ON metrics(brand);
CREATE INDEX IF NOT EXISTS idx_metrics_category ON metrics(category);

-- Post performance tracking (for ROI-based throttling)
CREATE TABLE IF NOT EXISTS post_performance (
  id SERIAL PRIMARY KEY,
  market_id TEXT NOT NULL,
  erid TEXT,
  brand TEXT,
  category TEXT,
  post_type TEXT,
  price_bucket TEXT,  -- e.g., '0-1000', '1000-5000', '5000+'
  clicks INTEGER DEFAULT 0,
  ctr FLOAT DEFAULT 0,
  revenue NUMERIC(10, 2) DEFAULT 0,
  published_at TIMESTAMP NOT NULL,
  created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_post_performance_published_at ON post_performance(published_at);
CREATE INDEX IF NOT EXISTS idx_post_performance_brand ON post_performance(brand);
CREATE INDEX IF NOT EXISTS idx_post_performance_category ON post_performance(category);
CREATE INDEX IF NOT EXISTS idx_post_performance_post_type ON post_performance(post_type);

-- Category performance (for learning what to post)
CREATE TABLE IF NOT EXISTS category_performance (
  id SERIAL PRIMARY KEY,
  category TEXT NOT NULL,
  post_type TEXT NOT NULL,
  price_bucket TEXT,
  avg_clicks_per_post FLOAT DEFAULT 0,
  total_posts INTEGER DEFAULT 0,
  total_clicks INTEGER DEFAULT 0,
  total_revenue NUMERIC(10, 2) DEFAULT 0,
  last_updated TIMESTAMP DEFAULT now(),
  UNIQUE(category, post_type, price_bucket)
);

CREATE INDEX IF NOT EXISTS idx_category_performance_category ON category_performance(category);
CREATE INDEX IF NOT EXISTS idx_category_performance_last_updated ON category_performance(last_updated);

-- Brand performance
CREATE TABLE IF NOT EXISTS brand_performance (
  id SERIAL PRIMARY KEY,
  brand TEXT NOT NULL UNIQUE,
  total_posts INTEGER DEFAULT 0,
  total_clicks INTEGER DEFAULT 0,
  avg_clicks_per_post FLOAT DEFAULT 0,
  last_updated TIMESTAMP DEFAULT now()
);

-- Shadow ban detector log
CREATE TABLE IF NOT EXISTS shadow_ban_log (
  id SERIAL PRIMARY KEY,
  catalog_url TEXT,
  parsed_count INTEGER,
  status_code INTEGER,
  error_message TEXT,
  detected_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_shadow_ban_log_detected_at ON shadow_ban_log(detected_at);

