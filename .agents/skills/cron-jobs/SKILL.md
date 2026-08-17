---
name: cron-jobs
description: >-
  Cron endpoints (backend/app/api/cron.py): check-links, analyze, refresh-prices, re-engage,
  facebook-post, daily-report + CRON_TOKEN auth + keep-alive. Use whenever the user mentions
  cron, ตั้งเวลา, CRON_TOKEN, check-links, analyze, refresh-prices, re-engage, daily-report,
  or "ทำไมบอทไม่โพสต์/ไม่อัปเดต".
---

# Cron Jobs (endpoints + auth)

## Endpoints (ทั้งหมด `POST /api/cron/<name>`)
| route | หน้าที่ |
|---|---|
| `check-links` | ตรวจลิงก์ s.shopee.co.th → อัปเดต link_status (OK/DEAD/SUSPECT/UNKNOWN) |
| `analyze` | เติมคอนเทนต์ให้สินค้าที่ยังไม่มีแถวใน contents (Groq `generate_script_for_product`,
  caption + format_hashtags_text; เรียง ai_score สูงก่อน; limit default 5) |
| `refresh-prices` | เปิดหน้าเว็บอ่านราคาจริง → อัปเดต products.price + บันทึก price_history +
  แจ้งราคาตก (ลด ≥ PRICE_DROP_PCT default 5%) หาลูกค้าที่สนใจหมวดนั้น |
| `hermes-learn` | สมองกลเรียนรู้ตลาด 48 ชม. (Groq ปรับ skills, hot-reload; LLM ล้ม = ไม่แตะของเดิม) |
| `re-engage` | push ของใหม่หมวดที่เคยสนใจให้ลูกค้าเงียบ ≥7 วัน (จำกัด limit/รอบ กันสแปม) |
| `facebook-post` | โพสต์คอนเทนต์ขึ้นเพจ (intro/curated/local หมุนเวียน) — **ปกติบอทโพสต์เองในตัว
  (`FB_AUTO_POST_INTERVAL`) อย่าเอาเข้า cron-job.org ซ้ำ** |
| `clean-fake-posts` | กวาดลบโพสต์ลิงก์ปลอมบนเพจ (shope.ee/lazada/ลิงก์ไม่ในคลัง) — `dry_run=true` ดูตัวอย่าง |
| `daily-report` | สรุปยอด/สินค้า/ลูกค้า 24 ชม. ให้เจ้าของร้าน |

## ตั้งอัตโนมัติผ่าน API (cron-job.org REST)
- `tools/cron_jobs.py` สร้าง 8 job ให้ครบ (keepalive + 7 cron) ผ่าน `PUT https://api.cron-job.org/jobs`
  (idempotent — เทียบชื่อ job เดิม สร้างเฉพาะตัวที่ยังไม่มี; `--dry-run` ตรวจอย่างเดียว)
- ต้องมี `CJKEY` (API key จาก cron-job.org → Settings) + `CRON_TOKEN` ใน `backend/.env`
- รัน: `python tools/cron_jobs.py` — ดูตาราง/curl ทางเลือกได้ใน `docs/cron-setup.example.md`

## Auth
- ตั้ง `CRON_TOKEN` → ทุก endpoint ต้อง `?token=...` (401 ไม่งั้น); **ไม่ตั้ง** → รัน unauthenticated
  (เหมือน /health) — อย่าลืมตั้งค่าจริง
- Token อยู่ใน `backend/.env` (gitignored) — ค่าที่ Render dashboard ต้องตรงกัน (ตั้งมือ, CLI ไม่มี env subcommand)

## Keep-alive / Scheduling
- Render free tier spin down ~15 นาที → `/health` ถูก cron-job.org ยิงทุก 10 นาที
- `app/main.py` มี **self keep-alive loop** (lifespan task ping ตัวเอง `RENDER_EXTERNAL_URL/health`
  ทุก 600s — `KEEP_ALIVE_INTERVAL` override; auto-disable ถ้าไม่มี env = dev)
- cron-job.org เรียก `https://shopee-affiliate-bot-9e9n.onrender.com/api/cron/<name>?token=<CRON_TOKEN>`

## กับดัก
1. **cron analyze ทำซ้ำ hashtag ถ้า caption ฝัง `#`** — caption ต้องข้อความล้วน (ดู ai-content-generation)
2. refresh-prices: ราคา Shopee อยู่ใน `<script>` (centavos หาร 100,000) — requests ก่อน (ฟรี)
   → โดน anti-bot/JS → Firecrawl scrape (rawHtml ไม่ตัด script) → best-effort ไม่พัง
3. facebook-post ต้อง `sanitize_post_text()` + ห้ามลิงก์ facebook.com (Permissions error ใน local)
4. แก้ cron แล้วรันเทสต์ `test_facebook_poster.py` / `test_price_refresh.py` — อย่าแตะ production ตรง ๆ

## ไฟล์
`backend/app/api/cron.py` (+ `facebook_poster.py`, `facebook_curated.py`, `facebook_local.py`,
`facebook_intro.py`, `price_refresh.py`, `line_quota.py`)

## เทสต์
`backend/tests/test_facebook_poster.py`, `test_price_refresh.py`, `test_facebook_curated.py`,
`test_facebook_local.py`
