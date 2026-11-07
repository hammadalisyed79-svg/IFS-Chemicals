@echo off
:: Renew Let's Encrypt for erp.ifschemicals.com (no-op if still valid).
setlocal EnableExtensions
cd /d "%~dp0"
set "CB=%CD%\venv\Scripts\certbot.exe"
if not exist "%CB%" (
  echo ERROR: certbot missing at "%CB%"
  exit /b 1
)
if not exist "%CD%\logs" mkdir "%CD%\logs" >nul 2>&1
"%CB%" renew --config-dir "%CD%\certs\config" --work-dir "%CD%\certs\work" --logs-dir "%CD%\certs\logs" --non-interactive --deploy-hook "%CD%\tools\restart_erp_proxy.bat"
exit /b %ERRORLEVEL%
