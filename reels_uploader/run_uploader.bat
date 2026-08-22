@echo off
cd /d "%~dp0"
..\backend\.venv\Scripts\python.exe uploader.py
pause
