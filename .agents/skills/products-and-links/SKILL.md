---
name: products-and-links
description: >-
  Product CRUD API + affiliate link policy: products.py endpoints, link_checker statuses
  (ok/dead/suspect/unknown/none), link verification before insert, image_url backfill,
  and catalog storage locations (Supabase, sim_db.db, CSV archives).
  Use whenever the user mentions สินค้า API, link_status, ลิงก์ตาย, check-links, import สินค้า,
  กู้คืนสินค้า, ฐานข้อมูลสินค้า, or "บอทไม่ตอบสินค้าตัวนี้".
---

# Products & Master Catalog Policy (เด็ดขาด)

## 1. จุดจัดเก็บฐานข้อมูลสินค้า (Master Catalog Storage)
- **Production (Ground Truth):** Supabase PostgreSQL (`aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres`) ตาราง `products` (มีสินค้าจริง **1,903 รายการ** 9 หมวดหมู่)
- **Local Master DB:** `backend/sim_db.db` (SQLite ขนาด 892 KB มีสินค้าต้นฉบับ 1,686 รายการ)
- **Raw CSVs:** อยู่ใน `D:\สินค้า\` และ `D:\` (รวมไฟล์ส่งออกจริง 18 ไฟล์)
- **Golden Snapshots:** `artifacts/backup_products_safe.json` และ `.csv` (1,903 รายการ)
- **เครื่องมือกู้คืนมาตรฐาน:** `python tools/restore_from_sim_db.py`

## 2. Link status (`link_checker.py`) & กฎห้ามลบสินค้า
- `check_affiliate_link(url)` → `(status, detail)`; status = `OK` / `DEAD` / `SUSPECT` / `UNKNOWN` / `NO_URL`
- **กฎเหล็กห้ามลบสินค้า (Strict Zero-Delete):**
  - **ห้ามรัน `check-links --delete` หรือ `DELETE FROM products` เด็ดขาด!** 
  - บอท Shopee มักส่ง 403/404 จากระบบ Anti-Scraping ทำให้เข้าใจผิดว่าลิงก์ตาย หากพบปัญหาให้มาร์กเป็น `suspect` เท่านั้น ห้ามลบข้อมูลสินค้าออกจากระบบ
- **บอท LINE ตอบเฉพาะ `link_status == 'ok'`** (ทั้ง search + หมุนเวียน + matcher)

## 3. รูปภาพสินค้า (Authentic CDN)
- ใช้รูปภาพ Shopee Official CDN (`https://down-th.img.susercontent.com/file/...`)
- เครื่องมือดึงภาพ: `python tools/shopee_image_harvester.py`
- หน้าร้าน `backend/app/static/shop.html` ต้องมี `<meta name="referrer" content="no-referrer">` ป้องกัน 403 Forbidden
