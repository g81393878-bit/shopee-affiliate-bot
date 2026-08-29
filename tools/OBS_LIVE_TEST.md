# ทดสอบคลิปกับ OBS แบบ Local

ส่วนนี้ใช้ทดสอบในเครื่องเท่านั้น ยังไม่เชื่อมต่อ Shopee และยังไม่เริ่มไลฟ์ขึ้นแพลตฟอร์ม

## เตรียม OBS

1. เปิด OBS Studio รุ่น 28 หรือใหม่กว่า
2. ไปที่ `Tools > WebSocket Server Settings`
3. เปิด `Enable WebSocket server`
4. ใช้พอร์ต `4455` และตั้งรหัสผ่าน
5. สร้าง Scene ชื่อ `Live` หรือใช้ชื่ออื่นผ่าน `--scene`

ติดตั้งไลบรารีควบคุม OBS:

```powershell
python -m pip install obsws-python
```

## ตรวจคลิปโดยไม่เชื่อมต่อ OBS

```powershell
python tools\obs_controller.py --dry-run
```

## เล่นคลิปแรกใน OBS

```powershell
$env:OBS_PASSWORD = "รหัสผ่านที่ตั้งใน OBS"
python tools\obs_controller.py
```

## เล่นคลิปถัดไป

```powershell
python tools\obs_controller.py --next
```

รหัสผ่านควรอยู่ใน environment variable เท่านั้น ห้ามบันทึกลง Git หรือส่งให้ผู้อื่น
