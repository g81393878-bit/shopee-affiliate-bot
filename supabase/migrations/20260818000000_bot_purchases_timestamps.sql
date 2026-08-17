-- Migration: 20260818000000_bot_purchases_timestamps.sql
-- Description: บันทึกเวลาชัดเจนสำหรับการขายบอท (รับเรื่อง/เริ่มทำ) — ยึดระยะเวลาจากจุดยืนยัน ไม่เลื่อนไปเรื่อย ๆ
-- Used by: backend/app/api/line_bot.py (ติดตามสถานะซื้อบอท + ระบบคิว)
--   paid_at      = ลูกค้าแจ้งโอนเงินเมื่อไหร่ (สถานะ paid_pending)
--   confirmed_at = เจ้าของยืนยันรับเงิน / เริ่มทำบอทเมื่อไหร่ (สถานะ confirmed)

ALTER TABLE bot_purchases ADD COLUMN IF NOT EXISTS paid_at TIMESTAMPTZ;
ALTER TABLE bot_purchases ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ;
