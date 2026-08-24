@echo off
setlocal
cd /d "%~dp0"
call venv\Scripts\activate.bat

echo ============================================================
echo  IFS ERP — EXTERNAL ACCESS (port 80)
echo  URL: http://erp.ifschemicals.com/
echo       http://138.201.139.157/
echo.
echo  NOTE: ifschemicals.com is your company website (different server).
echo        Add DNS: erp.ifschemicals.com -^> 138.201.139.157
echo.
echo  This stops IIS Default Web Site and starts:
echo    1) Streamlit ERP on 127.0.0.1:8501
echo    2) Reverse proxy on 0.0.0.0:80
echo.
echo  Run as Administrator.
echo ============================================================
echo.

net session >nul 2>&1
if errorlevel 1 (
    echo ERROR: Run this batch file as Administrator.
    pause
    exit /b 1
)

echo Stopping IIS Default Web Site...
powershell -NoProfile -Command "Import-Module WebAdministration; Stop-Website -Name 'Default Web Site' -ErrorAction SilentlyContinue"

echo Starting ERP backend on 127.0.0.1:8501 ...
start "IFS ERP Backend" /MIN cmd /c "cd /d %~dp0 && call venv\Scripts\activate.bat && python -m streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port 8501"

timeout /t 5 /nobreak >nul

echo Starting reverse proxy on port 80 ...
python ifs_reverse_proxy.py
