@echo off
REM ============================================================
REM  FB group monitor (Pa Khem) - runs on this machine ONLY.
REM  Called by Task Scheduler every 2 hours.
REM  MUST keep --once: without it the script loops forever,
REM  scanning every 5 minutes all day (that was the hung process
REM  from 06:13 the other morning).
REM  --pid-timeout 10: if a previous run hung for >10 min, its
REM  stale lock is broken automatically and we start fresh.
REM ============================================================
cd /d "%~dp0"
python -u tools\fb_group_monitor_local.py --once --pid-timeout 10 --api-url https://shopee-affiliate-bot-9e9n.onrender.com >> local_monitor_output.log 2>&1
