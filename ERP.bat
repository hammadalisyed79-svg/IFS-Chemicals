@echo off
:: =============================================================================
::  IFS Chemicals ERP — SINGLE STARTER
::  Double-click this file (or Run as administrator). It will:
::    1) Ask for Admin (needed for public HTTPS ports 80/443)
::    2) Install/repair boot + watchdog + 5-min keepalive tasks
::    3) Start Streamlit + HTTPS proxy + watchdog
::    4) Open https://erp.ifschemicals.com/
:: =============================================================================
setlocal EnableExtensions
cd /d "%~dp0"
title IFS ERP — start all

net session >nul 2>&1
if errorlevel 1 (
  echo.
  echo  Requesting Administrator rights...
  echo  Click YES on the UAC prompt so public HTTPS can start.
  echo.
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
  exit /b
)

if not exist "%CD%\logs" mkdir "%CD%\logs" >nul 2>&1
if not exist "%CD%\venv\Scripts\python.exe" (
  echo ERROR: venv missing. Run:  python -m venv venv ^&^& venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)
if not exist "%CD%\certs\config\live\erp.ifschemicals.com\fullchain.pem" (
  echo ERROR: SSL certificate missing under certs\config\live\erp.ifschemicals.com\
  pause
  exit /b 1
)

echo.
echo ============================================================
echo  IFS ERP — START ALL
echo  %CD%
echo ============================================================
echo.

echo [1/4] Repair auto-start tasks (boot + watchdog + keepalive + DB backup)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\tools\_install_erp_autostart.ps1" > "%CD%\logs\erp_autostart_install.log" 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\tools\_install_erp_keepalive_task.ps1" > "%CD%\logs\erp_keepalive_install.log" 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\tools\_install_erp_backup_task.ps1" > "%CD%\logs\erp_backup_install.log" 2>&1

echo [2/4] Stop old ERP processes...
powershell -NoProfile -Command ^
  "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine -match 'streamlit run app\.py|ifs_reverse_proxy|erp_watchdog\.py') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Get-NetTCPConnection -LocalPort 8501,80,443 -ErrorAction SilentlyContinue | ForEach-Object { if ($_.OwningProcess -gt 0) { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } }"
timeout /t 3 /nobreak >nul

echo [3/4] Start Streamlit + HTTPS proxy + watchdog...
set "PY=%CD%\venv\Scripts\python.exe"
set "STREAMLIT_SERVER_ENABLE_CORS=false"
set "STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false"
powershell -NoProfile -Command "Start-Process -FilePath '%PY%' -ArgumentList '-m','streamlit','run','app.py','--server.headless','true','--server.address','127.0.0.1','--server.port','8501','--browser.gatherUsageStats','false' -WorkingDirectory '%CD%' -RedirectStandardOutput '%CD%\logs\streamlit_start.out.log' -RedirectStandardError '%CD%\logs\streamlit_start.err.log' -WindowStyle Hidden"

powershell -NoProfile -Command "for ($i=1; $i -le 90; $i++) { try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8501/_stcore/health' -UseBasicParsing -TimeoutSec 2; if ($r.Content -eq 'ok' -or $r.StatusCode -eq 200) { Write-Host ('   Backend ready in ' + $i + 's'); exit 0 } } catch {}; Start-Sleep 1 }; Write-Host 'ERROR: Streamlit did not start.'; if (Test-Path '%CD%\logs\streamlit_start.err.log') { Get-Content '%CD%\logs\streamlit_start.err.log' -Tail 30 }; exit 1"
if errorlevel 1 (
  echo.
  echo Failed. See logs\streamlit_start.err.log
  pause
  exit /b 1
)

powershell -NoProfile -Command "Start-Process -FilePath '%PY%' -ArgumentList 'ifs_reverse_proxy.py' -WorkingDirectory '%CD%' -RedirectStandardOutput '%CD%\logs\proxy_start.out.log' -RedirectStandardError '%CD%\logs\proxy_start.err.log' -WindowStyle Hidden"
powershell -NoProfile -Command "Start-Process -FilePath '%PY%' -ArgumentList 'erp_watchdog.py' -WorkingDirectory '%CD%' -RedirectStandardOutput '%CD%\logs\erp_watchdog.out.log' -RedirectStandardError '%CD%\logs\erp_watchdog.err.log' -WindowStyle Hidden"

echo [4/4] Wait for public site...
powershell -NoProfile -Command "for ($i=1; $i -le 45; $i++) { try { $r = Invoke-WebRequest -Uri 'https://erp.ifschemicals.com/_stcore/health' -UseBasicParsing -TimeoutSec 3; if ($r.Content -eq 'ok') { Write-Host ('   PUBLIC ready in ' + $i + 's'); exit 0 } } catch {}; Start-Sleep 1 }; Write-Host 'WARN: Public HTTPS not ready yet.'; exit 1"
if errorlevel 1 (
  echo Local ERP is up, but public site may need firewall / DNS check.
  echo Local:  http://127.0.0.1:8501
)

:: Desktop shortcut (once)
powershell -NoProfile -Command ^
  "$desk=[Environment]::GetFolderPath('Desktop'); $lnk=Join-Path $desk 'IFS ERP.lnk'; " ^
  "$ws=New-Object -ComObject WScript.Shell; $s=$ws.CreateShortcut($lnk); " ^
  "$s.TargetPath='%~f0'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%%SystemRoot%%\System32\shell32.dll,165'; " ^
  "$s.Description='Start IFS Chemicals ERP (all services)'; $s.Save(); Write-Host '   Desktop shortcut: IFS ERP.lnk'"

echo.
echo ============================================================
echo  READY
echo    Public:  https://erp.ifschemicals.com/
echo    Local:   http://127.0.0.1:8501
echo  Auto: boot + watchdog + keepalive every 5 minutes
echo ============================================================
echo.
start "" "https://erp.ifschemicals.com/"
pause
