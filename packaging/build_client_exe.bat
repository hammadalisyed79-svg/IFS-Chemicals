@echo off
setlocal
cd /d "%~dp0.."

set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if not exist "%CSC%" (
    echo ERROR: C# compiler ^(csc.exe^) not found.
    exit /b 1
)

set "OUTDIR=%CD%\client_dist"
if not exist "%OUTDIR%" mkdir "%OUTDIR%"

echo Building IFS_Chemicals_ERP.exe ^(client^) ...
"%CSC%" /nologo /target:winexe /optimize+ /out:"%OUTDIR%\IFS_Chemicals_ERP.exe" /r:System.Windows.Forms.dll /r:System.dll "packaging\IFS_ERP_Client_Launcher.cs"
if errorlevel 1 (
    echo BUILD FAILED
    exit /b 1
)

> "%OUTDIR%\erp_url.txt" echo https://erp.ifschemicals.com/

> "%OUTDIR%\IFS_Chemicals_ERP.url" (
echo [InternetShortcut]
echo URL=https://erp.ifschemicals.com/
echo IconIndex=0
)

> "%OUTDIR%\README.txt" (
echo IFS chemicals ERP — Client PC
echo =============================
echo.
echo OPEN THE APP
echo   Double-click  IFS_Chemicals_ERP.exe
echo   It opens your browser to https://erp.ifschemicals.com/
echo.
echo OR USE THE BROWSER DIRECTLY
echo   https://erp.ifschemicals.com/
echo.
echo LOGIN
echo   Use your username and password from the administrator.
echo   On first login you may be asked to change your password.
echo.
echo REQUIREMENTS
echo   Windows PC with internet
echo   Chrome / Edge / Firefox
echo.
echo OPTIONAL
echo   Edit erp_url.txt next to the EXE if the ERP address changes.
echo.

)

echo.
echo OK: %OUTDIR%\IFS_Chemicals_ERP.exe
echo     %OUTDIR%\erp_url.txt
echo     %OUTDIR%\README.txt
echo.
echo Clients download from:
echo   https://erp.ifschemicals.com/  ^(ERP - Download App^)
echo   or copy the client_dist folder.
exit /b 0
