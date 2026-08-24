# Auto-commit tracked ERP changes and push via WSL + Cursor Origin.
param(
    [switch]$Quiet
)

$ErrorActionPreference = "Continue"
$RepoWin = "C:\MY ERPS"

function Write-Log($msg, [ConsoleColor]$color = [ConsoleColor]::Gray) {
    if (-not $Quiet) {
        Write-Host $msg -ForegroundColor $color
    }
}

$distros = wsl --list --quiet 2>$null
if (-not ($distros -match "Ubuntu")) {
    Write-Log "ERROR: Ubuntu WSL not found. Run: wsl --install -d Ubuntu" Red
    exit 1
}

Write-Log "=== IFS ERP Git auto-sync ===" Cyan
$output = wsl -d Ubuntu -e bash -lc "chmod +x '/mnt/c/MY ERPS/tools/git_auto_sync.sh' 2>/dev/null; '/mnt/c/MY ERPS/tools/git_auto_sync.sh'" 2>&1
$output | ForEach-Object { Write-Log $_ }

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
