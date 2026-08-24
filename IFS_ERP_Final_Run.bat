@echo off
setlocal EnableExtensions
title IFS_ERP_Final_Run
cd /d "%~dp0"

set "ERP_URL=https://erp.ifschemicals.com/"
set "PY=%CD%\venv\Scripts\python.exe"
set "LOG=%CD%\IFS_ERP_Final_Run.log"

echo.
echo ============================================================
echo   IFS Chemicals ERP  —  IFS_ERP_Final_Run
echo   %ERP_URL%
echo ============================================================
echo.

net session >nul 2>&1
if errorlevel 1 (
    echo This file needs Administrator rights for ports 80 and 443.
    echo Click YES on the Windows security prompt...
    echo.
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -WorkingDirectory '%~dp0' -Verb RunAs"
    if errorlevel 1 (
        echo ERROR: Administrator permission was denied. ERP was not started.
        echo Right-click this file and choose "Run as administrator".
        pause
        exit /b 1
    )
    exit /b 0
)

> "%LOG%" echo [%date% %time%] Final_Run started as Administrator
>> "%LOG%" echo cwd=%CD%

if not exist "app.py" (
    echo ERROR: app.py not found. Keep this file in C:\MY ERPS
    >> "%LOG%" echo ERROR: app.py missing
    pause
    exit /b 1
)

if not exist "%PY%" (
    echo First run: creating Python environment...
    where python >nul 2>nul
    if errorlevel 1 (
        echo ERROR: Python is not installed or not on PATH.
        pause
        exit /b 1
    )
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Could not create venv.
        pause
        exit /b 1
    )
    "%PY%" -m pip install --upgrade pip
    "%PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Could not install requirements.
        pause
        exit /b 1
    )
)

if not exist "%CD%\certs\config\live\erp.ifschemicals.com\fullchain.pem" (
    echo ERROR: HTTPS certificate is missing.
    echo Expected: %CD%\certs\config\live\erp.ifschemicals.com\fullchain.pem
    pause
    exit /b 1
)

echo Opening firewall for HTTP 80 and HTTPS 443 ...
netsh advfirewall firewall delete rule name="IFS ERP HTTP 80" >nul 2>&1
netsh advfirewall firewall add rule name="IFS ERP HTTP 80" dir=in action=allow protocol=TCP localport=80 profile=any >nul
netsh advfirewall firewall delete rule name="IFS ERP HTTPS 443" >nul 2>&1
netsh advfirewall firewall add rule name="IFS ERP HTTPS 443" dir=in action=allow protocol=TCP localport=443 profile=any >nul

powershell -NoProfile -Command "Import-Module WebAdministration; Stop-Website -Name 'Default Web Site' -ErrorAction SilentlyContinue" >nul 2>&1

echo Stopping old ERP / proxy copies ...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ( $_.CommandLine -match 'streamlit run app.py' -or $_.CommandLine -match 'ifs_reverse_proxy' ) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 4 /nobreak >nul

echo Waiting for ports 80, 443 and 8501 to be free ...
powershell -NoProfile -Command "for ($i=0; $i -lt 15; $i++) { $busy = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in 80,443,8501 }; if (-not $busy) { exit 0 }; Start-Sleep 1 }; exit 0"

set "STREAMLIT_SERVER_ENABLE_CORS=false"
set "STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false"

echo Starting ERP backend (127.0.0.1:8501) ...
powershell -NoProfile -Command "Start-Process -FilePath '%PY%' -ArgumentList '-m','streamlit','run','app.py','--server.headless','true','--server.address','127.0.0.1','--server.port','8501','--browser.gatherUsageStats','false' -WorkingDirectory '%CD%' -WindowStyle Minimized"
>> "%LOG%" echo [%date% %time%] started streamlit

echo Waiting for backend health ...
powershell -NoProfile -Command "for ($i=1; $i -le 60; $i++) { $code = & curl.exe -s -o NUL -w '%%{http_code}' --max-time 3 http://127.0.0.1:8501/_stcore/health; if ($code -eq '200') { Write-Host ('Backend ready in ' + $i + 's'); exit 0 }; Start-Sleep 1 }; Write-Host 'ERROR: ERP backend did not become healthy on port 8501.'; exit 1"
if errorlevel 1 (
    >> "%LOG%" echo [%date% %time%] backend health FAILED
    echo See log: %LOG%
    pause
    exit /b 1
)
echo Backend is ready.
>> "%LOG%" echo [%date% %time%] backend health OK

echo Starting HTTPS proxy (80 + 443) ...
powershell -NoProfile -Command "Start-Process -FilePath '%PY%' -ArgumentList 'ifs_reverse_proxy.py' -WorkingDirectory '%CD%' -WindowStyle Minimized"
>> "%LOG%" echo [%date% %time%] started proxy

echo Waiting for HTTPS proxy health ...
powershell -NoProfile -Command "for ($i=1; $i -le 30; $i++) { $code = & curl.exe -sk -o NUL -w '%%{http_code}' --max-time 4 https://127.0.0.1/_stcore/health; if ($code -eq '200') { Write-Host ('HTTPS proxy ready in ' + $i + 's'); exit 0 }; Start-Sleep 1 }; Write-Host 'ERROR: HTTPS proxy did not start on ports 80/443.'; Write-Host 'IIS or another program may be using those ports.'; netstat -ano | Select-String ':80 |:443 ' | Select-Object -First 12; exit 1"
if errorlevel 1 (
    >> "%LOG%" echo [%date% %time%] proxy health FAILED
    echo See log: %LOG%
    pause
    exit /b 1
)
echo HTTPS proxy is ready.
>> "%LOG%" echo [%date% %time%] proxy health OK

echo.
echo Checking %ERP_URL% ...
powershell -NoProfile -Command "try { $r = Invoke-WebRequest 'https://erp.ifschemicals.com/_stcore/health' -UseBasicParsing -TimeoutSec 12; Write-Host ('Public HTTPS ' + $r.StatusCode) } catch { Write-Host ('Public HTTPS check: ' + $_.Exception.Message) }"

echo Opening browser: %ERP_URL%
start "" "%ERP_URL%"

echo.
echo ============================================================
echo   Software is active.
echo   Public:  https://erp.ifschemicals.com/
echo   Local:   http://127.0.0.1:8501/
echo.
echo   Leave this window and the minimized Python windows open.
echo   Run this file again only when you need a restart.
echo ============================================================
echo.
>> "%LOG%" echo [%date% %time%] success
pause
exit /b 0
