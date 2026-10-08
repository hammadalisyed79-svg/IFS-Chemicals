@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title IFS Chemicals ERP — public start

:: Ports 80/443 need Administrator. Re-launch elevated if needed.
net session >nul 2>&1
if errorlevel 1 (
  echo Requesting Administrator rights for public HTTPS (ports 80 + 443)...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
  exit /b
)

echo ============================================================
echo  IFS Chemicals ERP — PUBLIC START
echo  Folder: %CD%
echo  Public: https://erp.ifschemicals.com/
echo ============================================================
echo.

set "PY=%CD%\venv\Scripts\python.exe"
if not exist "%PY%" (
  echo ERROR: venv not found at "%PY%"
  echo Create it:  python -m venv venv ^&^& venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)

if not exist "%CD%\certs\config\live\erp.ifschemicals.com\fullchain.pem" (
  echo ERROR: SSL certificate missing:
  echo   %CD%\certs\config\live\erp.ifschemicals.com\fullchain.pem
  pause
  exit /b 1
)

echo [1] Stop old Streamlit + HTTPS proxy ...
powershell -NoProfile -Command ^
  "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine -match 'streamlit run app\.py|ifs_reverse_proxy') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Get-NetTCPConnection -LocalPort 8501,80,443 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
timeout /t 2 /nobreak >nul

echo [2] Start Streamlit (local backend 127.0.0.1:8501) ...
set "STREAMLIT_SERVER_ENABLE_CORS=false"
set "STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false"
powershell -NoProfile -Command "Start-Process -FilePath '%PY%' -ArgumentList '-m','streamlit','run','app.py','--server.headless','true','--server.address','127.0.0.1','--server.port','8501','--browser.gatherUsageStats','false' -WorkingDirectory '%CD%' -WindowStyle Minimized"

echo [3] Wait for local health ...
powershell -NoProfile -Command "for ($i=1; $i -le 60; $i++) { try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8501/_stcore/health' -UseBasicParsing -TimeoutSec 2; if ($r.Content -eq 'ok' -or $r.StatusCode -eq 200) { Write-Host ('Backend ready in ' + $i + 's'); exit 0 } } catch {}; Start-Sleep 1 }; Write-Host 'ERROR: Backend did not become healthy.'; exit 1"
if errorlevel 1 (
  echo.
  echo Failed to start Streamlit. Check venv and app.py.
  pause
  exit /b 1
)

echo [4] Start public HTTPS reverse proxy (ports 80 + 443) ...
powershell -NoProfile -Command "Start-Process -FilePath '%PY%' -ArgumentList 'ifs_reverse_proxy.py' -WorkingDirectory '%CD%' -WindowStyle Minimized"

echo [5] Wait for public site https://erp.ifschemicals.com/ ...
powershell -NoProfile -Command "for ($i=1; $i -le 45; $i++) { try { $r = Invoke-WebRequest -Uri 'https://erp.ifschemicals.com/_stcore/health' -UseBasicParsing -TimeoutSec 3; if ($r.Content -eq 'ok') { Write-Host ('PUBLIC site ready in ' + $i + 's'); exit 0 } } catch {}; Start-Sleep 1 }; Write-Host 'ERROR: Public HTTPS still not ready.'; exit 1"
if errorlevel 1 (
  echo.
  echo Local ERP is running, but PUBLIC site failed.
  echo Check firewall and that ports 80/443 are free.
  echo Then run this file again as Administrator.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo  READY — open in browser:
echo    https://erp.ifschemicals.com/
echo  Local health:
echo    http://127.0.0.1:8501/_stcore/health
echo ============================================================
echo.
start "" "https://erp.ifschemicals.com/"
pause
