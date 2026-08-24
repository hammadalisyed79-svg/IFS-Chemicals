@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo  IFS ERP — Restart HTTPS proxy (80 + 443)
echo  URL: https://erp.ifschemicals.com/
echo ============================================================
echo.

net session >nul 2>&1
if errorlevel 1 (
    echo ERROR: Run as Administrator.
    pause
    exit /b 1
)

netsh advfirewall firewall delete rule name="IFS ERP HTTP 80" >nul 2>&1
netsh advfirewall firewall add rule name="IFS ERP HTTP 80" dir=in action=allow protocol=TCP localport=80 profile=any >nul
netsh advfirewall firewall delete rule name="IFS ERP HTTPS 443" >nul 2>&1
netsh advfirewall firewall add rule name="IFS ERP HTTPS 443" dir=in action=allow protocol=TCP localport=443 profile=any >nul

powershell -NoProfile -Command "Import-Module WebAdministration; Stop-Website -Name 'Default Web Site' -ErrorAction SilentlyContinue" >nul 2>&1

echo Stopping old proxy ...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'ifs_reverse_proxy' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 2 /nobreak >nul

netstat -ano | findstr "127.0.0.1:8501.*LISTENING" >nul
if errorlevel 1 (
  start "IFS ERP Backend" /MIN cmd /c "cd /d %~dp0 && call venv\Scripts\activate.bat && python -m streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false"
  timeout /t 8 /nobreak >nul
)

echo Starting HTTPS proxy ...
start "IFS ERP Proxy HTTPS" /MIN cmd /c "cd /d %~dp0 && call venv\Scripts\activate.bat && python ifs_reverse_proxy.py"
timeout /t 4 /nobreak >nul

powershell -NoProfile -Command "try { $r=Invoke-WebRequest 'https://erp.ifschemicals.com/' -UseBasicParsing -TimeoutSec 15; Write-Host 'HTTPS' $r.StatusCode } catch { Write-Host 'HTTPS check:' $_.Exception.Message }; try { $r=Invoke-WebRequest 'http://127.0.0.1/' -UseBasicParsing -MaximumRedirection 0 -TimeoutSec 8; Write-Host 'HTTP' $r.StatusCode } catch { if ($_.Exception.Response.StatusCode.value__) { Write-Host 'HTTP redirect' $_.Exception.Response.StatusCode.value__ } else { Write-Host $_.Exception.Message } }"

echo.
echo Open: https://erp.ifschemicals.com/
echo.
pause
