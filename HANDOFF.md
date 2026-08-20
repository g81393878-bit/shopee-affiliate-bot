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

- **ลบฟีเจอร์แชร์ลงกลุ่ม Facebook ทั้งหมด (20/08)** — Meta ปิด Groups API (`publish_to_groups`) ถาวร เม.ย. 2024 → ทางเดียวที่เหลือคือ browser automation (ผิด ToS) → เจ้าของสั่งลบทุกที่: ตาราง `group_share_tasks` + `facebook_groups_monitor` + `group_id` ของ lead · endpoint `/api/admin/group-shares/*` + `/tasks/*` · hook `_enqueue_group_share` · `bot/share_group.py` + `run_campaign.py share` + legacy + bat + `groups.txt` · `tools/fb_group_monitor_local.py` + `fb_group_search_local.py` · migration `20260820000000_remove_group_sharing.sql` · radar ทุก lead ลงเพจป้าเข็ม (Flow B) ไม่แยกกลุ่มแล้ว · เทสต์ 1100 passed — **ยังไม่ commit/push**
- **push `3126b7f..446e296` (19/08) — งาน radar/monitor + แคปชั่นบอทแชร์กลุ่ม 7 commits** — แตะเฉพาะ `bot/`, `tools/`, `backend/tests/` — **ไม่มีการแก้ `backend/app/` → production (Render) runtime ไม่เปลี่ยน** (รายละเอียดแต่ละ commit ด้านล่าง)
- **`446e296` test(radar): เทสต์ `_kill_chrome_tree` + `_sweep_orphan_drivers` 6 ตัว (mock subprocess/tasklist)** — ฆ่า undetected_chromedriver ด้วย taskkill /T /F · ไม่แตะ chrome.exe ของ user · no-op บน non-Windows · no-PID ไม่ crash — `test_fb_group_monitor_local.py` 28 passed, รวม radar 54 passed
- **`3893f51` feat(radar): single-instance lock กันรัน monitor ซ้อนกัน** — `.fb_monitor.lock` เก็บ PID · เจอ lock ของ process ที่ยังมีชีวิต → refuse + exit 1 · lock ค้างจาก PID ตายเขียนทับอัตโนมัติ · ปลด lock ทุกทางออก (Ctrl+C/error/จบ) · `--lock-file ''` ปิดได้ · gitignore `.fb_monitor.lock` + `.fb_monitor_seen.json`
- **`6a90b01` feat(radar): กวาดซาก chromedriver ตอนสตาร์ท + คำเตือน loop mode** — `_sweep_orphan_drivers()` ฆ่า `undetected_chromedriver.exe` ที่ค้างจากรอบโดน hard-kill (finally ไม่ทันรัน) เฉพาะโหมด scrape จริง · เตือนเด่นเมื่อรันโหมด loop ไม่มี `--once`
- **`5c2dba3` fix(radar): ปิด Chrome สิ้นซาก** — `_kill_chrome_tree()` จับ PID driver ก่อนปิด แล้ว `taskkill /PID <pid> /T /F` ฆ่าทั้ง process tree (chrome.exe + chromedriver) หลัง `driver.quit()` · terminate บน Unix
- **`32c9b05` feat(bot): หมุนแคปชั่น spintax 15 แบบต่อกลุ่มใน `share_group.py main()`** — เดิมใช้แบบแรกตลอด → ตอนนี้ `captions[(i-1) % len]` หมุนทีละกลุ่ม
- **`4449bb7` refactor(bot): ลบโค้ดตาย** — `_share_post_to_groups_batch` + `MAX_GROUPS_PER_SHARE` (165 บรรทัด, ไม่มี caller เหลือ)
- **`d411d51` feat(bot): แคปชั่น spintax 15+18 แบบ** — `_share_caption_variants()` 15 แบบ (share_group.py) + `_build_group_captions()` 18 แบบ (run_campaign.py) — hook/benefit × CTA หมุนเวียนกัน FB จับสแปม · `@@LINE@@` → `LINE_OA_URL` อัตโนมัติ — **สคริปต์ local ไม่ต้อง deploy**
- **แชร์กลุ่มอัตโนมัติปลอดภัย (local bot)** — `bot/share_group.py` batching แชร์ครั้งละ ≤10 กลุ่ม (FB จำกัด) · `bot/run_campaign.py` โควต้า `--max-posts-per-day 3` + `--max-posts-per-run 1` + ตัวนับ `fb_daily_share.json` (รีเซ็ตรายวัน) · `bot/run_share_auto.bat` + Task Scheduler 3 งาน (08:00/12:00/18:00) ดึง CRON_TOKEN จาก backend/.env เอง · `groups.txt` ขยายเป็น 20 กลุ่ม (join ครบแล้ว) · ลบโพสต์คิวเก่า id 5,6,7 ออกจาก `group_share_tasks` — **สคริปต์ local ไม่ต้อง deploy บน Render (backend ไม่เปลี่ยน)**
- **`4aa60bb` feat(bot): ระบบคิวสั่งบอท + ราคาบอทสรุปย่อ + บันทึกเวลารับเรื่อง/เริ่มทำ** — `ราคาบอท` ตอบสรุปย่อ 5 แพ็กเกจ + ปุ่มเลือก, keyword `ระยะเวลา` เดี่ยวตอบได้, ลูกค้าดูเลขคิวตอนสั่ง + พิมพ์ `คิวของฉัน`, เจ้าของพิมพ์ `/คิว`, บันทึก `paid_at`/`confirmed_at` (มี migration `supabase/migrations/20260818000000_bot_purchases_timestamps.sql` + auto-migrate ตอน startup) — **deploy ขึ้น production แล้ว**
- **`7168190` feat(bot): รับสลิปโอนเงินผ่าน LINE + OCR อ่านยอด/เลขอ้างอิงด้วย Groq แล้วแจ้งเจ้าของเทียบยอดคาดก่อนยืนยัน** (commit โดยเจ้าของ 05:25 +07) — **deploy live แล้ว**
- **Auto-deploy ผ่าน GitHub Action + Render Deploy Hook** — `.github/workflows/auto-deploy.yml` push ขึ้น `main` → POST ไป Deploy Hook (`RENDER_DEPLOY_HOOK_URL` secret) · ข้าม deploy ด้วย `[skip deploy]` ใน commit message · ใช้ `[skip deploy]` ต้องมีเครื่องหมายวงเล็บเหลี่ยมทั้งคู่ใน message ด้วย (รอบแรกโดน skip เองเพราะข้อความ commit มีคำนี้)
- **`a1d0aaf` feat(admin+bot): หน้าแอดมินดูสลิป (💰 สลิป) + แจ้งเจ้าของเป็น Flex การ์ดปุ่มแตะเปิดสลิป** — /api/admin/purchases, /api/admin/slips/{id}/image, แท็บ 💰 สลิป, _notify_owner_slip ส่ง Flex การ์ด + ปุ่ม uri — **deploy live แล้ว**
- **`808270f` fix(ocr): เปลี่ยนโมเดล OCR สลิปเป็น `qwen/qwen3.6-27b`** — `llama-3.2-11b-vision-preview` ถูก decommission 16/08/26 (400 ทุก key → amount/ref เป็น None); qwen3.6 เป็น vision model ตัวเดียวที่เหลือบน Groq (gpt-oss เป็น text-only) + ตัด `<think>...</think>` ก่อน parse JSON (โมเดล reasoning คืนบล็อกคิดมาด้วย)
- **`dd52e12` feat(bot): log ส่ง reply สำเร็จ/ล้ม (`[reply] OK/FAIL/MOCK` ใน `_send_reply`) + คำสั่ง `/สลิป <userId>` (เจ้าของดึงรูปสลิปจาก DB ส่งกลับในแชทได้) — เทสต์รวม 1144 passed**
- **`7477409` fix(cron): กรอง cooldown หมวดใน SQL ก่อน limit 20** — เดิมดึง 20 ตัวแรก (คอมสูง) แล้วกรองหมวดที่เพิ่งโพสต์ใน Python → ถ้าติด cooldown หมด ระบบเงียบทั้งที่มีสินค้าพร้อม 1,000+ ตัว (เจอจริง 18/08) — **deploy live แล้ว**
- **`ce69986` feat(fb): ป้ายกำกับโพสต์ + คิวแชร์ลงกลุ่ม** — ป้าย `🛍️ โพสต์ขายสินค้า` / `👵 โพสต์แนะนำบอท` · ตารางใหม่ `group_share_tasks` (สร้างอัตโนมัติ + ตรวจแล้วบน prod มี 1 แถว = enqueue ทำงานจริง) + hook เข้าคิวทุกโพสต์สำเร็จ · API `/api/admin/group-shares/{pending,{id}/status,}` · `bot/run_campaign.py share --from-queue` — เทสต์รวม 1154 passed — **deploy live แล้ว**

## 2. งานค้าง

<!-- ว่าง -->

## 3. ขั้นตอนต่อไป

<!-- ว่าง -->

## 4. ไฟล์ที่ถืออยู่ / โดนแก้

<!-- ว่าง -->

## 5. หมายเหตุ

- **Render Auto-Deploy (native):** flag เป็ข `yes` (ผ่าน API) แต่ push จริงไม่ trigger (repo ไม่มี webhook เลย `[]` — สงสัย GitHub integration หลุดตอน rollback) → จึงเปลี่ยนเป็น **GitHub Action + Deploy Hook** (route stable กว่า); ถ้าอยากลองกลับไปใช้ native อีก ให้ reconnect GitHub ใน Dashboard
- **secret `RENDER_DEPLOY_HOOK_URL` ตั้งแล้ว + auto-deploy ทำงานจริง** — GH Action `auto-deploy to render` รัน success ทุก push ล่าสุด (รวม `3f9ddad`) · trigger deploy hook จาก API เองก็ได้ (curl POST ไป Deploy Hook URL)
- **Deploy ปัจจุบัน (production):** commit `ce69986` live (deploy `dep-da1vgmmgekts73ethgog`) — มีฟีเจอร์สลิปครบ + ป้ายกำกับโพสต์ (งานลบแชร์กลุ่มยังไม่ deploy)
- **`FB_CONTENT_POST_INTERVAL=1440` ตั้งบน Render แล้ว (โพสต์คอนเทนต์ 1 ครั้ง/วัน)** — โพสต์แนะนำบอท/ข่าว/ร้านสลับกัน วันละ 1 ตัว · `FB_AUTO_POST_INTERVAL=60` = โพสต์สินค้า 1 ตัว/ชม.
- **เวลาในตาราง `bot_purchases`:** `created_at` (รับเรื่อง) · `paid_at` (โอน) · `confirmed_at` (เริ่มทำ) — แสดงเป็นเวลาไทย UTC+7
- **หลัง deploy งานลบแชร์กลุ่ม:** ลบ Task Scheduler `PaKhem Share Morning/Noon/Evening` บนเครื่องเจ้าของ (`schtasks /delete /tn "PaKhem Share Morning"` + Noon/Evening) — ไฟล์ `bot/share_auto.log`/`share_run_now.log`/`_share_run.log`/`_dryrun.log` + `fb_shared_state.json`/`fb_blacklist.json`/`fb_daily_share.json` เป็นซาก runtime (gitignored) ลบทิ้งได้
- **วิธี apply migration ลบแชร์กลุ่มบน prod (`.sql` ไม่ถูก auto-run — ไม่มี supabase/config.toml และ create_all ไม่ drop ตารางเดิม):** ต้อง (1) push+deploy commit `cb0e847` ก่อน (โค้ดใหม่ไม่แตะตารางแล้ว) แล้ว (2) drop มือใน Supabase Dashboard → SQL Editor (project `usqhvujqmnxqrdoovvnp`) ตามลำดับ: `DROP TABLE IF EXISTS group_share_tasks;` → `ALTER TABLE facebook_detected_leads DROP COLUMN IF EXISTS group_id;` → `DROP TABLE IF EXISTS facebook_groups_monitor;` (drop group_id ก่อน = ถอด FK กันติด constraint) — **ห้าม drop ก่อน deploy** ไม่งั้นโค้ดเก่า (ce69986) ยัง query ตารางอยู่ → 500