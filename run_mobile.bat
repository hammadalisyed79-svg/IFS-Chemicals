@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
echo.
echo ============================================================
echo  IFS ERP — MOBILE ACCESS MODE
echo.
echo  Open on your phone browser:
echo    http://ifschemicals.com/
echo    http://www.ifschemicals.com/
echo.
echo  Tips:
echo  - Run open_erp_firewall.bat as Admin (once)
echo  - Open port 8501 in your cloud/hosting firewall too
echo  - Use Administration ^> Mobile Approvals for phone workflows
echo  - For production use HTTPS on port 443 (see DEPLOYMENT_SERVER_GUIDE.md)
echo ============================================================
echo.
python -m streamlit run app.py --server.headless true --server.address 0.0.0.0 --server.port 8501 --server.enableWebsocketCompression true
