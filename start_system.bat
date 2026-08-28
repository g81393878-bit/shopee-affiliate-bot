@echo off
chcp 65001 >nul
title Shopee Affiliate AI Bot - Commercial Turnkey Edition
cls

echo =====================================================================
echo    🚀 Shopee Affiliate & AI Social Automation (Commercial Edition)
echo =====================================================================
echo.
echo  [1] เริ่มต้นระบบทำงานอัตโนมัติทั้งหมด (Feed Post + Reels Video + TTS)
echo  [2] ผลิตคลิปวิดีโอสินค้า Reels ทันที (Auto Product Reels Generator)
echo  [3] เปิดหน้าจัดการระบบ (Admin Dashboard)
echo  [4] ตรวจสอบสถานะการทำงาน (Check System Status)
echo  [5] ออกจากโปรแกรม (Exit)
echo.
echo =====================================================================
set /p choice="กรุณาเลือกตัวเลข (1-5) แล้วกด Enter: "

if "%choice%"=="1" goto run_all
if "%choice%"=="2" goto run_reels
if "%choice%"=="3" goto open_admin
if "%choice%"=="4" goto check_status
if "%choice%"=="5" goto end

:run_all
cls
echo 🚀 กำลังเริ่มต้นระบบทำงานอัตโนมัติทั้งหมด...
backend\.venv\Scripts\python.exe tools\system_runner.py
pause
goto end

:run_reels
cls
echo 🎬 กำลังผลิตคลิป Reels พร้อมเสียงพากย์ไทย TTS...
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

:end
