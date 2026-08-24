@echo off
REM Copy client app package to a shared folder or USB for staff PCs
setlocal
cd /d "%~dp0"
if not exist "client_dist\IFS_Chemicals_ERP.exe" (
  echo Building client EXE first...
  call packaging\build_client_exe.bat
)
echo.
echo Client package ready:
echo   %CD%\client_dist\
echo.
echo Give staff:
echo   1^) Browser link  http://138.201.139.157/
echo   2^) Or copy IFS_Chemicals_ERP.exe from client_dist
echo.
explorer "%CD%\client_dist"
exit /b 0
