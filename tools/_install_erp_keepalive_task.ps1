# Add / refresh a recurring task that keeps ERP up during the day.
$ErrorActionPreference = "Stop"
$Root = "C:\MY ERPS"
$Ensure = Join-Path $Root "ENSURE_ERP_RUNNING.bat"
if (-not (Test-Path $Ensure)) { throw "Missing $Ensure" }

cmd /c "schtasks /Delete /TN `"IFS ERP Keepalive`" /F >nul 2>&1" | Out-Null

# Every 5 minutes, run ensure script as SYSTEM with highest privileges
$tr = "`"$Ensure`""
schtasks /Create /F /TN "IFS ERP Keepalive" /SC MINUTE /MO 5 /RL HIGHEST /RU SYSTEM /TR $tr | Out-Host

try {
    $t = Get-ScheduledTask -TaskName "IFS ERP Keepalive"
    $s = $t.Settings
    $s.ExecutionTimeLimit = "PT10M"
    $s.MultipleInstances = "IgnoreNew"
    $s.StartWhenAvailable = $true
    Set-ScheduledTask -TaskName "IFS ERP Keepalive" -Settings $s | Out-Null
} catch {
    Write-Host "Note: keepalive settings soft-fail: $($_.Exception.Message)"
}

# Run once now
schtasks /Run /TN "IFS ERP Keepalive" | Out-Host
Write-Host "OK: IFS ERP Keepalive (every 5 minutes)"
schtasks /Query /TN "IFS ERP Keepalive" /FO LIST | Select-String "TaskName|Status|Next Run|Task To Run"
