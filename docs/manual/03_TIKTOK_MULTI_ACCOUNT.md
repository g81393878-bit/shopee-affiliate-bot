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

## 🚀 3. แผนพัฒนายกระดับสถาปัตยกรรม TikTok 2026 (Anti-Shadowban Roadmap)

เพื่อแก้ปัญหายอดวิวเป็น 0 (Shadowban) ในระยะยาว ระบบมีแผนยกระดับตามมาตรฐานปี 2026 ดังนี้:

1. **Browser-Level C++ Stealth (Patchright / Camoufox):** ย้ายการคุมเบราว์เซอร์จาก Playwright Stealth ทั่วไป มาใช้ Patchright / Camoufox เพื่อซ่อนร่องรอย CDP Protocol ในระดับ C++
2. **4G/5G Mobile Proxies (CGNAT):** เส้นทางการเชื่อมต่อของแต่ละช่องจะถูกแยกผ่าน 1:1 Sticky Mobile Proxy เพื่อไม่ให้โดนบล็อก Data Center IP จาก VPS
3. **Android Device Automation (ADB & uiautomator2):** ย้ายการอัปโหลดเข้าสู่แอป TikTok บนอุปกรณ์มือถือ Android จริงเพื่อใช้ Device Telemetry ฮาร์ดแวร์แท้ 100%
4. **Account Warmup Strategy (14-21 วัน):** กระบวนการสะสมคะแนน Account Trust Score ด้วยการรัน Persistent Context (`user_data_dir`) และสุ่มพฤติกรรมมนุษย์ก่อนเปิดอัปโหลดอัตโนมัติ

📖 **อ่านกรณีศึกษาฉบับเต็ม:** [CASE_STUDY_TIKTOK_AUTOMATION.md](file:///d:/Shopee_Web_Scraping/docs/manual/CASE_STUDY_TIKTOK_AUTOMATION.md) — เจาะลึกสถาปัตยกรรมทางวิศวกรรม, กลไกโพสต์อัตโนมัติ, การคำนวณรอบเวลา 45 นาที และวิธีแก้ปัญหาจริง 5 กรณี