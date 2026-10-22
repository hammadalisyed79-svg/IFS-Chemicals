# Non-interactive install of IFS ERP boot + watchdog scheduled tasks.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not (Test-Path (Join-Path $Root "erp_watchdog.py"))) {
    $Root = "C:\MY ERPS"
}
$Silent = Join-Path $Root "START_ERP_SILENT.bat"
$WatchBat = Join-Path $Root "START_WATCHDOG.bat"
$Py = Join-Path $Root "venv\Scripts\python.exe"
$WatchPy = Join-Path $Root "erp_watchdog.py"

foreach ($p in @($Silent, $WatchBat, $Py, $WatchPy)) {
    if (-not (Test-Path $p)) { throw "Missing: $p" }
}

foreach ($tn in @("IFS ERP HTTPS Startup", "IFS ERP Boot", "IFS ERP Watchdog")) {
    cmd /c "schtasks /Delete /TN `"$tn`" /F >nul 2>&1" | Out-Null
}

$bootTr = "`"$Silent`""
$watchTr = "`"$WatchBat`""

schtasks /Create /F /TN "IFS ERP Boot" /SC ONSTART /DELAY 0000:45 /RL HIGHEST /RU SYSTEM /TR $bootTr | Out-Host
schtasks /Create /F /TN "IFS ERP Watchdog" /SC ONSTART /DELAY 0001:30 /RL HIGHEST /RU SYSTEM /TR $watchTr | Out-Host

# Hardening via schtasks is optional — created ONSTART tasks are enough.
# (Some Server SKUs reject RestartInterval / battery flags via Set-ScheduledTask.)
try {
    $watch = Get-ScheduledTask -TaskName "IFS ERP Watchdog"
    $ws = $watch.Settings
    $ws.ExecutionTimeLimit = "PT0S"   # run forever
    $ws.MultipleInstances = "IgnoreNew"
    $ws.StartWhenAvailable = $true
    Set-ScheduledTask -TaskName "IFS ERP Watchdog" -Settings $ws | Out-Null
} catch {
    Write-Host "Note: watchdog task created; optional settings skipped ($($_.Exception.Message))"
}

$existing = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match "erp_watchdog\.py" }
if (-not $existing) {
    $logs = Join-Path $Root "logs"
    New-Item -ItemType Directory -Force -Path $logs | Out-Null
    Start-Process -FilePath $Py -ArgumentList "erp_watchdog.py" -WorkingDirectory $Root `
        -RedirectStandardOutput (Join-Path $logs "erp_watchdog.out.log") `
        -RedirectStandardError (Join-Path $logs "erp_watchdog.err.log") `
        -WindowStyle Hidden
    Start-Sleep 2
}

Write-Host "OK: IFS ERP Boot + IFS ERP Watchdog installed"
schtasks /Query /TN "IFS ERP Boot" /FO LIST | Select-String "TaskName|Status|Task To Run"
schtasks /Query /TN "IFS ERP Watchdog" /FO LIST | Select-String "TaskName|Status|Task To Run"
$log = Join-Path $Root "logs\erp_watchdog.log"
if (Test-Path $log) { Get-Content $log -Tail 10 }
