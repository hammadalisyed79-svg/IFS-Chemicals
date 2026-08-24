@echo off
cd /d "%~dp0"
echo IFS ERP REST API — http://127.0.0.1:8600/api/v1/docs
.\venv\Scripts\uvicorn.exe api.main:app --host 127.0.0.1 --port 8600
pause
