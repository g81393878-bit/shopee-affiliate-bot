# 📱 คู่มือระบบอัปโหลด TikTok อัตโนมัติเต็มรูปแบบ (TikTok Automation Guide)
## ฉบับสมบูรณ์ — รองรับ Playwright Web Studio & Content Posting API v2

---

## 🌟 1. ภาพรวมสถาปัตยกรรมการโพสต์ TikTok

ระบบบอทของเรารองรับการโพสต์วิดีโอ 9:16 Full HD เข้าสู่ **TikTok** แบบอัตโนมัติ 100% ควบคู่ไปกับ Facebook Reels และ YouTube Shorts โดยมี **2 กลไกหลัก (Dual Engine Architecture)**:

```text
[คลังคลิป 9:16 Full HD (reels_uploader/pending_videos)]
                         ⬇️
       [reels_uploader/uploader.py (ตัวกระจายโพสต์)]
                         ⬇️
      ┌──────────────────┴──────────────────┐
      ▼                                     ▼
[Engine 1: Web Studio Automation]     [Engine 2: TikTok Content API v2]
(Playwright + Session Cookies)        (OAuth 2.0 PKCE + Direct Post)
• tools/tiktok_studio_uploader.py     • tools/tiktok_uploader.py
• ไม่ต้องขอ App Review                 • สำหรับ Production API
• บันทึก Session ในเครื่องถาวร           • มีระบบ Token Refresh อัตโนมัติ
      └──────────────────┬──────────────────┘
                         ⬇️
        [อัปโหลดเข้าช่อง @healthgooddeals]
                         ⬇️
        [แจ้งเตือนรายงานเข้า Telegram Commander]
```

---

## 🚀 2. โหมดหลัก: TikTok Web Studio Automation (Playwright)

เป็นโหมดที่ใช้งานจริงในปัจจุบัน สะดวก รวดเร็ว ไม่ติดเงื่อนไขการตรวจ App Review ของ TikTok

### 📁 ไฟล์ที่เกี่ยวข้อง:
- **ตัวจัดการหลัก**: [`tools/tiktok_studio_uploader.py`](file:///d:/Shopee_Web_Scraping/tools/tiktok_studio_uploader.py)
- **ไฟล์เก็บคุกกี้**: `tools/tiktok_cookies.json` *(Gitignored ปลอดภัย 100%)*
- **โฟลเดอร์เก็บ Session บราวเซอร์**: `tools/tiktok_user_data/` *(Gitignored)*
- **ตัวแปลงคุกกี้**: [`tools/import_tiktok_cookies.py`](file:///d:/Shopee_Web_Scraping/tools/import_tiktok_cookies.py)

---

### 💻 คำสั่งใช้งาน (CLI Commands):

#### 1. ทดสอบอัปโหลดคลิปเดี่ยว:
```bash
backend\.venv\Scripts\python tools/tiktok_studio_uploader.py --upload "reels_uploader/pending_videos/prod_125_Lenovo_Earbuds_Audio_LP40S_True_wireless.mp4" --caption "หูฟังบลูทูธไร้สาย Lenovo LP40S เสียงดีเบสแน่น #ป้าเข็มรีวิว #ของดีบอกต่อ #shopee"
```

#### 2. ทดสอบอัปโหลดแบบเปิดหน้าต่างบราวเซอร์ดูการทำงาน (Visible Mode):
```bash
backend\.venv\Scripts\python tools/tiktok_studio_uploader.py --upload "reels_uploader/pending_videos/prod_125_Lenovo_Earbuds_Audio_LP40S_True_wireless.mp4" --visible
```

#### 3. ล็อกอินใหม่ผ่านหน้าเว็บ (เมื่อคุกกี้หมดอายุ):
```bash
backend\.venv\Scripts\python tools/tiktok_studio_uploader.py --login
```

---

## 🔑 3. วิธีการอัปเดตคุกกี้ TikTok เมื่อหมดอายุ (Cookie Refresh)

หาก TikTok มีการแจ้งเตือน Session Expired ในอนาคต ให้ทำตามขั้นตอนนี้ใน 1 นาที:

### วิธีที่ 1: ผ่านคำสั่งบราวเซอร์อัตโนมัติ (ง่ายที่สุด)
1. รันคำสั่ง:
   ```bash
   backend\.venv\Scripts\python tools/tiktok_studio_uploader.py --login
   ```
2. หน้าต่าง Chrome จะเปิดขึ้นมา ➔ สแกน QR Code จากแอป TikTok ในมือถือ
3. เมื่อเข้าสู่ระบบเสร็จ บอทจะบันทึก Session ใหม่เข้าเครื่องทันที

### วิธีที่ 2: คัดลอก Cookie String จากเบราว์เซอร์
1. เปิด `tiktok.com` ในคอมพิวเตอร์ ➔ กด `F12` (Developer Tools) ➔ ไปที่แท็บ **Network**
2. คลิกเลือก Request ใดก็ได้ ➔ ดูที่หัวข้อ **Request Headers** ➔ คัดลอกค่าในช่อง `cookie:`
3. เปิดไฟล์ `tools/import_tiktok_cookies.py` ➔ วางค่าลงในตัวแปร `RAW_COOKIES`
4. รันคำสั่ง:
   ```bash
   backend\.venv\Scripts\python tools/import_tiktok_cookies.py
   ```

---

## 📡 4. โหมดสำรอง: TikTok Content Posting API (v2)

โมดูล [`tools/tiktok_uploader.py`](file:///d:/Shopee_Web_Scraping/tools/tiktok_uploader.py) ถูกออกแบบตามมาตรฐาน Direct Post API v2 ของ TikTok:

- **Endpoint Upload**: `https://open.tiktokapis.com/v2/post/publish/video/init/`
- **Chunk Stream**: แบ่งอัปโหลดไฟล์ขนาดละ 10MB
- **Token Auto-Refresh**: รีเฟรช Token อัตโนมัติทุก 24 ชั่วโมง บันทึกใน `tools/tiktok_token.json`
- **URL เอกสารนโยบาย**:
  - Terms of Service: `https://shopee-affiliate-bot-9e9n.onrender.com/terms`
  - Privacy Policy: `https://shopee-affiliate-bot-9e9n.onrender.com/privacy`

---

## 🎯 5. กฎเหล็กของคลิปและแคปชั่น TikTok (TikTok Posting Policy)

1. **ห้ามมีตัวเลขราคาในแคปชั่นและคลิป (Strict No-Price Policy)**:
   - บอทจะทำการตัดคำว่า "บาท", "฿", "baht" และตัวเลขราคาออกจากแคปชั่นอัตโนมัติ (`sanitize_caption`)
2. **แฮชแท็กประจำแบรนด์อัตโนมัติ**:
   - บอทจะเติม `#ป้าเข็มรีวิว #ของดีบอกต่อ` ท้ายทุกคลิปเสมอ เพื่อดันคลิปขึ้นฟีด For You Page (FYP)
3. **ความยาวแคปชั่นจำกัดไม่เกิน 150 ตัวอักษร**:
   - เพื่อความกระชับ อ่านง่าย และไม่บังหน้าจอวิดีโอ 9:16
4. **ความละเอียดวิดีโอ**:
   - วิดีโอ 1080x1920 (9:16 Vertical HD) อัตราเฟรมเรต 30fps เสียงพากย์ไทยมาตรฐานป้าเข็ม 100%

---

## 🤖 6. การทำงานร่วมกับระบบ Multi-Broadcast

ในโมดูล [`reels_uploader/uploader.py`](file:///d:/Shopee_Web_Scraping/reels_uploader/uploader.py) ฟังก์ชัน `post_next()` จะทำการโพสต์ไปที่:
1. 📘 **Facebook 3 เพจ** (ป้าเข็ม 1, 2, 3)
2. 🔴 **YouTube Shorts** (หมุนเวียน 5 ช่อง)
3. ⚫ **TikTok** (ช่อง `@healthgooddeals` ผ่าน Web Studio)

พร้อมส่งสรุปลิงก์ของทุกแพลตฟอร์มเข้า **Telegram Commander (`@pakhem_commander_bot`)** ทุก ๆ 30 นาทีตลอด 24 ชม.! 🚀
