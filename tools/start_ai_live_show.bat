@echo off
setlocal
cd /d "%~dp0.."
echo ================================================
echo   AI Live Show - Local OBS Test
echo   คลิปสินค้า + ป้าย AI + อวตารแบรนด์
echo ================================================
echo.
set /p OBS_PASSWORD=ใส่รหัสผ่าน OBS WebSocket (ไม่บันทึกลงไฟล์): 
if "%OBS_PASSWORD%"=="" exit /b 1
set /p LIVE_SECONDS=แสดงแต่ละคลิปกี่วินาที (ค่าเริ่มต้น 120): 
if "%LIVE_SECONDS%"=="" set LIVE_SECONDS=120
python tools\ai_live_show.py --seconds %LIVE_SECONDS%
pause
endlocal
