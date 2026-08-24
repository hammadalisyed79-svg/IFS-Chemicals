@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo  IFS ERP — 2026 cutover import from FMYE export
echo  Requires fresh files in: import\fmye\full\
echo ============================================================
echo.

if not exist "import\fmye\full\reload.sql" (
    echo ERROR: import\fmye\full\reload.sql not found.
    echo Copy a fresh FMYE dbunload export first.
    echo See: import\fmye\CUTOVER_SATURDAY.txt
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
echo.
echo [1/3] Reset ERP database (backup created automatically)...
python migrate_fmye.py --reset
if errorlevel 1 goto fail

echo.
echo [2/3] Import masters...
python migrate_fmye.py --step masters
if errorlevel 1 goto fail

echo.
echo [3/3] Import 2026 openings + transactions...
python migrate_fmye.py --phase 2026
if errorlevel 1 goto fail

echo.
echo DONE. Next:
echo   1. Run reset_admin_password.bat
echo   2. Start with IFS_ERP.exe or restart_external.bat
echo   3. Verify sample invoices and balances
pause
exit /b 0

:fail
echo.
echo IMPORT FAILED — check messages above. Old backup is under import\fmye\backups\
pause
exit /b 1
