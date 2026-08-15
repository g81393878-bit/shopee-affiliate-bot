---
name: facebook-page-automation
description: >-
  Facebook Page automation: post_feed (Graph API) + Messenger webhook (facebook_bot.py)
  + caption builders (curated RSS / local Firecrawl / intro) + product image fetch.
  Use whenever the user mentions โพสต์เพจ, post_feed, Messenger, webhook facebook,
  แคปชั่น, RSS, โพสต์ท้องถิ่น, or แนบรูปสินค้า.
---

# Facebook Page Automation (โพสต์ + Messenger)

## โพสต์เพจ (`facebook_poster.post_feed`)
- `POST /{page_id}/feed` (message + link) หรือ `/photos` (url + message caption) —
  **มี image_url จะใช้ /photos และไม่ส่ง link** (Facebook เลือก media อย่างเดียว)
- `background_preset_id` (โพสต์พื้นสี): ข้อความล้วน ≤130 ตัวอักษร, ห้าม media/link
- **ทุกโพสต์ผ่าน `sanitize_post_text()`** ก่อน — ตัดอักษรต่างภาษา (อาหรับ/ซีริลลิก/CJK)
  ที่ LLM หลุด ("دیزاین") กันเพจดูไม่เป็นมืออาชีพ
- `log_post_async()` บันทึก Sheets (daemon thread, `POSTS_SHEET_WEBHOOK_URL`) —
  follow_redirects=True ต้องเปิด (Apps Script ตอบ 302)

## Messenger webhook (`facebook_bot.py`)
- endpoint จริง = `GET/POST /api/webhooks/facebook` (**พหูพจน์** — `/api/webhook` เดี่ยวผิด)
- GET = verify handshake (hub.challenge plain text); POST = ตรวจ `X-Hub-Signature-256`
  (HMAC-SHA256 ด้วย FACEBOOK_APP_SECRET) + fallback sha1 header เก่า
- ตอบลูกค้า Messenger → แนะนำ + ลิงก์ LINE OA (`lin.ee/o9Kjp1N`)
- **สลับ Dev→Live ไม่มี API** — ต้องกดใน Dev Center; ยืนยัน Live ด้วยบัญชีธรรมดาทักเพจ

## แคปชั่น (gen สด ไม่ได้อ่าน contents)
- `_build_fb_caption` (cron.py): `generate_script_for_product` caption + `format_hashtags_text` —
  caption ต้องข้อความล้วน (ดู ai-content-generation)
- **curated (RSS)**: `facebook_curated.py` — feed ไทย (Beartai/Techhub/The Standard) →
  Groq เขียนเสียงป้าเข็ม → + ลิงก์ LINE OA + hashtags; กันซ้ำ CampaignLog status='fbrss'
- **local**: `facebook_local.py` — Firecrawl ค้น 77 จังหวัด × 3 หัวข้อ (หมุน index);
  **ข้ามลิงก์ facebook.com/fb.com** (Graph API "Permissions error" → โพสต์ติดตาย); กันซ้ำ status='fblocal'
- **intro**: `facebook_intro.py` — โพสต์แนะนำตัวป้าเข็ม (CampaignLog status='fbintro')

## รูปสินค้า (`product_image.py`)
- ลำดับหา og:image: หน้าเว็บตรง → derive `opaanlp→/product/{shop}/{item}` (มี og:image/JSON-LD)
  → Facebook og scrape → Firecrawl; best-effort คืน "" (fallback การ์ดลิงก์)
- `fetch_product_image_direct` = ฟรี/เร็ว ใช้ eager backfill ตอน import

## ไฟล์
`backend/app/services/facebook_poster.py`, `api/facebook_bot.py`, `services/facebook_curated.py`,
`facebook_local.py`, `facebook_intro.py`, `product_image.py`, `text_cleaner.py`

## เทสต์
`backend/tests/test_facebook_webhook.py`, `test_facebook_poster.py`, `test_facebook_curated.py`,
`test_facebook_local.py`, `test_product_image.py` (mock ทุกเน็ต)
