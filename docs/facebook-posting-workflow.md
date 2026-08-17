# Workflow การโพสต์เพจ Facebook — แต่ละบอททำงานเป็นขั้นตอน ไม่โพสต์เงียบ ๆ

> เอกสารนี้ = แหล่งความจริงของ "ใครสั่งโพสต์ / ตรวจอะไรก่อน / ไม่พร้อมทำยังไง / ล้มแล้วแจ้งใคร"
> อ่านคู่กับ `.agents/skills/facebook-post-coordination/SKILL.md` (สกิลสำหรับ AI ที่จะแตะโค้ดโพสต์)

## หลักการร่วม (ทุกบอท)

ทุกบอทที่ยิงขึ้นเพจต้องผ่าน **ขั้นตอนเดียวกัน ตามลำดับ**:

```
1. ตรวจความพร้อม (preflight)      → พร้อมไหม?  (token ตั้ง/ใช้ได้, page id ครบ)
2. ไม่พร้อม → ข้ามโพสต์ + แจ้งเจ้าของ LINE (throttle 1 ครั้ง/6 ชม. ต่อเหตุผล)
3. พร้อม     → ตรวจ guard เฉพาะ flow (cooldown/โควต้า/dedup/lock)
4. จองหมวดก่อนยิง (กันอีก flow ยิงซ้ำ) → ยิง post_feed
5. สำเร็จ → บันทึก CampaignLog/demand_event + Sheets
6. ล้ม     → ลบการจอง + ลองตัวถัดไป (ไม่ติดตาย) + แจ้งเจ้าของถ้า error รุนแรง
```

- **Preflight**: `preflight_ready()` ใน `backend/app/services/facebook_poster.py`
  - ตรวจ `FACEBOOK_PAGE_ACCESS_TOKEN` ตั้งไหม + `verify_page_token()` (Graph API `GET /{page_id}?fields=id`,
    cache 1 ชม., fail-open ถ้าเน็ตสะดุด) + `FACEBOOK_PAGE_ID`
  - **เฉพาะ production (postgres) ถึงบังคับ/แจ้งจริง** — dev/test (sqlite) lenient (post_feed ถูก mock)
- **แจ้งเจ้าของ**: `notify_owner_once(key, text)` — push LINE ไป `ADMIN_LINE_USER_ID`, throttle 6 ชม./key,
  best-effort (push ล้มไม่พังโค้ด); throttle เป็น in-memory (Render restart = รีเซ็ต)
- **Error รุนแรง** (ต้องแจ้งเจ้าของ): `classify_post_error()` — OAuth หมดอายุ / `#(200)` Permissions /
  rate-limit / token revoke — อย่างอื่น (ลิงก์ไม่ valid, HTTP 400 เฉพาะโพสต์) ไม่กวนเจ้าของ

---

## บอท 1: Radar (Social Demand Radar) — โพสต์ตาม Demand

**ใครสั่ง:** local monitor (`tools/fb_group_monitor_local.py`) ส่ง lead → `POST /api/admin/facebook-radar/leads`
**ตัดสินใจ:** API วิเคราะห์ demand → จับคู่สินค้า → โพสต์

**ขั้นตอน (ตามลำดับ):**
1. กรอง lead ทดสอบ (`fb_sample_/fb_mock_/demo_`) + สแปมลิงก์ (Lazada/s.shopee.co.th/shope.ee)
2. dedup ด้วย `fb_post_id` (ซ้ำ → `already_processed`)
3. วิเคราะห์ AI: demand_score, urgency, budget, keyword, intent
4. demand ≥ `radar_min_score` (default 70) → จับคู่สินค้า (`link_status='ok'` + ลิงก์ valid)
5. **Guard:** category cooldown 24 ชม. (`RADAR_CATEGORY_COOLDOWN_HOURS`) + daily limit
   (`RADAR_MAX_DAILY_POSTS` default 5) — นับ `posted/sent/pending` + CampaignLog `fbpost/fbpost_pending`
   (กันซ้ำกับ cron)
6. **Preflight** → ไม่พร้อม = บันทึก event `failed` + แจ้งเจ้าของ (`fb_preflight_radar`) ไม่โพสต์
7. พร้อม → สร้าง demand_event `pending` + **commit ก่อน post_feed** (กัน record หาย → โพสต์ซ้ำ)
8. `post_feed` → สำเร็จ = `posted` / ล้ม = `failed` (+ แจ้งเจ้าของถ้า error รุนแรง `fb_post_hard_error`)
9. บันทึก Sheets (`POSTS_SHEET_WEBHOOK_URL`, kind=`radar`)

**ไม่พร้อม/ติด guard:** status `ignored` (cooldown/โควต้า — ปกติ รอรอบหน้า) หรือ `failed` (preflight/โพสต์ล้ม)

---

## บอท 2: Cron Rotation — โพสต์หมุนเวียน 4 คลัง

**ใครสั่ง:** scheduler ในตัว (`main.py` `facebook_auto_post_loop` ตรวจทุก 60 วิ ว่าครบ
`FB_AUTO_POST_INTERVAL` นาทีไหม นับจากโพสต์ล่าสุดใน CampaignLog) — **ไม่** เอา `/cron/facebook-post`
ไปลง cron-job.org (เสี่ยงโพสต์ซ้ำ)

**ขั้นตอน (ตามลำดับ):**
1. `_AUTO_POST_LOCK` (กัน 2 thread ยิงพร้อมกัน — ข้ามรอบถ้าติด lock)
2. **Preflight** → ไม่พร้อม = แจ้งเจ้าของ (`fb_preflight_cron`) + คืน `{"posted": [], note}` ไม่โพสต์
3. นับโพสต์แต่ละคลัง → slot = (brand+prod+rss+local) % 4 → วนลอง slot จนกว่าจะโพสต์ได้ 1 ตัว
4. ต่อ slot:
   - **สินค้า** (`_post_next_product`, เปิดเมื่อ `FB_POST_PRODUCTS=1`): กรอง dedup (`fbpost`) +
     หมวด cooldown (ดู CampaignLog `fbpost` + radar `posted/sent/pending`) + ลิงก์ valid →
     **จอง `fbpost_pending` ก่อนยิง** → สำเร็จเปลี่ยนเป็น `fbpost` / ล้มลบการจอง + ลองตัวถัดไป
   - **RSS** (`_post_next_curated`): กันซ้ำ `fbrss` sha1(guid) — ลิงก์ล้ม → ลองข่าวถัดไป
   - **ท้องถิ่น** (`_post_next_local`): หมุน 77 จังหวัด × 3 หัวข้อ — ลิงก์ facebook.com ข้าม (Permissions error)
   - **แบรนด์** (`_post_next_brand`): แนะนำตัว(`fbintro`) ↔ พื้นสี(`fbbg`) — ล้ม → ข้ามตัวถัดไป
5. ทุกคลังล้ม/หมด → คืน `{"posted": [], note}` (ไม่ block scheduler)

**กันซ้ำ:** `posted_ids` = CampaignLog `fbpost` ทั้งหมด (สินค้าโพสต์ครั้งเดียว) + `fbpost_pending` = การจอง
(ไม่นับเป็นโพสต์สำเร็จ — `_auto_post_due`/slot count ไม่มอง)

---

## บอท 3: Local Monitor — สแกนกลุ่มส่ง lead

**ใครสั่ง:** เจ้าของรัน `tools/fb_group_monitor_local.py` (ต้อง `--once` เสมอ — ไม่งั้น loop ค้าง)
**หน้าที่:** สแกนกลุ่ม → ส่ง lead ให้ radar API (ไม่โพสต์เอง)

**ขั้นตอน:**
1. ดึงกลุ่ม active จาก API → สแกนโพสต์ (sample หรือ real scraper)
2. dedup ด้วย `fb_post_id` (ในหน่วยความจำ + `--state-file`)
   - **ห้ามใช้ `hash()`** สร้าง id (Python salt ต่อ process → dedup ข้าม run พัง → โพสต์ซ้ำ) — ใช้ sha1
3. ส่ง `POST /api/admin/facebook-radar/leads` (token ผ่าน `X-Admin-Token`/`?token=`)

---

## บอท 4: Fake-Post Watcher + Clean-Fake-Posts — กวาดลบโพสต์ลิงก์ปลอมอัตโนมัติ

**ใครสั่ง:** 2 ชั้น — (1) **watcher ในตัว** (`main.py` `facebook_fake_post_watcher` ตรวจทุก
`FB_FAKE_POST_CHECK_SECONDS` วิ default 300) ลบทันทีที่เจอ; (2) cron-job.org ทุก 6 ชม.
→ `POST /api/cron/clean-fake-posts?token=...` (เผื่อ manual)

**ขั้นตอน (ทั้ง 2 ชั้นใช้ `sweep_fake_posts()` ฟังก์ชันเดียวกัน):**
1. โหลดลิงก์ในคลัง (`products.affiliate_url`) → normalize
2. `fetch_page_posts(limit)` → เช็ค `is_fake_link_post()` (shope.ee / lazada / s.shopee.co.th รหัสไม่ valid /
   **ไม่ใช่ลิงก์ในคลัง**)
3. ลบเฉพาะตัวปลอม (`delete_page_post`) — `dry_run=true` ดูตัวอย่างก่อน
4. watcher ลบได้ → แจ้งเจ้าของ (`fb_fake_post_deleted`, throttle 6 ชม.) — "mock poster ยังรันอยู่?"

**เปิดเมื่อ:** production (postgres) + มี `FACEBOOK_PAGE_ACCESS_TOKEN` — dev/test (sqlite) ปิด
(กันลบของจริงโดยไม่ได้ตั้งใจ)

**ข้อควรรู้:** ลบ `s.shopee.co.th` ที่ไม่อยู่ในคลังด้วย (ตามดีไซน์ กัน mock poster) — ระวังลิงก์มือที่ยังไม่ import

---

## ตารางสรุป "ใครสั่ง / ตรวจอะไร / ไม่พร้อมทำยังไง"

| บอท | Trigger | Preflight | Guard เฉพาะ | ไม่พร้อม | โพสต์ล้ม |
|---|---|---|---|---|---|
| Radar | monitor ส่ง lead | ✅ | demand/cooldown/limit/valid | event `failed` + แจ้ง | แจ้งถ้า error รุนแรง |
| Cron rotation | scheduler ในตัว | ✅ | lock/dedup/cooldown/valid | note + แจ้ง | ลบจอง + ลองตัวถัดไป + แจ้งถ้ารุนแรง |
| Local monitor | เจ้าของรัน | — | dedup | ไม่ส่ง lead | log อย่างเดียว |
| Fake-post watcher | scheduler ในตัว (ทุก 5 นาที) | — | เช็คลิงก์ก่อนลบ | ไม่ลบ | log อย่างเดียว |
| Clean-fake-posts | cron-job.org (6 ชม.) | — | เช็คลิงก์ก่อนลบ | ไม่ลบ | log อย่างเดียว |

## ไฟล์ที่เกี่ยวข้อง
- `backend/app/services/facebook_poster.py` — post_feed + preflight/verify/notify/classify
- `backend/app/api/cron.py` — rotation + `_AUTO_POST_LOCK` + `fbpost_pending` reservation
- `backend/app/api/facebook_radar.py` — radar ingest + cooldown (นับ `fbpost_pending` ด้วย)
- `backend/app/main.py` — auto-post loop + `_auto_post_due`
- `tools/fb_group_monitor_local.py`, `tools/clean_fake_page_posts.py`
