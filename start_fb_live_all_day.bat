@echo off
title PaKhem Facebook Live All-Day Autopilot
cd /d "%~dp0"
python -X utf8 tools/fb_live_streamer.py --auto-page 1 --hours 4 --rest-minutes 30 --auto-cycle --yes
pause
