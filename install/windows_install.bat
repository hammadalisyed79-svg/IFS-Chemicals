@echo off
REM IFS ERP V16 Windows installer helper
cd /d "%~dp0"
echo === IFS Industrial ERP V16 Installer ===
if not exist venv (
  python -m venv venv
)
call venv\Scripts\activate.bat
pip install -r requirements.txt
python -c "import database as db; db.init_db(); print('Database migrated to', __import__('erp_version').APP_VERSION)"
echo.
echo Installed. Run:
echo   RUN_SOFTWARE.bat  - Desktop ERP
echo   RUN_PORTAL.bat    - Distributor portal
echo   RUN_API.bat       - REST API
pause
