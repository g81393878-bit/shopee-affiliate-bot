# HANDOFF.md — สถานะงานค้างระหว่าง AI session

> **วิธีใช้ (อ่านก่อน):**
> - **AI ตัวใหม่ที่เข้ามาทำงาน: ต้องอ่านไฟล์นี้ + ตรวจ `git status` ก่อนเริ่มงานเสมอ**
>   (บังคับตาม AGENTS.md → Multi-Agent Handoff Protocol)
> - **AI ตัวที่กำลังทำงาน:** ถ้าจะหยุดกลางคัน (ยังไม่ commit งานให้ครบ) ให้เติมข้อมูลจริงลงใน
>   ส่วน 1–5 ด้านล่าง แล้ว commit ไฟล์นี้ทันที พร้อมกับงานที่ทำไว้
> - **เมื่องานเสร็จและ commit ครบ:** ให้ล้างเนื้อหาในส่วน 1–5 กลับเป็นสถานะว่าง แล้ว commit
>   ไฟล์นี้ — เพื่อไม่ให้ AI ตัวถัดไปเข้าใจผิดว่างานยังค้าง

## สถานะ: 🟡 มีงานค้างเฉพาะส่วน 3 (push + deploy) — งานโค้ด commit ครบแล้ว

---

## 1. งานที่ทำแล้ว (ล่าสุด)

- `c085ab0` feat(persona): ปรับปรุงตัวตนป้าเข็มตาม RCAO Framework สำหรับการจัดการความรู้ชุมชน (`persona.py`)
- `a29aec7` feat(facebook): รองรับ `LINE_OA_URL` — ใส่ลิงก์ LINE OA ใน `BOT_INTRO` + ชุดโพสต์ (fallback บอกชื่อร้าน)
- `9b35347` docs: เพิ่มชุดโพสต์ Facebook แนะนำบอทป้าเข็ม (`docs/facebook-content.md` — 3 caption + เนื้อ + image prompt)
- `d6ab88f` docs(skills): align facebook-app-config SKILL กับตัวจริง (FACEBOOK_VERIFY_TOKEN + /api/webhooks/facebook)
- `dce3c82` feat(facebook): เปลี่ยน reply จาก ack เป็นแนะนำบอทป้าเข็ม (`BOT_INTRO`) — ไม่ค้น/ไม่โพสต์สินค้า
  (ใครทักแชทเพจ Facebook → ตอบแนะนำบอท + วิธีคุยต่อที่ LINE)
- `965bdb9` feat(facebook): เพิ่ม webhook `/api/webhooks/facebook` — GET verify (challenge) + POST ตรวจ X-Hub-Signature-256
  (ไฟล์ใหม่ `app/api/facebook_bot.py` + 7 เทสต์ใน `tests/test_facebook_webhook.py`; ทำขั้น 1–2 ของ architecture guide)
- `2bad44e` docs: เพิ่ม Facebook & Shopee Affiliate Bot Architecture Guide
  (ไฟล์ใหม่ `docs/facebook-architecture-guide.md` — แผนผัง + บทบาทส่วนประกอบ + ขั้นเชื่อมต่อ + 2 ไอเดียต่อยอด)
- `465dfc2` docs: อัปเดต HANDOFF.md — บันทึก commit orchestrator + ขั้นตอน push/deploy
- `65a8476` feat(orchestrator): เพิ่ม Claude "บอสใหญ่" คุมวง plan/dispatch/review + worker groq/firecrawl/claude + fallback Groq
  (ฟีเจอร์ใหม่ `app/services/orchestrator.py` + 8 เทสต์ mock ใน `tests/test_orchestrator.py`)

## 2. งานค้าง

<!-- ว่าง — ไม่มีงานโค้ดค้าง ทำงานทุกชิ้น commit ครบแล้ว -->

## 3. ขั้นตอนต่อไป

- ⚠️ **push 13 commits ขึ้น GitHub** (`git push origin main`) — local นำ origin/main อยู่ 13 commits (orchestrator + facebook webhook + docs/skills + persona.py)
- **trigger deploy บน Render** → production ยังไม่มีฟีเจอร์ใหม่
- 🔗 ยังไม่มีลิงก์ LINE OA จริง — รอเจ้าของร้านให้ URL (`https://line.me/R/ti/p/@xxxxx`) แล้ว set env `LINE_OA_URL`

## 4. ไฟล์ที่ถืออยู่ / โดนแก้

- `backend/app/services/persona.py` — แก้โดยคนอื่น (เปลี่ยนคาแรกเตอร์ "ป้าเข็ม" จากแม่ค้าออนไลน์ → AI คู่คิดพัฒนาชุมชน/OTOP ตาม RCAO/RAG) ยังไม่ stage รอเจ้าของตัดสินใจ

## 5. หมายเหตุ

- CI: `.github/workflows/test.yml` รัน `pytest` + coverage gate 85% ทุก push/PR
- เทสต์ทั้งชุด: 382 passed (orchestrator +8, facebook webhook +7)
- ฟีเจอร์ orchestrator ยังเป็นโมดูลเดี่ยว — ยังไม่ถูกเรียกจาก `line_bot.py` (ยังไม่มีผลกับลูกค้าจริง)
- facebook webhook: หน้าที่ตอนนี้ = แนะนำบอทป้าเข็ม (ไม่ค้นสินค้า/ไม่โพสต์สินค้า ตามเจ้าของร้านสั่ง)
  — ไอเดีย A/B ใน architecture guide (ค้นสินค้า/โพสต์อัตโนมัติ) ถูกพักไว้
- ⚠️ มีการแก้ `persona.py` คู่ขนาน — เนื้อ Facebook/ขายของที่เขียนไว้ยังอิงคาแรกเตอร์เดิม (แม่ค้า) ต้องเช็คทิศทางกับเจ้าของร้าน
- Push + Deploy รอบก่อนหน้า (`49fb55e`) เรียบร้อยแล้ว — บอทจริงได้โค้ดล่าสุดของงานก่อนหน้า
- repo สะอาด ไม่มี untracked junk สำหรับงานใหม่

