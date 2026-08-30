# MULTI_CHANNEL_AND_ANTI_SPAM_OPERATIONS.md
# คู่มือการจัดการระบบ 4-Channel Multi-Broadcast & Anti-Spam Shield (ป้าเข็ม 24/7)

---

## 📌 1. ภาพรวมระบบการเผยแพร่คลิปวิดีโอ 4 ช่องทางพร้อมกัน

ระบบอัตโนมัติของป้าเข็มถูกออกแบบให้ยิงคอนเทนต์วิดีโอ 9:16 Full HD พร้อมเสียงพากย์ไทย TTS ลง **Facebook 3 เพจ + YouTube Shorts 4 ช่องหมุนเวียน ทุกๆ 30 นาที ตลอด 24 ชม.**

```
                                  ┌───► Facebook เพจ 1: ป้าเข็ม ขายของ (ID: 1307380735783361)
                                  ├───► Facebook เพจ 2: ป้าเข็ม ชี้เป้าของดี (ID: 1323469404180656)
[โรงงานผลิตคลิป Reels/Shorts] ────┼───► Facebook เพจ 3: ป้าเข็ม ของดีบอกต่อ (ID: 1307380735783361)
   (ทุกๆ 30 นาที / 48 คลิปต่อวัน)      │
                                  └───► YouTube Shorts (Round-Robin หมุนเวียน 4 ช่อง)
                                          ├─ ช่อง 1: ป้าเข็ม ขายของ (@regency1229)
                                          ├─ ช่อง 2: ของดีติดบ้าน by ป้าเข็ม (@goodthings-w4e)
                                          ├─ ช่อง 3: ชี้เป้า ไอเทมต้องมี (@pakmud.review)
                                          └─ ช่อง 4: อันดา ป้ายยาของใช้ดี (@anda.review99)
```

---

## 🔴 2. รายละเอียดช่อง YouTube Shorts ที่เชื่อมต่ออยู่ (4 ช่อง)

| ลำดับ | ชื่อช่อง YouTube | Handle | ไฟล์ OAuth Token | โหมดการทำงาน |
| :---: | :--- | :--- | :--- | :---: |
| 1️⃣ | **ป้าเข็ม ขายของ - ชี้เป้าของดี** | `@regency1229` | `tools/youtube_token.json` | Round-Robin |
| 2️⃣ | **🏠 ของดีติดบ้าน by ป้าเข็ม** | `@goodthings-w4e` | `tools/youtube_token_2.json` | Round-Robin |
| 3️⃣ | **🛒 ชี้เป้า ไอเทมต้องมี** | `@pakmud.review` | `tools/youtube_token_3.json` | Round-Robin |
| 4️⃣ | **🔥 อันดา ป้ายยาของใช้ดี** | `@anda.review99` | `tools/youtube_token_4.json` | Round-Robin |

### 🔄 กลไกการหมุนเวียนและการป้องกันสะดุด (Round-Robin & Auto-Failover):
1. **การสลับช่องอัตโนมัติ:** เมื่อโพสต์สำเร็จ ระบบจะบันทึกลำดับช่องลง `tools/last_youtube_channel_index.txt` เพื่อให้รอบถัดไปสลับไปช่องต่อไปทันที
2. **Auto-Failover กันสะดุด:** หากช่องใดช่องหนึ่งติดลิมิต Google Daily Quota หรือ Token มีปัญหา ระบบจะ **ข้ามไปโพสต์ช่องสำรองถัดไปทันที** ทำให้คลิปไม่ตกหล่น

---

## ➕ 3. วิธีการเพิ่มช่อง YouTube ช่องใหม่ (ช่องที่ 5, 6, 7...)

1. บนเครื่องคอมพิวเตอร์ ให้เปิด PowerShell หรือ Terminal ที่โฟลเดอร์โปรเจกต์
2. รันคำสั่งระบุลำดับช่องที่ต้องการเพิ่ม:
   ```powershell
   python tools/youtube_uploader.py --add-channel 5
   ```
   *(หรือดับเบิ้ลคลิกไฟล์ `tools\add_youtube_channel.bat` แล้วพิมพ์เลข `5`)*
3. หน้าต่างเบราว์เซอร์ Google จะเปิดขึ้นมา ให้เลือกบัญชี Google และเลือกช่อง YouTube ที่ต้องการ
4. กดยืนยันอนุญาตสิทธิ์ (Allow Permissions)
5. ระบบจะสร้างไฟล์ `tools/youtube_token_5.json` ขึ้นมาให้อัตโนมัติ
6. ก๊อปปี้ไฟล์ไปยัง VPS หรือใช้คำสั่งซิงค์:
   ```powershell
   scp tools/youtube_token_5.json root@157.85.111.232:/root/shopee-affiliate-bot/tools/
   ```
7. ระบบผลิตคลิปจะตรวจพบช่องใหม่และนำเข้าสู่คิวหมุนเวียน 24 ชม. ทันที!

---

## 🔵 4. รายละเอียด Facebook Pages ที่เชื่อมต่ออยู่ (3 เพจ)

| เพจ | ชื่อเพจ Facebook | Page ID | ตัวแปร Token ใน `.env` |
| :---: | :--- | :---: | :--- |
| 1️⃣ | **ป้าเข็ม ขายของ** | `1307380735783361` | `FACEBOOK_PAGE_ACCESS_TOKEN` |
| 2️⃣ | **ป้าเข็ม ชี้เป้าของดี** | `1323469404180656` | `FACEBOOK_PAGE_2_ACCESS_TOKEN` |
| 3️⃣ | **ป้าเข็ม ของดีบอกต่อ** | `1307380735783361` | `FACEBOOK_PAGE_3_ACCESS_TOKEN` |

### 🔑 วิธีต่ออายุ / อัปเดต Facebook Page Token (Never-Expiring):
1. ไปที่ Meta Graph API Explorer: `https://developers.facebook.com/tools/explorer/`
2. เลือก Page ในเมนู **User or Page**
3. ติ๊กสิทธิ์: `pages_manage_posts`, `pages_read_engagement`, `pages_show_list`
4. กด **Generate Access Token** และนำมาอัปเดตใน `backend/.env` บน VPS

---

## 🛡️ 5. ระบบความปลอดภัย Anti-Spam Shield (3 ชั้น)

เพื่อป้องกันปัญหาข้อความแจ้งเตือนเด้งรัว หรือมีผู้ใช้งานแกล้งกดปุ่มชำระเงิน/แพ็กเกจซ้ำๆ ใน LINE OA:

1. **⏱️ Per-User Cooldown Throttle (60 วินาที/คน):**
   * หากลูกค้าคนเดิมกดปุ่ม *"ชำระเงิน"* หรือ *"ดูราคา"* ซ้ำๆ รัวๆ หลายครั้ง
   * ระบบจะส่งแจ้งเตือนเข้า Telegram แอดมิน **เพียง 1 ครั้งในรอบ 60 วินาทีเท่านั้น** ข้อความที่เหลือจะถูกสกัดทิ้งในหน่วยความจำทันที
2. **🚫 Duplicate Message De-duplication (20 วินาที):**
   * ข้อความแจ้งเตือนที่ซ้ำซ้อนกันทั้งหมดจะถูกหน่วงเวลาและตัดทิ้งอัตโนมัติภายใน 20 วินาที
3. **🧪 Unit Test & Simulation Quarantine Guard:**
   * บล็อกข้อความจากการทดสอบ (`pytest`, `PYTEST_CURRENT_TEST`, `U_cust_`, `mock`) 100% ไม่ให้ยิงออกนอกระบบเด็ดขาด

---

## 📊 6. สรุปสถานะคลังสินค้าและกระบวนการทำงาน 24 ชม.

* 🛍️ **สินค้าในคลัง Supabase:** 2,472 รายการ (ตรงตาม 8 หมวดหมู่เทรนด์ของใช้จำเป็น)
* ⏱️ **รอบการโพสต์:** ทุก 30 นาที (วันละ 48 คลิป / เฉลี่ยช่องทางละ 12 คลิป)
* 📢 **LINE Webhook & Telegram Ops:** สแตนด์บายตอบลูกค้าและรับคำสั่งแอดมินตลอด 24 ชม. ผ่าน Google Apps Script & VPS
