# 📋 รายการตรวจสอบก่อนส่งมอบระบบ (Delivery Checklist)
## Shopee Affiliate & Facebook Reels Automation — Commercial Turnkey Edition

---

เอกสารนี้ใช้สำหรับผู้พัฒนา/ผู้ขาย เพื่อตรวจสอบความเรียบร้อยก่อนส่งมอบแพ็กเกจโปรเจกต์ให้แก่ลูกค้าหรือผู้ซื้อ:

### 1. ⚙️ การตั้งค่าระบบ (Configuration Check)
- [ ] มีไฟล์ `.env.example` ที่อธิบายตัวแปรภาษาไทยครบทุกบรรทัด
- [ ] ไฟล์ `.env` ส่วนตัวไม่มีการหลุดขึ้น GitHub (`.gitignore` ครอบคลุม)
- [ ] รัน `setup_wizard.py` และสามารถสร้างไฟล์คอนฟิกได้ถูกต้อง

### 2. 🎬 ระบบ Reels & เสียงพากย์ภาษาไทย (Reels & TTS Engine)
- [ ] ภาพโปสเตอร์ 9:16 Full HD (1080x1920) คมชัด สวยงาม ไม่มีเต้าหู้หรือภาษาต่างดาว
- [ ] เสียงพากย์ภาษาไทย (Microsoft Edge Neural TTS) อ่านบทพูดลื่นไหล ไม่พูดซ้ำ ไร้รหัสโมเดลขยะ
- [ ] มีการจำกัดความยาว Title ไม่เกิน 80 ตัวอักษร เพื่อผ่าน Meta Graph API ฉลุย 100%
- [ ] สคริปต์ `reels_uploader/auto_product_reels.py` สามารถผลิตคลิปเข้าคิวได้อัตโนมัติ

### 3. 🛡️ เสถียรภาพและการแยกส่วน (Stability & Separation)
- [ ] ส่วนโพสต์ Feed ปกติถูกแยกเก็บเข้า `tools/legacy_feed_poster/` และปิดการทำงานเรียบร้อย
- [ ] ระบบหลักรันเฉพาะ Reels 100% ผ่าน `tools/system_runner.py`
- [ ] การใช้ RAM ต่ำกว่า 120MB และ CPU ต่ำกว่า 3%

### 4. 📦 แพ็กเกจส่งมอบ (Handover Package)
- [ ] ไฟล์ `start_system.bat` ดับเบิ้ลคลิกใช้งานได้ทันที มีเมนูให้เลือกครบถ้วน
- [ ] คู่มือการใช้งาน `USER_MANUAL.md` ภาษาไทย ครบทุกขั้นตอน
- [ ] ผลการทดสอบ Unit Tests ผ่านครบ 1,162 ข้อ (100% Pass)

---
*Checked & Certified for Commercial Deployment.*
