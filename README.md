# 🚀 Shopee Affiliate & AI Social Automation — Commercial Turnkey Edition

An all-in-one, white-label AI automation suite for **Shopee Affiliate marketers and e-commerce brands**. Integrates **Facebook Feed Auto-Posting**, **Facebook Reels Auto-Video Production with Thai Neural TTS**, **LINE OA Smart AI Chatbot**, and a **Web Admin Dashboard** — all ready to deploy or sell as a turnkey solution.

Built with **FastAPI**, **Pillow**, **ffmpeg**, **edge-tts**, **Supabase PostgreSQL**, and **Groq AI**.

---

## ✨ Key Features (ฟีเจอร์เด่นของระบบ)

### 1. 🎬 Auto Product Video Reels + Thai Neural TTS (ผลิตคลิป Reels พร้อมเสียงพากย์ไทยอัตโนมัติ)
- **อัตโนมัติ 100%:** ดึงภาพสินค้าขายดีจากคลัง ➔ ออกแบบโปสเตอร์ 9:16 Full HD (พื้นหลังเบลอ, ป้ายราคาเด่น, ดาวรีวิว) ➔ เรนเดอร์เป็นคลิปวิดีโอ 6-8 วินาที (Ken Burns zoom effect)
- **เสียงพากย์ภาษาไทยเป็นธรรมชาติ (Microsoft Edge Neural TTS):** ฝังเสียงพากย์ไทยแนะนำสินค้าและราคาจริง เช่น `th-TH-PremwadeeNeural` (เสียงป้าเข็ม) หรือ `th-TH-NiwatNeural` (เสียงมืออาชีพ)
- **แคปชั่นป้ายยา AI + ลิงก์ Affiliate:** Groq AI เขียนแคปชั่นรีวิวพร้อมใส่ลิงก์ Shopee Affiliate ให้อัตโนมัติ

### 2. 🛍️ Facebook Feed Auto-Poster (โพสต์สินค้าลงเพจทุกๆ 60 นาที)
- ดึงสินค้าจากคลัง Shopee ตามหมวดหมู่และยอดขาย
- AI เขียนแคปชั่นรีวิวเสียงเป็นกันเอง และแนบรูปภาพสินค้าความละเอียดสูง
- ระบบ Safe Pacing & Anti-Duplicate ป้องกันการโพสต์ซ้ำ

### 3. 🤖 LINE Official Account AI Assistant (บอทตอบแชทลูกค้า 24 ชม.)
- ค้นหาสินค้าด้วยภาษาธรรมชาติ ("หูฟังไม่เกิน 300", "กระติก 200-400")
- เปรียบเทียบสินค้าข้างเคียง ("เทียบ A กับ B")
- **Account Memory (ระบบจำความชอบลูกค้า):** "จำไว้ ชอบหูฟัง" ➔ แนะนำสินค้าตรงใจเมื่อมีสินค้าใหม่
- แจ้งเตือนราคาลง (Price-Drop Alerts) อัตโนมัติเมื่อสินค้าลดราคา ≥5%

### 4. 🏷️ White-Label 100% (ปรับแต่งแบรนด์ได้ใน 1 นาที)
- เปลี่ยนชื่อร้าน (`BOT_NAME`), สโลแกน (`BRAND_SLOGAN`), เสียงพากย์ (`TTS_VOICE`), และสีประจำร้าน (`BRAND_COLOR`) ได้ทันทีผ่าน `.env`
- ไม่มี Hardcoded แบรนด์ใน Core Engine

### 5. 🖱️ 1-Click Launcher & Watchdog (`start_system.bat` & `system_runner.py`)
- ดับเบิ้ลคลิกเดียวเริ่มระบบทั้งหมดบน Windows
- Multi-Threaded Watchdog พร้อมระบบ Self-Healing Auto-Reconnect เชื่อมต่อใหม่อัตโนมัติเมื่อเน็ตหลุด

---

## 🚀 Quick Start (เริ่มต้นใช้งานใน 3 ขั้นตอน)

### 1. ตั้งค่า `.env`
คัดลอกไฟล์ `.env.example` เป็น `.env` แล้วกรอกค่าที่ต้องการ:
```env
BOT_NAME="ป้าเข็ม ขายของ"
BRAND_SLOGAN="คัดของดี ของเด็ด Shopee แท้ 100% • รีวิวแน่น"
BRAND_COLOR="#EE4D2D"
TTS_VOICE="th-TH-PremwadeeNeural"

GROQ_API_KEY="gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
FACEBOOK_PAGE_ID="1307380735783361"
FACEBOOK_PAGE_ACCESS_TOKEN="EAAR9kFeYyesBSxxxxxxxxxxxxxxxxxxxx"
```

### 2. รันระบบด้วย 1-Click
ดับเบิ้ลคลิกไฟล์ **`start_system.bat`** บนหน้าจอ:
* กด `1` เพื่อเริ่มระบบทำงานอัตโนมัติทั้งหมดทันที
* กด `2` เพื่อสั่งผลิตคลิป Reels สินค้าล่วงหน้า

### 3. เปิด Admin Dashboard
เข้าสู่ระบบจัดการสินค้าและดูสถิติได้ที่: `http://localhost:8000/admin`

---

## 📂 โครงสร้างโปรเจกต์ (Project Structure)

```text
Shopee_Web_Scraping/
├── start_system.bat          <-- 🚀 ตัวเปิดระบบแบบ 1-Click
├── USER_MANUAL.md            <-- 📖 คู่มือการใช้งานฉบับส่งมอบลูกค้า
├── .env.example              <-- ⚙️ เทมเพลตการตั้งค่าแบรนด์
├── reels_uploader/
│   ├── auto_product_reels.py <-- 🎬 ระบบผลิตคลิป 9:16 + เสียงพากย์ TTS
│   ├── uploader.py           <-- 🚀 ตัวอัปโหลด Reels ขึ้น Meta Graph API
│   ├── pending_videos/       <-- 📦 คิวคลิปวิดีโอรอโพสต์
│   └── posted/               <-- 📁 ประวัติคลิปที่โพสต์สำเร็จ
├── backend/
│   ├── app/
│   │   ├── config.py         <-- 🏷️ รวมศูนย์ White-Label Config
│   │   ├── main.py           <-- 🌐 FastAPI Server & Webhook Endpoints
│   │   ├── services/         <-- 🧠 LLM, Facebook Poster, Product Cards
│   │   └── api/              <-- 📡 Webhooks & Admin Dashboard API
└── tools/
    ├── system_runner.py      <-- 🐕 Multi-Threaded Watchdog Orchestrator
    └── local_auto_poster.py  <-- 🛍️ Facebook Feed Auto-Poster
```

---

## 🧪 Testing & Reliability
- ผ่านการทดสอบ Unit Tests ครบถ้วน **1,162 ข้อ (100% Pass)**
- รันคำสั่งทดสอบ: `pytest` ในโฟลเดอร์ `backend/`

---
*© 2026 Shopee Affiliate & AI Social Automation — Commercial Turnkey Edition*
