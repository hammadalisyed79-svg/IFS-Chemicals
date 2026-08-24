@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
python tools\apply_domain_settings.py
pause
