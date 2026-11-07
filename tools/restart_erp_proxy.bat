@echo off
:: Reload HTTPS reverse proxy (used after Let's Encrypt renew).
setlocal EnableExtensions
cd /d "%~dp0.."
set "PY=%CD%\venv\Scripts\python.exe"
if not exist "%PY%" exit /b 1
if not exist "%CD%\logs" mkdir "%CD%\logs" >nul 2>&1

powershell -NoProfile -Command ^
  "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine -match 'ifs_reverse_proxy') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 2 /nobreak >nul
powershell -NoProfile -Command "Start-Process -FilePath '%PY%' -ArgumentList 'ifs_reverse_proxy.py' -WorkingDirectory '%CD%' -WindowStyle Hidden"
exit /b 0
