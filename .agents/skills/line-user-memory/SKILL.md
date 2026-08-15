---
name: line-user-memory
description: >-
  Account Memory (แบบ Amazon) ของบอทป้าเข็ม: "จำไว้ …" เก็บหมวด/โน้ตใน user_preferences,
  tone วัย, _customer_categories, และการลบข้อมูล PDPA. Use when the user mentions
  จำไว้, ป้าเข็มจำได้ไหม, ความสนใจลูกค้า, preferences, tone วัย, or customer memory.
---

# LINE User Memory (Account Memory)

## เก็บอะไร ที่ไหน
- **ห้ามเพิ่มคอลัมน์ใน `users`** — users คือ `auth.users` ของ Supabase มี preferences ของ auth อยู่แล้ว
- เก็บในตารางแยก `user_preferences` (หมวด `category`, โน้ต `note`, `tone`)
- `_customer_categories(db, line_user_id)`: ใช้ pref ก่อน แล้วค่อย fallback ไป chat_logs
- "มีอะไรใหม่" / แคมเปญ / ของใกล้เคียง → แนะนำตามหมวดที่ลูกค้าระบุเอง (pref ชนะ chat_logs)

## กับดัก
1. **tone วัย (youth/elder) เดาแล้วจำถาวร** — `detect_tone()` ดูสัญญาณซับสตริง แล้วเขียน
   `user_preferences.tone`; ถ้าเดาผิด (ชนชื่อสินค้า ดู line-bot-core ข้อ 5) ลูกค้าติดวัยผิดถาวร
   — ไม่มีคำสั่งให้ลบเอง ต้องระวังตอนเพิ่มสัญญาณใหม่
2. **"จำไว้ …"** → `handle_remember()`: เก็บหมวดที่อยู่ในโน้ต (`_remember_categories_from_note`)
   + ตัวโน้ตเอง; ลูกค้าถาม "ป้าเข็มจำได้ไหม" → อ่านคืนจาก pref
3. **ลบข้อมูล**: "ลบข้อมูลฉัน" → ลบ user + chat_logs + user_preferences ทันที (PDPA) —
   และไม่ log คำสั่งลบ (ถ้าลบแล้ว log จะขัด PDPA)
4. เส้นทางแนะนำของลูกค้าขึ้นกับ `_sellable_categories` → ต้อง `link_status='ok'` เท่านั้น

## ไฟล์
`backend/app/api/line_bot.py` (`handle_remember`, `_customer_categories`, `_saved_categories`,
`_saved_notes`, `get_tone`, `detect_tone`), `backend/app/models.py` (UserPreference)

## เทสต์
`backend/tests/test_line_bot.py` — มีเทสต์วัย/จำไว้/ลบข้อมูลแล้ว; เพิ่มเทสต์ทุกครั้งที่แตะ logic นี้
