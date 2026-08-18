@echo off
REM ============================================================
REM  Auto group-share bot (Pa Khem) - called by Task Scheduler
REM  3x per day (morning/noon/evening).
REM  Quota 3 posts/day + 1 post/run is enforced inside run_campaign.py.
REM  CRON_TOKEN is read from backend\.env (not stored here).
REM ============================================================
cd /d "%~dp0.."

REM --- read CRON_TOKEN from backend\.env ---
set "TOKEN="
for /f "tokens=2 delims==" %%a in ('findstr /b /c:"CRON_TOKEN=" "backend\.env"') do set "TOKEN=%%a"

if not defined TOKEN (
    echo [ERROR] CRON_TOKEN not found in backend\.env >> bot\share_auto.log
    exit /b 1
)

REM --- run bot: fetch queue -> share to groups at once -> report back ---
python bot\run_campaign.py share --method share --from-queue --groups-file groups.txt --token %TOKEN% >> bot\share_auto.log 2>&1
