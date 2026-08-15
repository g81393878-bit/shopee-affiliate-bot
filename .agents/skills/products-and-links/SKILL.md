---
name: products-and-links
description: >-
  Product CRUD API + affiliate link policy: products.py endpoints, link_checker statuses
  (ok/dead/suspect/unknown/none), link verification before insert, and image_url backfill.
  Use whenever the user mentions สินค้า API, link_status, ลิงก์ตาย, check-links, import สินค้า,
  or "บอทไม่ตอบสินค้าตัวนี้".
---

# Products & Link Policy (เด็ดขาด)

## Link status (`link_checker.py`)
- `check_affiliate_link(url)` → `(status, detail)`; status = `OK` / `DEAD` / `SUSPECT` / `UNKNOWN` / `NO_URL`
- ต้องเป็นลิงก์สั้น `s.shopee.co.th/...`; GET ตาม redirect (BROWSER_UA) แล้วดู:
  - HTTP 400/404/410 หรือหน้า "ไม่พบสินค้า" → DEAD
  - 401/403 / หน้า anti-bot ("เข้าสู่หน้าที่ต้องการไม่สำเร็จ"/captcha) → SUSPECT (เช็คมือ)
  - redirect ไป `/product/|/opaanlp/|-i.<shop>.<item>` → OK; redirect ไปอื่น → SUSPECT
- **กฎเหล็ก**: สินค้าเข้าระบบต้องมีลิงก์ตรวจผ่านเท่านั้น
  - API POST/PUT /products ตรวจก่อนบันทึก (ไม่ OK → 400)
  - `product_pipeline.py import-csv` ตรวจก่อน insert (ข้ามตัวไม่ผ่าน)
  - **บอท LINE ตอบเฉพาะ `link_status == 'ok'`** (ทั้ง search + หมุนเวียน + matcher)
  - cron `check-links` อัปเดตสถานะลงตาราง (`--delete` ลบตัว DEAD)

## API (`products.py`)
- `GET /` / `GET /{id}` / `POST /` (201) / `PUT /{id}` / `DELETE /{id}` (204)
- `POST /{id}/analyze` + `/analysis` (ai_analyzer) + `/script` (ai_generator, style param)
- `POST /{id}/script` **upsert** แถว contents ตาม (product_id, style) — ไม่ซ้ำ

## กับดัก
1. ลูกค้าทักหา "สินค้าที่หายไป" = มักเป็นลิงก์ dead/ยังไม่ตรวจ (link_status != 'ok') — อย่า "แก้"
   โดยปลดล็อกการกรอง; ต้องตรวจลิงก์จริงก่อน
2. `ai_score` = คะแนนความน่าสนใจ (sales/rating/commission) — ใช้เรียงลำดับ/ป้ายสีการ์ด ไม่ใช่ราคา
3. `image_url` ตอน import → `fetch_product_image_direct` (eager backfill) — ตรวจรูปไม่ดึง = ค่าเดิมไม่พัง

## ไฟล์
`backend/app/api/products.py`, `services/link_checker.py`, `services/product_image.py`,
`tools/product_pipeline.py` (import-csv)

## เทสต์
`backend/tests/test_product_image.py`; test_webhook.py/test_line_bot.py ตรวจบอทตอบเฉพาะ ok
