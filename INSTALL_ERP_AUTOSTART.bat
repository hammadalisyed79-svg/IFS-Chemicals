@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Install IFS ERP auto-start + watchdog

net session >nul 2>&1
if errorlevel 1 (
  echo Requesting Administrator rights...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
  exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\_install_erp_autostart.ps1"
if errorlevel 1 (
  echo Install failed.
  pause
  exit /b 1
)
echo.
pause
