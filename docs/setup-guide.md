# 🛠️ คู่มือติดตั้งระบบป้าเข็ม (บอทขายของ LINE + Shopee Affiliate)

คู่มือนี้บอก "ต้องมีอะไรบ้าง" + ขั้นตอนติดตั้งทีละขั้น + คำแนะนำ (ทั้งหมดใช้ free tier ได้)

---

## 1️⃣ ต้องมีอะไรบ้าง (4 ส่วนหลัก + 1 ส่วน dev)

| # | ส่วน | ใช้ทำอะไร | ราคา | ต้องมีก่อนเริ่ม |
|---|------|----------|------|----------------|
| ① | **LINE Official Account** | หน้าร้านที่ลูกค้าแอด (`line.me/R/ti/p/@...`) | ฟรี | ✓ |
| ② | **Supabase** | ฐานข้อมูลคลาวด์ — สินค้า/ลูกค้า/คอนเทนต์/chat_logs | ฟรี (free tier) | ✓ |
| ③ | **Render** | เซิร์ฟเวอร์รันบอท 24 ชม. + รับ webhook LINE | ฟรี (free tier) | ✓ |
| ④ | **คีย์ AI** — Groq (หรือ Gemini/OpenAI) | สมองสร้างคอนเทนต์/ตอบคำถามซับซ้อน | ฟรี | ✓ |
| ⑤ | (เครื่อง dev) Git + Python 3.11+ | รัน/แก้โค้ด/import สินค้าท้องถิ่น | ฟรี | เท่านั้น |

> 💡 **ลูกค้าไม่ต้องติดตั้งอะไรเลย** — ใช้ผ่าน LINE โดยตรง แค่แอดไลน์ร้านแล้วพิมพ์ถามได้ทันที

---

## 2️⃣ ขั้นตอนติดตั้งทีละขั้น

### ขั้น 1 — เตรียมบัญชี
- สมัคร **LINE OA** → https://manager.line.biz (สร้างบัญชีร้านค้า) → จด `Channel Access Token` + `Channel Secret` (LINE Developers → Messaging API)
- สมัคร **Supabase** → https://supabase.com → create project → จด `Project URL` + `Database password`
- สมัคร **Render** → https://render.com → link GitHub repo
- ขอคีย์ **Groq** → https://console.groq.com/keys (ฟรี 1 คีย์ = ~90 คอนเทนต์/วัน) หรือ **Gemini** → https://aistudio.google.com/apikey (ฟรี ~1,500/วัน — แนะนำ)

### ขั้น 2 — เตรียมโค้ด + ฐานข้อมูล
```bash
git clone <repo-url> && cd <repo>
cd backend
pip install -r requirements.txt        # ติดตั้ง dependencies
cp .env.example .env                    # แล้วกรอกค่าข้างล่าง
```

`.env` ต้องมี (ดู `backend/.env.example`):
```
DATABASE_URL=postgresql://...           # Supabase (Transaction Pooler พอร์ต 6543)
LINE_CHANNEL_ACCESS_TOKEN=...
LINE_CHANNEL_SECRET=...
GROQ_API_KEY=key1,key2,...              # ใส่หลายคีย์ได้ คั่นด้วยคอมม่า
LLM_PROVIDER=groq                       # groq | gemini | openai
CRON_TOKEN=...                          # ล็อก cron endpoints
ADMIN_DASHBOARD_PASSWORD=...            # เปิด /admin
ADMIN_LINE_USER_ID=...                  # LINE userId ของเจ้าของร้าน
```

สร้างตารางใน Supabase (SQL Editor รัน `backend/schema.sql`)

### ขั้น 3 — import สินค้า (CSV จากพอร์ทัล Shopee Affiliate)
```bash
python ../tools/product_pipeline.py import-csv "ไฟล์ลิงก์สินค้า.csv" --analyze
```
- ตรวจลิงก์ affiliate ก่อนเข้า (ไม่ผ่าน = ข้าม ไม่เข้าร้าน)
- `--analyze` = สร้างคอนเทนต์ (Hook/แคปชัน) ให้อัตโนมัติ

### ขั้น 4 — deploy ขึ้น Render
- New Web Service → เลือก repo → `rootDir: backend` (สำคัญ!)
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- ตั้ง env vars เดียวกับ `.env` (ใน Render dashboard — ดู `render.yaml` ประกอบ)

### ขั้น 5 — ต่อ LINE webhook (สำคัญ: ใช้พหูพจน์ `/webhooks/`)
LINE Developers → Messaging API → Webhook URL:
```
https://<ชื่อ-service>.onrender.com/api/webhooks/line
```
กด Verify — ต้องได้ 200 (ถ้า URL ผิดบอทไม่ทำงานเงียบๆ)

### ขั้น 6 — ตั้ง cron เฝ้าร้าน (cron-job.org)
ดู `docs/cron-setup.md` — 5 งาน + `?token=<CRON_TOKEN>`:
`check-links` (ลิงก์ตาย) · `analyze` (คอนเทนต์) · `refresh-prices` (ราคา + แจ้งราคาลง) · `daily-report` (รายงานเช้า) · `re-engage` (ดึงลูกค้าเงียบกลับมา)

### ขั้น 7 — ทดสอบ
พิมพ์ใน LINE: `สวัสดี` / `ค้นสินค้า` / `หูฟังไม่เกิน 300` / `วันนี้ขายอะไรดี` / `เทียบ A กับ B` / `คุยกับป้าเข็ม` — เปิด `/admin` ดูสถิติ

---

## 3️⃣ คำแนะนำ (จากของจริงที่เจอ)

- **Supabase บน Render ต้องใช้ Transaction Pooler URL** (พอร์ต 6543, `*.pooler.supabase.com`) — ใช้ Direct Connection จะ fail (IPv6)
- **Groq ฟรี = ~90 คอนเทนต์/วัน/คีย์** — ถ้าต้องทำคอนเทนต์เยอะ สลับเป็น **Gemini ฟรี (~1,500/วัน)** ด้วย env `LLM_PROVIDER=gemini`
- **สินค้าทุกตัวต้องมีลิงก์ affiliate ที่ตรวจผ่าน** (`link_status == ok`) — บอทตอบเฉพาะของที่ตรวจแล้ว ห้ามเอาลิงก์ไม่มีค่าคอมมาใส่เด็ดขาด
- **เก็บ secrets ไว้ใน dashboard เท่านั้น** — ห้าม commit `.env` (ใน `.gitignore` แล้ว)
- **แยกงาน commit** + อ่าน `HANDOFF.md` ก่อนเริ่ม (ดู AGENTS.md)
- Render free tier หลับหลัง 15 นาที — `/health` + cron ping ทุก 10 นาทีกันหลับ (ระบบทำไว้ให้แล้ว)

---

## 3.5️⃣ ❓ คำถามยอดนิยมของเจ้าของร้าน (จากคำถาม LINE OA ที่พบบ่อย)

| ถาม | ตอบ (เช็คอะไรก่อน) |
|-----|--------------------|
| **บอทไม่ตอบลูกค้า** | 1) Webhook URL ถูกไหม → ต้องเป็น `/api/webhooks/line` (พหูพจน์!) 2) env keys ครบไหม (LINE token/secret) 3) ดู Render log มี error ไหม |
| **ข้อความต้อนรับ/ปุ่มไม่เปลี่ยน** | ข้อความต้อนรับอยู่ในโค้ด (แก้แล้ว deploy) · ปุ่มเมนู = Rich Menu → `tools/line_rich_menu.py` |
| **อยากส่งโปรให้ลูกค้า** | LINE OA Console → Broadcast หรือตั้ง cron `re-engage` (docs/cron-setup.md) |
| **เพิ่มสินค้าใหม่** | `python tools/product_pipeline.py import-csv <ไฟล์.csv> --analyze` |
| **ราคา/ลิงก์ตาย** | cron `refresh-prices` + `check-links` หรือจัดการผ่าน `/admin` dashboard |
| **เปลี่ยน AI / คีย์หมดโควต้า** | เปลี่ยน `LLM_PROVIDER` / เพิ่มคีย์ใน `GROQ_API_KEY` (คั่นคอมม่า) แล้ว deploy |

---

## 4️⃣ ใช้บอทนี้บนเครื่องอื่น / ขายบอท?

- โค้ดพกพาได้: clone → `.env` ใหม่ (ของแต่ละร้าน) → import สินค้าของร้านนั้น → deploy — ไม่ผูกกับบัญชีใคร
- ทุกอย่างเป็น env var — สลับ LINE OA / Supabase / Render ได้ทั้งชุดโดยไม่แก้โค้ด
- ⚠️ ต้องแน่ใจว่าใช้ LINE OA + Affiliate ID ของร้านนั้นจริง (อย่าเอา cross-account มาใช้)
