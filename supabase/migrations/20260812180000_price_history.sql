-- ประวัติราคาเก่า→ใหม่ (cron refresh-prices) — ใช้แจ้งเตือนราคาตก
CREATE TABLE IF NOT EXISTS price_history (
    id BIGSERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    price_old NUMERIC(12, 2),
    price_new NUMERIC(12, 2),
    drop_pct NUMERIC(6, 2),
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_price_history_product ON price_history(product_id, created_at DESC);
