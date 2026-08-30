@echo off
chcp 65001 >nul
title Shopee Affiliate AI Bot - 24/7 Automation System
cls

echo =====================================================================
echo    Shopee Affiliate Automation (Facebook 3 Pages + YouTube Shorts)
echo =====================================================================
echo.
echo  [1] Start 24/7 Automation (Auto Produce + Auto Post every 30 mins)
echo  [2] Produce New Product Videos Now (TTS Voice)
echo  [3] Post 1 Video Immediately (Force Upload to 4 Channels)
echo  [4] Open Admin Dashboard
echo  [5] Exit
echo.
echo =====================================================================
set /p choice="Please select an option (1-5) and press Enter: "

if "%choice%"=="1" goto run_system
if "%choice%"=="2" goto produce_videos
if "%choice%"=="3" goto force_post
if "%choice%"=="4" goto open_admin
if "%choice%"=="5" goto end

:run_system
cls
echo Starting 24/7 Automation System...
python tools\system_runner.py
pause
goto end

:produce_videos
cls
echo Producing new product videos with Thai TTS voice...
python reels_uploader\auto_product_reels.py 3
pause
goto end

:force_post
cls
echo Uploading 1 video immediately to 4 channels...
python reels_uploader\uploader.py --force
pause
goto end

:open_admin
cls
echo Opening Admin Dashboard...
start http://127.0.0.1:8000/admin
goto end

:end

