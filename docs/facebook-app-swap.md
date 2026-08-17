# Facebook App Swap — Option B (ลบ app "post api" + สร้าง app ใหม่)

Runbook สำหรับสลับบอทป้าเข็มไป Facebook app **ใหม่** แล้วลบ app "post api"
(`1263958805236203`) ทิ้ง — ฆ่า token ของ mock poster "หูฟังลิงก์จริง" ให้สิ้นซาก

> **ทำไมต้อง Option B:** mock poster ใช้ token จาก app "post api" ตัวเดียวกับบอทเรา
> (ตรวจแล้ว: `.env` == Render env, app เดียวกัน, token ตัวเดียวกัน) — Option A (reset
> app secret) ก็ฆ่า token เก่าได้เหมือนกัน แต่ token ใหม่**ยังมาจาก app เดิม** ถ้าสงสัยว่า
> mock poster เข้าถึง app ได้ลึก ต้องแยก app ให้สิ้นซาก = Option B นี้
>
> **ถ้าอยากเร็วกว่า:** Option A (reset app secret) ใช้เวลา ~10 นาที ไม่ต้องตั้ง webhook ใหม่
> ดู `docs/facebook-posting-workflow.md` → ส่วน "สลับ token"

---

## 📋 Config ปัจจุบัน (document ไว้ — ต้องสร้างใหม่บน app ใหม่ให้เหมือน)

ตรวจจาก production (read-only) เมื่อ 2026-08-17:

| รายการ | ค่า |
|---|---|
| Page id | `1307380735783361` |
| App เก่า | `1263958805236203` ("post api") |
| Webhook callback URL | `https://shopee-affiliate-bot-9e9n.onrender.com/api/webhooks/facebook` |
| Verify token | env `FACEBOOK_VERIFY_TOKEN` (ไม่ต้องเปลี่ยน) |
| **ชั้น 1: App subscriptions** (object=page) | fields: `messages, messaging_postbacks, feed, message_reads, name, live_videos, message_deliveries` |
| **ชั้น 2: Page subscribed_apps** | subscribed_fields: `messages, messaging_postbacks, message_deliveries, message_reads` |

> ⚠️ Meta docs: "only fields with subscriptions at **both** the page and app levels will
> get Webhooks" — ต้องตั้งครบ 2 ชั้น ไม่งั้นบอทเงียบ (บอทเงียบทั้งที่ callback ถูก =
> ลืมชั้น 2)

---

## Phase 1 — สร้าง app ใหม่ (เจ้าของทำใน dashboard — ไม่มี API สร้าง app)

1. `developers.facebook.com` → **My Apps → Create App**
2. เลือก type: **Business** → ตั้งชื่อ (เช่น "ป้าเข็ม bot v2")
3. เปิดหน้า **Settings → Basic** → จด **App ID** + **App Secret** (กด Show)
4. **Add Page** (หน้า App Roles หรือผ่าน Graph API Explorer) — เลือกเพจ `1307380735783361`
   ให้ app ใหม่จัดการเพจได้ (ต้องเป็น admin ของเพจ)

**ได้ของ 2 อย่าง: `NEW_APP_ID` + `NEW_APP_SECRET`**

---

## Phase 2 — สร้าง page token ใหม่ + อัปเดต .env + Render (ผมทำได้)

1. Graph API Explorer (เลือก app ใหม่) → เอา short-lived user token ด้วย scopes:
   `pages_manage_posts, pages_read_engagement, pages_show_list, pages_manage_engagement,
   pages_read_user_content, publish_video, pages_manage_metadata, pages_manage_ads, pages_messaging`
2. รันสคริปต์:
   ```bash
   python tools/gen_fb_page_token.py \
     --app-id <NEW_APP_ID> --app-secret <NEW_APP_SECRET> \
     --short-token <SHORT_TOKEN> --page-id 1307380735783361
   ```
   → ได้ `NEW_PAGE_TOKEN` (ยืนยันด้วย debug_token ว่า app = app ใหม่)
3. อัปเดต `backend/.env`: `FACEBOOK_APP_ID` / `FACEBOOK_APP_SECRET` / `FACEBOOK_PAGE_ACCESS_TOKEN`
4. อัปเดต Render env (Management API):
   ```bash
   PUT /services/srv-d9tknl2d0e5s739ebo40/env-vars/FACEBOOK_APP_ID        = <NEW_APP_ID>
   PUT /services/srv-d9tknl2d0e5s739ebo40/env-vars/FACEBOOK_APP_SECRET    = <NEW_APP_SECRET>
   PUT /services/srv-d9tknl2d0e5s739ebo40/env-vars/FACEBOOK_PAGE_ACCESS_TOKEN = <NEW_PAGE_TOKEN>
   ```
5. Trigger deploy: `POST /services/srv-d9tknl2d0e5s739ebo40/deploys`

---

## Phase 3 — ตั้ง webhook 2 ชั้นบน app ใหม่ (Graph API — ผมทำได้)

### ชั้น 1 — App-level subscription (ต้องใช้ **app access token** = `NEW_APP_ID|NEW_APP_SECRET`)

```bash
curl -X POST "https://graph.facebook.com/v26.0/<NEW_APP_ID>/subscriptions" \
  -d "object=page" \
  -d "callback_url=https://shopee-affiliate-bot-9e9n.onrender.com/api/webhooks/facebook" \
  -d "fields=messages,messaging_postbacks,feed,message_reads,name,live_videos,message_deliveries" \
  -d "include_values=true" \
  -d "verify_token=<FACEBOOK_VERIFY_TOKEN>" \
  -d "access_token=<NEW_APP_ID>|<NEW_APP_SECRET>"
# → {"success": true}  (Facebook จะยิง GET verify มาที่ callback — ต้องได้ challenge กลับ)
```

> ⚠️ ถ้าได้ error ต้องเช็ค: callback URL ขึ้น production แล้ว (`GET /api/webhooks/facebook`
> คืน challenge เป็น plain text เมื่อ `hub.verify_token` ตรง) — verify token ใน Render
> กับที่ส่งในคำสั่งต้องตรงกัน

### ชั้น 2 — Page subscription (ต้องใช้ **page access token** ของ app ใหม่)

```bash
curl -X POST "https://graph.facebook.com/v26.0/1307380735783361/subscribed_apps" \
  -d "subscribed_fields=messages,messaging_postbacks,message_deliveries,message_reads" \
  -d "access_token=<NEW_PAGE_TOKEN>"
# → {"success": true}
```

### Pre-flight จำลอง verify ก่อนยิง (กันตั้งแล้วเงียบ)

```bash
curl "https://shopee-affiliate-bot-9e9n.onrender.com/api/webhooks/facebook?hub.mode=subscribe&hub.verify_token=<FACEBOOK_VERIFY_TOKEN>&hub.challenge=test123"
# → ต้องคืน "test123" เป็น plain text (ไม่ใช่ JSON)
```

### ยืนยันครบ 2 ชั้น

```bash
# ชั้น 1
GET /v26.0/<NEW_APP_ID>/subscriptions?access_token=<NEW_APP_ID>|<NEW_APP_SECRET>
# ชั้น 2
GET /v26.0/1307380735783361/subscribed_apps?access_token=<NEW_PAGE_TOKEN>
```

---

## Phase 4 — ตรวจก่อนลบ app เก่า (สำคัญ!)

ก่อนลบ app "post api" ให้ยืนยันทุกอย่างทำงานกับ app ใหม่แล้ว:
- [ ] `/health` = ok
- [ ] โพสต์ทดสอบขึ้นเพจ (ผ่าน `post_feed` หรือโพสต์มือ) — ดูว่า "เผยแพร่โดย" เป็น **app ใหม่**
- [ ] Messenger webhook รับข้อความจริง (ทักเพจด้วยบัญชีธรรมดา → ได้คำตอบแนะนำบอท)
- [ ] watcher ยัง enabled (ตรวจทุก 5 นาที)

> ถ้าขาดข้อไหน → **หยุด** แก้ให้ครบก่อน อย่าเพิ่งลบ app เก่า

---

## Phase 5 — ลบ app เก่า (เจ้าของทำใน dashboard — **ไม่มี API ลบ app สาธารณะ**)

การลบ app ผ่าน Graph API **ไม่มี endpoint สาธารณะ** — ต้องทำใน dashboard:

1. `developers.facebook.com` → My Apps → **post api** (`1263958805236203`)
2. **Settings → Advanced** → scroll ล่างสุด → **Delete App** → พิมพ์ชื่อ app ยืนยัน
3. พอ app ถูกลบ → **token ทุกตัวของ app นี้ตายทันที** (รวม mock poster) — หยุดเด็ดขาด

> ถ้าอยากล้าง webhook ของ app เก่าก่อนลบ (optional — app ถูกลบแล้วทุกอย่างหายเอง):
> ```bash
> # ถอด app เก่าออกจากเพจ (ใช้ page token ของ app เก่า — ต้องยังไม่ตาย)
> curl -X DELETE "https://graph.facebook.com/v26.0/1307380735783361/subscribed_apps?access_token=<OLD_PAGE_TOKEN>"
> # ล้าง app-level subscription (ใช้ app token เก่า)
> curl -X DELETE "https://graph.facebook.com/v26.0/1263958805236203/subscriptions?object=page&access_token=<OLD_APP_ID>|<OLD_APP_SECRET>"
> ```

---

## 🧪 วิธีพิสูจน์ว่า mock poster ตายจริง

หลังลบ app เก่า → รอ 1-2 ชม. ดูว่าเพจมีโพสต์ปลอมใหม่ไหม (watcher จะลบเองทุก 5 นาที
+ แจ้ง LINE เจ้าของ `fb_fake_post_deleted` ถ้ายังเจอ) — ถ้ายังมีโพสต์ปลอม แปลว่า mock
poster มีช่องทางอื่น (เช่น token จาก app อื่น) → ต้องหาต้นตอเพิ่ม

## 🔁 Rollback

ถ้า app ใหม่พัง (โพสต์/webhook ไม่ทำงาน) → Render dashboard → **Rollback** ไป deploy
ก่อนหน้า (โค้ดเก่า) แต่ env (app id/secret/token) ยังเป็นของ app ใหม่ — ต้องตั้ง env กลับ
เป็นของ app เก่าด้วย (ถ้ายังไม่ลบ app เก่า) หรือสลับกลับ

---

## สรุป: ใครทำอะไร

| ขั้น | ใครทำ | ผ่านอะไร |
|---|---|---|
| สร้าง app ใหม่ | เจ้าของ | dashboard |
| gen page token + อัปเดต .env + Render + deploy | AI (มี token/secret) | `gen_fb_page_token.py` + Render API |
| ตั้ง webhook ชั้น 1 + 2 | AI | Graph API (app token + page token) |
| ตรวจก่อนลบ | เจ้าของ + AI | dashboard + API |
| ลบ app เก่า | เจ้าของ | dashboard (ไม่มี API) |
