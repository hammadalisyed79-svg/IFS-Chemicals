@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
python tests\test_nav_wiring.py || exit /b 1
python tests\test_v16_platform.py || exit /b 1
python tests\test_v17_platform.py || exit /b 1
python tests\test_v17_1_manufacturing.py || exit /b 1
python tests\test_v17_2_certification.py || exit /b 1
python tests\test_api_v1.py || exit /b 1
python tests\test_portal_security.py || exit /b 1
echo All V17 test suites passed.