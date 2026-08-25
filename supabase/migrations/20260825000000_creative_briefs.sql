-- Migration: 20260825000000_creative_briefs.sql
-- Description: สร้างตาราง creative_briefs — ชิ้นงานโฆษณา 3 มุมมองสำหรับ Meta Ads (Creative is Targeting)
--   แต่ละสินค้ามี 3 briefs: problem_solution | review | education
-- Used by: backend/app/models.py (CreativeBrief), backend/app/api/creative_brief.py

CREATE TABLE IF NOT EXISTS creative_briefs (
    id BIGSERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    perspective VARCHAR(30) NOT NULL,   -- problem_solution | review | education
    hook TEXT NOT NULL,
    script_body TEXT NOT NULL,
    cta TEXT NOT NULL,
    caption TEXT NOT NULL,
    hashtags JSONB,
    format_type VARCHAR(50),
    video_duration VARCHAR(20),
    target_behavior TEXT,
    thumbnail_prompt TEXT,
    ai_confidence INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_creative_briefs_product_id ON creative_briefs(product_id);
CREATE INDEX IF NOT EXISTS idx_creative_briefs_perspective ON creative_briefs(perspective);
