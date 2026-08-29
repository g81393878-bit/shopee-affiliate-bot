@echo off
chcp 65001 >nul
title Facebook Reels Video AI Bot - Standalone Edition
cls

echo =====================================================================
echo    🎬 Facebook Reels Video AI Bot (Standalone Edition)
echo    ระบบผลิตคลิปสินค้า 9:16 + เสียงพากย์ไทย TTS + โพสต์ Reels อัตโนมัติ
echo =====================================================================
echo.
echo  [1] เริ่มต้นระบบผลิตคลิปและโพสต์ Reels อัตโนมัติ (Auto 1.5 - 2 ชม.)
echo  [2] สั่งผลิตคลิปวิดีโอสินค้าใหม่ทันที (Produce Reels Now)
echo  [3] ตั้งค่าชื่อร้าน / เสียงพากย์ / Token (Setup Wizard)
echo  [4] ตรวจสอบสถานะและประวัติการโพสต์ (Check Status)
echo  [5] ออกจากโปรแกรม (Exit)
echo.
echo =====================================================================
set /p choice="กรุณาเลือกตัวเลข (1-5) แล้วกด Enter: "

if "%choice%"=="1" goto run_reels
if "%choice%"=="2" goto produce_reels
if "%choice%"=="3" goto setup_wizard
if "%choice%"=="4" goto check_status
if "%choice%"=="5" goto end

:run_reels
cls
echo 🚀 กำลังเริ่มต้นระบบอัตโนมัติ Facebook Reels...
backend\.venv\Scripts\python.exe tools\system_runner.py
pause
goto end

:produce_reels
cls
echo 🎬 กำลังผลิตคลิป Reels สินค้าใหม่พร้อมเสียงพากย์ไทย TTS...
backend\.venv\Scripts\python.exe reels_uploader\auto_product_reels.py 3
pause
goto end

:setup_wizard
cls
backend\.venv\Scripts\python.exe setup_wizard.py
pause
goto end

:check_status
cls
backend\.venv\Scripts\python.exe reels_uploader\check_status.py
pause
goto end

:end
