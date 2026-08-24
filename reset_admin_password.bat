@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
python tools\reset_admin_password.py
pause
