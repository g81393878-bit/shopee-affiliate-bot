@echo off
chcp 65001 >nul
title PaKhem Facebook Live 24/7 Streamer
cd /d "%~dp0"

echo ================================================================
echo    🐟 PaKhem Facebook Live 24/7 Automation Streamer (CLI)
echo ================================================================
echo.

python tools/fb_live_streamer.py

pause
