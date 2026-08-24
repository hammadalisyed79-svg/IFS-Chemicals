@echo off
setlocal
cd /d "%~dp0.."

set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if not exist "%CSC%" (
    echo ERROR: C# compiler (csc.exe) not found.
    exit /b 1
)

echo Building IFS_ERP.exe ...
"%CSC%" /nologo /target:winexe /optimize+ /out:"IFS_ERP.exe" /r:System.Windows.Forms.dll /r:System.dll "packaging\IFS_ERP_Launcher.cs"
if errorlevel 1 (
    echo BUILD FAILED
    exit /b 1
)

echo.
echo OK: %CD%\IFS_ERP.exe
echo Double-click IFS_ERP.exe to start the ERP and open the browser.
exit /b 0
