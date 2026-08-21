@echo off
REM ============================================================
REM  เปิดแดชบอร์ดแอดมิน (ป้าเข็ม) — 1 คลิก
REM  ถ้า uvicorn ยังไม่รัน -> สตาร์ทอัตโนมัติ (หลังรีบูตใช้ได้ทันที)
REM  แล้วเปิดเบราว์เซอร์ไปที่ http://localhost:8000/admin
REM ============================================================
setlocal
set BACKEND=D:\Shopee_Web_Scraping\backend
set HEALTH_FILE=%TEMP%\pkh_admin_health.txt

if not exist "%BACKEND%" (
    echo backend not found: %BACKEND%
    pause
    exit /b 1
)

REM --- เช็คว่า server รันอยู่แล้วไหม ---
curl -s -o nul -w "%%{http_code}" http://127.0.0.1:8000/health > "%HEALTH_FILE%" 2>nul
set /p HEALTH=<"%HEALTH_FILE%"
if "%HEALTH%"=="200" goto open

REM --- ยังไม่รัน -> สตาร์ท uvicorn (หน้าต่างย่อ, log ที่ %TEMP%) ---
echo Starting admin server, please wait...
start "pkh-admin" /min cmd /c "cd /d %BACKEND% && .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > %TEMP%\pkh_admin_uvicorn.log 2>&1"

REM --- รอ server ขึ้น (สูงสุด ~30 วิ) ---
set N=0
:wait
set /a N+=1
if %N% gtr 30 goto open
timeout /t 1 /nobreak > nul
curl -s -o nul -w "%%{http_code}" http://127.0.0.1:8000/health > "%HEALTH_FILE%" 2>nul
set /p HEALTH=<"%HEALTH_FILE%"
if "%HEALTH%"=="200" goto open
goto wait

:open
del "%HEALTH_FILE%" 2>nul
start "" http://localhost:8000/admin
exit /b 0
