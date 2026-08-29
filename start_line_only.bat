@echo off
chcp 65001 >nul
title LINE OA Smart Shopping Bot - Standalone Edition
cls

echo =====================================================================
echo    🤖 LINE OA Smart Shopping Assistant Bot (Standalone Edition)
echo    ระบบบอทตอบแชทลูกค้า 24 ชม. + ค้นหาสินค้าตามงบ + จำความชอบลูกค้า
echo =====================================================================
echo.
echo  [1] เริ่มต้นเซิร์ฟเวอร์บอท LINE OA (Start LINE Bot Server)
echo  [2] เปิดหน้าแดชบอร์ดจัดการสินค้า (Admin Dashboard)
echo  [3] ตั้งค่าระบบ / เปลี่ยนชื่อแบรนด์ (Setup Wizard)
echo  [4] ออกจากโปรแกรม (Exit)
echo.
echo =====================================================================
set /p choice="กรุณาเลือกตัวเลข (1-4) แล้วกด Enter: "

if "%choice%"=="1" goto run_line_bot
if "%choice%"=="2" goto open_admin
if "%choice%"=="3" goto setup_wizard
if "%choice%"=="4" goto end

:run_line_bot
cls
echo 🚀 กำลังเริ่มต้นเซิร์ฟเวอร์บอท LINE OA...
backend\.venv\Scripts\python.exe tools\run_local_bot.py
pause
goto end

:open_admin
cls
echo 🌐 กำลังเปิดหน้า Admin Dashboard...
start http://127.0.0.1:8000/admin
goto end

:setup_wizard
cls
backend\.venv\Scripts\python.exe setup_wizard.py
pause
goto end

:end
