@echo off
title Add YouTube Shorts Channel
cls

echo ========================================================
echo    YouTube Shorts Channel Connector (Multi-Channel)
echo ========================================================
echo.
echo  [1] List all connected channels
echo  [2] Add Channel 2 (youtube_token_2.json)
echo  [3] Add Channel 3 (youtube_token_3.json)
echo  [4] Add Channel 4 (youtube_token_4.json)
echo  [5] Add Channel 5 (youtube_token_5.json)
echo  [6] Exit
echo.
echo ========================================================
set /p choice=Select (1-6) and press Enter: 

cd /d "%~dp0\tools"

if "%choice%"=="1" goto list_ch
if "%choice%"=="2" goto add_2
if "%choice%"=="3" goto add_3
if "%choice%"=="4" goto add_4
if "%choice%"=="5" goto add_5
goto end

:list_ch
cls
python youtube_uploader.py --list-channels
pause
goto end

:add_2
cls
echo Connecting Channel 2...
python youtube_uploader.py --add-channel 2
pause
goto end

:add_3
cls
echo Connecting Channel 3...
python youtube_uploader.py --add-channel 3
pause
goto end

:add_4
cls
echo Connecting Channel 4...
python youtube_uploader.py --add-channel 4
pause
goto end

:add_5
cls
echo Connecting Channel 5...
python youtube_uploader.py --add-channel 5
pause
goto end

:end
