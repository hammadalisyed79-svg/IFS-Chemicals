@echo off
:: Silent-friendly DB backup (used by scheduled task)
setlocal
cd /d "%~dp0"
if not exist "%CD%\logs" mkdir "%CD%\logs" >nul 2>&1
set "PY=%CD%\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%CD%\tools\backup_erp_db.py" >> "%CD%\logs\erp_backup.log" 2>&1
exit /b %ERRORLEVEL%
