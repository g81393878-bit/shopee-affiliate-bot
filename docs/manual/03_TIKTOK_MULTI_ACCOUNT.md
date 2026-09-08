# ⚫ คู่มือที่ 3: วิธีเพิ่มและจัดการบัญชี TikTok Studio (TikTok Multi-Account Guide)

---

## 🎯 1. รายชื่อบัญชี TikTok ในระบบปัจจุบัน

| ลำดับช่อง | ชื่อช่อง TikTok | Handle | ไฟล์คุกกี้ | โควตาวันละ |
| :---: | :--- | :--- | :--- | :--- |
| **ช่อง 1** | Anda Review | `@healthgooddeals` | `tiktok_cookies.json` | 8 คลิป/วัน |
| **ช่อง 2** | ชี้เป้าโปรคุ้ม | `@cheepao.review` | `tiktok_cookies_2.json` | 8 คลิป/วัน |
| **ช่อง 3** | ป้าเข็ม รีวิว | `@pakhem.review99` | `tiktok_cookies_3.json` | 8 คลิป/วัน |
| **ช่อง 4** | ช่องที่ 4 | `@khonyangmefan` | `tiktok_cookies_4.json` | 8 คลิป/วัน |

---

## 🔄 1.1 กลยุทธ์การกระจายคลิปอย่างสมดุล (Equal Daily Distribution):
* ระบบจะโพสต์ทุกๆ **45 นาที** ตลอด 24 ชม.
* สลับช่อง 1 ➔ ช่อง 2 ➔ ช่อง 3 ➔ ช่อง 4 วนรอบ Round-Robin อย่างสมบูรณ์แบบ
* แต่ละช่องจะได้รับคลิปใหม่ห่างกัน **3 ชั่วโมงพอดีเป๊ะ** (ปลอดภัย ไม่โดนแบน เป็นธรรมชาติ 100%)
* ทุกช่องจะได้คลิป **8 คลิป/วัน เท่ากันเป๊ะ** รวม 4 ช่อง = **32 คลิป/วัน** เต็มโควตาพอดี!

---

## 📋 2. ขั้นตอนการเพิ่มบัญชี TikTok ช่องที่ 4

### วิธีที่ 1: ผ่านเมนู Master Control (ง่ายที่สุด)
1. ดับเบิ้ลคลิกไฟล์ `START.bat` บนหน้า Desktop หรือในโฟลเดอร์โปรเจกต์
2. เลือกเมนู **`[5] ⚫ จัดการบัญชี TikTok Studio`**
3. เลือกเมนู **`[2] เพิ่ม / เข้าสู่ระบบ TikTok ช่องใหม่`**
4. พิมพ์เลข **`4`** แล้วกด Enter

---

### วิธีที่ 2: ผ่านคำสั่ง PowerShell
```powershell
D:
cd D:\Shopee_Web_Scraping
python tools/tiktok_studio_uploader.py --add-account 4
```

---

### 📲 ขั้นตอนการสแกน QR Code เพื่อล็อกอิน:
1. หน้าต่างเบราว์เซอร์ Chrome สำหรับ TikTok จะเปิดขึ้นมา
2. เปิดแอป TikTok ในมือถือของคุณ ➔ ไปที่หน้าโปรไฟล์ ➔ กดเมนูมุมบนขวา ➔ เลือก **สแกน QR Code**
3. สแกน QR Code บนหน้าจอคอมพิวเตอร์
4. เมื่อล็อกอินสำเร็จ ระบบจะดึง Cookie เซสชันและบันทึกลง **`tools/tiktok_cookies_4.json`** ให้อัตโนมัติทันที

---

### 🚀 การนำขึ้น VPS (กรณีรันระบบบน VPS 24 ชม.):
```powershell
scp tools/tiktok_cookies_4.json root@119.10.140.161:/root/shopee-affiliate-bot/tools/tiktok_cookies_4.json
ssh root@119.10.140.161 "systemctl restart shopee-bot"
```

✅ **ผลลัพธ์:** บอทจะตรวจพบไฟล์ `tiktok_cookies_4.json` และนำเข้าคิวหมุนเวียนสลับโพสต์อัตโนมัติ 100% ทันทีครับ!

---

## 🚀 3. แผนพัฒนายกระดับสถาปัตยกรรม TikTok 2026 (Anti-Shadowban & Device-Native Master Architecture)

เพื่อแก้ปัญหายอดวิวเป็น 0 (Shadowban) อย่างเด็ดขาดในระดับวิศวกรรม ระบบได้เปลี่ยนผ่านเข้าสู่มาตรฐาน **Device-Native ADB Automation (2026 Best Practices)** ดังนี้:

### 1. **หลีกเลี่ยง Appium & Dynamic Resource IDs**:
   - ระบบความปลอดภัยยุคใหม่ของ TikTok สามารถตรวจจับ Process ของ Appium ที่รันอยู่เบื้องหลังระบบ Android ได้ รวมถึงปุ่มบนหน้าจอใช้ Dynamic Resource IDs ที่เปลี่ยนใหม่ทุกครั้งที่เปิดแอป
   - **ทางออก Best Practice**: ใช้ภาษา Python + Native ADB Shell + `uiautomator2` สั่งการผ่านพิกัดสัมพัทธ์เปอร์เซ็นต์หน้าจอ (`Normalized Relative Coordinates`) ผสมผสานกับ UIAutomator Dump สดเพื่อค้นหาองค์ประกอบหน้าจอจริง

### 2. **FYP Human Warmup (Trust Score Training)**:
   - ก่อนอัปโหลดวิดีโอ ระบบจะรัน `warmup_fyp()` สุ่มปัดหน้าจอ For You Page เป็นเวลา 1.5 - 3 นาที
   - จำลองการดูคลิป 4-12 วินาที สุ่มกดไลก์ (Double Tap) 15% และสุ่มความเร็วการปัดหน้าจอ (`human_like_swipe`) เพื่อสะสมคะแนน Behavioral Fingerprint เสมือนคนเล่นจริง

### 3. **พิกัดสัมพัทธ์เปอร์เซ็นต์หน้าจอ (Normalized Percentages)**:
   - แปลงพิกัดจากพิกเซลคงที่ เป็นเปอร์เซ็นต์ตามสัดส่วนความกว้าง/ความสูงของหน้าจอมือถือแต่ละรุ่น (`Screen W x H`):
     - **ปุ่มสร้าง (+)**: `(50% W, 92.7% H)`
     - **ปุ่มอัปโหลด (Upload)**: `(8.75% W, 68.5% H)`
     - **คลิปใหม่ล่าสุด (Row 1 Col 1)**: `(17.5% W, 20.9% H)`
     - **ปุ่มถัดไป (Next)**: `(92.5% W, 91.2% H)`
     - **ปุ่มโพสต์ (Post)**: `(74.25% W, 91.64% H)`

### 4. **4G/5G CGNAT Mobile IP & Content Randomization**:
   - มือถือ Android ที่เชื่อมต่อบอทควรใช้ซิมอินเทอร์เน็ตมือถือ 4G/5G จริง (CGNAT IP) เพื่อให้ทราฟิกเสมือนผู้ใช้งานมือถือทั่วไป ไม่โดนแบน Data Center ASN IP จาก VPS
   - สุ่มเวลาโพสต์และสุ่ม Metadata ก่อนส่งเข้าแกลเลอรีมือถือด้วย `am broadcast MEDIA_SCANNER_SCAN_FILE`

📖 **อ่านกรณีศึกษาฉบับเต็ม:** [CASE_STUDY_TIKTOK_AUTOMATION.md](file:///d:/Shopee_Web_Scraping/docs/manual/CASE_STUDY_TIKTOK_AUTOMATION.md) — เจาะลึกสถาปัตยกรรมทางวิศวกรรม, กลไกโพสต์อัตโนมัติ, การคำนวณรอบเวลา 45 นาที และวิธีแก้ปัญหาจริง 5 กรณี