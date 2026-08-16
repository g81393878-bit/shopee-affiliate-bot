# SRS — ขายบอท LINE OA แบบ White-Label (Phase 1: Bot Profile)

- สถานะ: ร่าง v0.2 — ข้อตกลงครบแล้ว (BRD v1.0), รอเจ้าของยืนยัน SRS ก่อน System/DB Design
- อ้างอิง BRD: `docs/brd-sell-line-oa-bot.md`
- วันที่: 16 ส.ค. 2026
- ผู้จัดทำ: วิศวกรผู้ช่วย (AI) — ไม่ใช่ผู้มีอำนาจตัดสินใจทางธุรกิจ

---

## 1. ขอบเขต (Scope)

- **Phase 1 = Bot Profile / White-Label** — แยก "ตัวตนร้าน" ออกจากโค้ด (รากฐานร่วมของ Model A และ C)
- **Phase 2 = โหมดขาย (Model A: แยก instance/DB ต่อร้าน)**
- **Model C (shared DB + RLS + Stripe + customer portal) = roadmap ระยะถัดไป — ไม่รวมใน SRS นี้**

---

## 2. ระบบปัจจุบัน (As-Is)

บอท "ป้าเข็ม" ตัวเดียว (single-tenant) มีฟีเจอร์: ค้นหาสินค้า / จำความชอบ / แจ้งราคา-ของใหม่ /
แดชบอร์ดแอดมิน / PDPA / (ตัวเสริม) Facebook auto-post + Radar

ปัญหา: ตัวตนร้าน (ชื่อ "ป้าเข็ม" / บุคลิก / ลิงก์ OA / โทเคน LINE / สโลแกน) **ฝังในโค้ด ~15 ไฟล์**
+ ผูก LINE OA 1 บัญชี + คลังสินค้า 1 ชุด → แก้ชื่อร้านต้องแก้โค้ด + deploy

---

## 3. เป้าหมาย (To-Be)

แยกตัวตนร้านเป็น **ข้อมูล (Bot Profile)** ที่เปลี่ยนผ่านหน้าแอดมินได้ทันที โดยไม่แตะโค้ด ไม่ deploy
→ ขายบอทต่อร้านได้: แต่ละร้านมีชื่อ/เสียง/สินค้า/ลิงก์ของตัวเอง

---

## 4. ข้อกำหนดการทำงาน (Functional Requirements) — IPO

### FR-1: จัดการ Bot Profile (ตั้งค่า White-Label)
- **Input:** ชื่อบอท, บุคลิก/เสียง (persona prompt), ลิงก์ LINE OA, โทเคน LINE, admin_user_id, (ตัวเลือก) เพจ FB, สโลแกน
- **Process:** บันทึกลงตาราง `bot_profiles`; จุดที่เคยฝัง "ป้าเข็ม" (persona.py / line_bot.py / facebook_* / ai_generator ฯลฯ) อ่านจากตารางนี้แทน
- **Output:** บอทตอบ/โพสต์ด้วยชื่อ+บุคลิกของร้านนั้น; แดชบอร์ดแสดงค่าและบันทึกได้

### FR-2: แยกคลังสินค้า + ลิงก์ affiliate ต่อร้าน
- **Input:** profile_id/tenant_id + รายการสินค้า
- **Process:** เพิ่มตัวระบุร้านใน `products` (Model A = แยก DB; Model C = คอลัมน์ tenant_id); ทุก query filter ตามร้าน
- **Output:** ลูกค้าร้าน A ไม่เห็น/ค้นไม่เจอสินค้าร้าน B

### FR-3: สร้างร้านใหม่ (Model A onboarding)
- **Input:** ชื่อร้าน + โทเคน LINE OA + คลังสินค้า
- **Process:** ก็อป template profile → สร้าง instance/DB แยก → ตั้ง webhook LINE → import สินค้า
- **Output:** บอท LINE OA ของร้านใหม่ ทำงานอิสระ (ล้มตัวหนึ่งไม่กระทบร้านอื่น)

### FR-4: หน้าแอดมินตั้งค่า
- **Input:** ล็อกอิน admin (cookie), ค่าที่แก้
- **Process:** อ่าน/เขียน `bot_profiles` ผ่าน API (`GET/PUT /api/admin/bot-profile`)
- **Output:** UI แท็บ "ตั้งค่าร้าน" (แก้แล้วมีผลทันที)

### FR-5: มาตรฐานบริการ 5 ขั้นตอนเป็นคอนเทนต์บอท
- สถานะ: **ทำแล้ว** (commit `bcf05dd`) — ลูกค้าถาม "มาตรฐานการบริการ/บริการ" → บอทตอบ 5 ขั้นตอน
- SRS บันทึกไว้เป็นข้อกำหนดคงสภาพ (Regression): ต้องคงไว้เมื่อสลับไปอ่านบุคลิกจาก profile

---

## 5. ข้อกำหนดที่ไม่ใช่การทำงาน (Non-Functional)

- **NFR-1 การแยกข้อมูล:** Model A = แยก DB (physical isolation) → ไม่ต้องใช้ RLS
- **NFR-2 PDPA:** คำสั่ง "ลบข้อมูลฉัน" ลบเฉพาะข้อมูลในร้านของลูกค้าคนนั้น
- **NFR-3 ความปลอดภัย:** โทเคน LINE / คุกกี้ / คีย์ AI ต้องไม่ commit เข้า Git (`.gitignore` มีอยู่แล้ว)
- **NFR-4 เสถียรภาพ:** คงกลไก pool_pre_ping / keep-alive / failover LLM เดิม
- **NFR-5 ต้นทุน:** ใช้ free tier (Render + Supabase) ได้นานที่สุดก่อนยกระดับ

---

## 6. โครงร่างโมเดลข้อมูล (เบื้องต้น — ต่อ System/DB Design)

```
bot_profiles
  id, name, persona_prompt, line_oa_url, line_token(encrypted),
  admin_user_id, facebook_page_id, slogan, created_at, updated_at

Model A (Phase 2): 1 bot_profile = 1 instance/DB →
  products / contents / chat_logs / user_preferences อยู่ใต้ DB ของร้านนั้น (ไม่มี tenant_id)

Model C (roadmap): shared DB + คอลัมน์ tenant_id + PostgreSQL Row-Level Security (RLS)
```

---

## 7. ชี้แจงประเด็น RLS / Multi-Tenancy

- **RLS จำเป็นเฉพาะ Model C (shared DB)** — Model A ใช้แยก DB ปลอดภัยโดยกายภาพ ไม่ต้อง RLS
- การที่ข้อเสนอราคากล่าวถึง RLS/Stripe Connect/Customer Portal คือฟีเจอร์ **Model C**
- แนะนำ: ทำ Phase 1 + Phase 2 (Model A) ก่อน; เมื่อลูกค้าจ่ายเงิน ≥ 10–20 ราย ค่อยประเมินย้าย C

---

## 8. ข้อตกลงที่ล็อกแล้ว (กระทบ SRS)

1. **ใครตั้งค่าบอท = ทั้งคู่** — แอดมินตั้งให้ได้ (FR-4, Model A) + ลูกค้าตั้งเองได้ (Model C, roadmap → ต้องมี customer portal + role/permission)
2. **ลูกค้าเป้าหมาย = ทั้งคู่** — ร้านค้าตัวเอง + คนทำ affiliate → FR-2 ต้องรองรับคลัง 2 แบบ (สินค้าร้านเอง + ลิงก์ affiliate)

> ขั้นถัดไป = System & Database Design (schema + API; RLS เฉพาะถ้าเลือก Model C)
