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
1. **ต้องส่ง `--once` เสมอ** — ไม่งั้นวน loop (default interval 300s) ดูเหมือน hang; ตั้งแต่
   `6a90b01` ถ้ารันโดยไม่มี `--once` จะมีคำเตือนเด่น `⚠️ LOOP MODE:` ขึ้นมา — เห็นแล้วให้รู้ว่า
   กำลังวนไม่หยุด (กด Ctrl+C หรือรันใหม่ด้วย `--once` ถึงจบ)
2. **HTTP timeout อัปเดตเป็น 60s** (`DEFAULT_TIMEOUT_SECONDS` ปรับปรุงแล้ว) — เพื่อให้เวลา AI หลังบ้านประมวลผลเรียงลำดับหลายโพสต์พร้อมกันได้เต็มที่ ป้องกัน TimeoutError
3. **Stealth Scraper (undetected_chromedriver)** — ระบบใช้ `uc` ในการปลอมแปลงลายนิ้วมือเบราว์เซอร์เพื่อหลบเลี่ยงระบบจับบอทของ Facebook
4. **การฉีด Session Cookies** — ระบบโหลดคุกกี้จากไฟล์ `fb_cookies.json` ที่โฟลเดอร์หลักของโปรเจกต์มาฉีดเข้าบราวเซอร์ก่อนเพื่อข้ามหน้าล็อกอิน
5. `notification_status='failed'` มักแปลว่า "จับคู่สินค้าในคลังไม่ได้" (matched_product_id=None)
   ไม่ใช่บั๊กโค้ด — เทสต์โพสต์จริงต้องเลือกคีย์เวิร์ดที่มีของในคลัง (ดู demand-radar skill)
6. uiautomator/UI dump (ถ้าใช้) โดน animation รบกวน — retry; อย่า dump ระหว่าง tap
7. **single-instance lock (`.fb_monitor.lock`)** — กันรัน monitor ซ้อนกัน: เจอ lock ของ
   process ที่ยังมีชีวิต → ปฏิเสธ + exit 1 (`❌ บอทสแกนอีกตัวกำลังรันอยู่แล้ว`); lock ค้างจาก
   PID ตาย → เขียนทับอัตโนมัติ; ปลด lock ทุกทางออก (Ctrl+C/error/จบ); `--lock-file ''` ปิดได้
8. **`--pid-timeout N` (นาที)** — ทำลาย lock ที่ process ถือค้างเกิน N นาที (คาดว่า hung)
   เพื่อให้เริ่มใหม่ได้โดยไม่ต้องลบ lock มือ; default 0 = ปิด
9. **Chrome สิ้นซาก** — `_kill_chrome_tree()` หลัง `driver.quit()` ใช้ `taskkill /PID /T /F`
   ฆ่าทั้ง process tree (chrome.exe + undetected_chromedriver.exe) กันซากค้าง;
   `_sweep_orphan_drivers()` กวาดซากจากรอบที่โดน hard-kill ตอนสตาร์ท (เฉพาะโหมด scrape จริง,
   ไม่แตะ Chrome ของ user)

## Lock & PID timeout (กันรันซ้อน / กัน lock ค้าง)
- **`--lock-file`** — path ของ lock file (default `.fb_monitor.lock`); ส่ง `''` เพื่อปิด
- **`--pid-timeout N`** — ถ้า lock ถูกถือโดย process ที่ยังมีชีวิตแต่อายุเกิน N นาที
  (ตรวจ `_process_age_seconds()`: PowerShell CIM บน Windows / `ps etimes` บน Unix,
  คืน invariant culture กัน locale ทำตัวเลขเพี้ยน) → เขียนทับและเริ่มใหม่ พร้อมข้อความ
  `⏰ lock ของ PID ... อายุเกิน N นาที (คาดว่า hung)`
- ตัวอย่าง: `python tools/fb_group_monitor_local.py --once --pid-timeout 10`

## Usage
```bash
python tools/fb_group_monitor_local.py --once            # สแกน 1 รอบ แล้วจบ
python tools/fb_group_monitor_local.py --sample --dry-run # ดูผลโดยไม่ส่ง backend
python tools/fb_group_monitor_local.py --once --pid-timeout 10  # เตะ lock ที่ค้างเกิน 10 นาที
```

## ไฟล์
`tools/fb_group_monitor_local.py`; ฝั่งรับ = `backend/app/api/facebook_radar.py`

## เทสต์
`backend/tests/test_fb_group_monitor_local.py`
