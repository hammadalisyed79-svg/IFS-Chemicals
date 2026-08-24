@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title IFS ERP — Git auto-push setup

echo ============================================================
echo  IFS ERP — configure Git + automatic push to Cursor Origin
echo ============================================================
echo.

echo [1] Repo-local Git identity ...
git config user.name "IFS ERP"
git config user.email "erp@ifschemicals.com"
git config push.default current
echo      user.name  = IFS ERP
echo      user.email = erp@ifschemicals.com
echo.

echo [2] Install post-commit push hook ...
set "HOOK=%~dp0.git\hooks\post-commit"
> "%HOOK%" (
  echo @echo off
  echo rem Auto-push after every commit via WSL + Cursor Origin
  echo wsl -d Ubuntu -e bash -lc "export PATH=\"$HOME/.local/bin:$PATH\"; cd '/mnt/c/MY ERPS'; git config --global --add safe.directory '/mnt/c/MY ERPS' 2^>/dev/null; git push origin \"$(git branch --show-current)\" 2^>/dev/null"
)
echo      Hook: %HOOK%
echo.

echo [3] Register scheduled task (every 30 minutes) ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\register_git_auto_push_task.ps1"
if errorlevel 1 (
  echo WARN: Could not register scheduled task. Run this .bat as Administrator.
) else (
  echo      Task: IFS_ERP_Git_AutoPush ^(every 30 min^)
)
echo.

echo [4] Test sync now ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\git_auto_sync.ps1"
echo.

echo ============================================================
echo  Done.
echo  - Commits + pushes tracked changes every 30 minutes
echo  - Also pushes immediately after manual git commit
echo  - Uses WSL Ubuntu + origin auth ^(run origin auth login if push fails^)
echo  - Manual run: tools\git_auto_sync.ps1
echo ============================================================
echo.
pause
