@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set "TARGET_DIR=%~dp0"
if "%TARGET_DIR:~-1%"=="\" set "TARGET_DIR=%TARGET_DIR:~0,-1%"

set "STARTUP_FOLDER=%appdata%\Microsoft\Windows\Start Menu\Programs\Startup"
set "VBS_FILE=%STARTUP_FOLDER%\run_reels_hidden.vbs"

echo Creating startup script at: %VBS_FILE%
(
echo Set WshShell = CreateObject^("WScript.Shell"^)
echo WshShell.CurrentDirectory = "%TARGET_DIR%"
echo WshShell.Run "run_uploader.bat", 0, False
echo Set WshShell = Nothing
) > "%VBS_FILE%"

echo.
echo ====================================================
echo  ✅ ตั้งค่าระบบแอบรันอัตโนมัติเมื่อเปิดคอมเรียบร้อยแล้ว!
echo ====================================================
echo.
echo ต่อจากนี้ เมื่อคุณพี่เปิดคอมพิวเตอร์ขึ้นมาใช้งาน 
echo ระบบจะทำงานโพสต์ Reels ในพื้นหลัง (Background) เงียบ ๆ ทันที
echo โดยไม่เปิดหน้าต่างดำขึ้นมารบกวนสายตาครับ
echo.
pause
