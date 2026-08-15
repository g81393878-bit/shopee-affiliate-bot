# HANDOFF.md — สถานะงานค้างระหว่าง AI session

> **วิธีใช้ (อ่านก่อน):**
> - **AI ตัวใหม่ที่เข้ามาทำงาน: ต้องอ่านไฟล์นี้ + ตรวจ `git status` ก่อนเริ่มงานเสมอ**
>   (บังคับตาม AGENTS.md → Multi-Agent Handoff Protocol)
> - **AI ตัวที่กำลังทำงาน:** ถ้าจะหยุดกลางคัน (ยังไม่ commit งานให้ครบ) ให้เติมข้อมูลจริงลงใน
>   ส่วน 1–5 ด้านล่าง แล้ว commit ไฟล์นี้ทันที พร้อมกับงานที่ทำไว้
> - **เมื่องานเสร็จและ commit ครบ:** ให้ล้างเนื้อหาในส่วน 1–5 กลับเป็นสถานะว่าง แล้ว commit
>   ไฟล์นี้ — เพื่อไม่ให้ AI ตัวถัดไปเข้าใจผิดว่างานยังค้าง

## สถานะ: 🟢 Rollout โพสต์ Character-first ครบ 3 ตัว + เปิดขายสินค้าแล้ว (FB_POST_PRODUCTS=1) — เหลืองาน manual ฝั่งเจ้าของ (Facebook webhook/Live, ลบโพสต์ manual, แถว TEST)

---

## 1. งานที่ทำแล้ว (ล่าสุด)

- ✅ feat(facebook): **โพสต์สินค้าแนบรูปจริง (ไม่พึ่งการ์ดลิงก์)** — ปัญหา: บางโพสต์การ์ดลิงก์ `s.shopee.co.th` รูปว่าง (Shopee กัน facebookexternalhit บางรอบ) → แก้: เพิ่ม `products.image_url` (migrate ALTER แล้วบน Supabase) + `product_image.py` (`fetch_product_image` ดึงรูปผ่าน **Facebook og scrape `scrape=true`** เพราะ Shopee เป็น SPA กัน requests/firecrawl ไม่เห็น `<meta og:image>` → FB crawler ดึงได้ คืน `down-th.img.susercontent.com/...`) → `_post_next_product` โพสต์ `/photos` แนบรูป + ลิงก์ affiliate ในแคปชั่น (fallback การ์ดลิงก์ถ้าหาไม่ได้) + แก้ bug เรียก `_build_fb_caption` ซ้ำ 2 รอบ — 450 passed — deploy `dep-da05f561egvs73fur6hg` live (commit `f374d14`); เทสต์จริง: สินค้า #20 ANCHI → full_picture = scontent-*.fbcdn.net (รูปอัปโหลดจริง) + ลิงก์ `s.shopee.co.th/7Kw73GWSLp` ในแคปชั่น
- ✅ fix(facebook): **คลังท้องถิ่นไม่ติดตายบนลิงก์ facebook.com** — Firecrawl มักคืนโพสต์กลุ่มเฟสเป็นผลแรก → Graph API link preview เจอ "Permissions error" และโค้ดเดิมหยุดทันที → แก้ 2 จุด: `facebook_local.py` กรองลิงก์ facebook.com/fb.watch/messenger ออกตอน fetch + `_post_next_local` ลองตัวถัดไปเมื่อล้ม / คืน None ถ้าล้มหมด (rotation ไปคลังอื่น) — 438 passed — **push+deploy แล้ว** (`7de8881` → `dep-da04mm61egvs73ft8thg` live); **เทสต์จริงบนเพจ**: โพสต์ local ตัวแรก "100 ร้านอาหารกรุงเทพ..." (wongnai, `...941443245`) — ตรวจ Graph API แล้ว caption มี `lin.ee/o9Kjp1N` + hashtags + น้ำเสียงป้าเข็ม ครบ
- ✅ feat(facebook): **คลังโพสต์ท้องถิ่น (ร้านอร่อย/ของฝาก/ของกิน)** — ไฟล์ใหม่ `app/services/facebook_local.py`: Firecrawl search หมุน 77 จังหวัด × 3 หัวข้อ → Groq เขียนเสียงป้าเข็ม + **ลิงก์ LINE OA ทุกตัว** → dedup `status='fblocal'` (sha1(url)); `web_search.py` เพิ่ม `firecrawl_search_results()` (ผลดิบ best-effort); `cron.py` เพิ่ม `_post_next_local` + `run_facebook_auto_post` เปลี่ยนเป็น **หมุนเวียน 4 คลัง: แบรนด์ → สินค้า → คอนเทนต์โลก → ท้องถิ่น** (slot % 4) — 434 passed — deploy `dep-da04jm0jo6nc73dngk40` → live (commit `c7ca520`)
- ✅ feat(facebook): **ตัวกรองอักษรต่างภาษา** — ไฟล์ใหม่ `app/services/text_cleaner.py` (`sanitize_post_text` ตัด script ที่ไม่ใช่ไทย/Latin/ตัวเลข/เครื่องหมาย/สัญลักษณ์/emoji — ครอบคลุมอาหรับ/เปอร์เซีย/ซีริลลิก/CJK...) + เรียกใน `post_feed` ก่อนโพสต์ทุกตัว (chokepoint เดียวครอบทั้ง 4 คลัง: แบรนด์/สินค้า/RSS/ท้องถิ่น) — 427 passed; **ยังไม่ commit/deploy** (รอเจ้าของสั่ง)
- ✅ feat(facebook): **RSS curated engine (คอนเทนต์โลก)** — ไฟล์ใหม่ `app/services/facebook_curated.py`: ดึง feed ข่าวไทย (Beartai/Techhub/The Standard, override ได้ด้วย env `RSS_SOURCES_JSON`) → parse RSS2/Atom (stdlib, ไม่มี dependency ใหม่) → Groq เขียนเสียงป้าเข็ม + ลิงก์ LINE OA → dedup ด้วย sha1(guid|link) เก็บ `status='fbrss'`; `run_facebook_auto_post` เปลี่ยนเป็น **หมุนเวียน 3 คลัง: แบรนด์ → สินค้า → คอนเทนต์โลก** (slot = จำนวนโพสต์ทั้งหมด % 3) — 418 passed — deploy `dep-da04535bedkc739s1j00` → live, commit `8ef185a`; เทสต์จริงบนเพจครบ 3 แบบ (intro #6 / สินค้า #939 / RSS DENZA Z9GT จาก Beartai)
- ✅ fix(facebook): **แคปชั่นสั้นพื้นสีชัดขึ้น + ใส่ลิงก์ LINE OA ทุกตัว** — เขียน 8 แคปชั่นใหม่ (สื่อสารประโยชน์ชัด + ลงท้าย CTA "แอดไลน์ป้า" + `https://lin.ee/o9Kjp1N`); `short_bg_posts()` แทน `{LINE}` ด้วย `LINE_OA_URL` env — 410 passed — deploy `dep-da03qlojo6nc73dlvhd0` → live, commit `ca2cfd4`; เทสต์จริงบนเพจ 2 ตัว (intro #4 + bg #0 พร้อมลิงก์) — ตรวจ Graph API แล้ว message มี `lin.ee` ครบ
- ✅ feat(facebook): **ชุดโพสต์สั้นพื้นสี (≤130 ตัว) หมุนเวียนสี + ต่อเข้ากับ scheduler** — `facebook_intro.py` เพิ่ม `short_bg_posts()` (8 แคปชั่นสั้น + สีหมุนเวียน 8 สีจาก `_BG_PRESETS`); `cron.py` เพิ่ม `_post_next_short_bg` (dedup `status='fbbg'`) + `run_facebook_auto_post` **สลับ tick คู่→แนะนำตัว(มาสคอต) / คี่→ข้อความสั้นพื้นสี** — 410 passed — deploy `dep-da03o8ojo6nc73dlqj80` → live, commit `f13a3f5`; ลำดับถัดไป: intro #4 (อ่านรีวิว 1 ดาว) → bg #0 (ของดีไม่ต้องแพง/แดง) → intro #5 → bg #1 …
- ✅ feat(facebook): **โพสต์พื้นสี (text background)** — `post_feed` เพิ่ม param `background_preset_id` (พารามิเตอร์ไม่เป็นทางการ `text_format_preset_id` ของ Graph API) → โพสต์ข้อความล้วนบนพื้นสีผ่าน `/feed` ไม่แนบ media/link (มีแล้ว FB จะ ignore preset); **ข้อจำกัด: ข้อความ ≤ 130 ตัวอักษร**; +2 เทสต์ (รวม 409 passed) — deploy `dep-da03k1lbedkc739qri0g` → live, commit `ba5d8c4`; **เทสต์จริง 1 ตัวบนเพจแล้ว** (`...617153443245`, 10:07 UTC, preset แดง `1903718606535395`, ข้อความ "ขายของ ราคาเท่าช้อปปี้ 🛍️ ถ้าไม่คุ้ม ป้าบอกให้ 💕")
- ✅ feat(facebook): **โฮสต์มาสคอต + แนบรูป + ป้ายข้อความ** — mount `/static` ใน `main.py` (StaticFiles) → serve `backend/app/static/pa-khem-avatar.png` ที่ `https://…/static/pa-khem-avatar.png`; `facebook_intro.py` เพิ่ม `badge` (ป้ายข้อความ 🏷️ นำหน้า caption) + `image_url` (ตั้ง `INTRO_IMAGE_URL` override, default = RENDER_EXTERNAL_URL/static/…) ต่อทุกโพสต์; `cron.py` ส่ง `image_url` ไป `post_feed` (โพสต์ผ่าน `/photos`) — 407 passed — **deploy แล้ว** (`dep-da01t6gjo6nc73dhsi00` → live, commit `8c1672f`); ตรวจ URL รูปจริงแล้ว `/static/pa-khem-avatar.png` → 200 image/png
- ✅ feat(facebook): **ขยาย `facebook_intro.py` เป็นคลังแคปชั่น 12 แบบ หมุนเวียนไม่ซ้ำ** — จาก 3 โพสต์ตายตัว → 12 โพสต์ (เปิดตัว / วิธีเลือกของ / เตือนภัย / ของถูกvsของคุ้ม / อ่านรีวิว 1 ดาว / โปรโมชันจริงหรือหลอก / เรื่องขำ / ของใช้จริง / งบน้อยก็ช้อปได้ / ส่งฟรี / ของขวัญ / PDPA) — dedup เดิมใช้ index ต่อได้เลย (3 ตัวแรกโพสต์แล้วจะถูกข้าม → ตัวที่ 4-12 โพสต์ตามลำดับ) — **deploy แล้ว** (`dep-da01p5gjo6nc73dhjq60` → live, commit `f88f2b8`)
- ✅ feat(facebook): `post_feed` รองรับ `image_url` — โพสต์รูปผ่าน `POST /{page-id}/photos` (ใช้ post_id กลับ, message เป็น caption, image_url กับ link ใช้ร่วมกันได้น้อย → มี image_url จะไม่ส่ง link) + 3 เทสต์ (รวม 406 passed) — **deploy แล้ว** (`dep-da01fkjl550s73cchujg` → live 07:40 UTC)
- ✅ chore(render): ลด `FB_AUTO_POST_INTERVAL` 240 → **60 นาที** (ชั่วคราวเพื่อทดสอบ — render.yaml + Render env; ถ้าทดสอบเสร็จให้กลับเป็น 240)
- ✅ feat(facebook): **โพสต์สินค้าตัวแรกขึ้นเพจแล้ว** — trigger `/api/cron/facebook-post` 1 ครั้ง → สินค้า #937 "[3Pcs] Za Facial Mask Niacinamide Brightening" (`...531533443245`, 07:23 UTC); dedup `fbpost` บันทึกแล้ว → scheduler จะโพสต์ตัวถัดไปทุก 4 ชม.
- ✅ feat(orchestrator): เพิ่ม **log ตรวจสอบการทำงาน** — log แต่ละขั้น dispatch ใช้ worker ไหน (firecrawl/groq) + token usage ของ Claude ต่อ call + สรุป `claude_calls` (plan+review) / steps / workers ต่อคำตอบ (return dict มี `claude_calls` แล้ว)
- ✅ feat(orchestrator): Claude สงวนเป็น**บอส plan/review เท่านั้น** ไม่เป็น worker — งานกลาง/เฉพาะกิจทั้งหมดให้ groq + firecrawl (ลบ worker "claude" + MAX_CLAUDE_STEPS; worker=claude ในแผน → normalize เป็น groq)
- ✅ feat(orchestrator): เขียน `BOSS_SYSTEM` บริบทเต็มรูปแบบ (ROLE/CONTEXT/TEAM/WORKFLOW/VOICE) ให้ Claude บอสใหญ่รู้บริบทธุรกิจ + น้ำเสียงป้าเข็ม (เทสต์จริง: ตอบตาม persona + สโลแกน "ถ้าไม่คุ้ม ป้าบอกให้")
- ✅ feat(render): ตั้ง `ANTHROPIC_API_KEY` + `ANTHROPIC_MODEL=claude-opus-5` บน Render → orchestrator บอสใหญ่ใช้ Claude จริง (ทดสอบ key ใช้ได้แล้ว "สวัสดี"); deploy `dep-da00v6bl550s73cb86l0` → `live` (19 env vars)
- ✅ test(facebook): เพิ่มเทสต์ webhook verify + X-Hub-Signature **ครบกรณี** (`backend/tests/test_facebook_webhook.py` +8 เทสต์ → รวม 402 passed)
  (verify token: wrong mode / missing challenge / missing token → 403; signature: missing header / unknown algo / malformed → 400; sha1 fallback → 200)
- ✅ **Rollout Character-first + เปิดขายสินค้า** (วันนี้): push `3f88206` → ตั้ง `FB_POST_PRODUCTS=1` → deploy `dep-da00oalg1s2s73c2npe0` → `live`; ลบโพสต์เก่า "แนะนำตัวหน่อยค่าา" (`...241443245`) + reset dedup `fbintro` (1 แถว) → trigger `/api/cron/facebook-post` 3 ครั้ง = โพสต์ใหม่ 3 ตัว (เปิดตัวป้าเข็ม / วิธีเลือกของ / เตือนภัยช้อปออนไลน์) ขึ้นเพจแล้ว
- docs: เพิ่ม **คู่มือเจ้าของตั้ง Facebook webhook + เปิดแอป Live** (`docs/facebook-webhook-live-setup.md` — step-by-step พร้อมค่าจริง App/Page ID, Callback URL, Privacy URL, การทดสอบ + ตารางปัญหาที่เจอบ่อย)
- feat(brand): เพิ่ม**ป้ายชื่อ + สโลแกน**ลงมาสคอต SVG ทั้ง 3 ตัว
  (`assets/pa-khem-mascot-{1,2,3}.svg` + `preview.html` — ป้าย "ป้าเข็ม ขายของ" / "ถ้าไม่คุ้ม ป้าบอกให้" ที่อกผ้ากันเปื้อน)
- `f9ece4c` feat(brand): สร้าง**มาสคอตป้าเข็ม SVG 3 ท่า** + คู่มือภาพลักษณ์
  (`assets/pa-khem-mascot-{1,2,3}.svg` ตัวเดียวกันเปลี่ยนท่า/อุปกรณ์; `docs/pa-khem-visual-identity.md` จานสี/ฟอนต์/แปลง PNG)
- `c2cb0be` docs: เพิ่ม **ป้าเข็ม Brand Bible** (`docs/pa-khem-brand-bible.md`) — Character ก่อน Product
  (Positioning "ถ้าไม่คุ้ม ป้าบอกให้" + ตัวตน/บุคลิก/ภาษา/คำติดปาก + 5 Content Pillars + กติกา Say/Don't Say + KPI Phase 0)
- `229ac7f` fix(sheet): **รวมสคริปต์ Google ชีทเป็นไฟล์เดียว** — จัดการทั้งแชทลูกค้า + โพสต์จาก URL เดียว
  (`tools/sheet_posts_apps_script.gs` แทน `sheet_apps_script.gs` — dispatch ด้วย field `kind`; แก้ปัญหาผู้ใช้วางทับโปรเจกต์แชทเดิมจนแชทหยุดบันทึก)
- `41bbdf6` feat(facebook): **บันทึกโพสต์ทุกตัวลง Google ชีทอัตโนมัติ** (`POSTS_SHEET_WEBHOOK_URL`)
  (ไฟล์ใหม่ `tools/sheet_posts_apps_script.gs`; cron บันทึกทั้ง intro/product ที่โพสต์สำเร็จ; ไม่ตั้ง env = ไม่บันทึก)
- `3c4d311` feat(facebook): ปรับ auto-post เป็น **Phase 1 แนะนำตัวป้าเข็มก่อน → Phase 2 ขายสินค้าทีหลัง**
  (ไฟล์ใหม่ `app/services/facebook_intro.py` 3 โพสต์; cron โพสต์แนะนำก่อน → ขายเฉพาะเมื่อตั้ง FB_POST_PRODUCTS=1;
  scheduler ในตัวใน `main.py` โพสต์ทุก FB_AUTO_POST_INTERVAL นาที — ไม่พึ่ง cron-job.org)
- `38e9cde` feat(facebook): post_feed รองรับ `link` param — Facebook ดึง preview รูปสินค้าจากลิงก์อัตโนมัติ
  (แยก affiliate URL ออกจากข้อความมาเป็น link param → โพสต์เป็นการ์ดมีรูป; เทสต์จริงยืนยันแล้ว)
- `a5c0c7f` feat(facebook): เพิ่ม auto-post ลงเพจ Facebook — cron `/api/cron/facebook-post`
  (ไฟล์ใหม่ `app/services/facebook_poster.py` + เลือกสินค้าที่ยังไม่โพสต์ → caption Groq/fallback → feed; 4 เทสต์)
- `ef52a63` feat(persona): ปรับแก้ตัวตนป้าเข็มเป็นแม่ค้าออนไลน์ Shopee Affiliate ด้วย RCAO Framework (`persona.py`)
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

- ⏳ โพสต์ manual 1 อันบนเพจ (04:26, ไม่ใช่ของบอท — ลบด้วย page token ไม่ได้) รอเจ้าของลบเองถ้าต้องการ
- ⏳ แถว TEST ในชีท (แท็บ "FB Posts" มี "TEST 2" + "TEST post" · แท็บ "คำถามลูกค้า" มี "ทดสอบแชท" U_TEST) รอเจ้าของลบเอง

## 3. ขั้นตอนต่อไป

- ✅ **push + deploy เรียบร้อย** — deploy `dep-da00oalg1s2s73c2npe0` → `live` (commit `3f88206`); โพสต์แนะนำใหม่ Character-first 3 ตัวขึ้นเพจแล้ว (ลบโพสต์เก่า + reset dedup แล้ว)
- ✅ ตั้ง env บน Render: `POSTS_SHEET_WEBHOOK_URL` = URL Apps Script (ทดสอบ webhook แล้ว `{"ok":true}`)
- ✅ ตั้ง env บน Render: `FB_AUTO_POST_INTERVAL=60` (ทดสอบ 1 ชม.) + `FB_POST_PRODUCTS=1` → โพสต์สินค้าตัวแรกขึ้นแล้ว (manual 07:23) · scheduler โพสต์สินค้าตัวถัดไปทุก **1 ชม.** (tick ถัดไป ~08:40 UTC = 15:40 ไทย หลัง deploy 07:40; ⚠️ deploy แต่ละครั้งรีเซ็ต timer)
- ✅ ตั้ง env บน Render ครบ: FACEBOOK_APP_ID / APP_SECRET / VERIFY_TOKEN / PAGE_ACCESS_TOKEN + LINE_OA_URL (รวม 17 ตัวแล้ว)
- ⏳ **ตั้ง Webhook บน Facebook** (เจ้าของทำเอง — ตาม `docs/facebook-webhook-live-setup.md`): Callback URL `https://shopee-affiliate-bot-9e9n.onrender.com/api/webhooks/facebook` + Verify Token (ค่าใน `tools/render_env.local.json`) → Verify and Save → Add Subscriptions ติ๊ก `messages`
- ⏳ **เปิดแอปเป็น Live** (เจ้าของทำเอง — ตาม `docs/facebook-webhook-live-setup.md`): Basic Settings → App Domains + Privacy Policy URL → สลับ Development → Live (ตอนนี้ยัง Development → ลูกค้าทั่วไปทักเพจไม่ได้)

## 4. ไฟล์ที่ถืออยู่ / โดนแก้

<!-- ว่าง -->

## 5. หมายเหตุ

- CI: `.github/workflows/test.yml` รัน `pytest` + coverage gate 85% ทุก push/PR
- เทสต์ทั้งชุด: 450 passed
- บอทจริง healthy: `/health` → 200, `llm_provider=groq`, `database_url_configured=true` (URL: `https://shopee-affiliate-bot-9e9n.onrender.com`)
- Render env vars ตอนนี้มี 20 ตัว: DATABASE_URL, CRON_TOKEN, GROQ_API_KEY, LINE_CHANNEL_ACCESS_TOKEN/SECRET, LLM_PROVIDER, TAVILY_API_KEY, FIRECRAWL_API_KEY, SHEET_WEBHOOK_URL, FACEBOOK_APP_ID/SECRET/VERIFY_TOKEN/PAGE_ACCESS_TOKEN, LINE_OA_URL, FB_AUTO_POST_INTERVAL, FB_POST_PRODUCTS, POSTS_SHEET_WEBHOOK_URL, ANTHROPIC_API_KEY, ANTHROPIC_MODEL, ADMIN_LINE_USER_ID (ตั้งเป็น `Uc88eb...` = default เดิม — ทำให้ explicit + เพิ่มใน render.yaml sync:false)
- ฟีเจอร์ orchestrator ยังเป็นโมดูลเดี่ยว — ยังไม่ถูกเรียกจาก `line_bot.py` (ยังไม่มีผลกับลูกค้าจริง); บอสใหญ่ใช้ Claude จริง (ANTHROPIC_API_KEY ตั้งบน Render) + `BOSS_SYSTEM` บริบทเต็ม; Claude สงวนเป็นบอส plan/review เท่านั้น งานกลาง/เฉพาะกิจให้ groq + firecrawl (ไม่เผาโควตา Claude)
- facebook webhook: หน้าที่ตอนนี้ = แนะนำบอทป้าเข็ม (แชท) — ไอเดีย A (ค้นสินค้าในแชท) ถูกพักไว้- facebook auto-post: scheduler ในตัว (ไม่พึ่ง cron-job.org) — **หมุนเวียน 4 คลัง (slot = จำนวนโพสต์ fb* ทั้งหมด % 4)**:
  (0) แบรนด์ status=fbintro/fbbg = แนะนำตัว(มาสคอต 12 ตัว, ป้าย 🏷️ + รูป) ↔ ข้อความสั้นพื้นสี(8 ตัว, ≤130 ตัว, 8 สี) — สลับคู่/คี่; ทุกตัวลงท้ายลิงก์ `LINE_OA_URL`
  (1) สินค้า status=fbpost — เปิดเมื่อ FB_POST_PRODUCTS=1 (ลิงก์ affiliate เป็น link param)
  (2) คอนเทนต์โลก status=fbrss — ข่าว RSS → Groq เขียนเสียงป้าเข็ม + ลิงก์ LINE (feed: Beartai/Techhub/The Standard; override `RSS_SOURCES_JSON`; dedup sha1(guid))
  (3) ท้องถิ่น status=fblocal — ร้านอร่อย/ของฝาก/ของกิน Firecrawl search หมุน 77 จังหวัด × 3 หัวข้อ → Groq + ลิงก์ LINE (dedup sha1(url); Firecrawl ล้ม → ข้ามไม่พัง)
  → โพสต์สำเร็จทุกตัว → Google ชีท (POSTS_SHEET_WEBHOOK_URL); kind = intro / bg / product / rss / local
- ⚠️ **หมายเหตุ ownership:** `assets/` มีงานของคุณเจ้าของเอง (ลบ SVG มาสคอตเดิม + เพิ่ม PNG ใหม่ 2 ไฟล์ `1e8c7fdf-*.png` / `pa-khem-avatar.png`) — **ยังไม่ commit** ปล่อยไว้ให้เจ้าของ/ไม่ทับงานนี้
- Google ชีท: SHEET_WEBHOOK_URL (แชท) และ POSTS_SHEET_WEBHOOK_URL (โพสต์) ชี้ URL เดียวกัน = สคริปต์รวม 1 ตัว
  จัดการ 2 แท็บ (คำถามลูกค้า / FB Posts) — ตั้งใจให้เป็นแบบนี้ ไม่ใช่ bug; เทสต์ทั้ง 2 ทางผ่านแล้ว
- repo: commit ล่าสุด `f374d14` (โพสต์สินค้าแนบรูป) push แล้ว — deploy โค้ดจริงตัวล่าสุดคือ `dep-da05f561egvs73fur6hg` (live); DB migrate แล้ว: `products.image_url` (ALTER ADD COLUMN) — untracked/deleted ยังเหลือเฉพาะงานของคุณเจ้าของใน `assets/` (ดูหมายเหตุ ownership)
- ✅ ตัวกรองอักษรต่างภาษา (เคยค้าง): `app/services/text_cleaner.py` + เรียกใน `post_feed` — เจอคำ "دیزاین" จาก Groq แล้วตัดทิ้งก่อนโพสต์ (427 passed)
- ⚠️ **token Facebook:** `backend/.env` (local) หมดอายุแล้ว (Session expired 14 ส.ค.) แต่ **Render ยังใช้ token valid ตัวอื่น** (`EAAR9k...PCbT`) — production โพสต์ได้ปกติ; ถ้าจะตรวจเพจ/เทสต์จาก local ต้องดึง token จาก Render (Management API GET env-vars) มาใส่ชั่วคราว (ยังไม่ได้ sync ลง `.env` — รอเจ้าของยืนยัน)
