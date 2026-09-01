# 🖥️ คู่มือการบริหารจัดการและ Deploy บอทบน VPS 24/7 (VPS Operations Manual)
## ฉบับสมบูรณ์ — ข้อมูลเซิร์ฟเวอร์, คำสั่งจัดการ และระบบอัตโนมัติ 5 แพลตฟอร์ม

---

## 🌟 1. ข้อมูลเซิร์ฟเวอร์ VPS (Server Specifications)

| รายการ | รายละเอียด |
| :--- | :--- |
| **IP Address** | `157.85.111.232` |
| **SSH User** | `root` (รองรับ SSH Key Authentication โดยตรง) |
| **โฟลเดอร์โปรเจกต์** | `/root/shopee-affiliate-bot` |
| **Python Virtualenv** | `/root/shopee-affiliate-bot/.venv` |
| **Systemd Service หลัก** | `shopee-bot.service` (ตัวคุมระบบผลิตและยิง 5 แพลตฟอร์ม) |
| **Systemd Backend Service** | `shopee-backend.service` (FastAPI Webhook & Admin API) |

---

## 🚀 2. ขั้นตอนการ Deploy & อัปเดตโค้ดบน VPS (1-Click Deployment)

ทุกครั้งที่มีการอัปเดตโค้ดหรือคุกกี้ใหม่ สามารถสั่งการจากเครื่อง Local ผ่าน SSH ได้ทันที:

### 2.1 ส่งคุกกี้ TikTok ล่าสุดขึ้น VPS:
```bash
scp -o StrictHostKeyChecking=no tools/tiktok_cookies.json root@157.85.111.232:/root/shopee-affiliate-bot/tools/
scp -r -o StrictHostKeyChecking=no tools/tiktok_user_data root@157.85.111.232:/root/shopee-affiliate-bot/tools/
```

### 2.2 สั่ง VPS ดึงโค้ด, ติดตั้ง Dependencies และรีสตาร์ทบอท (คำสั่งเดียวจบ):
```bash
ssh -o StrictHostKeyChecking=no root@157.85.111.232 "cd /root/shopee-affiliate-bot && git pull origin main && source .venv/bin/activate && pip install playwright && playwright install chromium && playwright install-deps && systemctl restart shopee-bot"
```

---

## ⚙️ 3. คำสั่งควบคุมระบบบน VPS (Systemd Commands)

| การทำงาน | คำสั่ง Linux บน VPS |
| :--- | :--- |
| **ตรวจสอบสถานะบอท** | `systemctl status shopee-bot` |
| **ดู Live Logs การผลิตและโพสต์คลิป** | `journalctl -u shopee-bot -f` |
| **รีสตาร์ทบอท** | `systemctl restart shopee-bot` |
| **หยุดการทำงานบอท** | `systemctl stop shopee-bot` |
| **เริ่มการทำงานบอท** | `systemctl start shopee-bot` |

---

## 🤖 4. สถาปัตยกรรมการทำงาน 5 แพลตฟอร์มบน VPS (Architecture)

เมื่อ `shopee-bot.service` รันบน VPS จะเปิดเธรดทำงานคู่ขนานอัตโนมัติ:

1. **ReelsPrebuffer**: ผลิตคลิป 9:16 Full HD + เสียงพากย์ไทย Google Female 1.28x เก็บไว้ในคลัง 3-5 คลิปเสมอ
2. **ReelsUploader**: ยิง Facebook 3 เพจ + YouTube Shorts 5 ช่อง ทุก ๆ **30 นาที**
3. **TikTokUploader**: ยิง TikTok Studio (`@healthgooddeals`) ทุก ๆ **60 นาที** (แยกเธรดอิสระ ไม่ดึงกันเอง)
4. **TelegramCommander**: สแตนด์บายรับคำสั่งโต้ตอบจากแอป Telegram (`@pakhem_commander_bot`) ตลอด 24 ชม.
5. **SystemReporter**: ส่งรายงานสรุปสุขภาพ VPS ทุกเช้า (08:00 น.) และค่ำ (20:00 น.)

---

## 📱 5. การควบคุมระยะไกลผ่าน Telegram (@pakhem_commander_bot)

คุณสามารถควบคุม VPS จากมือถือได้ตลอดเวลาโดยไม่ต้องเข้า SSH:
* `/status` ➔ ดูสถานะสดของคลังคลิป, RAM, และ Disk บน VPS
* `/post` ➔ สั่งยิงโพสต์คลิปทันที 1 รอบ
* `/produce` ➔ สั่งผลิตคลิปใหม่เพิ่ม 3 คลิป
* `/stock` ➔ เช็ครายชื่อคลิปที่รอโพสต์อยู่ในคลัง
