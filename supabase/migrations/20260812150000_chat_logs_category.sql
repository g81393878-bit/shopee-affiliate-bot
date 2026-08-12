-- หมวดที่ลูกค้าสนใจ (แท็กจากคำค้น) — ใช้ต่อยอดวิเคราะห์/แนะนำสินค้า
alter table chat_logs add column if not exists category text;
create index if not exists idx_chat_logs_category on chat_logs(category);
