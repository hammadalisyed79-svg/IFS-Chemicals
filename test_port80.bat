@echo off
echo Testing ERP port 80 on 138.201.139.157 ...
echo.
powershell -NoProfile -Command "Test-NetConnection 138.201.139.157 -Port 80 | Format-List ComputerName,RemotePort,TcpTestSucceeded"
echo.
curl.exe -s -o NUL -w "HTTP response: %%{http_code}\n" --connect-timeout 10 http://138.201.139.157/
echo.
echo TcpTestSucceeded True + HTTP 200 = ERP reachable.
echo If TcpTestSucceeded False = open port 80 in Hetzner Cloud Firewall.
pause
