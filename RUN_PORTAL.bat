@echo off
cd /d "%~dp0"
echo Starting IFS Distributor Portal on http://127.0.0.1:8502
echo Production: use Nginx HTTPS at /portal — do not expose port 8502 publicly.
.\venv\Scripts\streamlit.exe run portal_app.py --server.port=8502 --server.address=127.0.0.1
pause
