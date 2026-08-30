@echo off
chcp 65001 >nul
title Add YouTube Shorts Channel
cls

echo ========================================================
echo    🎬 เพิ่มช่อง YouTube Shorts ใหม่ (Multi-Channel)
echo ========================================================
echo.
echo  [1] ดูรายการช่อง YouTube ทั้งหมดที่เชื่อมต่อแล้ว
echo  [2] เพิ่มช่องที่ 2 (สร้าง youtube_token_2.json)
echo  [3] เพิ่มช่องที่ 3 (สร้าง youtube_token_3.json)
echo  [4] เพิ่มช่องที่ 4 (สร้าง youtube_token_4.json)
echo  [5] ออก
echo.
echo ========================================================
set /p choice="กรุณาเลือกตัวเลข (1-5) แล้วกด Enter: "

cd /d "%~dp0\.."

if "%choice%"=="1" (
    cls
    backend\.venv\Scripts\python.exe tools\youtube_uploader.py --list-channels
    pause
    goto end
)
if "%choice%"=="2" (
    cls
    echo กำลังเปิดเบราว์เซอร์เพื่อเชื่อมต่อช่องที่ 2...
    backend\.venv\Scripts\python.exe tools\youtube_uploader.py --add-channel 2
    pause
    goto end
)
if "%choice%"=="3" (
    cls
    echo กำลังเปิดเบราว์เซอร์เพื่อเชื่อมต่อช่องที่ 3...
    backend\.venv\Scripts\python.exe tools\youtube_uploader.py --add-channel 3
    pause
    goto end
)
if "%choice%"=="4" (
    cls
    echo กำลังเปิดเบราว์เซอร์เพื่อเชื่อมต่อช่องที่ 4...
    backend\.venv\Scripts\python.exe tools\youtube_uploader.py --add-channel 4
    pause
    goto end
)

:end
