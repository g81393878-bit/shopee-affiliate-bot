@echo off
setlocal
cd /d "%~dp0.."
echo ================================================
echo   AI Live Show - Local OBS Test
echo ================================================
echo.
set /p OBS_PASSWORD=OBS WebSocket password: 
if "%OBS_PASSWORD%"=="" exit /b 1
echo.
python tools\ai_live_show.py --seconds 120
pause
endlocal
