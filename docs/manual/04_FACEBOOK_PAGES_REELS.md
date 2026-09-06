# 📘 คู่มือที่ 4: การตั้งค่า Facebook Pages & Reels Multi-Broadcast

---

## 🎯 1. รายชื่อเพจ Facebook ในระบบ (โพสต์พร้อมกันทั้ง 3 เพจทุก 30 นาที)

| ลำดับเพจ | ชื่อเพจ Facebook | Page ID |
| :---: | :--- | :--- |
| **เพจ 1** | ป้าเข็ม ขายของ | `1373348778319835` |
| **เพจ 2** | ป้าเข็ม ชี้เป้าของดี | `1573158934491511` |
| **เพจ 3** | ป้าเข็ม ของดีบอกต่อ | `1573158934491511` |

---

## 🔑 2. การต่ออายุ Facebook Token (Long-Lived Token 60 วัน)

หากระบบแจ้งเตือน Token Expired (Error 190):
1. ไปที่ [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
2. เลือก User Token ที่มีสิทธิ์ `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`
3. ก๊อปปี้ Token มาใส่ในคำสั่ง:
```powershell
python tools/exchange_fb_token.py --user-token "YOUR_NEW_TOKEN"
```
4. อัปโหลดไฟล์ `backend/.env` ขึ้น VPS:
```powershell
scp backend/.env root@157.85.111.232:/root/shopee-affiliate-bot/backend/.env
ssh root@157.85.111.232 "systemctl restart shopee-bot"
```\n