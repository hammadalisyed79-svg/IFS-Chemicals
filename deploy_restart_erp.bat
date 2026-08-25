@echo off
setlocal
cd /d "%~dp0"
title IFS ERP — quick redeploy (reload code, restart Streamlit)

echo ============================================================
echo  IFS ERP quick redeploy — restart Streamlit on port 8501
echo  Code folder: %CD%
echo  Public URL:  https://erp.ifschemicals.com/
echo ============================================================
echo.

set "PY=%CD%\venv\Scripts\python.exe"
if not exist "%PY%" (
  echo ERROR: venv not found. Run from C:\MY ERPS
  pause
  exit /b 1
)

echo [1] Stop old Streamlit (app.py) ...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -match 'streamlit run app.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 3 /nobreak >nul

echo [2] Start Streamlit backend ...
set "STREAMLIT_SERVER_ENABLE_CORS=false"
set "STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false"
powershell -NoProfile -Command "Start-Process -FilePath '%PY%' -ArgumentList '-m','streamlit','run','app.py','--server.headless','true','--server.address','127.0.0.1','--server.port','8501','--browser.gatherUsageStats','false' -WorkingDirectory '%CD%' -WindowStyle Minimized"

echo [3] Wait for health ...
powershell -NoProfile -Command "for ($i=1; $i -le 60; $i++) { $code = & curl.exe -s -o NUL -w '%%{http_code}' --max-time 3 http://127.0.0.1:8501/_stcore/health; if ($code -eq '200') { Write-Host ('Backend ready in ' + $i + 's'); exit 0 }; Start-Sleep 1 }; Write-Host 'ERROR: Backend did not start on port 8501.'; exit 1"
if errorlevel 1 (
  echo.
  echo Backend failed to start. Run START_ERP.bat as Administrator.
  pause
  exit /b 1
)

echo.
echo Done. Refresh browser: https://erp.ifschemicals.com/
echo If site is down, run START_ERP.bat as Administrator.
echo.
pause
