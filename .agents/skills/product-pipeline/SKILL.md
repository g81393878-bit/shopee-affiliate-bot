---
name: product-pipeline
description: >-
  Product pipeline CLI (tools/product_pipeline.py): import-csv from Shopee affiliate portal,
  analyze, check-links, fix-scores, customers export. Use whenever the user mentions
  import CSV, product_pipeline, นำเข้าสินค้า, check-links --delete, fix-scores, or สรุปลูกค้า.
---

# Product Pipeline (import/วิเคราะห์สินค้า)

## Commands (รันด้วย venv backend: `backend/.venv/Scripts/python tools/product_pipeline.py ...`)
- `import-csv <file.csv> [--analyze] [--top N] [--style ...]` — นำเข้า CSV จากพอร์ทัล
  Shopee Affiliate "สร้างลิงก์" → คัด/ให้คะแนน/ตัดซ้ำ → ตรวจลิงก์ก่อน insert (ข้ามตัวไม่ผ่าน) →
  วิเคราะห์ + เขียนคอนเทนต์ → Supabase
- `analyze [--top N] [--style]` — เติมคอนเทนต์ให้สินค้าที่ว่าง (Groq, เรียง ai_score สูงก่อน)
- `check-links [--delete]` — ตรวจลิงก์ทุกตัว (--delete = ลบตัว DEAD)
- `fix-scores` — คำนวณ ai_score ใหม่ให้ทุกตัว
- `customers [--export x.csv]` — สรุปความสนใจลูกค้าจาก chat_logs

## CSV columns (จากพอร์ทัล)
`รหัสสินค้า, ชื่อสินค้า, ราคา, ขาย, ชื่อร้านค้า, อัตราค่าคอมมิชชัน, คอมมิชชัน, ลิงก์สินค้า, ลิงก์ข้อเสนอ`
- ราคา/ยอดขายรองรับ "พัน/หมื่น/ล้าน" และ "฿" (เช่น "6.9พัน" = 6,900)

## กับดัก
1. **เขียนลง Supabase production ตรง** (อ่าน pooler-url + db-password.txt) — ใช้ `--sqlite`
   เพื่อเทสต์กับ local dev DB; อย่ารัน import ใหญ่โดยไม่ `--top`/ตรวจ CSV ก่อน
2. ตรวจลิงก์ก่อน insert (นโยบายเด็ดขาด) — ตัวไม่ผ่านข้ามไป (รายงานใน log)
3. `--analyze` ใช้ Groq — ระวัง rate limit; ใช้ `batch_generate_content.py` (หลาย key ขนาน) สำหรับล็อตใหญ่
4. Windows console mojibake ไทย — ตั้ง `$env:PYTHONIOENCODING="utf-8"` (ดู generate-ai-content skill)

## ไฟล์
`tools/product_pipeline.py`, `tools/batch_generate_content.py`, `tools/_backfill_content_template.py`,
`tools/_backfill_product_images.py`, `tools/csv_batch_rebuild.py`, `tools/export_content_csv.py`

## หมายเหตุ
สคริปต์ `_*` เป็น dev/backfill — ต้องมีทั้ง `backend/` และ `backend/app/` ใน sys.path
(ดู AGENTS.md); ไม่ commit ไฟล์ CSV นำเข้าที่ root (gitignore *.csv)
