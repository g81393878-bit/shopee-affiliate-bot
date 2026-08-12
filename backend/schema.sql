-- Production Database Schema for AI Affiliate Marketing Platform (Phase 1 MVP Refactored)

-- Users Table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'affiliate_manager', -- admin | affiliate_manager | caregiver_staff
    line_user_id VARCHAR(100) UNIQUE,
    shopee_affiliate_id VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Products Table
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    price DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    rating REAL DEFAULT 0.00,
    sales_count INTEGER DEFAULT 0,
    commission DECIMAL(10, 2) DEFAULT 0.00,
    affiliate_url TEXT,
    link_status VARCHAR(20) NOT NULL DEFAULT 'unknown', -- ok | dead | suspect | unknown | none (บอทตอบเฉพาะ ok)
    ai_score INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Product Analysis Table
CREATE TABLE IF NOT EXISTS product_analysis (
    id SERIAL PRIMARY KEY,
    product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
    score INTEGER DEFAULT 0,
    target_customer VARCHAR(255),
    reason TEXT, -- Stores JSON list of reasons
    analysis_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Contents Table
CREATE TABLE IF NOT EXISTS contents (
    id SERIAL PRIMARY KEY,
    product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
    style VARCHAR(50) NOT NULL DEFAULT 'Standard', -- Standard | Funny | Educational | Unboxing
    hook TEXT,
    problem TEXT,
    solution TEXT,
    cta TEXT,
    caption TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Performance Logs Table
CREATE TABLE IF NOT EXISTS performance_logs (
    id SERIAL PRIMARY KEY,
    content_id INTEGER REFERENCES contents(id) ON DELETE CASCADE,
    views INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    orders INTEGER DEFAULT 0,
    commission DECIMAL(10, 2) DEFAULT 0.00,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Staging: raw products from Shopee Affiliate Open API (productOfferV2) — bulk catalog
CREATE TABLE IF NOT EXISTS shopee_products (
    id BIGSERIAL PRIMARY KEY,
    item_id BIGINT NOT NULL UNIQUE,
    shop_id BIGINT,
    shop_name TEXT,
    product_name TEXT NOT NULL,
    product_link TEXT,
    offer_link TEXT,
    image_url TEXT,
    price_min NUMERIC(12, 2),
    price_max NUMERIC(12, 2),
    price_discount_rate DOUBLE PRECISION,
    sales INTEGER,
    rating_star DOUBLE PRECISION,
    commission_rate TEXT,
    seller_commission_rate TEXT,
    shopee_commission_rate TEXT,
    commission NUMERIC(12, 2),
    shop_type INTEGER,
    category_id BIGINT,
    period_start_time BIGINT,
    period_end_time BIGINT,
    raw_json JSONB,
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_shopee_products_item_id ON shopee_products(item_id);
CREATE INDEX IF NOT EXISTS idx_shopee_products_shop_id ON shopee_products(shop_id);

-- Indexes for optimal querying
CREATE INDEX IF NOT EXISTS idx_users_line_id ON users(line_user_id);
CREATE INDEX IF NOT EXISTS idx_products_ai_score ON products(ai_score DESC);
CREATE INDEX IF NOT EXISTS idx_product_analysis_product_id ON product_analysis(product_id);
CREATE INDEX IF NOT EXISTS idx_contents_product_id ON contents(product_id);
CREATE INDEX IF NOT EXISTS idx_performance_logs_content_id ON performance_logs(content_id);

-- ประวัติสนทนาลูกค้า (PDPA: เก็บแค่ 90 วัน — ลบใน log_chat + cron)
CREATE TABLE IF NOT EXISTS chat_logs (
    id BIGSERIAL PRIMARY KEY,
    line_user_id TEXT NOT NULL,
    message_text TEXT NOT NULL,
    intent TEXT NOT NULL DEFAULT 'unknown',
    category TEXT,
    reply_kind TEXT NOT NULL DEFAULT 'text',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_chat_logs_user ON chat_logs(line_user_id);
CREATE INDEX IF NOT EXISTS idx_chat_logs_created ON chat_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_chat_logs_category ON chat_logs(category);

-- บันทึกแคมเปญที่เอเจนต์ส่ง (กันส่งซ้ำ + ตรวจสอบ)
CREATE TABLE IF NOT EXISTS campaign_logs (
    id BIGSERIAL PRIMARY KEY,
    category TEXT NOT NULL,
    recipients INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'dryrun',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
