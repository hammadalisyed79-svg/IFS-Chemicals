@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo  IFS ERP — IIS redirect to port 8501
echo  Use when run_external_port80.bat is not used.
echo  Requires: run_external.bat + open_erp_firewall.bat
echo ============================================================
echo.

net session >nul 2>&1
if errorlevel 1 (
    echo ERROR: Run as Administrator.
    pause
    exit /b 1
)

copy /Y "%~dp0deploy\web.config.redirect" "C:\inetpub\wwwroot\web.config"
echo Installed redirect: http://ifschemicals.com/ -^> http://ifschemicals.com:8501/
echo.
echo Next steps:
echo   1. Run run_external.bat
echo   2. Run open_erp_firewall.bat
echo   3. Open port 8501 in your hosting/cloud firewall
echo.
pause
