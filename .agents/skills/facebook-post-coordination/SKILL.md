---
name: facebook-post-coordination
description: >-
  Facebook posting coordination for the ป้าเข็ม page: who triggers each post,
  what readiness checks run before posting, how cron rotation and the demand
  radar avoid posting the same category, and how the owner is alerted when
  posting is not ready or fails. Use whenever the user touches anything that
  posts to the Facebook page — โพสต์เพจ, auto-post, rotation, radar post,
  cooldown, โพสต์ซ้ำ, เพจเงียบ, โพสต์ไม่ขึ้น, owner alert, or asks "ใครสั่งโพสต์"
  / "ทำไมเพจไม่โพสต์" / "ตรวจก่อนโพสต์ไหม".
---

# Facebook Posting Coordination (ใครสั่งโพสต์ / ตรวจก่อน / ไม่พร้อมแจ้งเจ้าของ)

จุดประสงค์: การโพสต์เพจมี **หลายตัวสั่ง** (radar + cron rotation) ที่ทำงานคนละที่ —
ถ้าแก้โดยไม่รู้ "สัญญา" ระหว่างกัน จะเจอโพสต์ซ้ำ / หมวดถี่เกิน / เพจเงียบซ้ำแล้วซ้ำอีก
อ่าน `docs/facebook-posting-workflow.md` (แหล่งความจริงของ workflow แต่ละบอท) ก่อนแตะโค้ดโพสต์

## ใครเป็นคนสั่งโพสต์ (มี 2 ตัวหลัก)

| บอท | Trigger | ไฟล์ |
|---|---|---|
| **Radar** | lead เข้า `/api/admin/facebook-radar/leads` → demand ≥70 → post_feed เพจ | `backend/app/api/facebook_radar.py` |
| **Cron rotation** | scheduler ในตัว (`main.py` ตรวจทุก 60 วิ ครบ `FB_AUTO_POST_INTERVAL` นาทีไหม) → หมุน 4 คลัง | `backend/app/api/cron.py` + `backend/app/main.py` |

ทุกตัวที่โพสต์**เพจ**ยิงผ่าน `post_feed()` ใน `backend/app/services/facebook_poster.py` (จุดเดียว) — ตรวจ/แก้ที่จุดเดียวนี้ก่อนเสมอ

## ทุก lead ลงเพจป้าเข็ม (ยกเลิก flow แชร์ลงกลุ่มแล้ว)

`ingest_facebook_leads` ไม่แยก group/page อีกต่อไป — ทุก lead ที่ demand ≥70 ผ่าน
cooldown + daily limit + `preflight_ready()` แล้ว `post_feed()` ลงเพจ (Flow B เดิมเท่านั้น)

**Pivot:** radar ไม่จับคู่สินค้าในคลังแล้ว (โพสต์ promo ติดตั้งบอท — `matched_product_id=None`) →
`check_category_cooldown_allowed` นับได้ทั้ง `Product.category` (event เก่า) และ `product_keyword`
(event ใหม่) ผ่าน `or_`

## สัญญา coordination (ห้ามทำลาย — เคยเจอโพสต์ซ้ำ/หมวดถี่เกินจริง)

1. **Preflight ก่อนยิงเสมอ**: `preflight_ready()` — token ตั้ง/ใช้ได้ (`verify_page_token()` cache 1 ชม.,
   fail-open ถ้าเน็ตสะดุด) + page id. **เฉพาะ production (postgres) ถึงบังคับ/แจ้ง** — dev/test (sqlite)
   lenient (post_feed ถูก mock). ไม่พร้อม → ข้ามโพสต์ + `notify_owner_once()`
2. **แจ้งเจ้าของ**: `notify_owner_once(key, text)` — push LINE ไป `ADMIN_LINE_USER_ID`,
   throttle 6 ชม./key (in-memory — Render restart รีเซ็ต), best-effort
3. **Error รุนแรง → แจ้งเจ้าของ**: `classify_post_error()` — OAuth หมดอายุ / `#(200)` Permissions /
   rate-limit / token revoke. อย่างอื่น (ลิงก์ไม่ valid ฯลฯ) ไม่กวน
4. **Cooldown หมวดข้าม flow** (กันหมวดเดียวถี่ เช่น หูฟัง): ทั้ง cron และ radar ต้องนับ
   **ทั้ง 2 ตาราง** — `CampaignLog.status in (fbpost, fbpost_pending)` (cron) +
   `FacebookDemandEvent.notification_status in (posted, sent, pending)` (radar)
   - `pending` = กำลังจะโพสต์ (commit ก่อน post_feed) — ถ้าไม่นับ จะยิงซ้ำในหน้าต่าง ~1-20 วิ
5. **จองหมวดก่อนยิง (cron)**: เขียน `CampaignLog(status='fbpost_pending')` + commit **ก่อน** post_feed
   → สำเร็จเปลี่ยนเป็น `fbpost` / ล้ม **ลบการจอง** (อย่าให้กันหมวดไปตลอด)
   - `fbpost_pending` ห้ามนับเป็นโพสต์สำเร็จใน `_auto_post_due()`/slot count
   - process ตายคาการจอง = ค้างกัน radar 24 ชม. (self-heal — ปลอดภัยกว่ายิงซ้ำ)
6. **กัน concurrent**: `_AUTO_POST_LOCK` (non-blocking) ครอบ `run_facebook_auto_post` —
   ติด lock = ข้ามรอบ ไม่รอ
7. **โพสต์ล้ม อย่าให้ rotation ติดตาย**: `_post_next_*` ต้องลองตัวถัดไป (ไม่ return ทันทีที่ตัวแรกพัง)
   — เคยเจอคลังติดตายเพราะลิงก์ตัวเดียวถูก Facebook ปฏิเสธ

## ขั้นตอนการทำงาน (เรียงลำดับ)

1. เปิด `docs/facebook-posting-workflow.md` → หาบอทที่เกี่ยวข้อง
2. ดูว่า flow ผ่านขั้นตอนครบไหม: preflight → guard → จอง → ยิง → บันทึก/ล้ม
3. แก้ที่จุดเดียว (`post_feed`) ก่อน ถ้าเป็นเรื่องการยิง
4. ถ้าแตะ cooldown/dedup → ดูทั้ง cron + radar (สัญญาข้อ 4-5) อย่าแก้ฝั่งเดียว
5. ลง `.env.example` ถ้าเพิ่ม env ใหม่ (เช่น `FB_POST_CATEGORY_COOLDOWN_HOURS`)
6. รันเทสต์: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -q`

## กับดักที่เจอจริง

- **`hash()` ห้ามใช้ทำ id กันซ้ำ** — Python salt ต่อ process (PYTHONHASHSEED) → id เปลี่ยนทุก run
  → dedup ข้าม run พัง → โพสต์ซ้ำ. ใช้ `hashlib.sha1(...)`
- **โพสต์แนบรูป** (image_url) → ลิงก์ affiliate อยู่ในแคปชั่น (ไม่ใช่ link param) → `post_feed` guard
  ตรวจ link ไม่ถึง → ต้องกรอง `is_valid_shopee_affiliate_url` ที่ฝั่ง caller ด้วย (cron มีแล้ว)
- **ไม่เอา `/cron/facebook-post` ลง cron-job.org** — บอทโพสต์เองในตัว (FB_AUTO_POST_INTERVAL)
  เอาเข้า cron-job.org ซ้ำ = โพสต์ซ้ำ

## บอทลบโพสต์ปลอมอัตโนมัติ (fake-post watcher)

- `main.py` `facebook_fake_post_watcher()` ตรวจทุก `FB_FAKE_POST_CHECK_SECONDS` (default 300) วิ
  → `sweep_fake_posts()` (ใน cron.py) ลบโพสต์ลิงก์ปลอม (shope.ee / lazada / s.shopee.co.th รหัสไม่ valid /
  ไม่ใช่ลิงก์ในคลัง) — ทำงานเอง ไม่ต้องรอครอน 6 ชม. (mock poster "หูฟังลิงก์จริง" โพสต์ลิงก์ปลอมซ้ำ ๆ)
- เปิดเมื่อ **prod (postgres) + มี FB token** — dev/test (sqlite) ปิด (กันลบของจริง)
- ลบได้ → แจ้งเจ้าของ (`fb_fake_post_deleted`, throttle 6 ชม.) = สัญญาณว่า mock poster ยังรันอยู่
- cron endpoint `/api/cron/clean-fake-posts` ใช้ `sweep_fake_posts()` ตัวเดียวกัน

## ไฟล์
`backend/app/services/facebook_poster.py` (post_feed + preflight/verify/notify/classify),
`backend/app/api/cron.py`, `backend/app/api/facebook_radar.py`, `backend/app/main.py`,
`tools/clean_fake_page_posts.py`, `docs/facebook-posting-workflow.md`

## เทสต์
`backend/tests/test_facebook_poster.py` (cron rotation + preflight/alert + cross-flow cooldown),
`test_facebook_radar_api.py`, `test_facebook_demand_radar.py` (mock ทุกเน็ต)
