---
name: hermes-ai
description: >-
  Hermes AI learning loop: วิเคราะห์ยอดสั่งซื้อปลาสลิดป้าเข็ม (direct_orders) + ตลาดจาก chat_logs +
  facebook_demand_events แล้วให้ Groq ปรับ skills (trending_categories / radar_min_demand_score /
  pa_khem_tone / fish_focus_package / fish_marketing_strategy) เก็บใน system_preferences เพื่อ hot-reload บอท.
  Use whenever the user mentions Hermes, สมองกล, เรียนรู้ตลาด, วิเคราะห์ยอดขายปลาสลิด, system_preferences,
  hermes_skills, or ปรับความไวเรดาร์อัตโนมัติ.
---

# Hermes AI (Learning Loop & Fish Sales Analytics)

## ภาพรวม
- `tools/hermes_brain.py` (CLI) + `backend/app/services/hermes_brain.py` (logic reusable)
- อ่านข้อมูลยอดสั่งซื้อปลาสลิด (`direct_orders` สะสมทั้งหมดและ 48 ชม. ล่าสุด) + `chat_logs` + `facebook_demand_events`
- ให้ Groq วิเคราะห์ → ปรับ skills → เก็บ `system_preferences` key=`hermes_skills` (JSON):
  `trending_categories` (list), `radar_min_demand_score` (int, clamp 50-90), `pa_khem_tone` (str),
  `fish_focus_package` (`"500g"` | `"1kg"` | `"2kg"`), `fish_marketing_strategy` (str)
- consumer ที่ใช้: `facebook_radar.py`, `line_bot.py`, `cron.py`, และเขียนสรุปลง `MARKET_MEMORY.md`

## หลักการ refactor (M1–M4)
- `gather_fish_order_stats(db, hours)` — รวบรวมสถิติออเดอร์ปลาสลิด (รายได้รวม, แพ็กเกจขายดี, สัดส่วนโอนเงิน vs COD, ช่องทางที่สั่งซื้อ)
- `gather_market_data(db, hours)` — pure aggregation (testable, ไม่แตะ LLM) รวมทั้ง `fish_orders`, `chat_logs`, `facebook_demand_events`
- `merge_skills(current, llm_result)` — clamp `radar_min_demand_score` ให้ [50, 90] และบันทึก `fish_focus_package` / `fish_marketing_strategy`
- `load_skills(db)` / `save_skills(db)` — อ่าน/upsert SystemPreference (merge กับ DEFAULT_SKILLS)
- `analyze_market(db)` — orchestrate: gather → `_call_llm` (วน Groq key failover, `settings.GROQ_MODEL`) →
  merge → save → คืน `{skills, report, reason}` หรือ None (LLM ล้ม ไม่แตะของเดิม)

## กับดัก
1. **timezone-aware เสมอ** — ห้าม `datetime.utcnow()` (naive) เทียบกับคอลัมน์ `DateTime(timezone=True)`
   ใช้ `datetime.now(timezone.utc)` (เคยมี bug ใน draft)
2. ห้ามฮาร์ดโค้ด model — ใช้ `settings.GROQ_MODEL`
3. เรียก LLM ล้มทุก key → คืน None ไม่ write ทับ skills เดิม (fail-safe)
4. `SystemPreference.value` เป็น JSON column — เก็บ dict ได้ทั้ง SQLite/Postgres

## ไฟล์
`backend/app/services/hermes_brain.py`, `tools/hermes_brain.py`, `backend/app/models.py`
(SystemPreference, DirectOrder), `backend/app/api/facebook_radar.py` (consumer), `MARKET_MEMORY.md` (diary)

## เทสต์
`backend/tests/test_hermes_brain.py` (mock `groq_clients` — ไม่แตะเน็ต)
