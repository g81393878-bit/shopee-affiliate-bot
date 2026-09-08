# 📺 คู่มือที่ 2: วิธีเพิ่มช่อง YouTube Shorts และการหมุนเวียน 6 ช่อง (Multi-Channel Guide)

---

## 🎯 1. รายชื่อช่อง YouTube Shorts ทั้ง 6 ช่องในปัจจุบัน

| ลำดับช่อง | ชื่อช่องบน YouTube | Handle | ไฟล์ Token | อีเมลที่เชื่อมต่อ (จดบันทึกกันลืม) |
| :---: | :--- | :--- | :--- | :--- |
| **ช่อง 1** | ป้าเข็ม ขายของ - ชี้เป้าของดี | `@regency1229` | `youtube_token.json` | `regency1229@gmail.com` |
| **ช่อง 2** | 🏠 ของดีติดบ้าน by ป้าเข็ม | `@goodthings-w4e` | `youtube_token_2.json` | `regency2919@gmail.com` |
| **ช่อง 3** | 🛒 ชี้เป้า ไอเทมต้องมี | `@pakmud.review` | `youtube_token_3.json` | `aiforge2569@gmail.com` |
| **ช่อง 4** | 🔥 อันดา ป้ายยาของใช้ดี | `@anda.review99` | `youtube_token_4.json` | `dev970115@gmail.com` |
| **ช่อง 5** | หยิบมารีวิว | `@yibmareview-th` | `youtube_token_5.json` | `devcraft757@gmail.com` |
| **ช่อง 6** | 🏷️ ป้าเข็ม ป้ายยาของดี | `@pakhem-paiya` | `youtube_token_6.json` | *(รอระบุ)* |

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
scp tools/youtube_token_7.json root@119.10.140.161:/root/shopee-affiliate-bot/tools/youtube_token_7.json
ssh root@119.10.140.161 "systemctl restart shopee-bot"
```\n

## OAuth recovery (2026-09-08)

- Background uploads never launch interactive login. Revoked or missing tokens require an explicit local login.
- Reconnect channel 2 and verify its identity before replacing its token:
  `backend/.venv/Scripts/python.exe tools/youtube_uploader.py --add-channel 2 --expected-handle @goodthings-w4e`
- OAuth client secrets must match the channel; no fallback to another channel's project.
- Transient refresh failures retry up to three times. Token writes are atomic and existing granted scopes are preserved.
- `tools/youtube_health_state.json` persists retry/notification cooldowns: auth, upload limit and API quota failures pause for six hours; other failures pause for five minutes. These are retry intervals, not a promise that Google resets limits at that time.
- Replacing a token bypasses its saved cooldown. Operational alerts use Telegram, never LINE push.
- `upload_shorts` retains its input when no upload succeeds. The Facebook/YouTube caller archives the original when ANY platform succeeds; retrying only the missing platform after partial success remains separate work.
- A new login while OAuth remains Testing is temporary; it does not remove Google's seven-day refresh-token lifetime.
