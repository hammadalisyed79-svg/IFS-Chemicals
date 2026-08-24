@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo  IFS ERP — Enable HTTPS (Let's Encrypt)
echo  Domain: erp.ifschemicals.com
echo ============================================================
echo.

net session >nul 2>&1
if errorlevel 1 (
    echo ERROR: Run as Administrator.
    pause
    exit /b 1
)

echo [1] Windows Firewall TCP 80 + 443 ...
netsh advfirewall firewall delete rule name="IFS ERP HTTP 80" >nul 2>&1
netsh advfirewall firewall add rule name="IFS ERP HTTP 80" dir=in action=allow protocol=TCP localport=80 profile=any >nul
netsh advfirewall firewall delete rule name="IFS ERP HTTPS 443" >nul 2>&1
netsh advfirewall firewall add rule name="IFS ERP HTTPS 443" dir=in action=allow protocol=TCP localport=443 profile=any >nul

echo [2] Hosts entry for local DNS ...
findstr /C:"erp.ifschemicals.com" %SystemRoot%\System32\drivers\etc\hosts >nul 2>&1
if errorlevel 1 (
  echo 138.201.139.157 erp.ifschemicals.com>> %SystemRoot%\System32\drivers\etc\hosts
)

echo [3] Ensure Streamlit on 127.0.0.1:8501 ...
netstat -ano | findstr "127.0.0.1:8501.*LISTENING" >nul
if errorlevel 1 (
  start "IFS ERP Backend" /MIN cmd /c "cd /d %~dp0 && call venv\Scripts\activate.bat && python -m streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false"
  timeout /t 8 /nobreak >nul
)

echo [4] Restart HTTP proxy (needed for ACME challenge) ...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R "0.0.0.0:80 .*LISTENING"') do (
  if not "%%p"=="4" taskkill /F /PID %%p >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R "0.0.0.0:443 .*LISTENING"') do (
  if not "%%p"=="4" taskkill /F /PID %%p >nul 2>&1
)
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'ifs_reverse_proxy' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 2 /nobreak >nul
start "IFS ERP Proxy" /MIN cmd /c "cd /d %~dp0 && call venv\Scripts\activate.bat && python ifs_reverse_proxy.py"
timeout /t 4 /nobreak >nul

echo [5] Obtain Let's Encrypt certificate ...
call venv\Scripts\activate.bat
python tools\obtain_letsencrypt.py
if errorlevel 1 (
  echo.
  echo Certificate failed. Open TCP 80 in Hetzner Cloud Firewall, then re-run.
  pause
  exit /b 1
)

echo [6] Restart proxy with HTTPS ...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'ifs_reverse_proxy' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 2 /nobreak >nul
start "IFS ERP Proxy HTTPS" /MIN cmd /c "cd /d %~dp0 && call venv\Scripts\activate.bat && python ifs_reverse_proxy.py"
timeout /t 4 /nobreak >nul

echo [7] Mark ERP ssl_configured=1 ...
python -c "import database as db; from db_v3 import set_setting; db.init_db(); set_setting('ssl_configured','1'); set_setting('public_url','https://erp.ifschemicals.com'); print('ssl_configured=1')"

echo.
echo ============================================================
echo  Open:  https://erp.ifschemicals.com/
echo  HTTP redirects to HTTPS automatically.
echo.
echo  ALSO open TCP 443 in Hetzner Cloud Firewall:
echo    https://console.hetzner.cloud  -^> Firewalls -^> Inbound TCP 443
echo ============================================================
echo.
pause
