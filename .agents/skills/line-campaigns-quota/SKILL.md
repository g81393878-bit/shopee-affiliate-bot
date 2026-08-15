---
name: line-campaigns-quota
description: >-
  LINE push campaigns: แจ้งราคาตก (price drop), re-engage ลูกค้าเงียบ, daily report,
  และ push quota guard (line_quota). Use when the user mentions แจ้งราคาลง, re-engage,
  ลูกค้าเงียบ, daily report, quota, push ข้อความ, or campaign spam control.
---

# LINE Campaigns & Push Quota

## แคมเปญ push (ทุกตัวนับ quota!)
- LINE **reply ไม่นับ quota** แต่ **push นับ** (ต้อนรับแอดเพื่อน / แจ้งราคาลง / re-engage /
  แคมเปญ / รายงานประจำวัน) — แผนฟรี ~500 ข้อความ/เดือน
- `line_quota.push_guard(db)` ใช้ก่อน push ทุกครั้ง: เหลือ ≤0 → บล็อก; เหลือ ≤ warn_left
  (env `PUSH_QUOTA_WARN_LEFT` default 30) → แจ้งแอดมิน (dedupe ผ่าน campaign_logs
  category `_quota` 1 ครั้ง/24 ชม.) แล้วยัง push ต่อ; ตรวจไม่ได้ (mock/dev) → ไม่บล็อก
- quota ตรวจผ่าน LINE API `/v2/bot/message/quota` — `type=none` = แผนไม่จำกัด

## ฟีเจอร์
1. **แจ้งราคาตก**: cron `refresh-prices` ราคาลด ≥ `PRICE_DROP_PCT` (default 5%) → push
   หาลูกค้าที่เคยสนใจหมวดนั้น (จำกัดคน/ตัว กันสแปม)
2. **re-engage**: cron `re-engage` push ของใหม่หมวดที่เคยสนใจให้ลูกค้าเงียบ ≥7 วัน
   (จำกัด limit/รอบ)
3. **daily-report**: สรุปยอด/สินค้า/ลูกค้าให้เจ้าของร้าน

## กับดัก
- แคมเปญใช้ `CampaignLog` (status='sent'/'pricedrop'/'reengage') กันซ้ำ — แต่ radar
  auto-post **ไม่ใช้** CampaignLog (ใช้ facebook_demand_events.notification_status แทน)
  → สินค้าตัวเดียวอาจโพสต์ซ้ำจาก 2 flow ได้ (รู้ไว้ อย่า "แก้" โดยไม่ตั้งใจ)
- push ห้ามทำใน request cycle ของลูกค้า — ใช้ daemon thread / cron เสมอ กัน LINE timeout

## ไฟล์
`backend/app/services/line_quota.py`, `backend/app/api/cron.py` (refresh-prices/re-engage/daily-report),
`backend/app/api/line_bot.py` (`_campaign_targets`/`_campaign_products`/`handle_campaign`)

## เทสต์
`backend/tests/test_price_refresh.py` + `test_line_bot.py` (mock push_guard → True ใน conftest)
