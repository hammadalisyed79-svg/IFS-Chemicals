@echo off
:: Non-interactive start for Scheduled Tasks / watchdog (no pause, no browser).
setlocal EnableExtensions
cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0' -WindowStyle Hidden"
  exit /b
)

if not exist "%CD%\logs" mkdir "%CD%\logs" >nul 2>&1

set "PY=%CD%\venv\Scripts\python.exe"
if not exist "%PY%" exit /b 1
if not exist "%CD%\certs\config\live\erp.ifschemicals.com\fullchain.pem" exit /b 1

powershell -NoProfile -Command ^
  "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine -match 'streamlit run app\.py|ifs_reverse_proxy') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Get-NetTCPConnection -LocalPort 8501,80,443 -ErrorAction SilentlyContinue | ForEach-Object { if ($_.OwningProcess -gt 0) { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } }"
timeout /t 3 /nobreak >nul

set "STREAMLIT_SERVER_ENABLE_CORS=false"
set "STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false"
powershell -NoProfile -Command "Start-Process -FilePath '%PY%' -ArgumentList '-m','streamlit','run','app.py','--server.headless','true','--server.address','127.0.0.1','--server.port','8501','--browser.gatherUsageStats','false' -WorkingDirectory '%CD%' -RedirectStandardOutput '%CD%\logs\streamlit_start.out.log' -RedirectStandardError '%CD%\logs\streamlit_start.err.log' -WindowStyle Hidden"

powershell -NoProfile -Command "for ($i=1; $i -le 90; $i++) { try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8501/_stcore/health' -UseBasicParsing -TimeoutSec 2; if ($r.Content -eq 'ok' -or $r.StatusCode -eq 200) { exit 0 } } catch {}; Start-Sleep 1 }; exit 1"
if errorlevel 1 exit /b 1

powershell -NoProfile -Command "Start-Process -FilePath '%PY%' -ArgumentList 'ifs_reverse_proxy.py' -WorkingDirectory '%CD%' -RedirectStandardOutput '%CD%\logs\proxy_start.out.log' -RedirectStandardError '%CD%\logs\proxy_start.err.log' -WindowStyle Hidden"

powershell -NoProfile -Command "for ($i=1; $i -le 45; $i++) { try { $r = Invoke-WebRequest -Uri 'https://erp.ifschemicals.com/_stcore/health' -UseBasicParsing -TimeoutSec 3; if ($r.Content -eq 'ok') { exit 0 } } catch {}; Start-Sleep 1 }; exit 1"
if errorlevel 1 exit /b 1

:: Keepalive monitor (idempotent — exits if already running)
powershell -NoProfile -Command "Start-Process -FilePath '%PY%' -ArgumentList 'erp_watchdog.py' -WorkingDirectory '%CD%' -RedirectStandardOutput '%CD%\logs\erp_watchdog.out.log' -RedirectStandardError '%CD%\logs\erp_watchdog.err.log' -WindowStyle Hidden"
exit /b 0
