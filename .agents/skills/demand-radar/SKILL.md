---
name: demand-radar
description: >-
  Social Demand Radar V1 (บอทป้าเข็ม): วิเคราะห์โพสต์กลุ่ม Facebook → demand score →
  จับคู่สินค้า → auto-post ขึ้นเพจ + บันทึก Google Sheets. Covers facebook_radar.py,
  demand_radar_ai.py, product_matcher.py. Use whenever the user mentions เรดาร์,
  demand score, facebook-radar, leads, แมตช์สินค้า, cooldown, or auto-post.
---

# Social Demand Radar V1

## โฟลว์
`POST /api/admin/facebook-radar/leads` → dedupe → `analyze_lead_intent_and_demand()`
(demand_score 0-100, urgency, budget, keyword, intent) → ผ่านเกณฑ์
(`is_high_demand >= radar_min_score` — Hermes ปรับได้) → `match_best_product_for_demand()`
→ เจอสินค้า → `post_feed()` ขึ้นเพจทันที + บันทึก Sheets (`POSTS_SHEET_WEBHOOK_URL`, kind='radar')

## กฎ/Guards (สำคัญ)
- **V1 = auto-post 100%** — LINE alert ปิด (`dispatch_radar_line_alert()` คืน False เสมอ, `alerts_sent=0`)
- **โพสต์เฉพาะสินค้า `link_status='ok'`** — กฎเหล็ก (matcher filter ตั้งแต่ query)
- **Relevance Safeguard**: keyword ชัดเจนแต่ relevance < 12.0 (จากเต็ม 40) → ไม่จับคู่
  (กันยิงโพสต์มั่ว — `notification_status='failed'` มักแปลว่า "จับคู่สินค้าไม่ได้" ไม่ใช่บั๊ก)
- **Cooldown 24 ชม. ต่อหมวด** (`RADAR_CATEGORY_COOLDOWN_HOURS`) + **limit รายวัน**
  (`RADAR_MAX_DAILY_POSTS` default 5) — นับจาก `facebook_demand_events.notification_status in (posted,sent)`
  **ไม่ใช้ CampaignLog** → สินค้าตัวเดียวโพสต์ซ้ำได้จาก 2 flow (รู้ไว้)
- โดนบล็อก cooldown/limit → บันทึก `notification_status='ignored'`, response status='ignored'

## Match Score (product_matcher.py)
Relevance 40% + Rating 20% + Sales 20% + Commission 10% + Budget Fit 10% (0-100);
`generate_suggested_reasons()` สร้างเหตุผลเชิงประจักษ์ (รีวิว/ยอดขาย/งบ/คอม/ลิงก์ OK)

## Demand AI (demand_radar_ai.py)
- Multi-provider LLM (groq→anthropic→gemini→openai) + heuristic fallback
  (`_heuristic_demand_analysis`: rule-based, SCAM_WARNING_PATTERNS → score 15, intent spam)
- `parse_post_budget()` รองรับ "ไม่เกิน 500" / "300-500" / "งบสองพัน" (เลขไทย)
- `_nfc()` (สระอำ) + `normalize_query()` (คำพ้อง) ก่อน match

## กับดัก
1. เทสต์โพสต์จริง ต้องเลือกคีย์เวิร์ดที่มีของในคลัง: "ชุดคลุมท้อง" = 0 ตัว vs "หูฟัง" = 123 ตัว
   (`SELECT count(*) FROM products WHERE link_status='ok' AND name ILIKE '%…%'`)
2. `scored_candidates.sort` ใช้ `reverse=True` — ตรวจ tuple ลำดับ (score, sales, ai_score) เมื่อแก้
3. `lead_id` FK จำเป็นตอน insert FacebookDemandEvent — เทสต์ต้อง seed FacebookDetectedLead ก่อน

## ไฟล์
`backend/app/api/facebook_radar.py`, `services/demand_radar_ai.py`, `services/product_matcher.py`,
`admin_dashboard.py` (radar feed/cooldown)

## เทสต์
`backend/tests/test_facebook_demand_radar.py` (19 scenarios), `test_facebook_radar_api.py`,
`test_demand_radar_ai.py` — mock วิเคราะห์ทั้งหมด กัน rate limit 429
