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

- `2bad44e` docs: เพิ่ม Facebook & Shopee Affiliate Bot Architecture Guide
  (ไฟล์ใหม่ `docs/facebook-architecture-guide.md` — แผนผัง + บทบาทส่วนประกอบ + ขั้นเชื่อมต่อ + 2 ไอเดียต่อยอด)
- `465dfc2` docs: อัปเดต HANDOFF.md — บันทึก commit orchestrator + ขั้นตอน push/deploy
- `65a8476` feat(orchestrator): เพิ่ม Claude "บอสใหญ่" คุมวง plan/dispatch/review + worker groq/firecrawl/claude + fallback Groq
  (ฟีเจอร์ใหม่ `app/services/orchestrator.py` + 8 เทสต์ mock ใน `tests/test_orchestrator.py`)

## 2. งานค้าง

<!-- ว่าง — ไม่มีงานโค้ดค้าง ทำงานทุกชิ้น commit ครบแล้ว -->

## 3. ขั้นตอนต่อไป

- ⚠️ **push 3 commits ขึ้น GitHub** (`git push origin main`) — local นำ origin/main อยู่ 3 commits (orchestrator + docs)
- **trigger deploy บน Render** → production ยังไม่มีฟีเจอร์ orchestrator

## 4. ไฟล์ที่ถืออยู่ / โดนแก้

<!-- ว่าง -->

## 5. หมายเหตุ

- CI: `.github/workflows/test.yml` รัน `pytest` + coverage gate 85% ทุก push/PR
- เทสต์: `tests/test_orchestrator.py` → 8 passed (mock worker ทั้ง 3 ตัว ไม่แตะ API จริง)
- ฟีเจอร์ orchestrator ยังเป็นโมดูลเดี่ยว — ยังไม่ถูกเรียกจาก `line_bot.py` (ยังไม่มีผลกับลูกค้าจริง)
- Push + Deploy รอบก่อนหน้า (`49fb55e`) เรียบร้อยแล้ว — บอทจริงได้โค้ดล่าสุดของงานก่อนหน้า
- repo สะอาด ไม่มี untracked junk สำหรับงานใหม่

