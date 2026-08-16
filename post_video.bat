@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

echo ============================================
echo    โพสต์วิดีโอลงเพจ Facebook ป้าเข็ม
echo ============================================
echo.

rem ถ้าลากไฟล์มาวางที่ไอคอน .bat ตัวนี้ จะได้ชื่อไฟล์อัตโนมัติ
set "VIDEOFILE=%~1"
if not defined VIDEOFILE (
    set /p "VIDEOFILE=ชื่อไฟล์คลิป (เช่น assets\clip.mp4 หรือ path เต็ม): "
)

set "CAPTION="
set /p "CAPTION=แคปชั่นใต้คลิป (เว้นว่างได้): "

set "MODE="
set /p "MODE=โพสต์เลย? (Enter=โพสต์จริง / พิมพ์ d=ดูตัวอย่างก่อน): "

echo.
echo กำลังทำงาน... (ไฟล์: %VIDEOFILE%)
echo.

if /i "%MODE%"=="d" (
    backend\.venv\Scripts\python.exe tools\post_fb_video.py --file "%VIDEOFILE%" --caption "%CAPTION%" --dry-run
) else (
    backend\.venv\Scripts\python.exe tools\post_fb_video.py --file "%VIDEOFILE%" --caption "%CAPTION%"
)

echo.
pause
