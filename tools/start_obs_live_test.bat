@echo off
setlocal
cd /d "%~dp0.."

echo ================================================
echo   Local OBS Live Video Test
echo   ยังไม่เชื่อมต่อหรือเริ่มไลฟ์บน Shopee
echo ================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ไม่พบ Python ในเครื่อง
  pause
  exit /b 1
)

if not exist "reels_uploader\pending_videos" (
  echo ไม่พบโฟลเดอร์ reels_uploader\pending_videos
  pause
  exit /b 1
)

python tools\obs_controller.py --dry-run
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
set /p OBS_PASSWORD=ใส่รหัสผ่าน OBS WebSocket (ไม่บันทึกลงไฟล์): 
if "%OBS_PASSWORD%"=="" (
  echo ไม่ได้ใส่รหัสผ่าน
  pause
  exit /b 1
)

echo.
echo กำลังส่งคลิปแรกเข้า OBS...
python tools\obs_controller.py
if errorlevel 1 (
  echo.
  echo ทำงานไม่สำเร็จ ตรวจว่า OBS เปิด WebSocket ที่พอร์ต 4455 แล้ว
)
pause
endlocal
