# Weekly Let's Encrypt renewal so erp.ifschemicals.com does not go dark on expiry.
$ErrorActionPreference = "Stop"
$Root = "C:\MY ERPS"
$Bat = Join-Path $Root "RENEW_ERP_SSL.bat"
if (-not (Test-Path $Bat)) { throw "Missing $Bat" }

cmd /c "schtasks /Delete /TN `"IFS ERP SSL Renew`" /F >nul 2>&1" | Out-Null

$tr = "`"$Bat`""
schtasks /Create /F /TN "IFS ERP SSL Renew" /SC WEEKLY /D SUN /ST 04:10 /RL HIGHEST /RU SYSTEM /TR $tr | Out-Host

try {
    $t = Get-ScheduledTask -TaskName "IFS ERP SSL Renew"
    $s = $t.Settings
    $s.ExecutionTimeLimit = "PT20M"
    $s.MultipleInstances = "IgnoreNew"
    $s.StartWhenAvailable = $true
    Set-ScheduledTask -TaskName "IFS ERP SSL Renew" -Settings $s | Out-Null
} catch {
    Write-Host "Note: ssl renew settings soft-fail: $($_.Exception.Message)"
}

schtasks /Query /TN "IFS ERP SSL Renew" /FO LIST | Select-String "TaskName|Status|Next Run|Task To Run"
Write-Host "OK: IFS ERP SSL Renew (weekly Sunday 04:10)"
