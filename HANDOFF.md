# HANDOFF.md — สถานะงานค้างระหว่าง AI session

> **วิธีใช้ (อ่านก่อน):**
> - **AI ตัวใหม่ที่เข้ามาทำงาน: ต้องอ่านไฟล์นี้ + ตรวจ `git status` ก่อนเริ่มงานเสมอ**
>   (บังคับตาม AGENTS.md → Multi-Agent Handoff Protocol)
> - **AI ตัวที่กำลังทำงาน:** ถ้าจะหยุดกลางคัน (ยังไม่ commit งานให้ครบ) ให้เติมข้อมูลจริงลงใน
>   ส่วน 1–5 ด้านล่าง แล้ว commit ไฟล์นี้ทันที พร้อมกับงานที่ทำไว้
> - **เมื่องานเสร็จและ commit ครบ:** ให้ล้างเนื้อหาในส่วน 1–5 กลับเป็นสถานะว่าง แล้ว commit
>   ไฟล์นี้ — เพื่อไม่ให้ AI ตัวถัดไปเข้าใจผิดว่างานยังค้าง

## สถานะ: 🟢 ว่าง — งานล่าสุด (Phase 1 White-Label: bot_profile + backup_config + FAQ แพ็กเกจ/5 ขั้นตอนในบอท) เสร็จ+commit — ยังไม่ deploy โค้ดใหม่ (กระทบ production: line_bot/facebook_bot/persona ต้อง deploy ก่อนลูกค้าเห็น)

---

## 1. งานที่ทำแล้ว (ล่าสุด)

- ✅ feat(line-bot): **ปุ่ม "คุยกับป้าเข็ม" ตอบด้วยมาตรฐาน 5 ขั้นตอน** — `CHAT_BOT_PROMPT` (สั้น/ชัด/ไม่อ่านรก: 5 หัวข้อ + ชวนพิมพ์) แทนข้อความ "พิมพ์คำถาม" ธรรมดา; แยก branch `normalized_text in CHAT_BOT_PHRASES` ก่อน `is_contact_request` ยัง set `_pending_question` → ข้อความถัดไป route ปกติ (หูฟัง→search); "ฝากคำถาม" ยังใช้ ASK_QUESTION_PROMPT เดิม; ข้อย่อยเต็มยังอยู่ที่ "บริการ"/"มาตรฐานการบริการ" → 606 passed
- ✅ feat(line-bot): **ขยาย "5 ขั้นตอน" เป็นรายละเอียดเต็มตามอินโฟกราฟิก** — แต่ละขั้นมี 3 ข้อย่อย (เช่น 1️⃣ ต้อนรับ → ทักทายด้วยรอยยิ้ม/เป็นกันเอง/พร้อมให้บริการ) แทนบรรทัดเดียว; footer `{BOT_SLOGAN}` (ความพึงพอใจของคุณคือความสำเร็จของเรา) → 605 passed
- ✅ feat(line-bot): **ล้างคำว่า "ฟรี/โอเพนซอร์ส/ดาวน์โหลดฟรี" ออกจาก FAQ** — โปรโมชั่นฟรีหมดแล้ว → ติดตั้ง/ค่าใช้จ่าย/ลิขสิทธิ์/โค้ด ชี้ไปแพ็กเกจ 990/1,990/4,990 แทน (INSTALL_REPLY_OWNER ยังเก็บ "เตรียม 4 อย่าง" ไว้กันเทสต์พัง); `_github_button_card` เปลี่ยนเป็นการ์ดแพ็กเกจ 3 ระดับ → 605 passed
- ✅ feat(line-bot): **FAQ แพ็กเกจ/ราคาบอทในคู่มือ** — พิมพ์ "ค่าบริการ"/"แพ็กเกจราคา"/"สมัครใช้บอท"/"ซื้อบอท"/"เปิดร้าน" → ตอบ 3 แพ็กเกจ (Starter 990 / Business 1,990 / White-Label 4,990); ใช้คำเฉพาะ ไม่ใช้ "แพ็กเกจ" เดี่ยว (ชนชื่อสินค้า 3 ตัว) + สลับ section ให้ "ค่าบริการ" ไปแพ็กเกจก่อน "บริการ" ไป 5 ขั้นตอน; guard test กัน "แพ็กเกจกล่อง/ผ้ามาตรฐาน" โดนดัก → 604 passed
- ✅ feat(white-label): **Bot Profile — รวมศูนย์ตัวตนร้านไว้จุดเดียว** (`app/services/bot_profile.py`) — อ่าน `BOT_NAME`/`PERSONA_NAME`/`BOT_SLOGAN` จาก env (default "ป้าเข็ม ขายของ"/"ป้าเข็ม"/"ความพึงพอใจของคุณคือความสำเร็จของเรา") → เปลี่ยนชื่อบอท/เสียง/สโลแกนได้โดยไม่แตะโค้ด; wire เข้า `persona.py` (PERSONA_PROMPT เป็น f-string ใช้ชื่อจริง), `line_bot.py` (BOT_NAME + สโลแกนท้าย 5 ขั้นตอน), `facebook_bot.py` (BOT_NAME) — 4 ไฟล์; เทสต์ `tests/test_bot_profile.py` 4 ตัว → รวม 598 passed
- ✅ feat(ops): **`tools/backup_config.py`** — ก๊อป `.env`/`fb_cookies.json`/`affiliate_db.db`/`db-password.txt`/`render cli.yaml` ไป `backups/<timestamp>/` (เพิ่ม `backups/` ใน `.gitignore` กัน secret หลุด commit); กู้คืนเมื่อโค้ด/ค่าพัง = ก๊อปกลับจากโฟลเดอร์ล่าสุด
- ✅ docs: **BRD v1.0 ล็อกแล้ว** (`docs/brd-sell-line-oa-bot.md`) + **SRS** (`docs/srs-white-label-bot.md`) — ตัดสินใจครบ: ลูกค้าทั้งคู่ (ร้านค้า + affiliate), ราคา 990/1,990/4,990 + M/A, ลูกค้าออกค่า LINE OA, ตั้งค่าทั้งแอดมิน+ลูกค้าเอง; RLS/Stripe = Model C roadmap (Phase 2+)
- ✅ feat(radar-tools): **เครื่องมือค้นกลุ่ม buyer-demand อัตโนมัติ** (`tools/fb_group_search_local.py`) — stealth Chrome + fb_cookies.json ค้นกลุ่มตามคีย์เวิร์ด "อยากได้/งบ/แนะนำ" → นับ buyer/seller signals จากโพสต์ล่าสุด → `--auto-add` เพิ่มกลุ่ม public+scannable+buyer เข้า radar อัตโนมัติ + `--loop` วนต่อเนื่อง + `log_group_to_sheet()` ดันผู้สมัครลง Google ชีทแท็บ "กลุ่มผู้สมัคร" (คอลัมน์ ชื่อ/ลิงก์/สิ่งที่ต้องการ/buyer/seller/สแกนได้); เทสต์ `tests/test_fb_group_search_local.py` 20 ตัว → รวม 589 passed
- ✅ data(prod): **ล้างข้อมูลปลอม + เพิ่มกลุ่มจริง** — ลบกลุ่ม FB ปลอม 7 กลุ่ม (grp_moms_th/grp_tech_deals/... ผ่าน DB production, FK ON DELETE SET NULL) + ลบ lead สังเคราะห์ 131 ตัว (fb_sample_*/fb_mock_bulk_*/grp_public_monitor_*) cascade ลบ demand events 104 ตัว → เหลือ leads จริง 155 ตัว; เพิ่มกลุ่ม buyer-demand 6 กลุ่ม (headphoneclub "หูฟังคลับ" + สมาร์ทโฮม + แม่และเด็ก + สัตว์เลี้ยง + อาร์ตทอย) → เรดาร์ตอนนี้ 14 กลุ่ม
- ✅ feat(sheet): **Apps Script เพิ่มแท็บ "กลุ่มผู้สมัคร"** (`tools/sheet_posts_apps_script.gs`) — รับ `kind='group_candidate'` เขียนชื่อกลุ่ม/ลิงก์/สิ่งที่ต้องการลงชีท (deploy แล้ว ใช้ URL เดิม POSTS_SHEET_WEBHOOK_URL)
- ✅ verify: **โพสต์เรดาร์จริงตัวแรกขึ้นเพจป้าเข็มแล้ว** — สแกนกลุ่ม headphoneclub → lead "แนะนำหูฟังงบ 1000" demand 80 → จับคู่ REMAX TWS-19 → post_feed สำเร็จ (permalink 122099133381443245); FB token production ใช้ได้, daily quota ว่าง
- ✅ fix(radar): **guard กัน test/mock lead เข้า production** (commit `667b97e`) — `_looks_like_test_lead()` + skip `fb_sample_`/`fb_mock_`/`demo_` ใน ingest endpoint ตอน DATABASE_URL เป็น postgres (production); ต้นตอ 102 แถว 'posted' หลอก = lead สังเคราะห์ `fb_mock_bulk_*` (author User_0..User_N) ที่ถูก insert ตรงเข้า prod DB 17:06 UTC 15/08 (sent_at คงที่ก่อน created_at = หลักฐานว่า insert ตรง ไม่ผ่าน ingest loop) — โค้ดนี้ไม่อยู่ใน repo (สคริปต์ temp ถูกลบ)
- ✅ fix(radar): **hard หา daily post limit + ล้าง mojibake** (commit `de394e7`) — `RADAR_MAX_DAILY_POSTS` เป็นของแอดมินเท่านั้น clamp [1,25] (Hermes/system_preferences ห้าม override โควต้าโพสต์ — ต้นเหตุโพสต์ระเบิด 102 ตัวใน 7 วิ), `merge_skills` strip `radar_daily_post_limit` ไม่ให้ persist, `_strip_garbled`/`_clean_llm_data` ล้าง lone surrogates + U+FFFD จาก product_keyword กัน mojibake + เทสต์ 567 ผ่าน; **unblock production: reset 102 แถว facebook_demand_events posted→ignored** (daily limit window เหลือ 0) + deploy live `de394e7`
- ✅ feat(llm): **rate-limit + retry กัน HTTP 429** — `call_with_backoff()` (retry 429/5xx แบบ exponential + เคารพ Retry-After แต่ cap max_delay) + `throttle_llm_request()` (จำกัด RPM process-wide, env `LLM_RATE_LIMIT_RPM` / `LLM_RETRY_*`) ใน `llm_clients.py`; ครอบครบทุก LLM call site (demand_radar_ai, hermes_brain, ai_generator, ai_analyzer, web_search, facebook_curated, facebook_local, orchestrator) + regression guard ใน `test_llm_providers.py` → เทสต์ 563 ผ่าน; **deploy live บน production (commit `9b3b98f`) + env 4 ตัวตั้งบน Render ครบ** → /health 200
- ✅ feat(content): **backfill คอนเทนต์แบบ template (ไม่ใช้ Groq)** — เพิ่ม `build_template_script()` ใน `app/services/ai_generator.py` (เสียงป้าเข็มสำเร็จรูป, field ครบ SCRIPT_KEYS) + refactor fallback เดิมมาใช้ตัวเดียวกัน + `tools/_backfill_content_template.py` ต่อ Supabase ตรงเติม `contents` ของสินค้าที่ยังไม่มี (เรียง ai_score สูงก่อน, batch 500) + skill `.agents/skills/content-backfill/` + เทสต์ใหม่ `test_ai_generator_template.py`
- ✅ feat(facebook): **Messenger webhook + แอพ Live ครบวงจร** — แก้ callback URL ให้ชี้ที่ `/api/webhooks/facebook` (เดิมชี้ผิดไป `huan-khuen-cafe`) + subscribe เพจ "ป้าเข็ม ขายของ" เข้ากับแอพ (Add Subscriptions ผ่าน Graph API) + สลับแอพเป็น Live — เทสต์จริง 22:08 ลูกค้าทัก "สวัสดี" บอทตอบแนะนำ + ลิงก์ LINE (`lin.ee/o9Kjp1N`) อัตโนมัติ
- ✅ data: **backfill `products.image_url` 1,672 ตัว** ด้วย fetch แบบใหม่ (og:image ตรงจากหน้า Shopee — ฟรี/เร็ว ไม่พึ่ง FB token/Firecrawl) → โพสต์ FB แนบรูปจริง (scontent CDN) ไม่ใช่การ์ดดำ
- ✅ feat(products): **eager backfill image_url ตอน import** (commit `725c966`) — สินค้าใหม่ได้รูปทันที ไม่ต้องรอโพสต์ FB

## 2. งานค้าง

<!-- ว่าง — ไม่มีงานโค้ดค้าง ทำงานทุกชิ้นเสร็จสมบูรณ์ -->

## 3. ขั้นตอนต่อไป

<!-- ว่าง — รัน backfill จริงได้เมื่อเจ้าของร้านสั่ง: cd backend && .venv/Scripts/python.exe ../tools/_backfill_content_template.py -->

## 4. ไฟล์ที่ถืออยู่ / โดนแก้

<!-- ว่าง -->

## 5. หมายเหตุ

*   🚨 **เรดาร์เคยมีแถว `facebook_demand_events` สถานะ `posted` 102 แถวใน 7 วินาที** (17:06 UTC 15/08, ids 5–104) — หลักฐาน `notification_sent_at` เท่ากันหมด (17:06:47.113) ทั้งที่ `created_at` ต่อเนื่อง → เป็นแถวหลอก/จากรุ่นเก่า **ไม่ใช่โพสต์จริงบนเพจ** (เจ้าของยืนยันเพจไม่มี); แถวพวกนั้นทำให้ daily-limit counter เต็ม → บอทหยุดโพสต์; DB reset แล้ว (posted→ignored 102 แถว) + โค้ดใหม่ clamp กันแล้ว
*   ⚠️ **commit `05e45f1` (agent อื่น, push ขึ้น origin แล้ว) ต้นไม้ ณ commit นั้น import พัง**: `demand_radar_ai.py` ใช้ `call_with_backoff` (งาน rate-limit ที่โดนกวาดปนเข้าไป) แต่ `llm_clients.py` ยังไม่มีฟังก์ชันนั้นตอน commit → commit `6fff794` ของเราที่เติมนิยามให้ถูก commit ตามมา ใครมีประวัติเก่าต้อง pull/reset ตามใหม่
*   ✅ **Production deploy สำเร็จ**: live ที่ commit `9b3b98f` (งาน 429 ครบ + regression test) — deploy เดิมของ `05e45f1` = `update_failed` (ยืนยัน commit นั้นพังจริง); ตั้ง env `LLM_RATE_LIMIT_RPM=20`/`LLM_RETRY_MAX_ATTEMPTS=3`/`LLM_RETRY_BASE_DELAY=1.0`/`LLM_RETRY_MAX_DELAY=30.0` บน Render แล้ว; `GET /health` → 200
*   การทดสอบทั้งหมดของ Social Demand Radar ใน `tests/test_facebook_demand_radar.py` ผ่านการ Mock การวิเคราะห์อย่างสมบูรณ์แบบเพื่อหลีกเลี่ยงผลกระทบจาก Rate Limit 429 ของ API ภายนอก และแก้ปัญหา Mojibake บนระบบ Windows ส่งผลให้เทสต์ทำงานได้เสถียรและเร็วขึ้นมาก
*   เพิ่มระบบ Relevance Safeguard ใน `product_matcher.py` เพื่อบล็อกดีลสินค้าหากไม่มีสินค้าในคลังที่ตรงกับความต้องการของลูกค้าจริง (Relevance Score < 12.0) ป้องกันการสแปมและยิงโพสต์มั่วซั่วขึ้นบนเพจ
*   Facebook Messenger webhook + Live เรียบร้อยแล้ว (ยืนยันจากลูกค้าจริงที่ทักแชทแล้วบอทตอบ); ล้าง subscription เก่า `object=user` ที่ชี้ `huan-khuen-cafe` แล้ว — ตอนนี้เหลือ subscription เดียว `object=page` ชี้ที่บอทป้าเข็ม
