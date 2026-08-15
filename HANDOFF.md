# HANDOFF.md — สถานะงานค้างระหว่าง AI session

> **วิธีใช้ (อ่านก่อน):**
> - **AI ตัวใหม่ที่เข้ามาทำงาน: ต้องอ่านไฟล์นี้ + ตรวจ `git status` ก่อนเริ่มงานเสมอ**
>   (บังคับตาม AGENTS.md → Multi-Agent Handoff Protocol)
> - **AI ตัวที่กำลังทำงาน:** ถ้าจะหยุดกลางคัน (ยังไม่ commit งานให้ครบ) ให้เติมข้อมูลจริงลงใน
>   ส่วน 1–5 ด้านล่าง แล้ว commit ไฟล์นี้ทันที พร้อมกับงานที่ทำไว้
> - **เมื่องานเสร็จและ commit ครบ:** ให้ล้างเนื้อหาในส่วน 1–5 กลับเป็นสถานะว่าง แล้ว commit
>   ไฟล์นี้ — เพื่อไม่ให้ AI ตัวถัดไปเข้าใจผิดว่างานยังค้าง

## สถานะ: 🟢 ว่าง — งานล่าสุด (แก้เรดาร์โพสต์ระเบิด 102 ตัว + ล้าง daily limit) เสร็จสมบูรณ์ + deploy live (commit de394e7, /health 200)

---

## 1. งานที่ทำแล้ว (ล่าสุด)

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

*   🚨 **เรดาร์เคยโพสต์ระเบิด 102 ตัวใน 7 วินาที** (17:06 UTC 15/08, ids 5–104) เพราะ Hermes/รุ่นเก่าปล่อยให้ daily limit ทะลุ — โพสต์พวกนั้นยังอยู่บนเพจ Facebook (ต้องลบในเพจเองถ้าต้องการ); ระบบ DB ถูก reset แล้ว (posted→ignored 102 แถว) + โค้ดใหม่ clamp กันแล้ว
*   ⚠️ **commit `05e45f1` (agent อื่น, push ขึ้น origin แล้ว) ต้นไม้ ณ commit นั้น import พัง**: `demand_radar_ai.py` ใช้ `call_with_backoff` (งาน rate-limit ที่โดนกวาดปนเข้าไป) แต่ `llm_clients.py` ยังไม่มีฟังก์ชันนั้นตอน commit → commit `6fff794` ของเราที่เติมนิยามให้ถูก commit ตามมา ใครมีประวัติเก่าต้อง pull/reset ตามใหม่
*   ✅ **Production deploy สำเร็จ**: live ที่ commit `9b3b98f` (งาน 429 ครบ + regression test) — deploy เดิมของ `05e45f1` = `update_failed` (ยืนยัน commit นั้นพังจริง); ตั้ง env `LLM_RATE_LIMIT_RPM=20`/`LLM_RETRY_MAX_ATTEMPTS=3`/`LLM_RETRY_BASE_DELAY=1.0`/`LLM_RETRY_MAX_DELAY=30.0` บน Render แล้ว; `GET /health` → 200
*   การทดสอบทั้งหมดของ Social Demand Radar ใน `tests/test_facebook_demand_radar.py` ผ่านการ Mock การวิเคราะห์อย่างสมบูรณ์แบบเพื่อหลีกเลี่ยงผลกระทบจาก Rate Limit 429 ของ API ภายนอก และแก้ปัญหา Mojibake บนระบบ Windows ส่งผลให้เทสต์ทำงานได้เสถียรและเร็วขึ้นมาก
*   เพิ่มระบบ Relevance Safeguard ใน `product_matcher.py` เพื่อบล็อกดีลสินค้าหากไม่มีสินค้าในคลังที่ตรงกับความต้องการของลูกค้าจริง (Relevance Score < 12.0) ป้องกันการสแปมและยิงโพสต์มั่วซั่วขึ้นบนเพจ
*   Facebook Messenger webhook + Live เรียบร้อยแล้ว (ยืนยันจากลูกค้าจริงที่ทักแชทแล้วบอทตอบ); ล้าง subscription เก่า `object=user` ที่ชี้ `huan-khuen-cafe` แล้ว — ตอนนี้เหลือ subscription เดียว `object=page` ชี้ที่บอทป้าเข็ม
