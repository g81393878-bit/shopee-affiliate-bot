# 📘 คู่มือมาตรฐานการขายและการติดตั้ง AI Bot อย่างมืออาชีพ (PaKhem Bot Sales & Deployment Playbook)

**เวอร์ชัน:** 1.0 (Production Ready)  
**สำหรับ:** เจ้าของระบบ, ฝ่ายขาย, และวิศวกรติดตั้ง (DevOps)  
**ระบบ:** Shopee Affiliate AI Bot Platform

---

## 📑 สารบัญ
1. [โครงสร้างแพ็กเกจและจุดขายหลัก (Product Tiers & USP)](#1-โครงสร้างแพ็กเกจและจุดขายหลัก)
2. [สคริปต์การขายและการปิดการขาย (Sales Script & Closing)](#2-สคริปต์การขายและการปิดการขาย)
3. [ขั้นตอนการรับลูกค้าใหม่ (Client Onboarding Checklist)](#3-ขั้นตอนการรับลูกค้าใหม่)
4. [คู่มือการติดตั้งลูกค้ารายเดือน (Multi-Tenant บน VPS เรา)](#4-คู่มือการติดตั้งลูกค้ารายเดือน)
5. [คู่มือการติดตั้งลูกค้าซื้อขาด (Dedicated VPS ลูกค้า)](#5-คู่มือการติดตั้งลูกค้าซื้อขาด)
6. [การส่งมอบงานและการดูแลหลังการขาย (Handover & SLA)](#6-การส่งมอบงานและการดูแลหลังการขาย)

---

## 1. โครงสร้างแพ็กเกจและจุดขายหลัก

| ระดับแพ็กเกจ | ราคา | กลุ่มเป้าหมาย | ฟีเจอร์ที่ได้รับ |
| :--- | :--- | :--- | :--- |
| 🟡 **Lean** | **490฿ / เดือน** | ผู้เริ่มต้น, งบน้อย | • บอท LINE OA ตอบค้นหาสินค้าจากคลัง 2,400+ รายการ<br>• ระบบรับรหัสตัวเลขจากคลิป (0.1 วินาที)<br>• ส่งการ์ด Shopee Flex Message สวยงาม |
| 🟢 **Starter** | **990฿ / เดือน** | ร้านค้าที่เริ่มมีฐานลูกค้า | • ฟีเจอร์ทั้งหมดใน Lean<br>• สมองกล AI Groq ตอบคำถามทั่วไป + ทักทายสุภาพ<br>• แดชบอร์ดสถิติแอดมิน + ระบบดึงโปรไฟล์ลูกค้า |
| 🔵 **Business** | **1,990฿ / เดือน** | ครีเอเตอร์, คนทำ Affiliate จริงจัง | • ฟีเจอร์ทั้งหมดใน Starter<br>• **โรงงานผลิตคลิป Reels อัตโนมัติ** 9:16 Full HD + เสียงพากย์ไทย TTS<br>• AI แต่งสคริปต์ไวรัล 3 วินาที (ไม่พูดราคา Evergreen) |
| 🟣 **White-Label** | **4,990฿ / เดือน** | แบรนด์, ธุรกิจครบวงจร | • ฟีเจอร์ทั้งหมดใน Business<br>• **กระจายโพสต์ 4 แพลตฟอร์มพร้อมกันทุก 30 นาที** (Facebook 3 เพจ + YouTube Shorts)<br>• ปรับแต่งแบรนด์, โลโก้, สี และน้ำเสียงพากย์เฉพาะตัว |
| 🟠 **ซื้อขาด (Source Code)** | **15,000 – 25,000฿** | บริษัท, นักลงทุน | • ส่งมอบ Source Code ทั้งระบบ 100%<br>• ติดตั้งบน Dedicated VPS ส่วนตัวของลูกค้า<br>• ไม่มีค่าบริการรายเดือน ไม่จำกัดข้อความ |

### 💎 จุดขายเด่น (Unique Selling Points - USP):
1. **ตอบไว 0.1 วินาที:** รับรหัสตัวเลขจากคลิปปุ๊บ ส่งลิงก์ซื้อ Shopee ปั๊บ ไม่ต้องให้ลูกค้ารอ
2. **คลิป Evergreen ไร้ราคา:** สคริปต์คลิปไม่มีวันหมดอายุเมื่อ Shopee เปลี่ยนโปรโมชั่น
3. **ระบบ Watchdog 24 ชม.:** มีระบบกู้คืนตัวเองและซิงค์ Webhook อัตโนมัติ บอทไม่มีวันดับ
4. **ศูนย์สั่งการ Telegram:** เจ้าของร้านตอบแชทลูกค้า LINE จาก Telegram ได้โดยตรง

---

## 2. สคริปต์การขายและการปิดการขาย

### 💬 เมื่อลูกค้าทักมาถาม: *"บอททำอะไรได้บ้าง / ราคาเท่าไหร่"*
> **ข้อความตอบกลับ:**  
> "สวัสดีครับคุณ [ชื่อลูกค้า] 😊 บอทของเราเป็นระบบ **AI ช่วยขายของ Shopee Affiliate แบบครบวงจร 24 ชม.** ครับ  
> 1. ช่วยผลิตคลิปวิดีโอสั้น Reels/Shorts พร้อมเสียงพากย์ไทยอัตโนมัติ  
> 2. โพสต์ลง Facebook และ YouTube ให้ตามรอบเวลา  
> 3. มีบอท LINE OA ปิดการขาย ส่งลิงก์ Shopee ของคุณให้ลูกค้าทันทีเมื่อเขาพิมพ์รหัสสินค้าครับ  
> 
> มีให้เลือกตั้งแต่เริ่มต้นเพียง **490 บาท/เดือน** (หรือแพ็กเกจยอดนิยม Business **1,990 บาท/เดือน** ที่มีระบบผลิตคลิปให้ครบ) สนใจแพ็กเกจประมาณไหน ให้แอดมินแนะนำได้เลยครับ ✨"

---

### 💳 เมื่อลูกค้าตัดสินใจซื้อ / ขอเลขบัญชี:
> **ข้อความส่งเลขบัญชี:**  
> "ยินดีต้อนรับครับคุณ [ชื่อลูกค้า] 🎉  
> สามารถชำระเงินตามยอดแพ็กเกจที่เลือกได้ที่:  
> 
> 🏦 **ธนาคารกรุงไทย**  
> • เลขที่บัญชี: **038-025-3631**  
> • ชื่อบัญชี: **จีรวัฒน์ พลอาจ**  
> 📱 **พร้อมเพย์:** `0935325959`  
> 
> โอนเงินเรียบร้อยแล้ว แนบรูปสลิปเข้ามาในห้องแชทนี้ได้เลยครับ แอดมินจะเริ่มตั้งค่าระบบให้ทันที ใช้เวลาประมาณ 5-10 นาทีพร้อมใช้งานครับ 🙏"

---

## 3. ขั้นตอนการรับลูกค้าใหม่ (Client Onboarding Checklist)

เมื่อลูกค้าชำระเงินแล้ว ให้ส่งแบบฟอร์มนี้ให้ลูกค้ากรอก:

```text
📋 แบบฟอร์มข้อมูลเปิดใช้งานบอท:
1. ชื่อแบรนด์ / ร้านค้า: ..............................
2. ลิงก์ LINE Official Account: ..............................
3. Channel Access Token (Long-lived): ..............................
4. Channel Secret: ..............................
5. รหัส Shopee Affiliate ID หรือ ลิงก์สั้นร้านค้า: ..............................
6. หมวดหมู่สินค้าที่ต้องการเน้น (เช่น เสื้อผ้า, ของใช้ในบ้าน, ไอที): ..............................
```

*(มีคู่มือภาพ 3 ขั้นตอนสอนลูกค้ากด Copy Channel Access Token จาก developers.line.biz ให้ลูกค้าดูตามได้ง่ายๆ)*

---

## 4. คู่มือการติดตั้งลูกค้ารายเดือน (Multi-Tenant บน VPS เรา)

บนเซิร์ฟเวอร์ VPS ของเรา สามารถสร้างบริการแยกของลูกค้าแต่ละรายได้ใน 3 นาที:

### ขั้นตอนที่ 1: สร้างไฟล์ Configuration ของลูกค้า
สร้างไฟล์ `/root/shopee-affiliate-bot/clients/client_{id}.env`:
```bash
# ตัวอย่าง: clients/client_somchai.env
PORT=8001
LINE_CHANNEL_ACCESS_TOKEN=โทเคน_LINE_ของลูกค้า
LINE_CHANNEL_SECRET=ซีเคร็ต_LINE_ของลูกค้า
SHOPEE_AFFILIATE_ID=รหัส_Shopee_ของลูกค้า
DATABASE_URL=postgresql://postgres.usqhvujqmnxqrdoovvnp:PV1ghsjZMwdzGDVDhF01prTM98CnGx9Q@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
```

### ขั้นตอนที่ 2: สร้าง Systemd Service สำหรับลูกค้า
สร้างไฟล์ `/etc/systemd/system/shopee-client-{id}.service`:
```ini
[Unit]
Description=Shopee Affiliate Bot for Client {id}
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/shopee-affiliate-bot
EnvironmentFile=/root/shopee-affiliate-bot/clients/client_{id}.env
ExecStart=/root/shopee-affiliate-bot/.venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port 8001
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### ขั้นตอนที่ 3: เปิดใช้งานและผูก Webhook
```bash
systemctl daemon-reload
systemctl enable --now shopee-client-{id}.service
```
นำ URL Webhook ไปวางในหน้า LINE Developers ของลูกค้า:  
`https://tale-favorite-famous-hide.trycloudflare.com/api/webhooks/line` ➜ กด **Verify** ➜ **เสร็จสิ้น 100%!**

---

## 5. คู่มือการติดตั้งลูกค้าซื้อขาด (Dedicated VPS ลูกค้า)

สำหรับแพ็กเกจ 15,000 – 25,000 บาท:

### ขั้นตอนที่ 1: เตรียม VPS ของลูกค้า (Ubuntu 22.04 / 24.04 LTS)
สเปกขั้นต่ำ: 2 vCPU, 2 GB RAM (เช่น Hetzner CPX11 เดือนละ ~180 บาท หรือ Hostinger KVM 2)

### ขั้นตอนที่ 2: รัน 1-Click Install Script
```bash
# ติดตั้ง dependencies และ clone repo
apt update && apt upgrade -y
apt install -y python3-pip python3-venv git ffmpeg nginx

git clone https://github.com/watt29/shopee-affiliate-bot.git /root/shopee-affiliate-bot
cd /root/shopee-affiliate-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
pip install -r reels_uploader/requirements.txt
```

### ขั้นตอนที่ 3: ตั้งค่า `.env` และเปิด Services
* กรอก Token LINE, Meta API, YouTube OAuth และ Supabase DB ของลูกค้า
* เปิดใช้งาน Services:
  ```bash
  systemctl enable --now shopee-backend shopee-bot tunnel-watchdog
  ```

---

## 6. การส่งมอบงานและการดูแลหลังการขาย (Handover & SLA)

### 📦 สิ่งที่ส่งมอบให้ลูกค้า:
1. **ข้อความยืนยันเปิดระบบ:**  
   > "🎉 ระบบ AI Bot ของคุณ [ชื่อร้าน] พร้อมเปิดให้บริการ 24 ชม. เรียบร้อยแล้วครับ!  
   > • 📱 ทดสอบทัก LINE พิมพ์ชื่อสินค้า หรือพิมพ์รหัสได้เลยครับ  
   > • 📊 หากต้องการปรับหมวดหมู่สินค้า ทักแจ้งแอดมินได้ตลอดเวลาครับ"
2. **การดูแลรักษารายเดือน (SLA):**
   * ตรวจเช็คสถานะ Uptime 99.9%
   * อัปเดตคลังสินค้าใหม่ทุกเดือน
   * ดูแลแก้ปัญหา Webhook และ API ฟรีตลอดอายุการเช่าใช้งาน

---
*เอกสารนี้ถือเป็นแนวทางปฏิบัติมาตรฐานสำหรับทีมงานและผู้ดูแลระบบ PaKhem Bot Platform*
