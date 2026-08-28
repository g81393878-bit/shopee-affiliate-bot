# 📖 คู่มือการใช้งานระบบ Shopee Affiliate & AI Social Automation
## Commercial Turnkey Edition (ฉบับส่งมอบลูกค้า)

---

## 🌟 จุดเด่นของระบบ (Key Features)

1. **🛍️ Facebook Feed Auto-Poster**: ดึงสินค้าจริงจาก Shopee ➔ AI เขียนแคปชั่นรีวิว ➔ โพสต์รูป+ลิงก์ Affiliate ลงหน้าเพจทุกๆ 60 นาที
2. **🎬 Facebook Reels Auto-Producer & Uploader**:
   - ดึงภาพสินค้าจากคลังมาตัดต่อเป็นคลิปวิดีโอ 9:16 Full HD อัตโนมัติ
   - **ใส่เสียงพากย์ภาษาไทยเป็นธรรมชาติ (Microsoft Edge Neural TTS)** แนะนำสินค้าและราคาจริง
   - โพสต์ลง Facebook Reels พร้อมแคปชั่นป้ายยาและลิงก์สั่งซื้อ
3. **🤖 LINE Official Account AI Assistant**:
   - บอทตอบคำถามลูกค้าภาษาไทยตลอด 24 ชั่วโมง
   - จดจำความชอบลูกค้า (Account Memory)
   - แนะนำสินค้าพร้อมการ์ด Flex Message และป้ายราคาลง
4. **📊 Web Admin Dashboard**:
   - หน้าควบคุมจัดการสินค้า ดูสถิติ ค้นหา และวิเคราะห์สินค้า
5. **🛡️ Rock-Solid Stability**:
   - ระบบ Self-Healing Auto-Reconnect เชื่อมต่อใหม่อัตโนมัติเมื่อเน็ตหลุด
   - ระบบ Safe Pacing และ Rate Limit Guard ป้องกันเพจโดนจำกัด

---

## 🚀 เริ่มต้นใช้งานใน 3 ขั้นตอน (Quick Start)

### ขั้นตอนที่ 1: ตั้งค่าข้อมูลแบรนด์ (.env)
คัดลอกไฟล์ `.env.example` แล้วเปลี่ยนชื่อเป็น `.env` จากนั้นกรอกข้อมูล:
* `BOT_NAME`: ตั้งชื่อแบรนด์หรือชื่อร้านของคุณ (เช่น "น้องส้ม ป้ายยา")
* `BRAND_SLOGAN`: สโลแกนร้านของคุณ
* `TTS_VOICE`: เลือกเสียงพากย์ภาษาไทย
  * `"th-TH-PremwadeeNeural"` (เสียงผู้หญิง / ป้าเข็ม นุ่มนวล)
  * `"th-TH-NiwatNeural"` (เสียงผู้ชาย มั่นใจ)
* `GROQ_API_KEY`: ใส่ API Key จาก Groq (ฟรี)
* `FACEBOOK_PAGE_ACCESS_TOKEN` & `FACEBOOK_PAGE_ID`: ใส่ Token และ Page ID ของเพจ Facebook

### ขั้นตอนที่ 2: เริ่มต้นระบบด้วย 1-Click
ดับเบิ้ลคลิกไฟล์ **`start_system.bat`** บนหน้าจอ:
* กดเลข **`1`** เพื่อเริ่มรันระบบโพสต์ Feed + คลิป Reels + เสียงพากย์ TTS อัตโนมัติทันที
* หรือกดเลข **`2`** เพื่อสั่งผลิตคลิปวิดีโอสินค้าใหม่เข้าคิวล่วงหน้า

---

## 📂 โครงสร้างโฟลเดอร์สำหรับผู้ดูแลระบบ

```text
Shopee_Web_Scraping/
├── start_system.bat          <-- 🚀 ปุ่มลัดเปิดระบบทั้งหมด (1-Click)
├── .env                      <-- ⚙️ ไฟล์ตั้งค่าแบรนด์และ Token
├── reels_uploader/
│   ├── pending_videos/       <-- 📦 กล่องใส่คลิปวิดีโอรอโพสต์
│   ├── posted/               <-- 📁 ประวัติคลิปที่โพสต์สำเร็จแล้ว
│   └── auto_product_reels.py <-- 🎬 ตัวผลิตคลิปสินค้า+เสียงพากย์ TTS
├── backend/
│   └── app/                  <-- 🧠 สมองกล AI, API และ Web Dashboard
└── tools/
    └── system_runner.py      <-- 🐕 Watchdog รวมศูนย์การทำงานอัตโนมัติ
```

---

## 💡 เทคนิคการใช้งานเพื่อสร้างยอดขายสูงสุด

1. **ตั้งเวลาโพสต์อย่างต่อเนื่อง:** ให้เปิด `start_system.bat` ทิ้งไว้ในช่วงเวลา 07:00 - 23:00 น. เพื่อให้มีโพสต์สินค้าและคลิป Reels ใหม่ๆ ตลอดทั้งวัน
2. **ใช้ LINE OA เชื่อมต่อกับเพจ:** นำลิงก์ LINE OA ไปใส่ในแคปชั่น เพื่อดึงคนที่สนใจสินค้าเข้ามาเป็นผู้ติดตามใน LINE เพิ่มโอกาสขายซ้ำ (Retargeting)
3. **อัปเดตสินค้าขายดี:** นำเข้าสินค้าใหม่ๆ ผ่านหน้า Web Admin Dashboard (`http://localhost:8000/admin`)

---
*© 2026 Shopee Affiliate & AI Social Automation — Commercial Edition*
