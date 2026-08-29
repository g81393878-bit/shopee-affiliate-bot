@echo off
setlocal
cd /d "%~dp0.."
set OBS_PASSWORD=
python tools\ai_live_show.py --seconds 120
pause
endlocal
