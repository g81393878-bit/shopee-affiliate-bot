-- โทนภาษาที่จำไว้ต่อลูกค้า (youth/elder) — เก็บถาวรข้าม deploy/restart
-- (เดิมจำในหน่วยความจำ _tone_memory ซึ่งหายทุกครั้งที่ restart/deploy)
ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS tone VARCHAR(10);
