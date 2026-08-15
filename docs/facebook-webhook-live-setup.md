# ตั้งค่า Facebook Webhook + เปิดแอปเป็น Live (คู่มือเจ้าของ)

คู่มือนี้สำหรับ**เจ้าของร้าน** ทำเองในหน้า Facebook Developer 2 จุดเท่านั้น
(ฝั่งเซิร์ฟเวอร์เสร็จหมดแล้ว: endpoint live + env ครบ 17 ตัว + โพสต์ auto-post ทำงานแล้ว)

---

## ค่าที่ต้องใช้ (จดไว้เปิดหน้าคู่กัน)

| รายการ | ค่า |
| :--- | :--- |
| App ID | `1263958805236203` |
| Page ID (เพจร้าน) | `1307380735783361` — เพจ "ป้าเข็ม ขายของ" |
| Callback URL (Webhook) | `https://shopee-affiliate-bot-9e9n.onrender.com/api/webhooks/facebook` |
| Verify Token | ค่าเดียวกับ `FACEBOOK_VERIFY_TOKEN` ที่ตั้งบน Render (ดูในไฟล์ `tools/render_env.local.json` บนเครื่อง) |
| Privacy Policy URL | `https://shopee-affiliate-bot-9e9n.onrender.com/privacy` (ตรวจแล้วตอบ 200) |
| App Domains | `shopee-affiliate-bot-9e9n.onrender.com` (ไม่ต้องใส่ `https://`) |

---

## ตอนที่ 1 — ตั้ง Webhook ให้ Messenger

1. เปิดหน้า **Messenger API Settings**:
   `https://developers.facebook.com/apps/1263958805236203/messenger/settings/`
2. เลื่อนลงไปที่ส่วน **Webhooks** → กด **Add Callback URL**
3. กรอก:
   - **Callback URL:** `https://shopee-affiliate-bot-9e9n.onrender.com/api/webhooks/facebook`
   - **Verify Token:** ค่า `FACEBOOK_VERIFY_TOKEN` (จาก `tools/render_env.local.json`)
4. กด **Verify and Save**
   - ผ่าน = Facebook ยิง GET มาทดสอบ เซิร์ฟเวอร์ตอบ challenge กลับทันที
   - ไม่ผ่าน = ดูหัวข้อ "ปัญหาที่เจอบ่อย" ท้ายไฟล์
5. ถัดจากช่อง Webhooks กด **Add Subscriptions**:
   - เลือกเพจ **"ป้าเข็ม ขายของ"**
   - ติ๊ก **messages** (อย่างน้อยตัวนี้) → กด **Save**

---

## ตอนที่ 2 — ตรวจ Page Access Token (ส่วนใหญ่ทำแล้ว ข้ามได้)

- ในหน้า Messenger Settings เดิม เลื่อนไปส่วน **Access Tokens**
- เพจ "ป้าเข็ม ขายของ" ควรมี token เชื่อมอยู่แล้ว (ตั้งบน Render ไว้แล้ว)
- ⚠️ ถ้ากด **Generate Token ใหม่** ต้องเอา token ใหม่ไปอัปเดต `FACEBOOK_PAGE_ACCESS_TOKEN` บน Render ด้วย ไม่งั้นบอทตอบแชท/โพสต์สินค้าไม่ได้

---

## ตอนที่ 3 — เปิดแอปเป็น Live

1. เปิดหน้า **Basic Settings**:
   `https://developers.facebook.com/apps/1263958805236203/settings/basic/`
2. **App Domains:** ใส่ `shopee-affiliate-bot-9e9n.onrender.com`
3. **Privacy Policy URL:** ใส่ `https://shopee-affiliate-bot-9e9n.onrender.com/privacy`
   (Meta เช็คว่าลิงก์ตอบ 200 — ตรวจแล้วว่าตอบ 200)
4. **Terms of Service URL** (ถ้ามีช่องบังคับ): ใส่ Privacy URL เดียวกันได้ชั่วคราว
5. **Category** (ถ้าถาม): เลือก Business / Commerce
6. กด **Save Changes**
7. สลับสวิตช์ **App Mode** บนสุดของหน้า จาก **Development → Live**

---

## ตอนที่ 4 — ทดสอบ

1. เปิดแอป Live + ตั้ง webhook ครบแล้ว: ทักแชทเพจ **"ป้าเข็ม ขายของ"** ด้วยบัญชีธรรมดา (ที่ไม่ใช่แอดมินแอป)
2. บอทควรตอบกลับอัตโนมัติ:
   > 🤗 สวัสดีค่ะ! ยินดีต้อนรับสู่ร้าน ป้าเข็ม ขายของ 💕 … 👉 แอดไลน์ป้าเข็มได้เลย: https://lin.ee/o9Kjp1N
3. ถ้าเงียบ: ดูหัวข้อ "ปัญหาที่เจอบ่อย" ข้อ 2 และ 3

---

## ปัญหาที่เจอบ่อย

| อาการ | สาเหตุ / วิธีแก้ |
| :--- | :--- |
| Verify and Save ขึ้น 403 / fail | ① path ต้องเป็น `/api/webhooks/facebook` (มี `s` และมี `api`) ② Verify Token ต้องตรงกับ `FACEBOOK_VERIFY_TOKEN` บน Render เป๊ะ |
| ทักเพจแล้วบอทเงียบ | ยังอยู่ใน **Development mode** → สลับเป็น Live แล้วลองใหม่ (Development มีแค่ admin/testers เห็นบอท) |
| Live ไม่ได้ / กดแล้วเด้ง | App Domains ใส่ `https://` เกิน → ใส่แค่ host อย่างเดียว; Privacy URL ต้องตอบ 200 |
| บอทตอบได้แต่โพสต์สินค้าไม่ออก | Page token ถูก regenerate ใหม่แต่ยังไม่อัปเดตบน Render |

## หมายเหตุ

- `pages_messaging` เป็น **standard permission** — ไม่ต้องรอ App Review, ไม่ต้อง Business Verification สำหรับขั้นตอนนี้
- หน้า `/privacy` (นโยบาย PDPA) อยู่ที่ `https://shopee-affiliate-bot-9e9n.onrender.com/privacy` — ใช้เป็นลิงก์อ้างอิงในเพจ/แอปได้เลย
