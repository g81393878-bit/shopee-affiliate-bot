@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ====================================================
echo     ระบบโพสต์ Reels อัตโนมัติ (เปิดหน้าต่างนี้ทิ้งไว้)
echo ====================================================
echo.

:loop
echo [%date% %time%] กำลังตรวจสอบคิวและโพสต์ Reels...
..\backend\.venv\Scripts\python.exe uploader.py
echo.
echo นอนหลับ 15 นาที... (กด Ctrl+C เพื่อหยุดการทำงาน)
echo ----------------------------------------------------
timeout /t 900 /nobreak
goto loop
