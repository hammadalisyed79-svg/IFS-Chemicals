@echo off
setlocal
cd /d "%~dp0"
title IFS ERP — restart Streamlit + HTTPS proxy

set "PY=%CD%\venv\Scripts\python.exe"
if not exist "%PY%" (
  echo ERROR: venv not found at "%PY%"
  pause
  exit /b 1
)

echo [1] Stop old Streamlit and reverse proxy ...
powershell -NoProfile -Command ^
  "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine -match 'streamlit run app\.py|ifs_reverse_proxy') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 2 /nobreak >nul

echo [2] Start Streamlit on 127.0.0.1:8501 ...
set "STREAMLIT_SERVER_ENABLE_CORS=false"
set "STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false"
powershell -NoProfile -Command "Start-Process -FilePath '%PY%' -ArgumentList '-m','streamlit','run','app.py','--server.headless','true','--server.address','127.0.0.1','--server.port','8501','--browser.gatherUsageStats','false' -WorkingDirectory '%CD%' -WindowStyle Minimized"

echo [3] Wait for Streamlit health ...
powershell -NoProfile -Command "for ($i=1; $i -le 60; $i++) { try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8501/_stcore/health' -UseBasicParsing -TimeoutSec 2; if ($r.Content -eq 'ok') { Write-Host ('Streamlit ready in ' + $i + 's'); exit 0 } } catch {}; Start-Sleep 1 }; Write-Host 'ERROR: Streamlit did not start.'; exit 1"
if errorlevel 1 exit /b 1

echo [4] Start HTTPS reverse proxy (ports 80 + 443) ...
powershell -NoProfile -Command "Start-Process -FilePath '%PY%' -ArgumentList 'ifs_reverse_proxy.py' -WorkingDirectory '%CD%' -WindowStyle Minimized"

echo [5] Wait for public HTTPS health ...
powershell -NoProfile -Command "for ($i=1; $i -le 30; $i++) { try { $r = Invoke-WebRequest -Uri 'https://erp.ifschemicals.com/_stcore/health' -UseBasicParsing -TimeoutSec 3; if ($r.Content -eq 'ok') { Write-Host ('Public site ready in ' + $i + 's'); exit 0 } } catch {}; Start-Sleep 1 }; Write-Host 'WARN: Public HTTPS not ready yet (check firewall / run as Administrator).'; exit 0"

echo.
echo Done. Open: https://erp.ifschemicals.com/
echo Local:  http://127.0.0.1:8501/_stcore/health
echo.
pause
