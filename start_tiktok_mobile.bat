@echo off
chcp 65001 >nul
title 📱 TikTok Mobile ADB Auto-Poster Daemon
cd /d "%~dp0"

set PYTHON_EXE=backend\.venv\Scripts\python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python

echo =====================================================================
echo  📱 ระบบโพสต์ TikTok อัตโนมัติ 100%% ผ่านสาย ADB มือถือ (Zero-Touch)
echo =====================================================================
echo  • ทำงานร่วมกับมือถือ Android เชื่อมสาย USB
echo  • ดึงคลิปอัตโนมัติ ➔ โพสต์ลงแอป TikTok ➔ แจ้งเตือน Telegram
echo =====================================================================
echo.

"%PYTHON_EXE%" tools\run_tiktok_mobile_daemon.py

if errorlevel 1 pause
