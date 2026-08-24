@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo  IFS ERP — External access (proxy port 80 -^> Streamlit 8501)
echo  URL: http://138.201.139.157/
echo ============================================================
echo.

net session >nul 2>&1
if errorlevel 1 (
    echo ERROR: Run as Administrator.
    pause
    exit /b 1
)

echo [1] Windows Firewall port 80 ...
netsh advfirewall firewall delete rule name="IFS ERP HTTP 80" >nul 2>&1
netsh advfirewall firewall add rule name="IFS ERP HTTP 80" dir=in action=allow protocol=TCP localport=80 profile=any >nul

echo [2] Stop IIS Default Web Site (frees port 80) ...
powershell -NoProfile -Command "Import-Module WebAdministration; Stop-Website -Name 'Default Web Site' -ErrorAction SilentlyContinue; Set-ItemProperty 'IIS:\Sites\Default Web Site' -Name serverAutoStart -Value $false -ErrorAction SilentlyContinue"

echo [3] Stop old proxy on port 80 ...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R "0.0.0.0:80 .*LISTENING"') do (
  if not "%%p"=="4" taskkill /F /PID %%p >nul 2>&1
)

echo [4] Ensure Streamlit on 127.0.0.1:8501 ...
netstat -ano | findstr "127.0.0.1:8501.*LISTENING" >nul
if errorlevel 1 (
  start "IFS ERP Backend" /MIN cmd /c "cd /d %~dp0 && call venv\Scripts\activate.bat && python -m streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false"
  timeout /t 8 /nobreak >nul
)

echo [5] Start reverse proxy on 0.0.0.0:80 ...
start "IFS ERP Proxy :80" /MIN cmd /c "cd /d %~dp0 && call venv\Scripts\activate.bat && python ifs_reverse_proxy.py"
timeout /t 4 /nobreak >nul

powershell -NoProfile -Command "try { $r=Invoke-WebRequest 'http://127.0.0.1/' -UseBasicParsing -TimeoutSec 15; Write-Host 'OK local HTTP' $r.StatusCode 'bytes' $r.Content.Length } catch { Write-Host 'FAIL local:' $_.Exception.Message }; try { $r=Invoke-WebRequest 'http://138.201.139.157/' -UseBasicParsing -TimeoutSec 15; Write-Host 'OK public IP' $r.StatusCode } catch { Write-Host 'FAIL public IP:' $_.Exception.Message }"

echo.
echo Open from client PC:  http://138.201.139.157/
echo.
echo If clients still cannot connect, open TCP 80 in Hetzner Cloud Firewall:
echo   https://console.hetzner.cloud  -^> Firewalls -^> Inbound TCP 80 from 0.0.0.0/0
echo.
pause
