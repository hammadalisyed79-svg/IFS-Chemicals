@echo off
REM Windows Git -> WSL Origin credential helper (Origin CLI is WSL-only on Windows).
setlocal
set OP=%1
if "%OP%"=="" set OP=get
wsl.exe -e bash -lc "origin credential-helper %OP%"
