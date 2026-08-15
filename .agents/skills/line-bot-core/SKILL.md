---
name: line-bot-core
description: >-
  Core LINE bot behaviors of ป้าเข็ม (backend/app/api/line_bot.py): intent routing,
  product search with Thai price parsing, tone detection (youth/elder), product
  comparison, WISMO, PDPA deletion, bot-manual replies, and web-search answers.
  Use whenever the user mentions ลูกค้าทัก/บอทตอบ, ค้นสินค้า, ราคา/งบ, วัยผู้ใช้,
  เปรียบเทียบสินค้า, ทวงพัสดุ, ลบข้อมูล, or LINE intent routing bugs.
---

# LINE Bot Core (ป้าเข็ม)

## โฟลว์หลัก
`POST /api/webhooks/line` → `message_text()` (line_bot.py) → แยก intent ตามลำดับ:
wismo → code buttons → greeting → deal query → compare → remember → campaign →
category menu → search → manual (คู่มือ) → web search → fallback

## กับดักข้อความไทย (เจอจริงทุกข้อ — ห้ามฝืน)

### 1. สระอำ — NFC ไม่พอ
- คลัง/DB เก็บสระอำได้ 3 รูปแบบ (U+0E33 / U+0E4D+U+0E33 / U+0E4D+U+0E32) — NFC **ไม่รวม**ให้
- ต้องแทนที่มือใน `_nfc()` (line_bot + demand_radar_ai + product_matcher มี copy ตัวเอง):
  `\u0e4d\u0e32`→`\u0e33` และ `\u0e4d\u0e33`→`\u0e33` ไม่งั้น "กระติกน้ำแข็ง" ค้นไม่เจอ

### 2. regex ราคา ห้ามใช้ `\d*` (เลขว่างได้)
- `PRICE_PHRASE_RES` (line_bot.py ~1466): "งบ" ไปแมตช์กลางคำ "หูฟัง**ง**+**บ**ลูทูธ" → ตัดทิ้งเหลือขยะ "หูฟัลูทูธ" → ค้น 0 ตัว
- เงื่อนไขราคาต้องมีตัวเลขจริงตามหลัง; คำ "ราคา/งบ" แบบไม่มีเลขต้องมีเว้นวรรค/ต้นประโยคก่อน

### 3. ตัดคำนำหน้า (FILLER_PREFIXES) ห้ามตัดกลางคำไทย
- "ขอ" ตัด "ขอ**ง**เล่นแมว" เหลือ "งเล่นแมว", "มี" ตัด "มีด" เหลือ "ด"
- ตัดต่อเมื่อส่วนที่เหลือขึ้นต้นด้วย category keyword ที่รู้จักเท่านั้น

### 4. คำกรองคู่มือ (BOT_MANUAL_PHRASES) — ตรวจด้วยซับสตริง ชนชื่อสินค้า
- ห้ามเพิ่มคำสั้น/อังกฤษสามัญ (ai/key/หลับ/สำรอง/ฟรี) — เจอในชื่อจริง (หูฟัง ai, KEYboard, หมอนหลับสบาย, แบตสำรอง, ส่งฟรี)
- ใช้คำเฉพาะไทย (คีย์/เซิร์ฟเวอร์/ฐานข้อมูล...); คีย์ห้ามมีเว้นวรรค + อังกฤษตัวพิมพ์เล็ก ("ไลน์oa"/"lineoa"/"richmenu")
- เรียง section ถูก: "โค้ดส่วนลด" (คูปอง) ต้องอยู่ก่อน "โค้ด" (GitHub) ไม่งั้นตอบผิดหัวข้อ

### 5. เดาโทนวัย (YOUTH_SIGNALS/ELDER_SIGNALS) — ชนชื่อสินค้าเหมือนข้อ 4
- "ตา" ชน แว่น**ตา** (64 ตัว), "ยาย" ชน น้ำ**ยาย้อม**ผม (8), "รบกวน" ชน ลด**เสียงรบกวน** (51 — หูฟัง!), "งับ" ชน ระ**งับ**กลิ่น, "ฟิน" ชน มาดาม**ฟิน**
- เดาแล้วจำถาวรใน `user_preferences.tone` (ไม่มีทางลบเอง) — ก่อนเพิ่มสัญญาณใหม่ ต้องเทียบกับ
  `SELECT name FROM products WHERE link_status='ok'` (หรือ query คลังจริง) ก่อนใส่

### 6. WISMO (ทวงพัสดุ)
- `is_wismo()`: คำว่า สั่งแล้ว/เลขพัสดุ/ของถึงยัง... → ตอบวิธีตรวจสั่งซื้อบน Shopee
  (เราเป็นนายหน้า ไม่มีเลขพัสดุเอง) + ปุ่มลิงก์

### 7. PDPA
- เก็บแค่ชื่อ + LINE userId ใน `users`; ข้อความ/ประเภทใน `chat_logs` (ลบของเก่า >90 วันอัตโนมัติใน `log_chat()`)
- "ลบข้อมูลฉัน" → ลบ user + logs + user_preferences ทันที และ**ไม่ log คำสั่งลบเอง**
- เขียน Google ชีท (SHEET_WEBHOOK_URL) ผ่าน daemon thread — ตอบ LINE ต้องไม่รอ Google

## ไฟล์ที่เกี่ยวข้อง
- `backend/app/api/line_bot.py` (หลัก), `backend/app/services/product_cards.py` (การ์ด),
  `category.py` (หมวด), `web_search.py` (ค้นเน็ต), `persona.py` (บุคลิกป้าเข็ม)

## เทสต์
`backend/tests/test_line_bot.py` (มี `sim` fixture จำลองลูกค้าส่งข้อความ) — เติมเทสต์ใหม่ทุกครั้งที่แตะ routing
