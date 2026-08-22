@echo off
setlocal

set "TARGET_DIR=%~dp0"
if "%TARGET_DIR:~-1%"=="\" set "TARGET_DIR=%TARGET_DIR:~0,-1%"

set "STARTUP_FOLDER=%appdata%\Microsoft\Windows\Start Menu\Programs\Startup"
set "VBS_FILE=%STARTUP_FOLDER%\run_reels_hidden.vbs"

echo Creating startup script...
echo Set WshShell = CreateObject("WScript.Shell") > "%VBS_FILE%"
echo WshShell.CurrentDirectory = "%TARGET_DIR%" >> "%VBS_FILE%"
echo WshShell.Run "run_uploader.bat", 0, False >> "%VBS_FILE%"
echo Set WshShell = Nothing >> "%VBS_FILE%"

echo Starting uploader in background...
wscript "%VBS_FILE%"

echo.
echo ====================================================
echo  Setup Completed Successfully!
echo ====================================================
echo.
echo The Reels uploader is now running in the background.
echo It will automatically start whenever you turn on your PC.
echo You can close this window now.
echo.
pause
