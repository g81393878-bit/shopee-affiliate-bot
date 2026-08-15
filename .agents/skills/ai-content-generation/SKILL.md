---
name: ai-content-generation
description: >-
  AI content generation: generate_script_for_product + build_template_script (ai_generator.py),
  analyze_product_with_ai + heuristic score (ai_analyzer.py), SCRIPT_KEYS schema, and the
  caption/hashtags contract. Use when the user mentions สคริปต์คอนเทนต์, hook/problem/solution/cta,
  caption, hashtags, ai_score, วิเคราะห์สินค้า, or template fallback.
---

# AI Content Generation (สคริปต์ + วิเคราะห์สินค้า)

## สคริปต์ (ai_generator.py)
- `generate_script_for_product(name, category, price, style, tone)` → dict ครบ `SCRIPT_KEYS`:
  hook / problem / solution / cta / caption / hashtags / title / thumbnail_prompt
- เดิน provider ตาม `LLM_PROVIDER` (gemini→openai→groq→anthropic); ล้มทุก key → fallback
  `build_template_script()` (เสียงป้าเข็มสำเร็จรูป ไม่เรียก LLM)
- **สัญญา caption/hashtags (ห้ามฝืน)**: `caption` ต้องเป็นข้อความล้วน **ไม่มี `#` ฝังในตัว**
  consumer ทุกตัว (`cron analyze`, `_build_fb_caption`, `batch_generate_content`) ต่อ
  `format_hashtags_text(hashtags)` เอง — ถ้าฝังแท็กใน caption จะโพสต์แท็กซ้ำ 2 รอบ
- `format_hashtags_text()`: normalize list/string, ตัดแท็ก 1 ตัวอักษร (แฮชที่ model แยกตัวอักษร),
  ตัดซ้ำ, จำกัด 8 แท็ก

## วิเคราะห์ (ai_analyzer.py)
- `analyze_product_with_ai(...)` → `{product_score, recommendation, reasons, content_ideas, script}`
  (LLM; `_normalize_analysis` รองรับ snake/camelCase)
- `calculate_heuristic_score(sales, rating, commission, price)` → คะแนน 0-100 (ยอดขาย 30% /
  รีวิว 20% / คอม 20% / เทรนด์ 20% / ราคา 10%) — ใช้ offline ไม่ต้อง LLM
- fallback `get_mock_analysis()` — caption ต้องข้อความล้วนเหมือน build_template_script

## กับดัก
1. เปลี่ยน field ใน SCRIPT_KEYS = พัง consumer ทุกตัว → ต้องอัปเทสต์ `test_ai_generator_template.py`
   (ตรวจครบ SCRIPT_KEYS + caption ไม่มี `#`) พร้อมกันเสมอ
2. `contents` ตารางเก็บแค่ hook/problem/solution/cta/caption — **ไม่มี hashtags/title**;
   โพสต์ FB ไม่ได้อ่าน `contents.caption` (gen สดใหม่) — `contents.hook` ใช้ทำการ์ด LINE เท่านั้น
3. template fallback มี "หยุดก่อนจ๊ะ" ขึ้นต้น — `batch_generate_content.py` ใช้เช็คว่า
   "ทุก Groq key ล้ม (429)" แล้ว retry (ไม่อยากได้ template ใส่ร้าน)

## ไฟล์
`backend/app/services/ai_generator.py`, `ai_analyzer.py`, `persona.py`

## เทสต์
`backend/tests/test_ai_generator_template.py`, `test_llm_providers.py`
