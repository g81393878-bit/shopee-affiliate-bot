---
name: line-product-cards
description: >-
  LINE Flex Message product cards (backend/app/services/product_cards.py): customer vs
  owner views, hook filtering, badges, price-drop display, and link-button safety.
  Use whenever the user mentions การ์ดสินค้า, Flex message, หน้าตาการ์ด, badge, hook,
  or LINE card rendering issues.
---

# LINE Product Cards (การ์ด Flex)

## โครงสร้าง
- `product_cards_message(db, user, products, title, is_owner)` → Flex Carousel สูงสุด 5 การ์ด (โชว์ 3 ตาม LINE)
- ลูกค้า (is_owner=False): ราคาใหญ่ + ⭐รีวิว + ขายแล้ว X ชิ้น + ป้าย 🆕/🔥 + ปุ่ม "🛒 ซื้อเลย" / "🔍 ค้นสินค้า"
- เจ้าของร้าน (is_owner=True = `ADMIN_LINE_USER_ID`): เพิ่ม 💸ค่านายหน้า + 📈คะแนน AI + 💡 Hook + ป้าย 💎คอมสูง

## กับดัก
1. **hook ผ่าน `_clean_hook()` ก่อนโชว์ลูกค้า** — ตัด hook ที่มีอักษร CJK (ภาษาปน เช่น "吗"),
   ความยาวต้อง 8-90 ตัวอักษร; ไม่ผ่าน = ไม่โชว์ (ไม่ตัดข้อความ)
2. **hook มาจาก `contents.hook`** (แถวล่าสุด per product) — สินค้าที่ "ยังไม่มีคอนเทนต์" จะไม่มีการ์ด hook
3. **ราคา = ราคาเริ่มต้น** — แสดง "เริ่มต้น" + "ราคาจริงตามโปรโมชันในลิงก์" เสมอ (กันฟ้องว่าโชว์ราคาไม่ตรง)
4. **📉 ราคาลง X%** แสดงเฉพาะตอนมีแถว `price_history.drop_pct` จริง (≥1%) — ไม่มโน
5. **URL ใน text message โดน LINE ธง "ข้อความนี้อาจไม่ปลอดภัย"** → ใช้ `link_button_message()`
   (ปุ่ม URI ใน Flex) แทนการแปะ URL ลงข้อความเสมอ
6. ป้าย 🆕 ของใหม่ = สร้าง ≤14 วัน; 🔥 ขายดี = ยอดขายติด top 1/5 ของคลัง; 💎 คอมสูง = top 1/5 (เฉพาะ owner)

## ไฟล์
`backend/app/services/product_cards.py` (+ `link_button_message` ใช้ที่อื่นด้วย เช่น WISMO)

## เทสต์
`backend/tests/test_line_bot.py` ตรวจ preview การ์ด (ใช้ `sim` fixture + `_preview`)
