@echo off
REM Incremental upload from FMYE + weighbridge + payroll (no ERP reset, skips duplicates)
REM Dates: refreshes live sources; imports only new document_no rows.
setlocal EnableExtensions
cd /d "%~dp0"

set "PY=.\venv\Scripts\python.exe"
if not exist "%PY%" (
  echo ERROR: venv python not found
  exit /b 1
)

echo ============================================================
echo  IFS ERP — incremental data upload (no duplicates)
echo  %DATE% %TIME%
echo ============================================================
echo.

echo [1/7] FMYE sales ...
"%PY%" migrate_fmye.py --step sales
if errorlevel 1 goto :fail

echo [2/7] FMYE purchases ...
"%PY%" migrate_fmye.py --step purchases
if errorlevel 1 goto :fail

echo [3/7] FMYE returns ...
"%PY%" migrate_fmye.py --step returns
if errorlevel 1 goto :fail

echo [4/7] FMYE vouchers ...
"%PY%" migrate_fmye.py --step vouchers
if errorlevel 1 goto :fail

echo [5/7] Inventory movements + balances + auth status ...
"%PY%" migrate_fmye.py --step inventory
"%PY%" migrate_fmye.py --step balances
"%PY%" sync_fmye_auth_status.py --apply

echo [6/7] Weighbridge slips ...
"%PY%" import_weight_scale.py --apply

echo [7/7] Payroll / HR refresh ...
"%PY%" import_payroll_hr.py --apply

echo.
echo Done. Spot-check Sale/Purchase Approval for pending_approval docs.
echo Web: http://138.201.139.157/
exit /b 0

:fail
echo FAILED — see errors above.
exit /b 1
