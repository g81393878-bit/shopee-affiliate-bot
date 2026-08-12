# HANDOFF.md — สถานะงานค้างระหว่าง AI session

> **วิธีใช้ (อ่านก่อน):**
> - **AI ตัวใหม่ที่เข้ามาทำงาน: ต้องอ่านไฟล์นี้ + ตรวจ `git status` ก่อนเริ่มงานเสมอ**
>   (บังคับตาม AGENTS.md → Multi-Agent Handoff Protocol)
> - **AI ตัวที่กำลังทำงาน:** ถ้าจะหยุดกลางคัน (ยังไม่ commit งานให้ครบ) ให้เติมข้อมูลจริงลงใน
>   ส่วน 1–5 ด้านล่าง แล้ว commit ไฟล์นี้ทันที พร้อมกับงานที่ทำไว้
> - **เมื่องานเสร็จและ commit ครบ:** ให้ล้างเนื้อหาในส่วน 1–5 กลับเป็นสถานะว่าง แล้ว commit
>   ไฟล์นี้ — เพื่อไม่ให้ AI ตัวถัดไปเข้าใจผิดว่างานยังค้าง

## สถานะ: 🟡 มีงานค้าง — ฟีเจอร์ "แนะนำสินค้าตามสภาพอากาศ" ทำค้างไว้ ~60%

---

## 1. งานที่ทำแล้ว (ล่าสุด)

- **`f46b1ec`** docs: AGENTS.md — บังคับอ่าน HANDOFF.md + ตัวอย่างคำสั่งตรวจก่อนเริ่มงาน
- **`eb533b5`** fix(bot): ค้นหาแม่นขึ้น — กันคำประสมคนละชนิด + คำค้นต้องครบทุกคำในชื่อ
  (งานค้นหาเสร็จ + เทสต์ 49 คำค้นกับคลังจริงผ่านหมด — อย่าไปแตะ `search_products` ใน `line_bot.py`)

## 2. งานค้าง

ฟีเจอร์ **"แนะนำสินค้าตามสภาพอากาศ"** — ลูกค้าพิมพ์ "วันนี้อากาศร้อนแนะนำหน่อย" / "ฝนตกจะซื้ออะไรดี"
→ บอทแนะนำสินค้าตามฤดูกาล/สภาพอากาศ (พัดลม/เสื้อกันฝน/ร่ม…)

**ทำไปแล้ว (ยังไม่ commit — ไฟล์ใหม่ทั้งหมด):**
1. `backend/app/services/weather.py` (ใหม่) — ฟังก์ชัน `get_weather_season()` คืนฤดูกาลจากเดือนปัจจุบัน
   (ร้อน/ฝน/หนาว) + map ฤดูกาล → หมวดสินค้า (ร้อน→พัดลม/แก้วน้ำ, ฝน→เสื้อกันฝน/ร่ม, หนาว→เสื้อกันหนาว/ผ้าห่ม)
   ยังไม่ต่อ API จริง (ไม่มี OpenWeather key) — ใช้เดือนเป็นตัวตัดสินก่อน
2. `backend/app/services/category.py` — เตรียมเพิ่ม keyword ฤดูกาลไว้ใน comment (ยังไม่ insert)

**ยังไม่ได้ทำ:**
- ยังไม่เพิ่ม intent/branch ใน `message_text()` (line_bot.py บรรทัด 1168) — ยังไม่มีเส้นทางรับคำสั่ง
- ยังไม่เขียนการ์ดตอบกลับ (ใช้ `product_cards_message()` เดิมได้ แต่ยังไม่ได้เรียก)
- ยังไม่ log intent ลง `chat_logs` (ต้องเพิ่มค่า intent ใหม่ "weather" — ดู `log_chat()` ที่บรรทัด 600)
- ยังไม่มีเทสต์

## 3. ขั้นตอนต่อไป

1. สร้างไฟล์ชั่วคราว `tools/_test_weather.py` รัน `get_weather_season()` เช็คว่า map ฤดูกาล→หมวดถูก
   (รัน: `cd backend && ./.venv/Scripts/python.exe ../tools/_test_weather.py`)
2. ใน `message_text()` (line_bot.py บรรทัด 1168) เพิ่ม branch **ก่อน `else` ตัวสุดท้าย** (ก่อนบรรทัด ~1242):
   ตรวจคำ "ร้อน/ฝนตก/หนาว/สภาพอากาศ" → เรียก `handle_weather_recommend(db, user)` ที่ต้องเขียนใหม่
   (วางข้างๆ `handle_today_deals` บรรทัด 220 — ใช้ `search_products` เดิมค้นหมวดตามฤดูกาลได้เลย)
3. ตัดสินใจเรื่อง intent: `_customer_categories()` (บรรทัด 733) กรองเฉพาะ `intent == "search"` —
   ถ้าอยากให้หมวดจากอากาศมีผลกับการแนะนำ ให้ log เป็น "search" พร้อม category หมวดนั้น;
   ถ้า log เป็น "weather" จะไม่ถูกนับในหมวดที่สนใจ (เลือกแล้วเขียนอธิบายลง code comment)
4. ทดสอบ 2 ระดับ:
   - **เทสต์กับคลังจริง** (อ่าน หมายเหตุ ข้อ 1): รันเทสต์ค้นหาที่มีอยู่ + เทสต์คำสั่งอากาศ 2-3 คำ
   - **เทสต์กับ LINE event** (ไม่ต้องต่อ LINE จริง): ใช้ `handle_events_manually()` ที่ line_bot.py บรรทัด 56
     สร้าง `MessageEvent` จำลองส่งเข้า handler → ดู reply (ตัวอย่างการเรียกดูใน หมายเหตุ ข้อ 4)
5. commit แยก: (ก) `feat(bot): แนะนำสินค้าตามสภาพอากาศ` (ข) ล้าง HANDOFF.md กลับเป็นว่าง

## 4. ไฟล์ที่ถืออยู่ / โดนแก้

- **ถืออยู่ (ยังไม่ commit):** `backend/app/services/weather.py` (ใหม่), `backend/app/services/category.py` (มี comment ค้าง)
- **ห้ามแตะ:** `backend/app/api/line_bot.py` เฉพาะส่วน `search_products` (งาน eb533b5 เพิ่งเสร็จ)
  แต่ `message_text()` และ `handle_today_deals` ว่างให้แก้ได้

## 5. หมายเหตุ

1. **ฐานข้อมูล**: ทดสอบกับคลังจริง Supabase (pooler-url ใน `supabase/.temp/` + รหัสผ่าน
   `~/.supabase/db-password.txt`) — อ่านไฟล์แล้วต่อผ่าน env `DATABASE_URL` (ดูตัวอย่างใน
   `tools/search_test.py` docstring); SQLite `backend/affiliate_db.db` เป็น schema เก่า ไม่มี
   `link_status`/`ai_score` — ถ้าใช้ต้อง migration ก่อน (อย่าใช้กับฟีเจอร์นี้)
2. **รัน app ท้องถิ่น**: `cd backend && ./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000`
   (line_bot มี fallback mock token เมื่อไม่มี env — app ขึ้นได้ แต่บอทจะไม่ทำงานจริง;
   env จริงต้องมี `LINE_CHANNEL_ACCESS_TOKEN` + `LINE_CHANNEL_SECRET`)
3. **นโยบายเด็ดขาด**: ตอบเฉพาะสินค้า `link_status == 'ok'` — ห้าม bypass (ดู AGENTS.md → Product link policy)
4. **เทสต์ LINE event โดยไม่ต้องต่อ LINE จริง**: `handle_events_manually()` ที่ line_bot.py บรรทัด 56
   รับ `MessageEvent` จำลอง (เช่น `MessageEvent(id="x", timestamp=..., source=..., message=TextMessage(id="x", text="ฝนตกแนะนำหน่อย"), reply_token="x")`)
   → ส่งเข้ากับ handler → ดูว่า reply เป็น FlexSendMessage/TextSendMessage ถูกไหม — เขียนเป็น
   `tools/_test_weather.py` แล้วลบก่อน commit (ตาม AGENTS.md ข้อ 6)
5. **PDPA**: `log_chat()` เก็บข้อความแค่ 90 วัน (ลบของเก่าอัตโนมัติ) — อย่าเก็บข้อมูลเกินที่จำเป็น;
   คำสั่ง "ลบข้อมูลฉัน" ต้องยังทำงานปกติ (อย่าไปแก้เส้นทาง delete ใน `message_text()`)
6. **ยังไม่มี OpenWeather API key** — อย่าเผลอ hardcode key ปลอม ถ้าจะใช้ API จริงต้องถาม user ก่อน
7. **AI ตัวต่อไป**: ตรวจ `git status` — ไฟล์ 2 ตัวในข้อ 4 ยังไม่ commit ต้องไม่ทับ; ถ้าเห็น working tree
   มีของค้างอื่นนอกจากนี้ ให้ถาม user ก่อนเริ่ม (AGENTS.md ข้อ 1)
