# 📺 คู่มือที่ 2: วิธีเพิ่มช่อง YouTube Shorts และการหมุนเวียน 6 ช่อง (Multi-Channel Guide)

---

## 🎯 1. รายชื่อช่อง YouTube Shorts ทั้ง 6 ช่องในปัจจุบัน

| ลำดับช่อง | ชื่อช่องบน YouTube | Handle | ไฟล์ Token |
| :---: | :--- | :--- | :--- |
| **ช่อง 1** | ป้าเข็ม ขายของ - ชี้เป้าของดี | `@regency1229` | `youtube_token.json` |
| **ช่อง 2** | 🏠 ของดีติดบ้าน by ป้าเข็ม | `@goodthings-w4e` | `youtube_token_2.json` |
| **ช่อง 3** | 🛒 ชี้เป้า ไอเทมต้องมี | `@pakmud.review` | `youtube_token_3.json` |
| **ช่อง 4** | 🔥 อันดา ป้ายยาของใช้ดี | `@anda.review99` | `youtube_token_4.json` |
| **ช่อง 5** | หยิบมารีวิว | `@yibmareview-th` | `youtube_token_5.json` |
| **ช่อง 6** | ป้าเข็มบอกต่อ | `@paakhem-f7b` | `youtube_token_6.json` |

---

## 📋 2. ขั้นตอนการเพิ่มช่อง YouTube Shorts ใหม่ (เช่น ช่องที่ 7)

### ขั้นตอนที่ 1: สร้าง OAuth Client ID บน Google Cloud
1. ไปที่ [Google Cloud Console Credentials](https://console.cloud.google.com/apis/credentials)
2. เลือก **Project เดิม** ที่ใช้อยู่
3. กด **`+ CREATE CREDENTIALS`** ➔ **`OAuth client ID`**
4. Application type ➔ เลือก **`Desktop app`**
5. ตั้งชื่อ เช่น `YouTube Channel 7` ➔ กด **`CREATE`**
6. กด **`DOWNLOAD JSON`** และนำไฟล์มาวางไว้ที่ `D:\Shopee_Web_Scraping\`

### ขั้นตอนที่ 1.5: เปิดใช้งาน YouTube Data API v3 (สำคัญมาก)
1. ไปที่ [YouTube Data API v3 Library](https://console.cloud.google.com/apis/library/youtube.googleapis.com)
2. กดปุ่มสีน้ำเงิน **`ENABLE`**

### ขั้นตอนที่ 2: เพิ่มอีเมลเจ้าของช่องใน Test Users (ป้องกัน Error 403)
1. ไปที่ **OAuth consent screen** ➔ เลื่อนไปที่ **`Test users`**
2. กด **`+ ADD USERS`** ➔ ใส่อีเมล Google ของช่องใหม่ ➔ กด **`SAVE`**

### ขั้นตอนที่ 3: รันคำสั่งเชื่อมต่อช่องบนคอมพิวเตอร์
เปิด PowerShell บนเครื่องแล้วพิมพ์:
```powershell
D:
cd D:\Shopee_Web_Scraping
python tools/youtube_uploader.py --add-channel 7
```
* ล็อกอินด้วยบัญชี Google ของช่องใหม่
* กด Advanced ➔ Go to ... (unsafe) ➔ Allow
* เมื่อหน้าต่างขึ้น `The authentication flow has completed` จะได้ไฟล์ `tools/youtube_token_7.json`

### ขั้นตอนที่ 4: ส่ง Token ขึ้น VPS
```powershell
scp tools/youtube_token_7.json root@157.85.111.232:/root/shopee-affiliate-bot/tools/youtube_token_7.json
ssh root@157.85.111.232 "systemctl restart shopee-bot"
```\n