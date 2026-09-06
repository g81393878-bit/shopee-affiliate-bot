# 🐧 คู่มือการติดตั้งโปรเจกต์ ป้าเข็ม ขายของ บน Ubuntu Linux ฉบับสมบูรณ์
## เริ่มต้นตั้งแต่ศูนย์ (Zero to Production Master Guide) — คำสั่งทีละสเต็ป, ปัญหา อุปสรรค และการแก้ไข 100%

> **Google Docs ฉบับทางการ:** [เปิดดูบน Google Docs](https://docs.google.com/document/d/1CRzzmpqWURcJuQVjGLqwWHEM2O3hLUP72USUr252Oog/edit)

---

## 📑 สารบัญเนื้อหา (Table of Contents)
- [บทที่ 1: ภาพรวมสถาปัตยกรรมระบบ (System Architecture Overview)](#-บทที่-1-ภาพรวมสถาปัตยกรรมระบบ-system-architecture-overview)
- [บทที่ 2: การเตรียมเครื่องเซิร์ฟเวอร์ Ubuntu จากศูนย์ (Server Hardening & Base Setup)](#-บทที่-2-การเตรียมเครื่องเซิร์ฟเวอร์-ubuntu-จากศูนย์-server-hardening--base-setup)
- [บทที่ 3: การติดตั้ง System Dependencies, FFmpeg และฟอนต์ภาษาไทย](#-บทที่-3-การติดตั้ง-system-dependencies-ffmpeg-และฟอนต์ภาษาไทย)
- [บทที่ 4: การติดตั้ง Python Virtualenv และ Playwright Headless Browser](#-บทที่-4-การติดตั้ง-python-virtualenv-และ-playwright-headless-browser)
- [บทที่ 5: การติดตั้งโค้ดโปรเจกต์และการตั้งค่าความลับ (Environment & Secrets)](#-บทที่-5-การติดตั้งโค้ดโปรเจกต์และการตั้งค่าความลับ-environment--secrets)
- [บทที่ 6: การติดตั้ง Cloudflare Tunnel & ระบบ Watchdog อัตโนมัติสำหรับ LINE OA](#-บทที่-6-การติดตั้ง-cloudflare-tunnel--ระบบ-watchdog-อัตโนมัติสำหรับ-line-oa)
- [บทที่ 7: การสร้างและเปิดใช้งาน Systemd Services ทั้ง 4 ระบบหลัก](#-บทที่-7-การสร้างและเปิดใช้งาน-systemd-services-ทั้ง-4-ระบบหลัก)
- [บทที่ 8: การทดสอบระบบทีละขั้นตอน (End-to-End Smoke Testing & Verification)](#-บทที่-8-การทดสอบระบบทีละขั้นตอน-end-to-end-smoke-testing--verification)
- [บทที่ 9: รวมปัญหา อุปสรรคจริงหน้างาน (Pitfalls) และวิธีแก้ไข 100%](#-บทที่-9-รวมปัญหา-อุปสรรคจริงหน้างาน-pitfalls-และวิธีแก้ไข-100)
- [บทที่ 10: สรุปคำสั่งสำหรับการดูแลรักษาและควบคุมระยะไกล (Operations & Telegram Commander)](#-บทที่-10-สรุปคำสั่งสำหรับการดูแลรักษาและควบคุมระยะไกล-operations--telegram-commander)

---

## 🏛️ บทที่ 1: ภาพรวมสถาปัตยกรรมระบบ (System Architecture Overview)

โปรเจกต์ "ป้าเข็ม ขายของ" เป็นระบบอัตโนมัติครบวงจร 2 รางคู่ขนาน (**Dual-Engine System**):

1. **โรงงานผลิตและกระจายสื่อวิดีโอ 13 ช่องทาง (Autonomous Media Factory 24/7):**
   - ระบบตัดต่อวิดีโอ 9:16 Full HD อัตโนมัติ โดยอิง Master Template 3 เฟส
   - อัตราส่วนคอนเทนต์: 90% ข่าวไวรัล/ดารา/ทริคการเงิน/ดวงมงคล + 10% สินค้า Shopee แท้
   - ระบบเสียงพากย์ไทยสตูดิโอ: Microsoft Edge Neural TTS (`th-TH-PremwadeeNeural`)
   - กระจายโพสต์อัตโนมัติพร้อมกันทุก 30 - 45 นาที สู่ 13 ช่องทาง:
     - ⚫ **TikTok Studio:** 4 บัญชีหมุนเวียน (รันผ่าน Playwright Headless)
     - 🔵 **Facebook Pages:** 2 เพจหลักซิงค์พร้อมกัน (ผ่าน Facebook Graph API)
     - 🔴 **YouTube Shorts:** 6 ช่องหมุนเวียนแบบ Round-Robin เฉลี่ยโควต้า (Google API)

2. **ระบบรับแชทและปิดการขาย LINE Official Account (Always-On Zero-Cost Webhook):**
   - FastAPI Backend Server เชื่อมต่อฐานข้อมูล Supabase PostgreSQL คลังสินค้า 2,472 รายการ
   - ตอบแชทลูกค้าตลอด 24 ชม., รองรับรหัสสินค้าตรงตัวจากคลิป (เช่น พิมพ์ `86`, `1628`), ส่ง Flex Message การ์ดสินค้า, ตรวจสลิปโอนเงิน
   - Cloudflare Tunnel + Watchdog อัปเดต Webhook อัตโนมัติทันทีที่ URL เปลี่ยนแปลง

3. **ศูนย์สั่งการและเฝ้าระวังหลังบ้าน (Telegram Commander):**
   - ส่งรายงานคลิปที่โพสต์สำเร็จ, สถานะระบบ, และแจ้งเตือนข้อผิดพลาดเข้า Telegram `@pakhem_commander_bot`
   - แอดมินสามารถพิมพ์สั่งการจากมือถือได้ตลอดเวลา เช่น `/status`, `/post`, `/stock`, `/produce`

---

## 🖥️ บทที่ 2: การเตรียมเครื่องเซิร์ฟเวอร์ Ubuntu จากศูนย์ (Server Hardening & Base Setup)

### สเปกเซิร์ฟเวอร์ขั้นต่ำที่แนะนำ:
- **OS:** Ubuntu 22.04 LTS หรือ Ubuntu 24.04 LTS x64 (Clean Install)
- **CPU:** 1 vCPU (แนะนำ 2 vCPU ขึ้นไป)
- **RAM:** 2 GB ถึง 3 GB
- **Storage:** 40 GB ถึง 60 GB SSD
- **Network:** 1 Public IPv4 (แบนด์วิดท์ไม่จำกัด)

### ขั้นตอนที่ 2.1: การเข้าสู่เซิร์ฟเวอร์ครั้งแรกและการอัปเดตระบบ
```bash
ssh root@<IP_ADDRESS>

apt update && apt upgrade -y
```

### ขั้นตอนที่ 2.2: การตั้งค่าเขตเวลา (Timezone) เป็นประเทศไทย
```bash
timedatectl set-timezone Asia/Bangkok
timedatectl
```

### ขั้นตอนที่ 2.3: การสร้างพื้นที่หน่วยความจำเสมือน (Swapfile 4.0 GB)
> [!IMPORTANT]
> Playwright Headless Chromium และการเรนเดอร์ FFmpeg ใช้หน่วยความจำค่อนข้างสูง หากเซิร์ฟเวอร์มี RAM เพียง 2-3 GB เมื่อรันพร้อมกัน เคอร์เนลจะเรียกใช้ OOM Killer ตัดโปรเซสทันที การสร้าง Swapfile ขนาด 4 GB จะขยายพื้นที่หน่วยความจำรวมเป็น 6-7 GB ป้องกันปัญหานี้ได้อย่างเด็ดขาด

```bash
fallocate -l 4G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile

echo '/swapfile none swap sw 0 0' >> /etc/fstab

sysctl vm.swappiness=10
echo 'vm.swappiness=10' >> /etc/sysctl.conf

free -h
```

### ขั้นตอนที่ 2.4: การติดตั้ง Local SSH Public Key เพื่อการดูแลแบบไร้รหัสผ่าน
1. บนเครื่องคอมพิวเตอร์ของคุณ (Local PowerShell):
   ```powershell
   type C:\Users\<Username>\.ssh\id_ed25519.pub
   ```
2. นำข้อความ Public Key ที่ได้ ไปเพิ่มในไฟล์บนเซิร์ฟเวอร์ VPS:
   ```bash
   mkdir -p /root/.ssh
   chmod 700 /root/.ssh
   echo "ssh-ed25519 AAAA..." >> /root/.ssh/authorized_keys
   chmod 600 /root/.ssh/authorized_keys
   ```

---

## 📦 บทที่ 3: การติดตั้ง System Dependencies, FFmpeg และฟอนต์ภาษาไทย

### ขั้นตอนที่ 3.1: ติดตั้งชุดเครื่องมือคอมไพล์เลอร์และแพ็กเกจระบบพื้นฐาน
```bash
apt install -y build-essential curl wget git jq \
python3 python3-venv python3-pip python3-dev \
libffi-dev libssl-dev libjpeg-dev zlib1g-dev \
libpq-dev ffmpeg

ffmpeg -version
```

### ขั้นตอนที่ 3.2: ติดตั้งฟอนต์ภาษาไทยและการตั้งค่าแคชฟอนต์
> [!WARNING]
> เซิร์ฟเวอร์ลินุกซ์มาตรฐานไม่มีฟอนต์ภาษาไทยติดตั้งมาด้วย เมื่อโปรแกรม Pillow พยายามวาดข้อความพาดหัว Hook 3 วินาที หรือชื่อสินค้า จะเกิดข้อผิดพลาด `IOError: cannot open resource` หรือข้อความแสดงผลเป็นสี่เหลี่ยมว่างเปล่า (Tofu boxes)

```bash
apt install -y fonts-thai-tlwg fonts-noto-cjk fonts-noto-core fonts-dejavu-core

fc-cache -fv

fc-list :lang=th
```

---

## 🐍 บทที่ 4: การติดตั้ง Python Virtualenv และ Playwright Headless Browser

### ขั้นตอนที่ 4.1: การเตรียมไดเรกทอรีโปรเจกต์และสภาพแวดล้อมเสมือน
```bash
cd /root
git clone https://github.com/g81393878-bit/shopee-affiliate-bot.git
cd /root/shopee-affiliate-bot

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip setuptools wheel
```

### ขั้นตอนที่ 4.2: ติดตั้ง Python Dependencies ทั้งหมด
```bash
pip install -r backend/requirements.txt
pip install -r requirements.txt
pip install edge-tts gtts pythainlp pillow playwright httpx uvicorn fastapi psycopg2-binary python-dotenv google-api-python-client google-auth-oauthlib google-auth-httplib2
```

### ขั้นตอนที่ 4.3: ติดตั้ง Playwright Headless Chromium และ System Shared Libraries
> [!IMPORTANT]
> การรันแค่ `pip install playwright` จะมีเฉพาะไลบรารี Python แต่ยังไม่มีตัวไบนารีของ Chromium และขาดไลบรารีระดับระบบ (เช่น libnss3, libatk, libdrm, libgbm) ทำให้ Playwright แครชทันทีที่พยายามเปิดเบราว์เซอร์

```bash
playwright install chromium
playwright install-deps
```

ทดสอบการทำงานของ Playwright Headless:
```bash
python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(headless=True); print('Playwright Headless Chromium Ready!'); b.close(); p.stop()"
```

---

## 🔐 บทที่ 5: การติดตั้งโค้ดโปรเจกต์และการตั้งค่าความลับ (Environment & Secrets)

### ขั้นตอนที่ 5.1: รายการไฟล์ความลับที่ต้องมีบนเซิร์ฟเวอร์
1. `backend/.env` (Database Pooler, Line Tokens, FB Tokens, Groq Multi-Key, Telegram Token)
2. `tools/tiktok_cookies*.json` (คุกกี้เซสชัน TikTok ทั้ง 4 บัญชี)
3. `tools/youtube_token*.json` (OAuth 2.0 Tokens ของ YouTube Shorts ทั้ง 6 ช่อง)
4. `tools/posted_tiktok_history.json` (ไฟล์ประวัติป้องกันคลิปซ้ำ)

### ขั้นตอนที่ 5.2: คำสั่งส่งไฟล์ความลับจากเครื่อง Local ขึ้น VPS
```powershell
# รันบนเครื่องคอมพิวเตอร์ของคุณ (ไดรฟ์ D:\Shopee_Web_Scraping)
scp backend/.env root@<VPS_IP>:/root/shopee-affiliate-bot/backend/.env
scp tools/tiktok_cookies*.json root@<VPS_IP>:/root/shopee-affiliate-bot/tools/
scp tools/youtube_token*.json root@<VPS_IP>:/root/shopee-affiliate-bot/tools/
scp tools/posted_tiktok_history.json root@<VPS_IP>:/root/shopee-affiliate-bot/tools/
```

### ขั้นตอนที่ 5.3: ตั้งค่าสิทธิ์ไฟล์ความปลอดภัยบน VPS
```bash
chmod 600 /root/shopee-affiliate-bot/backend/.env
chmod 600 /root/shopee-affiliate-bot/tools/tiktok_cookies*.json
chmod 600 /root/shopee-affiliate-bot/tools/youtube_token*.json
```

---

## 🌐 บทที่ 6: การติดตั้ง Cloudflare Tunnel & ระบบ Watchdog อัตโนมัติสำหรับ LINE OA

```bash
curl -L --output /tmp/cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
dpkg -i /tmp/cloudflared.deb
rm -f /tmp/cloudflared.deb

cloudflared --version
```

---

## ⚙️ บทที่ 7: การสร้างและเปิดใช้งาน Systemd Services ทั้ง 4 ระบบหลัก

### 1. บริการที่ 1: `/etc/systemd/system/shopee-backend.service`
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

### 2. บริการที่ 2: `/etc/systemd/system/cloudflared-tunnel.service`
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

### 3. บริการที่ 3: `/etc/systemd/system/tunnel-watchdog.service`
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

### 4. บริการที่ 4: `/etc/systemd/system/shopee-bot.service`
```ini
[Unit]
Description=Shopee Affiliate Reels & AI Automation 24/7
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/shopee-affiliate-bot
EnvironmentFile=/root/shopee-affiliate-bot/backend/.env
ExecStart=/root/shopee-affiliate-bot/.venv/bin/python tools/system_runner.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### การสั่งเริ่มใช้งานทั้ง 4 บริการพร้อมกัน:
```bash
systemctl daemon-reload
systemctl enable --now shopee-backend cloudflared-tunnel tunnel-watchdog shopee-bot

systemctl status shopee-backend cloudflared-tunnel tunnel-watchdog shopee-bot --no-pager
```

---

## 🧪 บทที่ 8: การทดสอบระบบทีละขั้นตอน (End-to-End Smoke Testing & Verification)

1. **ทดสอบการเชื่อมต่อฐานข้อมูล Supabase:**
   ```bash
   /root/shopee-affiliate-bot/.venv/bin/python -c "
   import os, psycopg2
   from dotenv import load_dotenv
   load_dotenv('backend/.env')
   db_url = os.getenv('DATABASE_URL')
   conn = psycopg2.connect(db_url)
   cur = conn.cursor()
   cur.execute('SELECT count(*) FROM products;')
   print('Supabase Connected! Total Products:', cur.fetchone()[0])
   conn.close()
   "
   ```
2. **ทดสอบระบบเสียงพากย์ Edge-TTS:**
   ```bash
   /root/shopee-affiliate-bot/.venv/bin/python -c "
   import asyncio, edge_tts
   async def test_tts():
       c = edge_tts.Communicate('ทดสอบเสียงพากย์ป้าเข็มบนระบบอูบุนตู', 'th-TH-PremwadeeNeural', rate='+20%')
       await c.save('/tmp/test_voice.mp3')
       print('Edge-TTS Success! Audio file generated.')
   asyncio.run(test_tts())
   "
   ```
3. **ทดสอบการแจ้งเตือน Telegram Commander:**
   ```bash
   /root/shopee-affiliate-bot/.venv/bin/python -c "
   import sys; sys.path.insert(0, '.')
   from tools.telegram_notifier import notify_telegram_sync
   res = notify_telegram_sync('🚀 [ทดสอบระบบ Ubuntu] การแจ้งเตือน Telegram ทำงานสมบูรณ์ 100%')
   print('Telegram Test:', 'SUCCESS' if res else 'FAILED')
   "
   ```
4. **ทดสอบ Health Check ของ LINE Webhook:**
   ```bash
   TUNNEL_URL=$(journalctl -u tunnel-watchdog -n 50 --no-pager | grep -o 'https://[^ ]*trycloudflare.com' | tail -n 1)
   curl -s ${TUNNEL_URL}/health
   # ผลลัพธ์ที่ถูกต้อง: {"status":"ok"}
   ```

---

## ⚠️ บทที่ 9: รวมปัญหา อุปสรรคจริงหน้างาน (Pitfalls) และวิธีแก้ไข 100%

### ปัญหาที่ 1: ตัวหนังสือภาษาไทยบนคลิปกลายเป็นสี่เหลี่ยม หรือสระลอย/ตัดคำผิด
- **สาเหตุ:** เซิร์ฟเวอร์ลินุกซ์มาตรฐานไม่มีชุดฟอนต์ภาษาไทย และการตัดคำธรรมดาทำให้สระลอย
- **วิธีแก้:**
  1. ติดตั้ง `apt install -y fonts-thai-tlwg fonts-noto-cjk`
  2. ระบุพาธฟอนต์ลินุกซ์ `/usr/share/fonts/truetype/tlwg/Loma.ttf`
  3. ใช้ฟังก์ชัน `wrap_thai_lines` ที่ใช้ `pythainlp.word_tokenize(engine='newmm')` เสมอ

### ปัญหาที่ 2: Playwright Chromium แครชทันที
- **สาเหตุ:** ขาดไลบรารีกราฟิกและระบบความปลอดภัยระดับ OS บนลินุกซ์
- **วิธีแก้:** รัน `playwright install-deps` และระบุ `args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]`

### ปัญหาที่ 3: ระบบค้างหรือเซอร์วิสดับปริศนา (Linux OOM Killer)
- **สาเหตุ:** เรนเดอร์ FFmpeg พร้อมกับ Playwright ใช้แรมเกิน 2.5 GB
- **วิธีแก้:** สร้าง Swapfile ขนาด 4.0 GB เสมอ

### ปัญหาที่ 4: เสียงพากย์ Edge-TTS ล้มเหลวจากข้อจำกัดเครือข่าย
- **สาเหตุ:** WebSocket ของ Edge-TTS หลุดเมื่อเน็ตกระตุก
- **วิธีแก้:** ติดตั้ง `gtts` ไว้เป็น Fallback อัตโนมัติ

### ปัญหาที่ 5: YouTube Shorts ขึ้น Error 403 `access_denied`
- **สาเหตุ:** Google Cloud Project อยู่ในสถานะ Testing และยังไม่ได้เพิ่มอีเมลลงใน Test Users
- **วิธีแก้:** ไปที่ Google Cloud Console > `OAuth consent screen` > `Test users` > กด `+ ADD USERS` ใส่อีเมลเจ้าของช่อง

### ปัญหาที่ 6: TikTok Studio ติด Pop-up ขวางการกดปุ่มโพสต์
- **สาเหตุ:** Joyride Onboarding Modal, Dropdown แฮชแท็ก, และปุ่มยืนยัน Post now
- **วิธีแก้:** โค้ด `tools/tiktok_studio_uploader.py` จัดการกด Escape 2 ครั้ง และคลิกผ่าน Pop-up อัตโนมัติ

### ปัญหาที่ 7: การใช้พอร์ตฐานข้อมูล Supabase ผิดประเภท
- **สาเหตุ:** Direct Port 5432 ทำให้โควต้าการเชื่อมต่อเต็ม
- **วิธีแก้:** ใช้ Transaction Pooler พอร์ต **6543** (`?pgbouncer=true`)

### ปัญหาที่ 8: ปัญหาแย่ง Webhook (Split-Brain Conflict) ระหว่าง VPS เก่ากับใหม่
- **สาเหตุ:** เปิด Watchdog ทั้งสองเครื่องพร้อมกัน
- **วิธีแก้:** สั่ง `systemctl disable --now ...` และลบไฟล์บน VPS เก่าทิ้งทันที

---

## 🛠️ บทที่ 10: สรุปคำสั่งสำหรับการดูแลรักษาและควบคุมระยะไกล (Operations & Telegram Commander)

1. **เช็คสถานะภาพรวมของทั้ง 4 บริการ:**
   ```bash
   systemctl list-units --type=service --state=running | grep -E 'shopee|tunnel'
   ```
2. **ดู Live Logs:**
   ```bash
   # ระบบผลิตและยิงคลิป 13 ช่องทาง
   journalctl -u shopee-bot -f
   # ระบบ LINE OA Webhook
   journalctl -u shopee-backend -f
   # ระบบ Watchdog ซิงค์ Webhook
   journalctl -u tunnel-watchdog -f
   ```
3. **รีสตาร์ทระบบฉุกเฉินแบบ One-Click:**
   ```bash
   systemctl restart shopee-bot shopee-backend cloudflared-tunnel tunnel-watchdog
   ```
4. **คำสั่งสั่งการผ่าน Telegram Commander (`@pakhem_commander_bot`):**
   - `/status` — เช็คสถานะสดของระบบและสุขภาพ VPS
   - `/stock` — ดูรายการคลิปที่รอโพสต์ในคลังสต็อก
   - `/post` — สั่งยิงโพสต์คลิปทันที
   - `/produce` — สั่งผลิตคลิปใหม่เข้าคลัง 3 ตัว
   - `/reply <uid> <ข้อความ>` — ส่งแชทตอบลูกค้า LINE ผ่าน Telegram โดยตรง
