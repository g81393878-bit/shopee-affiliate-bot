# HANDOFF.md — สถานะงานค้างระหว่าง AI session

> **วิธีใช้ (อ่านก่อน):**
> - **AI ตัวใหม่ที่เข้ามาทำงาน: ต้องอ่านไฟล์นี้ + ตรวจ `git status` ก่อนเริ่มงานเสมอ**
>   (บังคับตาม AGENTS.md → Multi-Agent Handoff Protocol)
> - **AI ตัวที่กำลังทำงาน:** ถ้าจะหยุดกลางคัน (ยังไม่ commit งานให้ครบ) ให้เติมข้อมูลจริงลงใน
>   ส่วน 1–5 ด้านล่าง แล้ว commit ไฟล์นี้ทันที พร้อมกับงานที่ทำไว้
> - **เมื่องานเสร็จและ commit ครบ:** ให้ล้างเนื้อหาในส่วน 1–5 กลับเป็นสถานะว่าง แล้ว commit
>   ไฟล์นี้ — เพื่อไม่ให้ AI ตัวถัดไปเข้าใจผิดว่างานยังค้าง

## สถานะ: 🟢 ว่าง

---

## 1. งานที่ทำแล้ว (ล่าสุด)

- **`4aa60bb` feat(bot): ระบบคิวสั่งบอท + ราคาบอทสรุปย่อ + บันทึกเวลารับเรื่อง/เริ่มทำ** — `ราคาบอท` ตอบสรุปย่อ 5 แพ็กเกจ + ปุ่มเลือก, keyword `ระยะเวลา` เดี่ยวตอบได้, ลูกค้าดูเลขคิวตอนสั่ง + พิมพ์ `คิวของฉัน`, เจ้าของพิมพ์ `/คิว`, บันทึก `paid_at`/`confirmed_at` (มี migration `supabase/migrations/20260818000000_bot_purchases_timestamps.sql` + auto-migrate ตอน startup) — **deploy ขึ้น production แล้ว**
- **`7168190` feat(bot): รับสลิปโอนเงินผ่าน LINE + OCR อ่านยอด/เลขอ้างอิงด้วย Groq แล้วแจ้งเจ้าของเทียบยอดคาดก่อนยืนยัน** (commit โดยเจ้าของ 05:25 +07) — **deploy live แล้ว** (เป็น commit ปัจจุบันของ production)
- **Auto-deploy ผ่าน GitHub Action + Render Deploy Hook** — `.github/workflows/auto-deploy.yml` push ขึ้น `main` → POST ไป Deploy Hook (`RENDER_DEPLOY_HOOK_URL` secret) · ข้าม deploy ด้วย `[skip deploy]` ใน commit message · ยังต้องตั้ง secret (ดูงานค้าง/ขั้นตอนต่อไป)

## 2. งานค้าง

<!-- ว่าง -->

## 3. ขั้นตอนต่อไป

<!-- ว่าง -->

## 4. ไฟล์ที่ถืออยู่ / โดนแก้

<!-- ว่าง -->

## 5. หมายเหตุ

- **Render Auto-Deploy (native):** flag เป็ข `yes` (ผ่าน API) แต่ push จริงไม่ trigger (repo ไม่มี webhook เลย `[]` — สงสัย GitHub integration หลุดตอน rollback) → จึงเปลี่ยนเป็น **GitHub Action + Deploy Hook** (route stable กว่า); ถ้าอยากลองกลับไปใช้ native อีก ให้ reconnect GitHub ใน Dashboard
- **secret `RENDER_DEPLOY_HOOK_URL` ยังไม่ตั้ง** — ต้องตั้งที่ repo Settings → Secrets and variables → Actions (`RENDER_DEPLOY_HOOK_URL` = Render Dashboard → service → Settings → Deploy Hook URL) — workflow จะรัน warning ถ้ายังไม่ตั้ง (ไม่ fail)
- **Deploy ปัจจุบัน (production):** commit `7168190` live (deploy `dep-da1olaojo6nc73f9q5bg`) — มีฟีเจอร์ระบบคิว + รับสลิป OCR ครบ
- **เวลาในตาราง `bot_purchases`:** `created_at` (รับเรื่อง) · `paid_at` (โอน) · `confirmed_at` (เริ่มทำ) — แสดงเป็นเวลาไทย UTC+7