# ตั้ง Cron อัตโนมัติ (cron-job.org) — ระบบดูแลตัวเอง

> เทมเพลต — ไฟล์ตัวจริง (`docs/cron-setup.md`) มี token จริงและ**ถูก gitignore ไว้**
> วิธีใช้: คัดลอก token จาก `backend/.env` (`CRON_TOKEN=...`) แล้วแทนที่ `<CRON_TOKEN>` ข้างล่าง

**Base URL:** `https://shopee-affiliate-bot-9e9n.onrender.com`

---

## ขั้นที่ 1 — ตั้ง CRON_TOKEN ที่ Render dashboard (ถ้ายังไม่ตั้ง)

1. เปิด https://dashboard.render.com → service **srv-d9tknl2d0e5s739ebo40**
2. เมนู **Environment** → Add Environment Variable
3. **Key:** `CRON_TOKEN` · **Value:** `<CRON_TOKEN>` (จาก `backend/.env`)
4. Save → Render จะ redeploy อัตโนมัติ ~2-3 นาที

**เช็คว่าตั้งสำเร็จ:**
```
curl -X POST "https://shopee-affiliate-bot-9e9n.onrender.com/api/cron/check-links?token=<CRON_TOKEN>&limit=3"
```
- `200 {"checked":3,...}` → เรียบร้อย ✅
- `401 invalid token` → ยังไม่ได้ตั้งใน Render หรือค่าไม่ตรง

> ถ้ายังไม่ตั้ง CRON_TOKEN → endpoint ทำงานแบบเปิดสาธารณะ (ใครก็เรียกได้) — ตั้งให้ครบเพื่อล็อก

---

## ขั้นที่ 2 — สร้าง 6 jobs ที่ cron-job.org

1. ไป https://cron-job.org → สมัคร/ล็อกอิน (ฟรี)
2. **Create Cron Job** → วาง URL (มี `?token=` ครบ) → **Method: POST** → **Schedule: Every day** + ตั้งเวลา
3. แต่ละ job ตั้ง **Timezone: Asia/Bangkok** (เวลาไทยตรง ไม่ต้องคำนวณ UTC)
4. Save แล้วกด **Run job** ทดสอบ → ควรได้ **HTTP 200** + response ตามที่เขียนไว้

### 6 jobs ที่ต้องสร้าง

| # | URL (วางทั้งบรรทัด) | Method | รอบ | Response ที่ควรได้ |
|---|---------------------|--------|-----|-------------------|
| 1 | `https://shopee-affiliate-bot-9e9n.onrender.com/health` | GET | **ทุก 10 นาที** | `{"status":"ok",...}` — บอทไม่หลับ (สำรองจาก self keep-alive) |
| 2 | `https://shopee-affiliate-bot-9e9n.onrender.com/api/cron/check-links?token=<CRON_TOKEN>` | POST | **วันละ 1 ครั้ง** เช่น 07:00 | `{"checked":464,"newly_dead":[...],...}` — ลิงก์ตายซ่อนอัตโนมัติ |
| 3 | `https://shopee-affiliate-bot-9e9n.onrender.com/api/cron/analyze?token=<CRON_TOKEN>&limit=30` | POST | **ทุก 2 ชม.** (จนคอนเทนต์ครบ แล้วค่อยลดวันละครั้ง) | `{"generated":[...],"still_missing":...}` — เขียน Hook/คอนเทนต์ AI |
| 4 | `https://shopee-affiliate-bot-9e9n.onrender.com/api/cron/refresh-prices?token=<CRON_TOKEN>` | POST | **วันละ 1 ครั้ง** เช่น 05:00 | `{"checked":...,"updated":...}` — อัปเดตราคา+แจ้งราคาตก |
| 5 | `https://shopee-affiliate-bot-9e9n.onrender.com/api/cron/daily-report?token=<CRON_TOKEN>` | POST | **ทุกเช้า 08:00** | `{"pushed":true,"report":"📊 รายงาน..."}` — push เข้า LINE เจ้าของ |
| 6 | `https://shopee-affiliate-bot-9e9n.onrender.com/api/cron/re-engage?token=<CRON_TOKEN>` | POST | **วันละ 1 ครั้ง** เช่น 09:00 | `{"candidates":...,"pushed":[...]}` — ดึงลูกค้าเงียบ 7 วันกลับ |

### หมายเหตุสำคัญ

- **analyze (`limit=30`)** — คลัง 464 ตัว ยังไม่มีคอนเทนต์ ~371 ตัว → รันทุก 2 ชม. จะครบใน ~1 วัน แล้วเปลี่ยนเป็นวันละครั้ง (ลบ `&limit=30` ได้)
- **refresh-prices** — Shopee บล็อก IP datacenter บ่อย → **ห้ามรันถี่** (ทุก 2 ชม. = เสี่ยงโดนบล็อก); ถ้าโดนบล็อก ราคาคงเดิม ไม่พัง ไม่หลอกลูกค้า
- **re-engage** — กันสแปมในตัวแล้ว (จำกัด 10 คน/รอบ + เฉพาะหมวดที่มีของใหม่)
- **daily-report** — push ให้เฉพาะ `ADMIN_LINE_USER_ID` (เจ้าของร้าน)
- อยากรู้ว่า job ไหนรันแล้วเป็นยังไง → Render log ดู `POST /api/cron/...` ได้

---

## ถ้าเจอปัญหา

| อาการ | สาเหตุ/แก้ |
|-------|-----------|
| `401 invalid token` | CRON_TOKEN ใน Render ยังไม่ตั้ง/ค่าต่างกัน — แก้ที่ Environment แล้ว redeploy |
| `404` | URL พิมพ์ผิด (เช็ค `/api/cron/` ไม่ใช่ `/api/webhook/`) |
| timeout ที่ cron-job.org | job โหลดนาน (check-links ตรวจ 464 ตัว) — ลองกด "Run job" อีกครั้ง; ปกติจะค้างไม่เกิน 60 วิ |
| อยากย่อ token ใน URL | โค้ดอ่านจาก query param เท่านั้น — ต้องมี token ใน URL เสมอ (ยอมรับได้ เพราะ job ของเราเอง) |
