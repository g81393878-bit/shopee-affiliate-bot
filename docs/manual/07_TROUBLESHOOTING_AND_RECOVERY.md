# 🛠️ คู่มือที่ 7: ตารางแก้ปัญหาฉุกเฉินและการกู้คืนระบบ (Complete Troubleshooting Matrix)

---

## 📋 1. ตารางวิเคราะห์และแก้ไขปัญหา (Troubleshooting Matrix)

| อาการ / ปัญหา | สาเหตุหลัก | วิธีแก้ปัญหาทีละขั้นตอน |
| :--- | :--- | :--- |
| **YouTube ขึ้น `access_denied` / OAuth 403** | Google Cloud Console อยู่ในสถานะ Testing และยังไม่ได้เพิ่มอีเมลเจ้าของช่องลงในรายชื่อ Test Users | ไปที่ Google Cloud Console > APIs & Services > OAuth consent screen > เลื่อนลงไปที่ `Test users` > กด `+ ADD USERS` > ใส่อีเมลเจ้าของช่อง แล้วกด `SAVE` |
| **YouTube ขึ้น `403 YouTube Data API v3 has not been used`** | ยังไม่ได้เปิดใช้งาน (Enable) YouTube Data API v3 ใน Google Cloud Project | ไปที่ Google Cloud Console > APIs & Services > Library > ค้นหา `YouTube Data API v3` แล้วกดปุ่มสีน้ำเงิน `ENABLE` |
| **Facebook โพสต์ไม่ติด / Token Expired (Error 190)** | Page Access Token ของ Facebook หมดอายุ | ดึง User Token จาก Graph API Explorer แล้วรัน `python tools/exchange_fb_token.py` เพื่อต่ออายุเป็น Long-Lived Token 60 วัน |
| **TikTok โพสต์ไม่ติด / Session หลุด** | Cookie เซสชันของ TikTok บนหน้าเว็บหมดอายุ | รัน `python tools/tiktok_studio_uploader.py --add-account <N>` บนเครื่องเพื่อล็อกอินใหม่ แล้วส่งไฟล์ `tiktok_cookies_<N>.json` ขึ้น VPS |
| **บอทเงียบ / ไม่ตอบ LINE Webhook** | IP หรือ URL ของ Cloudflare Tunnel เปลี่ยนแปลง | ระบบมี `tunnel-watchdog.service` ตรวจจับและซิงค์ Webhook ให้อัตโนมัติทุก 15 วินาที หรือรันคำสั่ง `systemctl restart tunnel-watchdog` |
| **คลังคลิปค้าง / ต้องการล้างของเก่า** | มีคลิปเวอร์ชันเดิมค้างในโฟลเดอร์ | รันคำสั่ง `ssh root@119.10.140.161 "rm -rf reels_uploader/pending_videos/*.mp4 && systemctl restart shopee-bot"` บอทจะเริ่มผลิตชุดใหม่ทันที |
| **`UnboundLocalError: local variable 'pending'`** | รัน `uploader.py --video` โดยตัวแปร `pending` อยู่ในบล็อก `else` | อัปเดต `uploader.py` ให้ประกาศ `pending = []` ตั้งแต่ต้นฟังก์ชัน (แก้แล้วในเวอร์ชันล่าสุด) |
| **YouTube ยิงไม่ครบ 6 ช่องเมื่อสั่งยิงด่วน** | ตัวอัปโหลด YouTube อยู่ในโหมดหมุนเวียน (Rotation) โดยค่าเริ่มต้น | เติมพารามิเตอร์ `--all-yt` ใน `uploader.py` หรือใช้ `--broadcast-all` ใน `youtube_uploader.py` |
| **`python: can't open file 'tools/...': No such file`** | Command Prompt รันอยู่ที่ไดรฟ์ C: (`C:\Users\...`) | พิมพ์ `d:` และ `cd \Shopee_Web_Scraping` ก่อนรันคำสั่ง หรือรันผ่าน `start_system.bat` / `post_all.bat` |

---

## 🔄 2. คำสั่งกู้คืนและล้างระบบแบบ One-Click

หากระบบมีปัญหา ให้ใช้คำสั่งมาตรฐานนี้เพื่อรีสตาร์ทบริการทั้งหมดบน VPS:
```bash
ssh root@119.10.140.161 "systemctl restart shopee-bot && systemctl restart tunnel-watchdog"
```\n