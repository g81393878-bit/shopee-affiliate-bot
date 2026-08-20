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

- **feat(reels): Facebook Reels auto-uploader (ยังไม่ commit)** — `post_reel()` 3-step upload (init→upload→publish) ใน `backend/app/services/facebook_poster.py` · `uploader.py` ที่ root (FIFO + AI caption Groq + pacing `POSTING_SPACING_HOURS` + guard `MAX_REELS_PER_DAY=30`) · `products.json` ตัวอย่าง + `pending_videos/.gitkeep` + `posted/.gitkeep` + rule ใน `.gitignore` · เทสต์ `post_reel` 3 ตัว (รวม 1104 passed) — ดู หมายเหตุ เรื่อง stray file `reels_publisher.py`
- **ลบฟีเจอร์แชร์ลงกลุ่ม + เศษโค้ดทั้งหมด 100% (20/08)** — Meta ปิด Groups API ถาวร เม.ย. 2024 → ลบ feature code ไปแล้วใน commit `cb0e847` แล้วรอบนี้เก็บกวาดเศษที่เหลือจนหมดตามคำสั่งเจ้าของ “ไม่ให้เหลือแม้แต่เศษโค้ด”: ลบ `_drop_group_sharing_schema()` + call ใน `backend/app/main.py` · ลบ migration `supabase/migrations/20260820000000_remove_group_sharing.sql` · ล้างคอมเมนต์/`--out-file`/ถ้อยคำที่อ้างแชร์ใน `facebook_radar.py`, `run_campaign.py`, `post_page.py`, `.agents/skills/facebook-post-coordination/SKILL.md` — เหลือเฉพาะซากตารางบน prod ที่ต้อง drop มือครั้งเดียว (ดู หมายเหตุ) — **deploy live แล้ว (push `107f509`) + drop ซากตาราง prod + ลบ Task Scheduler 4 ตัว เรียบร้อย**
- **push `3126b7f..446e296` (19/08) — งาน radar/monitor 7 commits** — แตะเฉพาะ `bot/`, `tools/`, `backend/tests/` — **ไม่มีการแก้ `backend/app/` → production (Render) runtime ไม่เปลี่ยน** (รายละเอียดแต่ละ commit ด้านล่าง)
- **`446e296` test(radar): เทสต์ `_kill_chrome_tree` + `_sweep_orphan_drivers` 6 ตัว (mock subprocess/tasklist)** — ฆ่า undetected_chromedriver ด้วย taskkill /T /F · ไม่แตะ chrome.exe ของ user · no-op บน non-Windows · no-PID ไม่ crash — `test_fb_group_monitor_local.py` 28 passed, รวม radar 54 passed
- **`3893f51` feat(radar): single-instance lock กันรัน monitor ซ้อนกัน** — `.fb_monitor.lock` เก็บ PID · เจอ lock ของ process ที่ยังมีชีวิต → refuse + exit 1 · lock ค้างจาก PID ตายเขียนทับอัตโนมัติ · ปลด lock ทุกทางออก (Ctrl+C/error/จบ) · `--lock-file ''` ปิดได้ · gitignore `.fb_monitor.lock` + `.fb_monitor_seen.json`
- **`6a90b01` feat(radar): กวาดซาก chromedriver ตอนสตาร์ท + คำเตือน loop mode** — `_sweep_orphan_drivers()` ฆ่า `undetected_chromedriver.exe` ที่ค้างจากรอบโดน hard-kill (finally ไม่ทันรัน) เฉพาะโหมด scrape จริง · เตือนเด่นเมื่อรันโหมด loop ไม่มี `--once`
- **`5c2dba3` fix(radar): ปิด Chrome สิ้นซาก** — `_kill_chrome_tree()` จับ PID driver ก่อนปิด แล้ว `taskkill /PID <pid> /T /F` ฆ่าทั้ง process tree (chrome.exe + chromedriver) หลัง `driver.quit()` · terminate บน Unix
- **`4aa60bb` feat(bot): ระบบคิวสั่งบอท + ราคาบอทสรุปย่อ + บันทึกเวลารับเรื่อง/เริ่มทำ** — `ราคาบอท` ตอบสรุปย่อ 5 แพ็กเกจ + ปุ่มเลือก, keyword `ระยะเวลา` เดี่ยวตอบได้, ลูกค้าดูเลขคิวตอนสั่ง + พิมพ์ `คิวของฉัน`, เจ้าของพิมพ์ `/คิว`, บันทึก `paid_at`/`confirmed_at` (มี migration `supabase/migrations/20260818000000_bot_purchases_timestamps.sql` + auto-migrate ตอน startup) — **deploy ขึ้น production แล้ว**
- **`7168190` feat(bot): รับสลิปโอนเงินผ่าน LINE + OCR อ่านยอด/เลขอ้างอิงด้วย Groq แล้วแจ้งเจ้าของเทียบยอดคาดก่อนยืนยัน** (commit โดยเจ้าของ 05:25 +07) — **deploy live แล้ว**
- **Auto-deploy ผ่าน GitHub Action + Render Deploy Hook** — `.github/workflows/auto-deploy.yml` push ขึ้น `main` → POST ไป Deploy Hook (`RENDER_DEPLOY_HOOK_URL` secret) · ข้าม deploy ด้วย `[skip deploy]` ใน commit message · ใช้ `[skip deploy]` ต้องมีเครื่องหมายวงเล็บเหลี่ยมทั้งคู่ใน message ด้วย (รอบแรกโดน skip เองเพราะข้อความ commit มีคำนี้)
- **`a1d0aaf` feat(admin+bot): หน้าแอดมินดูสลิป (💰 สลิป) + แจ้งเจ้าของเป็น Flex การ์ดปุ่มแตะเปิดสลิป** — /api/admin/purchases, /api/admin/slips/{id}/image, แท็บ 💰 สลิป, _notify_owner_slip ส่ง Flex การ์ด + ปุ่ม uri — **deploy live แล้ว**
- **`808270f` fix(ocr): เปลี่ยนโมเดล OCR สลิปเป็น `qwen/qwen3.6-27b`** — `llama-3.2-11b-vision-preview` ถูก decommission 16/08/26 (400 ทุก key → amount/ref เป็น None); qwen3.6 เป็น vision model ตัวเดียวที่เหลือบน Groq (gpt-oss เป็น text-only) + ตัด `<think>...</think>` ก่อน parse JSON (โมเดล reasoning คืนบล็อกคิดมาด้วย)
- **`dd52e12` feat(bot): log ส่ง reply สำเร็จ/ล้ม (`[reply] OK/FAIL/MOCK` ใน `_send_reply`) + คำสั่ง `/สลิป <userId>` (เจ้าของดึงรูปสลิปจาก DB ส่งกลับในแชทได้) — เทสต์รวม 1144 passed**
- **`7477409` fix(cron): กรอง cooldown หมวดใน SQL ก่อน limit 20** — เดิมดึง 20 ตัวแรก (คอมสูง) แล้วกรองหมวดที่เพิ่งโพสต์ใน Python → ถ้าติด cooldown หมด ระบบเงียบทั้งที่มีสินค้าพร้อม 1,000+ ตัว (เจอจริง 18/08) — **deploy live แล้ว**
- **`ce69986` feat(fb): ป้ายกำกับโพสต์** — ป้าย `🛍️ โพสต์ขายสินค้า` / `👵 โพสต์แนะนำบอท` — เทสต์รวม 1154 passed — **deploy live แล้ว**

## 2. งานค้าง

<!-- ว่าง -->

## 3. ขั้นตอนต่อไป

<!-- ว่าง -->

## 4. ไฟล์ที่ถืออยู่ / โดนแก้

<!-- ว่าง -->

## 5. หมายเหตุ

- **Render Auto-Deploy (native):** flag เป็ข `yes` (ผ่าน API) แต่ push จริงไม่ trigger (repo ไม่มี webhook เลย `[]` — สงสัย GitHub integration หลุดตอน rollback) → จึงเปลี่ยนเป็น **GitHub Action + Deploy Hook** (route stable กว่า); ถ้าอยากลองกลับไปใช้ native อีก ให้ reconnect GitHub ใน Dashboard
- **secret `RENDER_DEPLOY_HOOK_URL` ตั้งแล้ว + auto-deploy ทำงานจริง** — GH Action `auto-deploy to render` รัน success ทุก push ล่าสุด (รวม `3f9ddad`) · trigger deploy hook จาก API เองก็ได้ (curl POST ไป Deploy Hook URL)
- **Deploy ปัจจุบัน (production):** push `7c27c2a` (FB rate-limit logging + classifier fix + Reels uploader + normalize + docs) → GH Action `Test` + `auto-deploy to render` success → `/health` = 200 — Reels uploader (`uploader.py`) รันฝั่งเครื่อง local ไม่ใช่บน Render; บน Render มีผลเฉพาะ rate-limit logging/classifier fix ของ `post_feed`
- **`FB_CONTENT_POST_INTERVAL=1440` ตั้งบน Render แล้ว (โพสต์คอนเทนต์ 1 ครั้ง/วัน)** — โพสต์แนะนำบอท/ข่าว/ร้านสลับกัน วันละ 1 ตัว · `FB_AUTO_POST_INTERVAL=60` = โพสต์สินค้า 1 ตัว/ชม.
- **เวลาในตาราง `bot_purchases`:** `created_at` (รับเรื่อง) · `paid_at` (โอน) · `confirmed_at` (เริ่มทำ) — แสดงเป็นเวลาไทย UTC+7
- **drop ซากตารางบน prod แล้ว (20/08):** ลบ `facebook_detected_leads.group_id` + `group_share_tasks` (48 แถว) + `facebook_groups_monitor` (14 แถว) ผ่าน pooler URL (port 5432) — verify แล้วไม่มีเหลือ · `facebook_detected_leads` ยังอยู่ครบ 1,117 แถว
- **ลบ Task Scheduler แล้ว (20/08):** ลบ `PaKhem Share Morning/Noon/Evening` + `PaKhem FB Group Monitor` (4 ตัว — ทุกตัวชี้ script ที่ลบไปแล้ว) · ไฟล์ log/state ของแชร์ถูกลบจากเครื่องแล้ว (gitignored)
- **Reels uploader env:** `FACEBOOK_PAGE_ACCESS_TOKEN` / `FACEBOOK_PAGE_ID` (มีใน `backend/.env` อยู่แล้ว) · `GROQ_API_KEY` (แคปชั่น AI) · `POSTING_SPACING_HOURS` (default 3.0) · `MAX_REELS_PER_DAY` (default 30 — ลิมิตจริงของ Reels API) · ใช้ `backend/.env` ร่วม ไม่ต้องสร้าง `.env` ใหม่ที่ root
- **`reels_publisher.py` (stray จาก agent อื่น) รวมเข้ากับงานแล้ว** — เอาเฉพาะส่วน decode error code (`_reels_error_hint()`: 190/102/10/32/506/1363128/1363040/1363127/1363129 → คำแนะนำไทย) มาใส่ใน `post_reel()` แล้วลบไฟล์ทิ้ง (README2.md → ย้ายเป็น `docs/facebook-reels-uploader.md` + ลิงก์จาก README.md)