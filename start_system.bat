@echo off
chcp 65001 >nul
title Shopee Affiliate AI Bot - Facebook Reels 100% Turnkey Edition
cls

echo =====================================================================
echo    🎬 Shopee Affiliate & Facebook Reels AI Automation (100% Reels)
echo =====================================================================
echo.
echo  [1] เริ่มต้นระบบผลิตคลิปและโพสต์ Reels อัตโนมัติ (100% Reels Mode)
echo  [2] สั่งผลิตคลิปวิดีโอสินค้าใหม่พร้อมเสียงพากย์ TTS ทันที
echo  [3] เปิดหน้าจัดการสินค้า (Admin Dashboard)
echo  [4] ตรวจสอบสถานะการทำงาน (Check System Status)
echo  [5] ตั้งค่าระบบ / เปลี่ยนชื่อแบรนด์ (Setup Wizard)
echo  [6] ออกจากโปรแกรม (Exit)
echo.
echo =====================================================================
set /p choice="กรุณาเลือกตัวเลข (1-6) แล้วกด Enter: "

if "%choice%"=="1" goto run_reels_system
if "%choice%"=="2" goto produce_now
if "%choice%"=="3" goto open_admin
if "%choice%"=="4" goto check_status
if "%choice%"=="5" goto run_wizard
if "%choice%"=="6" goto end

:run_reels_system
cls
echo 🚀 กำลังเริ่มต้นระบบผลิตและโพสต์ Facebook Reels อัตโนมัติ...
backend\.venv\Scripts\python.exe tools\system_runner.py
pause
goto end

:produce_now
cls
echo 🎬 กำลังผลิตคลิป Reels สินค้าใหม่พร้อมเสียงพากย์ไทย TTS...
backend\.venv\Scripts\python.exe reels_uploader\auto_product_reels.py 3
pause
goto end

:open_admin
cls
echo 🌐 กำลังเปิดหน้า Admin Dashboard...
start http://127.0.0.1:8000/admin
goto end

:check_status
cls
echo 📊 ตรวจสอบสถานะระบบ...
backend\.venv\Scripts\python.exe reels_uploader\check_status.py
pause
goto end

:run_wizard
cls
backend\.venv\Scripts\python.exe setup_wizard.py
pause
goto end

:end
