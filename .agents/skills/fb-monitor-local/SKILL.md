---
name: fb-monitor-local
description: >-
  Local Facebook group demand scanner (tools/fb_group_monitor_local.py): reads posts from
  FB groups and submits them to the radar leads API. Use whenever the user mentions
  สแกนกลุ่ม, fb_group_monitor, --once, ตรวจโพสต์กลุ่ม Facebook, or demand radar data source.
---

# FB Group Monitor (Local scanner)

## หลักการ
- สแกนโพสต์กลุ่ม Facebook → dedupe (SeenPostTracker, JSON state) → ส่ง
  `POST /api/admin/facebook-radar/leads` (radar วิเคราะห์ demand ต่อฝั่ง server)
- **ต้องรันบน IP บ้านจริง (Local/VPS) ไม่ใช่คลาวด์** — เลี่ยงการถูกจำกัดของเซิร์ฟเวอร์คลาวด์
  (Read-only monitoring ตามข้อกำหนดแพลตฟอร์ม; ไม่รับประกัน 100% ปลอดภัย/ไม่ต้อง login)

## กับดัก (เจอจริง)
1. **ต้องส่ง `--once` เสมอ** — ไม่งั้นวน loop (default interval 300s) ดูเหมือน hang
2. **HTTP timeout ฝังตาย 15s** (`DEFAULT_TIMEOUT_SECONDS` ไม่มี flag) → เรียก production
   (Groq + FB post >15s) จะ TimeoutError ทั้งที่ server ทำงานเสร็จ — ส่งเองด้วยสคริปต์ timeout 60s
3. `notification_status='failed'` มักแปลว่า "จับคู่สินค้าในคลังไม่ได้" (matched_product_id=None)
   ไม่ใช่บั๊กโค้ด — เทสต์โพสต์จริงต้องเลือกคีย์เวิร์ดที่มีของในคลัง (ดู demand-radar skill)
4. uiautomator/UI dump (ถ้าใช้) โดน animation รบกวน — retry; อย่า dump ระหว่าง tap

## Usage
```bash
python tools/fb_group_monitor_local.py --once            # สแกน 1 รอบ แล้วจบ
python tools/fb_group_monitor_local.py --sample --dry-run # ดูผลโดยไม่ส่ง backend
```

## ไฟล์
`tools/fb_group_monitor_local.py`; ฝั่งรับ = `backend/app/api/facebook_radar.py`

## เทสต์
`backend/tests/test_fb_group_monitor_local.py`
