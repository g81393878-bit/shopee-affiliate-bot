---
name: demand-radar
description: >-
  Social Demand Radar V1 (บอทป้าเข็ม): วิเคราะห์ lead → demand score →
  auto-post promo ขึ้นเพจ + บันทึก Google Sheets. Covers facebook_radar.py,
  demand_radar_ai.py. Use whenever the user mentions เรดาร์, demand score,
  facebook-radar, leads, cooldown, or auto-post.
---

# Social Demand Radar V1

## โฟลว์
`POST /api/admin/facebook-radar/leads` → dedupe → `analyze_lead_intent_and_demand()`
(demand_score 0-100, urgency, budget, keyword, intent) → ผ่านเกณฑ์
(`is_high_demand >= radar_min_score` — Hermes ปรับได้) → `post_feed()` ขึ้นเพจทันที
+ บันทึก Sheets (`POSTS_SHEET_WEBHOOK_URL`, kind='radar')

## กฎ/Guards (สำคัญ)
- **V1 = auto-post 100%** — LINE alert ปิด (`alerts_sent=0`)
- **Pivot: ไม่จับคู่สินค้าในคลังแล้ว** — โพสต์ promo ติดตั้งบอท (`matched_product_id=None`)
- **Cooldown 24 ชม. ต่อหมวด** (`RADAR_CATEGORY_COOLDOWN_HOURS`) + **limit รายวัน**
  (`RADAR_MAX_DAILY_POSTS` default 5) — นับจาก `facebook_demand_events.notification_status in (posted,sent,pending)`
  + `CampaignLog (fbpost, fbpost_pending)` (กันหมวดถี่ข้าม flow กับ cron rotation)
- โดนบล็อก cooldown/limit → บันทึก `notification_status='ignored'`, response status='ignored'

## Demand AI (demand_radar_ai.py)
- Multi-provider LLM (groq→anthropic→gemini→openai) + heuristic fallback
  (`_heuristic_demand_analysis`: rule-based, SCAM_WARNING_PATTERNS → score 15, intent spam)
- กัน 429: ทุก LLM call ผ่าน `call_with_backoff` (retry + throttle RPM process-wide) — ดู skill llm-providers
- `parse_post_budget()` รองรับ "ไม่เกิน 500" / "300-500" / "งบสองพัน" (เลขไทย)
- `_nfc()` (สระอำ) + `normalize_query()` (คำพ้อง)

## กับดัก
1. `lead_id` FK จำเป็นตอน insert FacebookDemandEvent — เทสต์ต้อง seed FacebookDetectedLead ก่อน
2. กัน lead ทดสอบ/สแปม: `fb_sample_/fb_mock_/demo_` prefix + ลิงก์ lazada/s.shopee/shope.ee

## ไฟล์
`backend/app/api/facebook_radar.py`, `services/demand_radar_ai.py`,
`admin_dashboard.py` (radar feed/cooldown)

## เทสต์
`backend/tests/test_facebook_demand_radar.py`, `test_facebook_radar_api.py`,
`test_demand_radar_ai.py` — mock วิเคราะห์ทั้งหมด กัน rate limit 429
