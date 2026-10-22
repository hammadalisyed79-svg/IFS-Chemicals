@echo off
:: Quiet keep-alive: if Streamlit or watchdog is down, start them (and proxy if needed).
:: Used by scheduled task every few minutes — no pause, no browser.
setlocal EnableExtensions
cd /d "%~dp0"

set "PY=%CD%\venv\Scripts\python.exe"
if not exist "%PY%" exit /b 1
if not exist "%CD%\logs" mkdir "%CD%\logs" >nul 2>&1

:: If local health is OK and watchdog is running, nothing to do.
powershell -NoProfile -Command ^
  "$ok=$false; try { $r=Invoke-WebRequest 'http://127.0.0.1:8501/_stcore/health' -UseBasicParsing -TimeoutSec 3; if ($r.Content -eq 'ok') { $ok=$true } } catch {}; " ^
  "$wd=Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -and $_.CommandLine -match 'erp_watchdog\.py' }; " ^
  "if ($ok -and $wd) { exit 0 }; exit 1"
if not errorlevel 1 exit /b 0

:: Prefer elevated silent full start when ports 80/443 need Admin.
net session >nul 2>&1
if errorlevel 1 (
  :: Not admin: at least start Streamlit + watchdog (local). Public may need Admin START_ERP.
  powershell -NoProfile -Command ^
    "$py='%~dp0venv\Scripts\python.exe'; $root='%~dp0'; " ^
    "$st=Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -and $_.CommandLine -match 'streamlit run app\.py' }; " ^
    "if (-not $st) { Start-Process -FilePath $py -ArgumentList '-m','streamlit','run','app.py','--server.headless','true','--server.address','127.0.0.1','--server.port','8501','--browser.gatherUsageStats','false' -WorkingDirectory $root -WindowStyle Hidden }; " ^
    "$wd=Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -and $_.CommandLine -match 'erp_watchdog\.py' }; " ^
    "if (-not $wd) { Start-Process -FilePath $py -ArgumentList 'erp_watchdog.py' -WorkingDirectory $root -WindowStyle Hidden }"
  exit /b 0
)

:: Admin: full silent stack (Streamlit + HTTPS + watchdog)
call "%~dp0START_ERP_SILENT.bat"
exit /b %ERRORLEVEL%
