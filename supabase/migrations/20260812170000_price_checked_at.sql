-- ราคาที่อัปเดตล่าสุดจากหน้าเว็บจริง (cron refresh-prices)
ALTER TABLE products ADD COLUMN IF NOT EXISTS price_checked_at TIMESTAMPTZ;
