@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
python tests\test_v17_3_finance.py || exit /b 1
python tests\test_v17_2_certification.py || exit /b 1
python tests\test_v17_1_manufacturing.py || exit /b 1
python tests\test_api_v1.py || exit /b 1
python tools\v17_3\factory_simulation.py || exit /b 1
python tools\generate_v17_3_certification.py || exit /b 1
echo V17.3 certification complete.