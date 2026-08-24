@echo off
REM V17 portable package builder
cd /d "%~dp0.."
set OUT=dist\ifs-erp-v17-portable
if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%"
xcopy /E /I /Y app.py portal_app.py api application domain infrastructure plugins services reports security migrations tools erp_core erp_ui db_*.py database.py erp_version.py requirements.txt schema*.sql "%OUT%\"
copy RUN_SOFTWARE.bat "%OUT%\"
copy RUN_PORTAL.bat "%OUT%\"
copy RUN_API.bat "%OUT%\"
copy install\windows_install.bat "%OUT%\install\"
echo Portable build: %OUT%
pause
