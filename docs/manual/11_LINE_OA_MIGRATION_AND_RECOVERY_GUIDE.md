# 📘 คู่มือการย้ายระบบ LINE OA และ Webhook สู่ Cloud VPS แบบสมบูรณ์
## ฉบับปฏิบัติการจริง — ขั้นตอนทีละสเต็ป, ปัญหาที่พบ (Pitfalls) และแนวทางแก้ไข 100%

> **Google Docs ฉบับทางการ:** [เปิดดูบน Google Docs](https://docs.google.com/document/d/1l4K93dOnGu3eRHPISL-xKgIuSuq-jgr2d5GayZYcnIY/edit)

---

## 🏛️ บทที่ 1: ภาพรวมสถาปัตยกรรมระบบ LINE OA Webhook (Architecture Overview)

ระบบ LINE Official Account (ป้าเข็ม ขายของ / `@137gsref`) ถูกออกแบบขึ้นภายใต้สถาปัตยกรรม **"Always-On Zero-Cost Webhook"** เพื่อให้สามารถตอบแชทลูกค้า ค้นหาสินค้าจากฐานข้อมูลกว่า 2,472 รายการ และปิดการขายแพ็กเกจ SaaS ได้ตลอด 24 ชั่วโมง โดยไม่ต้องเปิดเครื่องคอมพิวเตอร์ทิ้งไว้

ระบบบน Cloud VPS ทำงานร่วมกัน 3 องค์ประกอบหลัก (**3-Pillar Unified Stack**):

1. **FastAPI Backend Service (`shopee-backend.service`):**
   - รันผ่าน Uvicorn ASGI Server บนพอร์ต 8000
   - รับคำขอ Webhook จาก LINE Platform ตรวจสอบ Signature (`X-Line-Signature`)
   - เชื่อมต่อฐานข้อมูล Supabase PostgreSQL ผ่าน Transaction Pooler (พอร์ต 6543)
   - ค้นหาสินค้า รองรับรหัสสินค้าตรงตัว (เช่น พิมพ์ `86`, `1628`) และตอบกลับด้วย LINE Flex Message
   - สลับเรียกใช้งาน Groq AI Multi-Key (7 Keys Failover) สำหรับการสนทนาทั่วไป
2. **Cloudflare HTTPS Tunnel (`cloudflared-tunnel.service`):**
   - รันโปรแกรม Cloudflared ทำหน้าที่สร้างอุโมงค์ปลอดภัยเชื่อมโยง Port 8000 บน Localhost ของ VPS ไปยังเครือข่ายระดับโลกของ Cloudflare
   - ให้บริการ HTTPS SSL Certificate ที่ได้มาตรฐานความปลอดภัยของ LINE โดยไม่ต้องเปิดพอร์ต 80 หรือ 443 ที่ไฟร์วอลล์ และไม่ต้องจดทะเบียนโดเมนเนมแบบเสียค่าใช้จ่าย
3. **Tunnel URL Watchdog Service (`tunnel-watchdog.service`):**
   - ทำหน้าที่เฝ้าระวังเบื้องหลังตลอด 24 ชม. โดยตรวจสอบ URL ของ Cloudflare ทุกๆ 15 วินาที
   - หาก URL เกิดการเปลี่ยนแปลง (เช่น เซิร์ฟเวอร์รีบูต หรือ Tunnel หลุดชั่วคราว) ระบบจะส่งคำขอ PUT ไปยัง LINE Messaging API เพื่ออัปเดต Webhook Endpoint ทันทีในระดับวินาที
   - ส่งข้อความแจ้งเตือนสถานะ URL ใหม่เข้า Telegram Commander (`@pakhem_commander_bot`) อัตโนมัติ

```text
[ลูกค้าพิมพ์แชท LINE] 
       ▼
[LINE Platform Server]
       ▼ (HTTPS Webhook)
[Cloudflare Tunnel (*.trycloudflare.com)]
       ▼ (Proxy to Port 8000)
[Uvicorn / FastAPI Backend]
       ▼ 
[Supabase Pooler (ค้นหาสินค้า 2,472 ชิ้น) + Groq AI]
       ▼ (LINE Messaging Reply API)
[ส่งข้อความ / Flex Message ตอบกลับลูกค้าใน 0.1 - 0.5 วินาที]
```

---

## 📋 บทที่ 2: สิ่งที่ต้องเตรียมความพร้อมก่อนย้าย (Prerequisites & Requirements)

1. **สเปกเซิร์ฟเวอร์ VPS ปลายทางที่แนะนำ:**
   - **ระบบปฏิบัติการ:** Ubuntu 22.04 LTS หรือ Ubuntu 24.04 LTS x64
   - **ซีพียู:** ขั้นต่ำ 1 vCPU (แนะนำ 1-2 vCPU)
   - **หน่วยความจำ (RAM):** ขั้นต่ำ 2 GB ขึ้นไป
   - **พื้นที่ดิสก์ (SSD):** ขั้นต่ำ 20 GB
   - **การเปิด Swap Memory:** แนะนำให้ตั้งค่า Swapfile ขนาด 4.0 GB เพื่อรองรับการประมวลผลสูงสุด ป้องกัน Linux OOM Killer ตัดโปรเซส
2. **การเชื่อมต่อและความปลอดภัย:**
   - บัญชี Root หรือ User ที่มีสิทธิ์ sudo
   - ติดตั้ง Local SSH Public Key (`~/.ssh/id_ed25519.pub`) เข้าไปยัง `/root/.ssh/authorized_keys` ของ VPS
3. **ไฟล์คอนฟิกและ Environment Variables (`backend/.env`):**
   - `DATABASE_URL`: URL สำหรับเชื่อมต่อ Supabase PostgreSQL Transaction Pooler (`aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres`)
   - `LINE_CHANNEL_ACCESS_TOKEN`: โทเค็นระยะยาวของ LINE Official Account
   - `LINE_CHANNEL_SECRET`: คีย์ลับสำหรับตรวจสอบ Signature ความปลอดภัยของ LINE
   - `TELEGRAM_BOT_TOKEN`: โทเค็นของบอทสั่งการหลังบ้าน (`@pakhem_commander_bot`)
   - `TELEGRAM_CHAT_ID`: ไอดีห้องแชทของแอดมิน (`6734965582`)
   - `GROQ_API_KEY`: คีย์ Groq AI Multi-Key

---

## 🚀 บทที่ 3: ขั้นตอนการย้ายระบบทีละสเต็ป (Step-by-Step Migration Execution)

### ขั้นตอนที่ 3.1: การเตรียมเครื่อง VPS ปลายทางและการติดตั้งสภาพแวดล้อม
```bash
apt update && apt upgrade -y
apt install -y git curl wget build-essential python3 python3-venv python3-pip

# สร้าง Swap Memory 4.0 GB
fallocate -l 4G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

### ขั้นตอนที่ 3.2: การโคลนโค้ดโปรเจกต์และการสร้าง Python Virtualenv
```bash
cd /root
git clone https://github.com/g81393878-bit/shopee-affiliate-bot.git
cd /root/shopee-affiliate-bot

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
pip install uvicorn fastapi httpx psycopg2-binary pythainlp python-dotenv
```

### ขั้นตอนที่ 3.3: การติดตั้ง Cloudflared Binary บนเซิร์ฟเวอร์
```bash
curl -L --output /tmp/cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
dpkg -i /tmp/cloudflared.deb
cloudflared --version
```

### ขั้นตอนที่ 3.4: การคัดลอกไฟล์ Environment (.env) สู่ VPS ปลายทาง
```bash
# รันบนเครื่องคอมพิวเตอร์ของคุณ
scp backend/.env root@<VPS_IP>:/root/shopee-affiliate-bot/backend/.env
```

### ขั้นตอนที่ 3.5: การสร้าง Systemd Service Units 3 ตัวหลัก

#### 1. ไฟล์ `/etc/systemd/system/shopee-backend.service`:
```ini
[Unit]
Description=Shopee Affiliate FastAPI Backend
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/shopee-affiliate-bot
ExecStart=/root/shopee-affiliate-bot/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

#### 2. ไฟล์ `/etc/systemd/system/cloudflared-tunnel.service`:
```ini
[Unit]
Description=Cloudflare HTTPS Tunnel for LINE Webhook
After=network.target shopee-backend.service

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/cloudflared tunnel --protocol http2 --url http://127.0.0.1:8000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

#### 3. ไฟล์ `/etc/systemd/system/tunnel-watchdog.service`:
```ini
[Unit]
Description=Cloudflare Tunnel URL Watchdog (Auto-sync LINE Webhook)
After=cloudflared-tunnel.service network.target
Requires=cloudflared-tunnel.service

[Service]
Type=simple
WorkingDirectory=/root/shopee-affiliate-bot
EnvironmentFile=/root/shopee-affiliate-bot/backend/.env
ExecStart=/root/shopee-affiliate-bot/.venv/bin/python tools/tunnel_watchdog.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
```

### ขั้นตอนที่ 3.6: การเริ่มระบบและตรวจสอบความสมบูรณ์ (Verification)
```bash
# 1. เริ่มบริการทั้งหมด
systemctl enable --now shopee-backend cloudflared-tunnel tunnel-watchdog

# 2. ตรวจสอบสถานะ
systemctl status shopee-backend cloudflared-tunnel tunnel-watchdog --no-pager

# 3. ตรวจสอบบันทึกการซิงค์ URL
journalctl -u tunnel-watchdog --no-pager -n 20

# 4. ทดสอบความพร้อมผ่าน Health Check
curl -s https://<tunnel_url>.trycloudflare.com/health
# ตอบกลับ: {"status":"ok"}
```

### ขั้นตอนที่ 3.7: การปิดบริการและล้างข้อมูลบน VPS เดิม (Safe Decommissioning)
> [!CAUTION]
> ต้องสั่งปิดระบบเดิมทันทีที่ระบบใหม่พร้อมใช้งาน เพื่อป้องกัน **Split-Brain Webhook Conflict** (สองเซิร์ฟเวอร์แย่งกันอัปเดต Webhook ทับกันไปมา)

```bash
# สั่งหยุดและลบบริการบน VPS เก่า
ssh root@<OLD_VPS_IP> "systemctl stop shopee-backend cloudflared-tunnel tunnel-watchdog && systemctl disable shopee-backend cloudflared-tunnel tunnel-watchdog"
ssh root@<OLD_VPS_IP> "rm -f /etc/systemd/system/shopee-backend.service /etc/systemd/system/cloudflared-tunnel.service /etc/systemd/system/tunnel-watchdog.service && systemctl daemon-reload && systemctl reset-failed"

# ลบโฟลเดอร์โปรเจกต์และไฟล์ข้อมูล Shopee บน VPS เก่า
ssh root@<OLD_VPS_IP> "rm -rf /root/shopee-affiliate-bot /root/affiliate_db.db"
```

---

## ⚠️ บทที่ 4: ปัญหาที่พบบ่อย (Pitfalls) จากหน้างานจริง และวิธีแก้ไข 100%

### ปัญหาที่ 1: บอทเงียบ / Cloudflare สุ่ม URL ใหม่แล้ว LINE Webhook หลุด
- **สาเหตุ:** Quick Tunnel (`trycloudflare.com`) สุ่มสร้างซับโดเมนใหม่เมื่อเชื่อมต่อใหม่ ทำให้ Webhook เดิมตาย
- **วิธีแก้:** เปิดใช้งาน `tunnel-watchdog.service` ตลอด 24 ชม. ตรวจจับและยิง PUT API อัปเดตไปยัง LINE ภายใน 15 วินาทีอัตโนมัติ

### ปัญหาที่ 2: สองเซิร์ฟเวอร์แย่งกันอัปเดต Webhook (Split-Brain Conflict)
- **สาเหตุ:** ไม่ได้ปิด Watchdog บน VPS เก่า ทำให้เครื่องเดิมยังคงพยายามยิงอัปเดต URL เก่าทับกับ URL ใหม่
- **วิธีแก้:** ต้องรัน `systemctl disable --now ...` และลบ service ออกจาก VPS เก่าทันที

### ปัญหาที่ 3: ฐานข้อมูลชนขีดจำกัดการเชื่อมต่อ (Supabase Connection Exhaustion)
- **สาเหตุ:** ใช้ Direct Connection พอร์ต 5432
- **วิธีแก้:** ใช้ Supabase Transaction Pooler พอร์ต **6543** (`?pgbouncer=true`) เสมอ

### ปัญหาที่ 4: Cloudflared เชื่อมต่อไม่ติด (QUIC Protocol UDP Blocked)
- **สาเหตุ:** เครือข่าย VPS บล็อก UDP พอร์ต 7844
- **วิธีแก้:** เติมแฟล็ก `--protocol http2` ใน `cloudflared-tunnel.service` เพื่อบังคับใช้อุโมงค์ TCP 443 100%

### ปัญหาที่ 5: โปรเซสดับปริศนาจากหน่วยความจำเต็ม (Linux OOM Killer)
- **สาเหตุ:** แรมจริงไม่พอเมื่อรันหลายเซอร์วิส
- **วิธีแก้:** ติดตั้ง Swapfile ขนาด 4.0 GB ป้องกันเคอร์เนลฆ่าโปรเซส

### ปัญหาที่ 6: การแจ้งเตือน Telegram ไม่ทำงานเมื่อรันเป็น Systemd Service
- **สาเหตุ:** Systemd ไม่ได้สืบทอด Environment Variables จาก Shell
- **วิธีแก้:** ระบุ `EnvironmentFile=/root/shopee-affiliate-bot/backend/.env` ในไฟล์ Unit และใส่ Hardcoded Fallback Token ใน Python

---

## 🛠️ บทที่ 5: คำสั่งลัดสำหรับการดูแลระบบ (Operations SOP)

1. **เช็คสถานะภาพรวม:**
   ```bash
   systemctl list-units --type=service --state=running | grep -E 'shopee|tunnel'
   ```
2. **ดู Live Logs:**
   ```bash
   journalctl -u shopee-backend -f
   journalctl -u tunnel-watchdog -f
   ```
3. **รีสตาร์ทบริการทั้งหมดแบบ One-Click:**
   ```bash
   systemctl restart shopee-backend cloudflared-tunnel tunnel-watchdog
   ```
4. **สั่งการผ่าน Telegram Commander (`@pakhem_commander_bot`):**
   - `/status` — เช็คสถานะสดของระบบ
   - `/stock` — ดูคลังสินค้าและคลิป
   - `/reply <user_id> <ข้อความ>` — ส่งแชทตอบลูกค้า LINE ผ่าน Telegram โดยตรง
