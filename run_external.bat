@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
echo.
echo ============================================================
echo  IFS ERP — EXTERNAL ACCESS MODE
echo  URL: http://ifschemicals.com:8501
echo       http://138.201.139.157:8501
echo.
echo  WARNING: HTTP only — use HTTPS/Nginx for production.
echo  Run open_erp_firewall.bat once if connection times out.
echo ============================================================
echo.
python -m streamlit run app.py --server.headless true --server.address 0.0.0.0 --server.port 8501
