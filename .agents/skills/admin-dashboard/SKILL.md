---
name: admin-dashboard
description: >-
  Admin web dashboard (backend/app/api/admin_dashboard.py + static/admin.html): HMAC cookie
  auth (pkh_admin), stats from real tables, product list/filter/update/delete, radar feed.
  Use whenever the user mentions /admin, แดชบอร์ด, แอดมิน, pkh_admin, สถิติ, ลบสินค้า,
  or "การ์ดยังไม่มีคอนเทนต์".
---

# Admin Dashboard

## Auth (ห้ามแก้ semantics)
- `GET /admin` → หน้า dashboard (ไฟล์เดียว vanilla JS, ไม่มี build step)
- `POST /admin/login` (รหัสผ่าน = env `ADMIN_DASHBOARD_PASSWORD`; ถ้าไม่ตั้ง fallback `CRON_TOKEN`;
  ไม่ตั้งทั้งคู่ → dashboard ปิด 503) → HMAC cookie `pkh_admin` อายุ 7 วัน
- `GET /api/admin/*` ต้องมี cookie → 401 ถ้าไม่มี; `POST/DELETE` บางตัวรับ `X-Admin-Token`/`?token=`
  (radar ใช้ `require_admin_auth`)
- **รหัสผ่าน/credential เปลี่ยน ต้องอัปเดตทั้ง 2 ที่**: Windows user env + backend/.env
  (load_dotenv ไม่ override env ที่ตั้งไว้แล้ว)

## ตัวเลขสถิติ = จากตารางจริง (ไม่มีตัวเลขมโน)
- `sellable` = link_status='ok' + sales_count ≥ MIN_SALES
- `no_content` = total − distinct product_id ใน `contents` (การ์ด "ยังไม่มีคอนเทนต์")
- `dead` / `hidden` (suspect) / `users` / today chats/searchers — query จริงทุกตัว
- radar feed/cooldown — `GET /api/admin/radar/feed` + `/cooldown` (นับจาก facebook_demand_events)

## กับดัก
1. แก้หน้า admin.html ระวัง syntax error ที่ทำพังทั้งหน้า (เจอจริง: emoji ใน JS block ทำพังบน Render —
   เคยต้อง revert ทั้งไฟล์) — หลังแก้ ให้ทดสอบ JS ผ่าน (node/เทสต์) ก่อน push
2. `datetime.now` ต้อง timezone-aware (เคยเจอ AttributeError/cooldown เพี้ยนจาก naive)
3. ลบสินค้าผ่าน dashboard = cascade ลบ contents/product_analysis — เจตนา (ไม่ใช่บั๊ก)

## ไฟล์
`backend/app/api/admin_dashboard.py`, `backend/app/static/admin.html`

## เทสต์
`backend/tests/test_facebook_radar_api.py` (mock radar AI); เทสต์ auth 401 ใน test ต่าง ๆ
