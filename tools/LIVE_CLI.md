# live-cli (Windows)

CLI สำหรับทดสอบ Local AI Live Show และควบคุม OBS โดยไม่ส่งข้อมูลไป Shopee อัตโนมัติ

จากโฟลเดอร์โปรเจกต์:

```powershell
.\live-cli.bat doctor --json
.\live-cli.bat clips --json
.\live-cli.bat preview
.\live-cli.bat obs-status --json
.\live-cli.bat show --seconds 120 --once
```

ก่อนคำสั่ง `play`, `show` หรือ `obs-status` ให้ตั้งรหัสผ่าน OBS เฉพาะใน session ปัจจุบัน:

```powershell
$env:OBS_PASSWORD = "รหัสผ่าน OBS WebSocket"
.\live-cli.bat show --seconds 120
```

CLI ไม่พิมพ์รหัสผ่านออกมา และไม่มีคำสั่งเริ่ม Twitch/Shopee โดยอัตโนมัติ
