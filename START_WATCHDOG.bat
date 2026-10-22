@echo off
cd /d "%~dp0"
if not exist "%CD%\logs" mkdir "%CD%\logs" >nul 2>&1
set "PY=%CD%\venv\Scripts\python.exe"
"%PY%" "%CD%\erp_watchdog.py" >> "%CD%\logs\erp_watchdog.out.log" 2>> "%CD%\logs\erp_watchdog.err.log"
