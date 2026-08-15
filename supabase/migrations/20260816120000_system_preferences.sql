-- Migration: 20260816120000_system_preferences.sql
-- Description: Create system_preferences table for Hermes AI (hot-reload bot skills)
-- Used by: backend/app/services/hermes_brain.py (load_skills/save_skills),
--          backend/app/api/facebook_radar.py (radar_min_demand_score / radar_daily_post_limit)

CREATE TABLE IF NOT EXISTS system_preferences (
    key         VARCHAR(100) PRIMARY KEY,
    value       JSONB NOT NULL,
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- ไม่ต้องสร้าง index เพิ่ม: key เป็น PRIMARY KEY อยู่แล้ว
-- ไม่มี seed row: load_skills() คืน DEFAULT_SKILLS เมื่อยังไม่มีแถว hermes_skills
