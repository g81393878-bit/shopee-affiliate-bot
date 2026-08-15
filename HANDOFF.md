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

- `5b7fbf9` ci: ขยาย test workflow ให้รันทุก push/PR + ยกเลิกรันซ้ำซ้อน
  (เดิมรันเฉพาะ push เข้า main; ยืนยัน CI ผ่าน 363 passed, coverage 87.52%)
- `26b538e` test(line-bot): battery routing 200 case (100 direct + 100 ผ่านเมนูฝากคำถาม)
  เป็น pytest ถาวร `backend/tests/test_battery_routing.py` — ลบ tools/_simulate_*.py แล้ว
- `c847eae` fix(line-bot): โฟลว์ "ฝากคำถาม" ตอบคู่มือ/เทียบ/ค้นเน็ตเอง ไม่หลุดไป web search ขยะ
  + guard search_products กันคำสุภาพล้วน ("ครับ"/"จ้า") แมตช์ทั้งร้าน
- `d07b0d6` fix(line-bot): "คีย์บอร์ด" ไม่โดน keyword "คีย์" จับเป็นคู่มือ AI
  (เพิ่ม `_mask_keyboard()` ใน is_bot_manual_request + bot_manual_reply)

## 2. งานค้าง

<!-- ว่าง — ไม่มีงานโค้ดค้าง ทำงานทุกชิ้น commit ครบแล้ว -->

## 3. ขั้นตอนต่อไป

- ⚠️ **push 4 commits ขึ้น GitHub** (`git push origin main`) — local นำ origin/main อยู่ 4 commits:
  `d07b0d6` · `c847eae` · `26b538e` · `5b7fbf9`
- **trigger deploy บน Render** → บอทไลฟ์ (`shopee-affiliate-bot-9e9n.onrender.com`) จะได้โค้ดใหม่
  (ตอนนี้ production ยังรันโค้ดเก่า — ลูกค้าจริงเจอ "จะซื้อสินค้าอย่างไร" ตอบ web search ขยะ)
- เปลี่ยนรหัสผ่าน cron-job.org (manual บนเว็บ ไม่ใช่โค้ด — ผู้ใช้ให้พักไว้ก่อน)

## 4. ไฟล์ที่ถืออยู่ / โดนแก้

<!-- ว่าง -->

## 5. หมายเหตุ

- CI: `.github/workflows/test.yml` รัน `pytest` + coverage gate 85% ทุก push/PR (มีผลหลัง push)
- เทสต์: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -q` → 363 passed
- `/health` มี 3 แหล่งยิง: cron-job.org (`23.88.105.37` ทุก 10 นาที), self keep-alive loop
  (`74.220.52.251` = Render egress ทุก 10 นาที), Render health checker (`10.209.x.x` ทุก ~5 วิ)
- Render logs API: `GET /v1/logs?ownerId=tea-d2iu2afdiees738r2o00&resource=srv-d9tknl2d0e5s739ebo40`
  (API key จาก `~/.render/cli.yaml` — วิธีอ่านใน AGENTS.md)
- repo สะอาด ไม่มี untracked junk (`.csv`/`.xlsx`/`.exe`/temp scripts ถูก ignore/ลบหมด)
