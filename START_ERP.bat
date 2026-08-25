@echo off
setlocal
cd /d "%~dp0"
title IFS Chemicals ERP — start

echo ============================================================
echo  IFS Chemicals ERP
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

echo [1] Stop any existing Streamlit app.py ...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -match 'streamlit run app\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 2 /nobreak >nul

echo [2] Start Streamlit on 127.0.0.1:8501 ...
set "STREAMLIT_SERVER_ENABLE_CORS=false"
set "STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false"
powershell -NoProfile -Command "Start-Process -FilePath '%PY%' -ArgumentList '-m','streamlit','run','app.py','--server.headless','true','--server.address','127.0.0.1','--server.port','8501','--browser.gatherUsageStats','false' -WorkingDirectory '%CD%' -WindowStyle Minimized"

echo [3] Wait for health ...
powershell -NoProfile -Command "for ($i=1; $i -le 60; $i++) { try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8501/_stcore/health' -UseBasicParsing -TimeoutSec 2; if ($r.Content -eq 'ok' -or $r.StatusCode -eq 200) { Write-Host ('Backend ready in ' + $i + 's'); exit 0 } } catch {}; Start-Sleep 1 }; Write-Host 'ERROR: Backend did not become healthy.'; exit 1"
if errorlevel 1 (
  echo.
  echo Failed to start. Check venv and app.py.
  pause
  exit /b 1
)

echo.
echo Running. Refresh: https://erp.ifschemicals.com/
echo Local health: http://127.0.0.1:8501/_stcore/health
echo.
pause
