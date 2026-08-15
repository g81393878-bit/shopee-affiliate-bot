---
name: content-backfill
description: >-
  Diagnose and fill the "ยังไม่มีคอนเทนต์" backlog (products missing an AI content
  script in the contents table) for the ป้าเข็ม Shopee affiliate bot. Use whenever the
  user mentions ยังไม่มีคอนเทนต์, สินค้าไม่มีคอนเทนต์, backfill คอนเทนต์, or asks to
  generate product content without spending Groq/LLM — even if they don't name the
  contents table or the analyze cron.
---

# Content Backfill — สินค้ายังไม่มีคอนเทนต์

## "ยังไม่มีคอนเทนต์" คืออะไร

แดชบอร์ดแอดมิน (`/admin`) การ์ด **"ยังไม่มีคอนเทนต์"** = จำนวนสินค้าที่**ไม่มีแถว**ในตาราง `contents`

- `contents` เก็บสคริปต์ขายที่ AI เขียนให้สินค้าแต่ละตัว: `hook` (เปิดเรื่อง) · `problem` (ปัญหา) · `solution` (ทางออก) · `cta` (ปิดขาย) · `caption` (แคปชั่น + แฮชแท็ก) · `style`
- คำนวณใน `backend/app/api/admin_dashboard.py::admin_stats`: `total − len(distinct product_id ใน contents)`

**ความสัมพันธ์ที่สำคัญ (อ่านโค้ดแล้วไม่เห็นง่ายๆ):**
- โพสต์สินค้าขึ้น Facebook (`cron.py::_build_fb_caption`) **ไม่ได้อ่าน** `contents` — gen caption สดผ่าน Groq ทุกครั้ง (มี template fallback ถ้า Groq พัง) → สินค้าที่ "ยังไม่มีคอนเทนต์" **โพสต์ FB ได้ปกติ ไม่ถูกบล็อก**
- `contents.hook` ใช้ทำ**การ์ดสินค้า LINE** (`product_cards.py`) — นี่คือที่ที่คอนเทนต์ถูกใช้จริง

## เติมแบบไหน

เจ้าของร้านสั่งชัดเจนว่า **"ไม่ต้องใช้ Groq"** — ใช้ template ไม่ใช้ LLM เป็น default

| วิธี | ใช้เมื่อ | ค่าใช้จ่าย |
|---|---|---|
| **Template** (`build_template_script`) | default — เติม backlog เร็ว | ฟรี ไม่เรียก LLM |
| **Cron `analyze`** (Groq) | ต้องการคอนเทนต์คุณภาพสูงเฉพาะตัว | เสีย Groq + ช้า (30 ตัว/2 ชม.) |

## เติมด้วย template (ไม่ใช้ LLM)

1. อ่าน pw Supabase: `~/.supabase/db-password.txt`
2. รัน (ต่อ production ตรง เหมือน `tools/_backfill_product_images.py`):

```bash
cd backend && DATABASE_URL="postgresql://postgres.usqhvujqmnxqrdoovvnp:$(cat ~/.supabase/db-password.txt)@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres" \
  .venv/Scripts/python.exe ../tools/_backfill_content_template.py --limit 5   # ทดสอบก่อน
```

3. รันเต็ม (ลบ `--limit` เพื่อเติมทั้งหมด):

```bash
cd backend && .venv/Scripts/python.exe ../tools/_backfill_content_template.py
```

- สคริปต์เรียงตาม `ai_score` สูงก่อน (เหมือน cron) และ batch commit 500 แถว/ครั้ง
- Template มาจาก `backend/app/services/ai_generator.py::build_template_script()` (เสียงป้าเข็มสำเร็จรูป)

## เติมด้วย LLM (cron analyze)

```bash
curl -X POST "https://shopee-affiliate-bot-9e9n.onrender.com/api/cron/analyze?token=<CRON_TOKEN>&limit=30"
```

- cron-job.org รันอัตโนมัติทุก 2 ชม. (`limit=30`) — backlog ~600 ตัว ≈ 40 ชม. กว่าจะครบ
- `limit` default 5; ใช้ `limit` ใหญ่ระวัง Groq rate limit

## ตรวจผล

```sql
SELECT count(*) FROM products p WHERE NOT EXISTS (SELECT 1 FROM contents c WHERE c.product_id = p.id);
```

ต้องลดลงเท่ากับจำนวนที่เติม → การ์ด "ยังไม่มีคอนเทนต์" ใน `/admin` ลดตาม

## กับดักที่เจอจริง

- อย่าเติมซ้ำ: `contents` อนุญาตหลายแถวต่อ product (style ต่างกัน) — เช็ค `NOT EXISTS` ก่อน insert เสมอ
- caption ของ template มีแฮชแท็ก inline อยู่แล้ว — ไม่ต้อง append `hashtags` ซ้ำ (cron `analyze` ทำซ้ำเพราะ caption จาก Groq ไม่มี inline tag; template มีอยู่แล้ว)
