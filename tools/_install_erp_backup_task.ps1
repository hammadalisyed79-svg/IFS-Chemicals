# Install / refresh automatic ERP database backup (every 6 hours).
$ErrorActionPreference = "Stop"
$Root = "C:\MY ERPS"
$Bat = Join-Path $Root "BACKUP_ERP_DB.bat"
if (-not (Test-Path $Bat)) { throw "Missing $Bat" }

cmd /c "schtasks /Delete /TN `"IFS ERP Backup`" /F >nul 2>&1" | Out-Null

$tr = "`"$Bat`""
# Every 6 hours — consistent SQLite snapshot for crash recovery
schtasks /Create /F /TN "IFS ERP Backup" /SC HOURLY /MO 6 /RL HIGHEST /RU SYSTEM /TR $tr | Out-Host

try {
    $t = Get-ScheduledTask -TaskName "IFS ERP Backup"
    $s = $t.Settings
    $s.ExecutionTimeLimit = "PT30M"
    $s.MultipleInstances = "IgnoreNew"
    $s.StartWhenAvailable = $true
    $s.WakeToRun = $true
    Set-ScheduledTask -TaskName "IFS ERP Backup" -Settings $s | Out-Null
} catch {
    Write-Host "Note: backup settings soft-fail: $($_.Exception.Message)"
}

# Take one backup immediately
& $Bat
schtasks /Query /TN "IFS ERP Backup" /FO LIST | Select-String "TaskName|Status|Next Run|Task To Run"
Write-Host "OK: IFS ERP Backup (every 6 hours) -> backups\auto\"
