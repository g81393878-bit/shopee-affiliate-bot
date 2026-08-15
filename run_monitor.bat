@echo off
cd /d "%~dp0"
python -u tools\fb_group_monitor_local.py --api-url https://shopee-affiliate-bot-9e9n.onrender.com > local_monitor_output.log 2>&1
