@echo off
title PaKhem Facebook Live 4-Hour Autopilot
cd /d "%~dp0"
python -X utf8 tools/fb_live_streamer.py --auto-page 1 --hours 4 --yes
pause
