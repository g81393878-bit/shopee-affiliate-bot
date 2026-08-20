-- Migration: 20260820000000_remove_group_sharing.sql
-- Description: ลบฟีเจอร์แชร์ลงกลุ่ม Facebook ทั้งหมด (Graph API ปิดถาวร เม.ย. 2024)
--   - drop group_share_tasks (คิวแชร์โพสต์เพจลงกลุ่ม)
--   - drop facebook_groups_monitor (ตารางเฝ้าส่องกลุ่ม)
--   - drop group_id column ของ facebook_detected_leads (lead ไม่ผูกกลุ่มแล้ว)

DROP TABLE IF EXISTS group_share_tasks;

-- ถอดคอลัมน์ + FK + index ที่อ้างถึง facebook_groups_monitor ก่อน
ALTER TABLE facebook_detected_leads DROP COLUMN IF EXISTS group_id;

DROP TABLE IF EXISTS facebook_groups_monitor;
