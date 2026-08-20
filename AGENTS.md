# AGENTS.md

## Safety, Conflicts, and Rollback Rules (กฎความปลอดภัยและการกู้คืนโค้ด)

เอเจนต์ AI ทุกตัวที่จะทำการแก้ไขระบบต่อจากนี้ ต้องทำตามกฎเหล็กความปลอดภัย 4 ข้อนี้อย่างเคร่งครัด:

1. **ห้าม Push โค้ดที่พังขึ้น GitHub เด็ดขาด (Never Push Broken Code)**:
   - ก่อนจะทำการ `git commit` หรือ `git push` ทุกครั้ง ต้องทดสอบรันโค้ดเครื่อง Local ก่อนเสมอ
   - หากเกิดข้อผิดพลาดในการทดสอบหรือเจอบั๊ก ห้ามทำการ push โค้ดชุดนั้นขึ้น GitHub

2. **การล้างข้อมูลเพื่อกลับสู่สถานะเสถียรล่าสุด (Git Reset & Clean)**:
   - หากพบว่าโค้ดมั่วหรือมีเอเจนต์หลายตัวเขียนโค้ดทับซ้อนกันจนระบบเสียหาย ให้ทำการล้างไพ่กลับสู่จุดเสถียรบน GitHub ล่าสุดทันทีโดยใช้คำสั่ง:
     ```bash
     git reset --hard HEAD && git pull origin main
     ```

3. **ขั้นตอนการย้อนกลับบน Render (Production Rollback)**:
   - หากพบว่าเว็บล่มบน Production (Render) ให้ดำเนินการแจ้งแอดมินหรือใช้ Render API สั่ง **Rollback** ไปยังประวัติการ Deploy เวอร์ชันสีเขียว (`Live`) ตัวก่อนหน้าทันที

4. **หลีกเลี่ยงการ Commit คุกกี้และข้อมูลส่วนตัว (Secret Privacy)**:
   - ห้ามทำการแอดไฟล์ `fb_cookies.json` หรือไฟล์ `.env` ที่มีข้อมูลคุกกี้เซสชันของแอดมินเข้าสู่ระบบ Git และต้องมีรายชื่อพวกมันอยู่ใน `.gitignore` เสมอ

## Skills Index (บังคับอ่านก่อนทำงาน — ใช้สกิลนำทางทุกฟีเจอร์)

สกิลอยู่ใน `.agents/skills/<name>/SKILL.md` — ก่อนแตะฟีเจอร์ใด อ่านสกิลของฟีเจอร์นั้นก่อน (มีกับดักที่เจอจริง + ไฟล์ + เทสต์):

**บอท LINE:** `line-bot-core` (routing/ค้นหา/ราคา/วัย/คู่มือ/wismo/PDPA) · `line-product-cards` (การ์ด Flex) · `line-user-memory` (จำไว้/prefs/tone) · `line-campaigns-quota` (แจ้งราคาลง/re-engage/daily-report/quota)

**AI:** `llm-providers` (multi-key failover) · `ai-content-generation` (สคริปต์/วิเคราะห์/template + สัญญา hashtags) · `demand-radar` (radar V1 + guards) · `facebook-page-automation` (post_feed/Messenger/RSS/local caption) · `web-search` (Tavily+Firecrawl circuit breaker)

**API/Admin:** `products-and-links` (สินค้า API + link policy) · `admin-dashboard` (/admin + cookie) · `cron-jobs` (ทุก cron + CRON_TOKEN)

**Dev tools:** `product-pipeline` (import-csv/analyze) · `mcp-servers` (pkh_mcp + shopee MCP) · `hermes-ai` (สมองกลเรียนรู้ตลาด) · `content-backfill` (เติมคอนเทนต์ template) · `generate-ai-content` (เติมคอนเทนต์ Groq) · `promo-caption-rotation` (แคปชันอัตโนมัติ+หมุนภาพโปสเตอร์)

**Deploy/Shopee:** `render-supabase-deploy` (ขึ้น production) · `shopee-affiliate` (ลิงก์ผ่านโทรศัพท์) · `facebook-app-config` (ตั้งค่า Meta App)

## Deployment (Render + Supabase)

- `backend/app/db.py` auto-converts `postgres://` → `postgresql://` (SQLAlchemy v2 rejects the former); Supabase and many cloud providers return `postgres://` URLs. Postgres pools use `pool_pre_ping=True` and `pool_recycle=300` — keep these when touching engine setup.
- On Render, Supabase **must** use the Transaction Pooler URL (port 6543, `*.pooler.supabase.com`), never the Direct Connection — direct connections fail on Render because of IPv6.
- `render.yaml` must declare `rootDir: backend` because its build/start commands (`pip install -r requirements.txt`, `uvicorn app.main:app --port $PORT`) only resolve when the working dir contains `requirements.txt` and the `app/` package, which both live under `backend/`. render.yaml ↔ `backend/requirements.txt` ↔ `backend/app/` must move together.
- Env vars marked `sync: false` in `render.yaml` (DATABASE_URL, LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, GEMINI_API_KEY, GROQ_API_KEY, ANTHROPIC_API_KEY, ANTHROPIC_MODEL, CRON_TOKEN, ADMIN_DASHBOARD_PASSWORD) are set manually in the Render dashboard; `LLM_PROVIDER=groq` is baked in. Admin web dashboard = `GET /admin` (ล็อกอินรหัสผ่าน → HMAC cookie `pkh_admin` 7 วัน) + `GET /api/admin/*` (stats / products list+filter / update / delete — ต้องมี cookie; 401 ถ้าไม่มี) ใน `app/api/admin_dashboard.py` + `app/static/admin.html` (ไฟล์เดียว vanilla JS, ไม่มี build step). รหัสผ่าน = env `ADMIN_DASHBOARD_PASSWORD` (ถ้าไม่ตั้ง fallback เป็น `CRON_TOKEN`; ไม่ตั้งทั้งคู่ → dashboard ปิด 503). ตัวเลขสถิติ query จากตารางจริง (products/contents/chat_logs/users) ไม่มีตัวเลขมโน; `sellable` = link_status ok + sales_count ≥ MIN_SALES. การลบสินค้าผ่าน dashboard cascade ลบ contents/product_analysis. `CRON_TOKEN` locks `POST /api/cron/*` (`check-links` / `analyze` / `refresh-prices` / `daily-report` / `re-engage`) — without it those endpoints run unauthenticated (like `/health`); with it, calls need `?token=...` (401 otherwise). `refresh-prices` ยังบันทึก `price_history` + แจ้งราคาตก (ลด ≥ `PRICE_DROP_PCT` default 5%) ให้ลูกค้าที่เคยสนใจหมวดนั้น; `re-engage` push ของใหม่หมวดที่เคยสนใจให้ลูกค้าเงียบ ≥7 วัน (จำกัด limit/รอบ กันสแปม). Current token is in `backend/.env` (gitignored) — paste the same value in the Render dashboard. The Render CLI has no env-var subcommand — env vars can only be set in the dashboard (or Management API). Groq is OpenAI-compatible (`base_url=https://api.groq.com/openai/v1`), default model `openai/gpt-oss-120b` (override with `GROQ_MODEL`); provider values are `gemini` | `openai` | `groq` | `anthropic`. `GROQ_API_KEY` supports MULTIPLE keys comma-separated — `app/services/llm_clients.py` round-robins across them and failovers to the next key when one errors (401/429); never hit Groq with raw `urllib` (Cloudflare 1010 blocks it), always use the `openai` library. Anthropic (Claude) ใช้ OpenAI-compat endpoint (`base_url=https://api.anthropic.com/v1/`), default model `claude-opus-5` (override `ANTHROPIC_MODEL`) — ไม่ต้องติดตั้ง anthropic SDK; ข้อจำกัด: `response_format` ถูก ignore ต้องสั่งให้ model คืน JSON ล้วนใน prompt เอง (`llm_clients.py` มี `anthropic_clients()` หมุนเวียนหลาย key เหมือน Groq). Render free tier spins down after ~15 min of inactivity — `/health` exists solely to be pinged by cron-job.org every 10 min to keep the bot warm. `app/main.py` also runs a **self keep-alive loop** (lifespan task pings its own `RENDER_EXTERNAL_URL/health` every 10 min via httpx) so the service stays warm even if cron-job.org stops; `KEEP_ALIVE_INTERVAL` overrides the 600s default, and the loop auto-disables when `RENDER_EXTERNAL_URL` is unset (dev).
- Render CLI on Git Bash mangles path-like args: `--health-check-path /health` becomes `C:/Program Files/Git/health`. Prefix the command with `MSYS_NO_PATHCONV=1` for any flag whose value starts with `/`. Changing the health check path only takes effect on the **next deploy** — the health checker reads the path from the deploy config, so an in-flight deploy must finish (or be redeployed) before the checker hits the new path.
- The live service is `srv-d9tknl2d0e5s739ebo40` at `https://shopee-affiliate-bot-9e9n.onrender.com` (repo `g81393878-bit/shopee-affiliate-bot`, not `watt29/...` — that repo doesn't exist; the local repo had no remote, `gh` CLI is authenticated as `g81393878-bit` with `repo` scope).
- One-click deploy script: `.\deploy_to_github.ps1 -Token <ghp_...>` creates/pushes `watt29/shopee-affiliate-bot`; token needs the `repo` scope. The full walkthrough lives in `.agents/skills/render-supabase-deploy/SKILL.md` — read it before touching deployment.
- Supabase free-tier projects **auto-pause after ~7 days of inactivity**; a paused project returns 400 `"Cannot reset password for non-active projects"` on the Management API. Restore with `POST /v1/projects/{ref}/restore` (Bearer = `sbp_...` access token), poll `GET /v1/projects/{ref}` until `status: ACTIVE_HEALTHY` (~2 min), then reset the DB password with `PATCH /v1/projects/{ref}/database/password` `{"password": ...}`.
- `supabase link` writes `supabase/.temp/` containing `pooler-url` (embeds the DB password) and `project-ref` — the folder is gitignored, never commit it. The linked project is `usqhvujqmnxqrdoovvnp` ("g81393878-bit's Project", created 2025-08-04, not named `shopee-affiliate`); its DB password was reset and stored at `~/.supabase/db-password.txt`.
- **Render Management API**: credential = API key แบบ no-expiry ใน env `RENDER_API_KEY` (ตั้งแล้วทั้ง Windows user env และ `~/.bashrc` — เปิด terminal ใหม่ถึงจะ inherit; เช็คด้วย `echo ${RENDER_API_KEY:0:4}` ต้องได้ `rnd_`); helper อ่านสำรองจาก `~/.bashrc` ก่อน แล้ว fallback = `~/.render/cli.yaml` บรรทัด `    key:` (CLI token หมดอายุเป็นระยะ ~6 วัน — refresh ด้วย `renderctl whoami` / `renderctl login`; ใช้ `sed -n 's/^[[:space:]]*key: //p'` ไม่งั้นได้ค่าว่าง). helper ครบจบใน `tools/render_set_env.py` (list/get/set/unset/diff/deploy — อ่าน `RENDER_API_KEY` → `~/.bashrc` → fallback cli.yaml). `GET /services/{id}/env-vars` ปัจจุบันคืน `envVar` เป็น dict `{key,value}` แล้ว (เวอร์ชันเก่าเคย double-encode เป็น string แบบ python-dict — `decode_env_var()` รองรับทั้งสองแบบ). `PUT /services/{id}/env-vars/{key}` upsert ทีละตัวไม่แตะตัวอื่น (ห้าม PATCH envVars ทั้งชุด — semantics แทนที่ทั้งหมด). ตั้ง/ลบ env แล้วต้อง trigger deploy (`POST /services/{id}/deploys`) ถึงจะมีผล.
- **เทสต์กับข้อมูลจริง (local)**: `backend/.env` เป็น SQLite — ต้อง export `DATABASE_URL="postgresql://postgres.usqhvujqmnxqrdoovvnp:<pw>@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres"` (pw = `~/.supabase/db-password.txt`); สคริปต์เทสต์ใน `tools/_*.py` ต้องมีทั้ง `backend/` และ `backend/app/` ใน sys.path (db.py/models.py อยู่ app/, line_bot import แบบ `app.…`). `openpyxl` ติดตั้งเฉพาะ venv ท้องถิ่น (ไม่เข้า requirements.txt — ใช้กับ export xlsx ฝั่ง dev เท่านั้น).

## LINE Bot / Webhook

- The real webhook endpoint is `POST /api/webhooks/line` (router mounted at `/api` + prefix `/webhooks` + route `/line`). The old deploy walkthrough documents `/api/webhook` (singular) — that URL is wrong and breaks LINE webhook verification; use the plural path.
- Architecture: LINE → Render FastAPI (webhook URL points **directly** at `https://shopee-affiliate-bot-9e9n.onrender.com/api/webhooks/line`) → Supabase → Groq. The old Cloudflare Worker hop (`throbbing-dust-a90b.regency2919.workers.dev`) was **removed** — its `FASTAPI_URL` pointed at a dead `loca.lt` tunnel that silently dropped every LINE event while still returning 200 to LINE. If the Render URL ever changes, only the LINE webhook URL needs updating.
- `line_bot.py` falls back to mock tokens when `LINE_CHANNEL_ACCESS_TOKEN`/`LINE_CHANNEL_SECRET` are unset, so the app starts fine in dev but the bot silently won't work — env vars are required in any real deployment.
- **PDPA / ข้อมูลลูกค้า:** เก็บเฉพาะชื่อ + LINE userId ใน `users` และข้อความ/ประเภทคำถามใน `chat_logs` (เก็บ 90 วัน — `log_chat()` ลบของเก่าให้อัตโนมัติทุกครั้งที่เขียน; คำสั่งลบ "ลบข้อมูลฉัน" ลบ user + logs + `user_preferences` ทันทีและไม่ log คำสั่งลบเอง). Account Memory (แบบ Amazon): ลูกค้าพิมพ์ "จำไว้ …" → เก็บหมวด/โน้ตในตาราง `user_preferences` (ตารางแยก — **ห้าม**เพิ่มคอลัมน์ใน `users` เพราะคือ `auth.users` ของ Supabase มี `preferences` ของ auth อยู่แล้ว) → `_customer_categories()` ใช้ pref ก่อน chat_logs → "มีอะไรใหม่"/แคมเปญ/ของใกล้เคียง แนะนำตามที่ลูกค้าระบุเอง; "ป้าเข็มจำได้ไหม" อ่านคืน. หน้า `/privacy` เป็นนโยบาย PDPA (ลิงก์ส่งใน follow welcome). ลูกค้าทวงถามพัสดุ (คำว่า สั่งแล้ว/เลขพัสดุ/ของถึงยัง...) → `is_wismo()` ตอบวิธีตรวจสั่งซื้อบน Shopee (เราเป็นนายหน้า ไม่มีเลขพัสดุเอง). เจ้าของร้าน = `ADMIN_LINE_USER_ID` (env, default `Uc88eb...`) เห็นข้อมูลแอดมินในการ์ด (ค่านายหน้า/คะแนน/Hook) ลูกค้าเห็นการ์ดสะอาด.
- **เขียนลง Google ชีทอัตโนมัติ**: env `SHEET_WEBHOOK_URL` = URL ของ Apps Script Web app (`tools/sheet_apps_script.gs` — วางใน script.google.com, Deploy→Web app→Anyone) → `log_chat()` push แถวทุกข้อความ (เวลา/ผู้ใช้/ข้อความ/ประเภทไทย/หมวด/ตอบแบบ) ใน **daemon thread** เพราะ LINE ตอบต้องไม่รอ Google; Apps Script ลบของเก่า >90 วัน + รับ `{"action":"delete_user",...}` ลบแถวของคนที่สั่ง "ลบข้อมูลฉัน" (PDPA ครบ 2 ที่); ไม่ตั้ง env = โค้ดเดิมทำงานปกติ
- On this machine, `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_CHANNEL_SECRET`, and `GROQ_API_KEY` are ALSO set as Windows **user** environment variables — and `load_dotenv` never overrides existing env vars, so stale values in the Windows env silently beat `backend/.env`. When credentials change, update BOTH places (or `[Environment]::SetEnvironmentVariable(...,'User')`). Current valid creds: LINE token + secret `feab701d...` (stored in `.env`), Groq `gsk_LzxL...`.

## Facebook Webhook / Messenger (Meta App)

- webhook มี 2 ชั้น ต้องครบทั้งคู่: **(1) App-level callback URL** และ **(2) Page subscription** — แก้ทั้งคู่ผ่าน Graph API ได้ ไม่ต้องเข้าหน้า Dev Center: `POST /{app_id}/subscriptions` (object=page, callback_url+verify_token), `POST /{page_id}/subscribed_apps` (fields=messages,messaging_postbacks,...), `DELETE /{app_id}/subscriptions` ล้าง object ที่เลิกใช้. บอทเงียบทั้งที่ callback ถูก = มักลืมชั้น (2). Pre-flight จำลอง verify ก่อนยิง: `GET /api/webhooks/facebook?hub.mode=subscribe&hub.verify_token=…&hub.challenge=…` ต้องคืน challenge เป็น plain text.
- **สลับ Development→Live ไม่มี API** — ต้องกดใน `developers.facebook.com/apps/.../settings/basic/` เอง. ยืนยัน Live จริงโดยให้**บัญชีธรรมดา** (ไม่ใช่ admin/tester ของแอพ) ทักเพจ — webhook ยิงให้ non-admin เฉพาะตอน Live. `App Domains` เอา host เปล่า (ไม่มี https:///path) และต้อง `onrender.com` (มี `on` นำหน้า — ผู้ใช้พิมพ์ `render.com` ผิดบ่อย).
- Endpoint = `GET/POST /api/webhooks/facebook` ใน `backend/app/api/facebook_bot.py` (verify challenge + `X-Hub-Signature-256`); คู่มือเก่าอาจเขียน `/webhook` ผิด. Messenger reply ใช้ page access token (Send API); long-lived token หมดอายุ ~60 วัน ต้อง refresh.

## Search & Thai text (ภาษาไทย — กับดักที่เจอจริง)

- **สระอำในคลังเก็บได้ 3 รูปแบบ** (U+0E33 เดี่ยว / U+0E4D+U+0E33 / U+0E4D+U+0E32) — NFC **ไม่**รวมให้ (เป็น compat form) ต้องแทนที่ด้วยมือใน `_nfc()`: `\u0e4d\u0e32`→`\u0e33` และ `\u0e4d\u0e33`→`\u0e33` ไม่งั้น "กระติกน้ำแข็ง" ค้นไม่เจอ (DB เก็บแบบแยก "น้ําแข็ง")
- **regex ราคาห้ามใช้ `\d*` (เลขว่างได้)**: "งบ" ไปแมตช์กลางคำ "หูฟัง**ง**+**บ**ลูทูธ" (ขอบคำติดกัน) → ตัดทิ้งเหลือขยะ "หูฟัลูทูธ" → ค้น 0. เงื่อนไขราคาต้องมีตัวเลขจริงตามหลัง; คำ "ราคา/งบ" แบบไม่มีเลขต้องมีเว้นวรรค/ต้นประโยคก่อน (ดู `PRICE_PHRASE_RES` 4 แพตเทิร์น)
- **ตัดคำนำหน้า (FILLER_PREFIXES) ห้ามตัดกลางคำไทย**: "ขอ" ตัด "ขอ**ง**เล่นแมว" เหลือ "งเล่นแมว", "มี" ตัด "มีด" เหลือ "ด" — ตัดต่อเมื่อส่วนที่เหลือขึ้นต้นด้วย category keyword ที่รู้จักเท่านั้น
- **คำกรองคู่มือ (BOT_MANUAL_PHRASES) ตรวจด้วยซับสตริง — ระวังชนกับชื่อสินค้า**: ห้ามเพิ่มคำสั้น/คำอังกฤษสามัญ (ai/key/หลับ/สำรอง/ฟรี) เพราะเจอในชื่อจริง (หูฟัง ai, KEYboard, หมอนหลับสบาย, แบตสำรอง, ส่งฟรี) → ต้องใช้คำเฉพาะไทย (คีย์/เซิร์ฟเวอร์/ฐานข้อมูล...)
- **คีย์เวิร์ดคู่มือห้ามมีเว้นวรรค + อังกฤษต้องตัวพิมพ์เล็ก**: `is_bot_manual_request`/`bot_manual_reply` strip ช่องว่าง+lowercase ทั้งข้อความและคีย์ — ใช้ "ไลน์oa"/"lineoa"/"richmenu" ไม่ใช่ "LINE OA"; เรียง section ถูกต้อง: "โค้ดส่วนลด" (คูปอง) ต้องอยู่ก่อน "โค้ด" (GitHub) ไม่งั้นตอบผิดหัวข้อ
- **สัญญาณเดาโทนวัย (YOUTH_SIGNALS/ELDER_SIGNALS ใน line_bot.py) ตรวจด้วยซับสตริง — ระวังชนชื่อสินค้าเหมือน BOT_MANUAL_PHRASES**: เจอจริงจากคลัง 1,319 สินค้า — "ตา" ชน แว่น**ตา**/**ตา**มหลักสรีรศาสตร์ (64 ตัว), "ยาย" ชน น้ำ**ยาย้อม**ผม (8 ตัว), "รบกวน" ชน ลด**เสียงรบกวน** (51 ตัว — หูฟัง!), "งับ" ชน ระ**งับ**กลิ่น, "ฟิน" ชน มาดาม**ฟิน**/**ฟิน**ิชแมทต์ — ลูกค้าค้นชื่อสินค้าตรงๆ แล้วโดน tag วัยผิด**ถาวร**ใน `user_preferences.tone` (เดาแล้วจำ ไม่มีทางลบเอง) → ก่อนเพิ่มสัญญาณใหม่ทุกครั้ง ให้เทียบกับ `SELECT name FROM products WHERE link_status='ok'` (หรือ query คลังจริง) แล้วค่อยใส่

## Product link policy (เด็ดขาด)

- สินค้าทุกตัวที่เข้าระบบ**ต้องมีลิงก์ affiliate ที่ตรวจผ่านแล้วเท่านั้น**: `link_status` ในตาราง `products` (ok | dead | suspect | unknown | none) — ตรวจด้วย `backend/app/services/link_checker.py` (GET ลิงก์สั้น + ดูหน้า "ไม่พบสินค้า" + redirect ไปหน้า `/opaanlp/`/item = OK, HTTP 400/404/410 = DEAD)
- **บอท LINE ตอบเฉพาะ `link_status == 'ok'`** (`line_bot.py` filter ทั้ง search และ หมุนเวียน) — ลิงก์เสีย/ยังไม่ตรวจ ไม่เด้งขึ้นหน้าลูกค้าเด็ดขาด
- API `POST/PUT /products` ตรวจลิงก์ก่อนบันทึก (ไม่ OK → 400) และ `tools/product_pipeline.py import-csv` ตรวจก่อน insert (ข้ามตัวไม่ผ่าน) — `check-links` อัปเดตสถานะลงตาราง (รันเป็นระยะ; `--delete` ลบตัว DEAD)
- **DB-level hard rule (ลิงก์ปลอมห้ามเข้าบอทเด็ดขาด)**: `Product.affiliate_url` ต้องเป็นลิงก์สั้น `s.shopee.co.th` เท่านั้น — SQLAlchemy event ใน `app/models.py` (`before_insert`/`before_update`) raise `ValueError` กันลิงก์ปลอมอย่าง `https://shope.ee/...` (กดแล้ว 404) แม้ insert ตรง DB/เทสต์ก็ไม่ผ่าน; `before_update` ตรวจเฉพาะเมื่อ `affiliate_url` ถูกแก้จริง (อัปเดตราคา/รูป/status ของแถว legacy ลิงก์ไม่ valid ยังผ่านได้); helper กลาง = `is_valid_shopee_affiliate_url()` ใน `app/services/link_checker.py` (ใช้ทั้ง DB rule, `product_matcher.py` และ guard หน้า `post_feed` ใน `cron.py`); เทสต์ fixture ที่ seed สินค้า mock ต้องใช้ URL รูปแบบ `s.shopee.co.th` + ข้ามเมื่อ `DATABASE_URL` เป็น postgres (กัน mock หลุดเข้า production)

## คอนเทนต์สินค้า (contents)

- "ยังไม่มีคอนเทนต์" ในแดชบอร์ด = สินค้าที่ไม่มีแถวในตาราง `contents` (สคริปต์ hook/problem/solution/cta/caption) — เติมโดย cron `analyze` (Groq, ทีละ 30 ตัว/2 ชม., เรียง ai_score สูงก่อน). โพสต์ FB **ไม่อ่าน** `contents` (gen caption สดผ่าน Groq + template fallback); `contents.hook` ใช้ทำการ์ดสินค้า LINE เท่านั้น
- เติมแบบไม่ใช้ LLM (เจ้าของสั่ง "ไม่ต้องใช้ Groq"): `build_template_script()` ใน `app/services/ai_generator.py` (template เสียงป้าเข็ม) + `tools/_backfill_content_template.py` ต่อ Supabase ตรงเขียน template ลง contents

## Facebook Automation & Social Demand Radar (ป้าเข็ม)

- **การวิเคราะห์ Intent:** ห้ามสร้างเพียงบอทตรวจจับคีย์เวิร์ด (Keyword Bot) เฝ้าดูคำตายตัว การตรวจจับความต้องการซื้อ (Demand) ต้องใช้ AI วิเคราะห์เจตนา (Intent), คะแนนความสนใจซื้อ (Demand Score 0-100), ความเร่งด่วน (Urgency) และงบประมาณ จากนั้นคัดกรองเฉพาะโพสต์ที่มี Demand Score >= 70
- **V1 เปลี่ยนเป็น auto-post 100% — LINE alert ปิดแล้ว:** `POST /api/admin/facebook-radar/leads` พอ demand ≥70 → `post_feed()` ขึ้นเพจป้าเข็มทันที (response `alerts_sent=0`). โพสต์ promo ติดตั้งบอท (ไม่จับคู่สินค้าแล้ว — `matched_product_id=None`). Guards: `RADAR_MAX_DAILY_POSTS` (default 5) + `RADAR_CATEGORY_COOLDOWN_HOURS` (default 24) — นับทั้ง `facebook_demand_events (posted,sent,pending)` + `CampaignLog (fbpost, fbpost_pending)` เพื่อกันโพสต์ซ้ำ/หมวดถี่เกินข้าม flow กับ cron rotation (ดูหัวข้อ Coordination ด้านล่าง). บันทึก Sheets ผ่าน `POSTS_SHEET_WEBHOOK_URL` (`kind='radar'`)
- **Coordination การโพสต์ (ใครสั่ง/ตรวจก่อน/ไม่พร้อมแจ้ง):** โพสต์เพจมี 2 ตัวสั่ง — radar (lead→demand≥70→post) + cron rotation (scheduler ในตัว `main.py` ตรวจทุก 60 วิ ครบ `FB_AUTO_POST_INTERVAL` นาทีไหม; **ห้าม**เอา `/cron/facebook-post` ลง cron-job.org = โพสต์ซ้ำ) — ทุกตัวยิงผ่าน `post_feed()` จุดเดียว. ก่อนยิงต้อง `preflight_ready()` (token ตั้ง/ใช้ได้ cache 1 ชม. — เฉพาะ prod postgres ถึงบังคับ/แจ้ง) → ไม่พร้อม = ข้าม + `notify_owner_once()` (LINE แจ้งเจ้าของ throttle 6 ชม./key in-memory); error รุนแรง (OAuth หมดอายุ/#(200)/rate-limit) → แจ้งเจ้าของด้วย (`classify_post_error`). Cooldown หมวดข้าม flow ต้องนับทั้ง 2 ตาราง: `CampaignLog status in (fbpost, fbpost_pending)` + `demand_event status in (posted,sent,pending)`; cron จอง `fbpost_pending` ก่อนยิง (สำเร็จ→fbpost / ล้ม→ลบการจอง) — `fbpost_pending` ห้ามนับเป็นโพสต์สำเร็จใน `_auto_post_due`/slot count; `_AUTO_POST_LOCK` กัน concurrent; `_post_next_*` โพสต์ล้มต้องลองตัวถัดไป (ห้าม return ทันที = rotation ติดตาย). ดู `docs/facebook-posting-workflow.md` + skill `facebook-post-coordination`
- **บอทลบโพสต์ปลอมอัตโนมัติ (fake-post watcher):** mock poster "หูฟังลิงก์จริง" (ข้อความตรงกับ test fixture `test_demand_radar_ai.py` — สคริปต์ local รัน flow radar กับสินค้า mock แล้วยิงตรงขึ้นเพจด้วย page token จริง, ไม่มี process ใน repo) โพสต์ลิงก์ปลอมซ้ำ ๆ → `main.py` `facebook_fake_post_watcher()` ตรวจทุก `FB_FAKE_POST_CHECK_SECONDS` วิ (default 300) → `sweep_fake_posts()` (cron.py) ลบ shope.ee/lazada/s.shopee.co.th รหัสปลอม/ไม่ใช่ลิงก์ในคลัง — ทำงานเองไม่ต้องรอครอน 6 ชม.; เปิดเมื่อ prod (postgres) + มี FB token เท่านั้น; ลบได้ → แจ้งเจ้าของ (`fb_fake_post_deleted`, throttle 6 ชม.) = สัญญาณว่า mock poster ยังรันอยู่
- **วงจรเรียนรู้ Data Flywheel:** ข้อมูลเหตุการณ์ต้องแยกตารางชัดเจนระหว่างโพสต์ดิบ (`facebook_detected_leads`), ข้อมูลการวิเคราะห์ความต้องการ (`facebook_demand_events`) และการตัดสินใจส่งข้อมูลของแอดมิน (`lead_actions`) เพื่อบันทึกประวัติ Conversions (การกดตอบ, การคลิก, และยอดการซื้อจริง) สำหรับนำไปใช้เทรนหรือปรับปรุงโมเดล AI แนะนำดีลในอนาคต

## MCP / Dev Tools

- `tools/pkh_mcp_server.py` = MCP server (Python SDK) expose admin API 10 tools (สินค้า/สถิติ/เรดาร์ feed) — auth ผ่าน cookie: `POST /admin/login` เอา `pkh_admin` แล้วแนบทุก request (`require_admin` ฝั่ง dashboard รับเฉพาะ cookie, `require_admin_auth` ฝั่ง radar รับ token ด้วย). `mcp` dep ติดตั้งเฉพาะ venv ท้องถิ่น ไม่เข้า requirements.txt
- **MCP SDK v2 ≠ FastMCP เก่า**: `pip install mcp` ให้ v2 — `from mcp.server.mcpserver import MCPServer` (ไม่มี `mcp.server.fastmcp`). Single Pydantic model param ถูก wrap เป็น nested key (ไม่ flatten) → ใช้ flat params `Annotated[str, Field(description=...)]` ให้ input schema สะอาด

## Git & Repo Hygiene

- `.gitignore` blocks drivers, `*.db`, `.env`, `*.zip`, `*.ipynb`. Pattern gap: `geckodriver*/` only matches directories, so a root `geckodriver.exe` keeps appearing as untracked in `git status` (chromedriver.exe is explicitly ignored) — don't stage it.

## บทบาท & ความรับผิดชอบของ AI (กัน AI ตัวอื่นสับสนบทบาท)

AI ที่ทำงานใน repo นี้มีบทบาทเดียว: **วิศวกรผู้ช่วย** — แก้โค้ดให้ถูกตามที่ user สั่ง แล้วบันทึกงานให้ครบ (commit + HANDOFF) ไม่ใช่เจ้าของร้าน/ผู้มีอำนาจตัดสินใจเรื่อง production

**ต้องทำเสมอ:**
- เริ่มงาน: อ่าน `AGENTS.md` + `HANDOFF.md` + ตรวจ `git status` (ตาม Multi-Agent Handoff Protocol ด้านล่าง)
- ปิดงาน: รันเทสต์ผ่าน (`cd backend && .venv/Scripts/python.exe -m pytest tests/ -q`) แล้ว commit แยกงาน atomic
- บันทึกงาน: อัปเดต `HANDOFF.md` ทุกครั้ง (งานเสร็จ = อัปเดตสถานะ/ล้าง, งานค้าง = เขียนรายละเอียด) แล้ว commit ด้วย
- ไม่ทิ้งขยะ: ไฟล์ชั่วคราว `_*` (debug/จำลอง) ลบก่อน commit

**ห้ามทำเอง (ต้องให้ user สั่ง/อนุมัติก่อน):**
- ❌ `git push` และทุกอย่างที่ deploy ขึ้น production (Render / Supabase / LINE webhook)
- ❌ รันสคริปต์/คำสั่งที่แตะฐานข้อมูลจริง, เปลี่ยน env/credential, ลบ/แก้ข้อมูลลูกค้า
- ❌ คำสั่ง irreversible ที่อาจทับงานคนอื่น (`git reset --hard`, `rm -rf` นอกโปรเจกต์)

**ขอบเขตการตัดสินใจ:**
- ทำเองได้: แก้ bug, เขียน/แก้ test, refactor, docs, commit ในเครื่อง (ยังไม่ push)
- ต้องถามก่อน: push, deploy, แตะ production, เขียนทับ/ลบงานที่ไม่ใช่ของตัวเอง
- เสนอแทนทำ: feature ใหญ่/นอก request → เขียนเป็น follow-up ให้ user เลือก

## Multi-Agent Handoff Protocol (บังคับ — ทุก AI ที่ทำงานใน repo นี้ต้องทำตาม)

AI หลายตัว (Codebuff / Claude Code / Cursor …) อาจสลับกันทำงานใน checkout เดียวกัน — บริบทของแต่ละตัวเริ่มว่าง ไม่รู้ว่าใครทำอะไรค้างไว้ กฎนี้กันการแก้ทับกันจนโค้ดพัง:

1. **ก่อนเริ่มงานเสมอ: อ่าน `HANDOFF.md` (ถ้ามี) + ตรวจ `git status`** — ตัวอย่างคำสั่งที่ต้องรันก่อนเริ่มงานทุกครั้ง:

   ```bash
   git status --short && git log --oneline -5   # ดู working tree + commit ล่าสุด
   cat HANDOFF.md 2>/dev/null || echo "ไม่มี HANDOFF.md — ไม่มีงานค้างที่บันทึกไว้"
   ```

   ถ้า working tree ไม่สะอาด (มี modified/untracked ที่ไม่รู้จัก) หรือ HANDOFF.md มีสถานะ "มีงานค้าง" ห้ามเริ่มแก้ไฟล์ ให้ถาม user ก่อนว่าของค้างคืออะไร ใครเป็นคนทำ จะ commit หรือ revert
2. **จบงานแต่ละชิ้น = commit ทันที** — ห้ามทิ้งงานค้างข้าม session เด็ดขาด งานที่ยังไม่ commit คือ "ของใครก็ไม่รู้" ที่ AI ตัวถัดไปอาจทับ
3. **Commit แยกตามงาน (atomic)** — แต่ละ commit ครอบ 1 งาน (เช่น แก้บั๊กค้นหา = 1 commit, เพิ่ม docs = 1 commit) อย่าใช้ `git add -A` อย่า stage ไฟล์ที่ไม่เกี่ยวกับงาน (เช่น `geckodriver.exe`, `chat_logs_export.csv`)
4. **ห้ามรัน AI หลายตัวพร้อมกันบน checkout เดียว** — ต้องรอให้ตัวก่อน commit เสร็จก่อน อยากขนานต้องแยก branch/โฟลเดอร์
5. **งานใหญ่ที่หยุดกลางคัน: เขียนลง HANDOFF.md ที่ root** (แล้ว commit) — ใช้เทมเพลตในไฟล์ (งานที่ทำแล้ว / งานค้าง / ขั้นตอนต่อไป / ไฟล์ที่ถืออยู่ / หมายเหตุ) แล้วตั้งสถานะ "มีงานค้าง"; เมื่องานเสร็จให้ล้างกลับเป็น "ว่าง" และ commit
6. **ห้ามทิ้งสคริปต์ชั่วคราวใน repo** — ไฟล์ `_*` ที่สร้างเพื่อ debug/รันเทสต์ ต้องลบก่อน commit (ดู `tools/search_test.py` docstring: ชั่วคราว ไม่ commit ใช้งาน)
7. **อย่าเชื่อสถานะจากความจำ — ตรวจไฟล์จริง** — ไฟล์อาจถูก agent ตัวอื่น/IDE/user แก้ระหว่างทำงาน (เปลี่ยน branch ได้ด้วย) ก่อนแก้ไฟล์ใด ให้ `git diff` เทียบกับ HEAD เสมอ เพื่อแยกงานของตัวเองออกจากของคนอื่น

## Tracking & Analytics Limitations

- **Sales & Clicks:** The system CANNOT track actual affiliate sales or conversions automatically. Shopee Affiliate does not provide webhooks or real-time APIs for individual order conversions. The 'sales_count' reflects the global Shopee sales, not our bot's conversions. To track conversions, export data manually from Shopee's web dashboard and match it with 'facebook_demand_events'.
- **View Tracking:** We do not use link shorteners, so we cannot track clicks/views on products. Traffic goes directly to s.shopee.co.th. Interest is gauged via chat volume instead.
- **Customer Behavior:** Tracked via 'chat_logs' (intents) and 'user_preferences'. Admin dashboard only shows aggregate stats, but the raw data is used for Data Flywheel ML training.
