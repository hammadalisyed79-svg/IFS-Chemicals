# Register Windows Scheduled Task: IFS ERP Git auto-push every 30 minutes.
$ErrorActionPreference = "Stop"

$TaskName = "IFS_ERP_Git_AutoPush"
$Runner = "C:\MY ERPS\tools\git_auto_sync_scheduled.bat"

if (-not (Test-Path $Runner)) {
    Write-Error "Missing $Runner"
}

schtasks /Create /TN $TaskName /TR "`"$Runner`"" /SC MINUTE /MO 30 /RU SYSTEM /F
if ($LASTEXITCODE -ne 0) {
    throw "schtasks failed with exit code $LASTEXITCODE"
}
Write-Host "Registered scheduled task: $TaskName (every 30 minutes)"
