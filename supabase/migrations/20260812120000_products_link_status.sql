-- นโยบายลิงก์เด็ดขาด: บอทตอบเฉพาะสินค้าที่ตรวจลิงก์ affiliate ผ่านแล้ว
-- เพิ่มคอลัมน์ link_status ให้ตาราง products (ok | dead | suspect | unknown | none)
ALTER TABLE products ADD COLUMN IF NOT EXISTS link_status VARCHAR(20) NOT NULL DEFAULT 'unknown';
