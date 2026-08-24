@echo off
title IFS Chemicals ERP
cd /d "%~dp0"

set "ERP_URL=http://127.0.0.1:8501"
set "PY=%CD%\venv\Scripts\python.exe"

echo.
echo ============================================================
echo   IFS Chemicals ERP
echo   Starting at %ERP_URL%
echo ============================================================
echo.

if not exist "%PY%" (
    echo First run: creating Python environment...
    where python >nul 2>nul
    if errorlevel 1 (
        echo ERROR: Python is not installed or not on PATH.
        echo Install Python 3.10+ from https://www.python.org/downloads/
        echo then run this file again.
        pause
        exit /b 1
    )
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Could not create venv.
        pause
        exit /b 1
    )
    "%PY%" -m pip install --upgrade pip
    "%PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Could not install requirements.
        pause
        exit /b 1
    )
)

if not exist "app.py" (
    echo ERROR: app.py not found. Put this file in the ERP folder.
    pause
    exit /b 1
)

"%PY%" -c "import database as db; db.init_db()" 2>nul

REM If ERP is already running, just open the browser.
netstat -ano | findstr /C:":8501 " | findstr LISTENING >nul 2>nul
if not errorlevel 1 (
    echo ERP is already running.
    start "" "%ERP_URL%"
    echo Browser opened: %ERP_URL%
    echo Close this window when you are done. Do not close the other ERP window.
    pause
    exit /b 0
)

echo Opening browser in a few seconds...
start "" cmd /c "timeout /t 4 /nobreak >nul & start "" %ERP_URL%"

echo.
echo Keep this window open while you use the ERP.
echo Close it to stop the software.
echo.
"%PY%" -m streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false

echo.
echo ERP stopped.
pause
