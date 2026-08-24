@echo off
echo Opening Windows Firewall for IFS ERP...
echo.

net session >nul 2>&1
if errorlevel 1 (
    echo ERROR: Run as Administrator.
    pause
    exit /b 1
)

netsh advfirewall firewall delete rule name="IFS ERP HTTP 80" >nul 2>&1
netsh advfirewall firewall add rule name="IFS ERP HTTP 80" dir=in action=allow protocol=TCP localport=80 profile=any
netsh advfirewall firewall delete rule name="IFS ERP HTTPS 443" >nul 2>&1
netsh advfirewall firewall add rule name="IFS ERP HTTPS 443" dir=in action=allow protocol=TCP localport=443 profile=any
netsh advfirewall firewall delete rule name="IFS ERP Streamlit 8501" >nul 2>&1
netsh advfirewall firewall add rule name="IFS ERP Streamlit 8501" dir=in action=allow protocol=TCP localport=8501 profile=any

echo.
echo Windows Firewall rules added for ports 80, 443, and 8501.
echo.
echo IMPORTANT — also open ports in HETZNER CLOUD FIREWALL:
echo   1. https://console.hetzner.cloud
echo   2. Your server ^> Firewalls (or Networking)
echo   3. Add INBOUND: TCP 80 and TCP 443 from 0.0.0.0/0
echo   4. Attach firewall to this server if not already
echo.
echo ERP URL: https://erp.ifschemicals.com/
echo.
pause
