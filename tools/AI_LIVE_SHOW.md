# AI Live Show

โหมดนี้ทำให้การไลฟ์ต่างจาก Reels โดยใช้คลิปสินค้าเป็นภาพประกอบ และเพิ่ม overlay ที่แสดงว่าเป็น AI Live, ชื่อสินค้า, ชื่อ AI Host และคำแนะนำให้กดสินค้าที่ปักไว้

ยังเป็น Local Test เท่านั้น ไม่เชื่อม Shopee และไม่ควรใช้คลิปเดิมวนซ้ำเพื่อหลอกว่าเป็นไลฟ์สด ต้องมีผู้ดูแลแชตและตรวจข้อมูลสินค้า

## ใช้แบบคลิกเดียว

1. เปิด OBS และเปิด WebSocket ที่ `Tools > WebSocket Server Settings`
2. ดับเบิลคลิก `tools\start_ai_live_show.bat`
3. ใส่รหัสผ่าน OBS และเวลาต่อคลิป

ระบบจะอ่านคลิปจาก `reels_uploader\pending_videos` และสร้าง overlay ที่ `tools\live_overlay.html` อัตโนมัติ
