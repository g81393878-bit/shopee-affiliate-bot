-- Account Memory (Amazon-style): สิ่งที่ลูกค้าบอกให้ป้าเข็มจำไว้
-- ใช้แนะนำสินค้า/แคมเปญ/แจ้งของใหม่ตามสิ่งที่ลูกค้าระบุเอง (ไม่ต้องเดาจากพฤติกรรมอย่างเดียว)
-- NOTE: ใช้ตารางแยก user_preferences — ห้ามเพิ่มคอลัมน์ใน users เพราะ users คือ
-- auth.users ของ Supabase (คอลัมน์ preferences มีอยู่แล้ว เป็นของระบบ auth)
CREATE TABLE IF NOT EXISTS user_preferences (
    id BIGSERIAL PRIMARY KEY,
    line_user_id TEXT NOT NULL UNIQUE,
    categories JSONB, -- หมวดที่ลูกค้าบอกว่าชอบ เช่น ["แมว", "หูฟัง"]
    notes JSONB,      -- สิ่งที่ลูกค้าบอกให้จำ เช่น ["เลี้ยงแมว 2 ตัว", "ชอบหูฟังไม่เกิน 300"]
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_user_preferences_user ON user_preferences(line_user_id);
