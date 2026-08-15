# HANDOFF.md — สถานะงานค้างระหว่าง AI session

> **วิธีใช้ (อ่านก่อน):**
> - **AI ตัวใหม่ที่เข้ามาทำงาน: ต้องอ่านไฟล์นี้ + ตรวจ `git status` ก่อนเริ่มงานเสมอ**
>   (บังคับตาม AGENTS.md → Multi-Agent Handoff Protocol)
> - **AI ตัวที่กำลังทำงาน:** ถ้าจะหยุดกลางคัน (ยังไม่ commit งานให้ครบ) ให้เติมข้อมูลจริงลงใน
>   ส่วน 1–5 ด้านล่าง แล้ว commit ไฟล์นี้ทันที พร้อมกับงานที่ทำไว้
> - **เมื่องานเสร็จและ commit ครบ:** ให้ล้างเนื้อหาในส่วน 1–5 กลับเป็นสถานะว่าง แล้ว commit
>   ไฟล์นี้ — เพื่อไม่ให้ AI ตัวถัดไปเข้าใจผิดว่างานยังค้าง

## สถานะ: 🟢 ปรับปรุงระบบ Social Demand Radar V1 ให้เป็น Auto-Post 100% ลง Facebook Page และบันทึกประวัติการโพสต์ลง Google Sheets เสร็จสมบูรณ์เรียบร้อยแล้ว (รันเทสต์ backend ทั้งหมด 529 ตัว ผ่าน 100% ครบถ้วน)

---

## 1. งานที่ทำแล้ว (ล่าสุด)

- ✅ feat(facebook): **Messenger webhook + แอพ Live ครบวงจร** — แก้ callback URL ให้ชี้ที่ `/api/webhooks/facebook` (เดิมชี้ผิดไป `huan-khuen-cafe`) + subscribe เพจ "ป้าเข็ม ขายของ" เข้ากับแอพ (Add Subscriptions ผ่าน Graph API) + สลับแอพเป็น Live — เทสต์จริง 22:08 ลูกค้าทัก "สวัสดี" บอทตอบแนะนำ + ลิงก์ LINE (`lin.ee/o9Kjp1N`) อัตโนมัติ
- ✅ data: **backfill `products.image_url` 1,672 ตัว** ด้วย fetch แบบใหม่ (og:image ตรงจากหน้า Shopee — ฟรี/เร็ว ไม่พึ่ง FB token/Firecrawl) → โพสต์ FB แนบรูปจริง (scontent CDN) ไม่ใช่การ์ดดำ
- ✅ feat(products): **eager backfill image_url ตอน import** (commit `725c966`) — สินค้าใหม่ได้รูปทันที ไม่ต้องรอโพสต์ FB

## 2. งานค้าง

<!-- ว่าง — ไม่มีงานโค้ดค้าง ทำงานทุกชิ้นเสร็จสมบูรณ์ -->

## 3. ขั้นตอนต่อไป

<!-- ว่าง — พร้อมส่งขึ้น Production ตามคำสั่งของเจ้าของร้าน -->

## 4. ไฟล์ที่ถืออยู่ / โดนแก้

<!-- ว่าง -->

## 5. หมายเหตุ

*   การทดสอบทั้งหมดของ Social Demand Radar ใน `tests/test_facebook_demand_radar.py` ผ่านการ Mock การวิเคราะห์อย่างสมบูรณ์แบบเพื่อหลีกเลี่ยงผลกระทบจาก Rate Limit 429 ของ API ภายนอก และแก้ปัญหา Mojibake บนระบบ Windows ส่งผลให้เทสต์ทำงานได้เสถียรและเร็วขึ้นมาก
*   เพิ่มระบบ Relevance Safeguard ใน `product_matcher.py` เพื่อบล็อกดีลสินค้าหากไม่มีสินค้าในคลังที่ตรงกับความต้องการของลูกค้าจริง (Relevance Score < 12.0) ป้องกันการสแปมและยิงโพสต์มั่วซั่วขึ้นบนเพจ
*   Facebook Messenger webhook + Live เรียบร้อยแล้ว (ยืนยันจากลูกค้าจริงที่ทักแชทแล้วบอทตอบ); ล้าง subscription เก่า `object=user` ที่ชี้ `huan-khuen-cafe` แล้ว — ตอนนี้เหลือ subscription เดียว `object=page` ชี้ที่บอทป้าเข็ม
