# Finish WSL + Cursor Origin setup, then push MY ERPS to origin.
# Run AFTER server reboot (required once after wsl --install).
# Usage (PowerShell as Administrator):
#   Set-ExecutionPolicy -Scope Process Bypass -Force
#   & "C:\MY ERPS\tools\wsl_origin_push.ps1"

$ErrorActionPreference = "Stop"
$RepoWin = "C:\MY ERPS"
$RepoWsl = "/mnt/c/MY ERPS"
$OriginUrl = "https://origin.cursor.com/hammad-ali/IFS-Chemicals.git"

Write-Host "=== WSL / Origin push helper ===" -ForegroundColor Cyan

$distros = wsl --list --quiet 2>$null
if (-not ($distros -match "Ubuntu")) {
    Write-Host "Installing Ubuntu (first time may take a few minutes)..." -ForegroundColor Yellow
    wsl --install -d Ubuntu --no-launch --web-download
}

Write-Host @"

If this is the FIRST time Ubuntu runs, WSL will ask you to create a Linux username and password.
Complete that in the window that opens, then run this script again.

"@ -ForegroundColor Yellow

Write-Host "Checking Ubuntu..." -ForegroundColor Cyan
wsl -d Ubuntu -e bash -lc "echo Ubuntu OK"

Write-Host "Installing Origin CLI inside Ubuntu..." -ForegroundColor Cyan
wsl -d Ubuntu -e bash -lc @"
set -e
export PATH=\"\$HOME/.local/bin:\$PATH\"
if ! command -v origin >/dev/null 2>&1; then
  curl -fsSL https://downloads.cursor.com/origin/install.sh | sh
fi
origin --version
"@

Write-Host @"

=== Sign in to Cursor Origin (browser will open) ===
Complete login in the browser, then return here.

"@ -ForegroundColor Green
wsl -d Ubuntu -e bash -lc "export PATH=\"\$HOME/.local/bin:\$PATH\"; origin auth login"

Write-Host "Pushing main to $OriginUrl ..." -ForegroundColor Cyan
wsl -d Ubuntu -e bash -lc @"
set -e
export PATH=\"\$HOME/.local/bin:\$PATH\"
cd '$RepoWsl'
git remote remove origin 2>/dev/null || true
git remote add origin '$OriginUrl'
git push -u origin main
"@

Write-Host "Done. Refresh: https://cursor.com/codebase/hammad-ali/IFS-Chemicals/tree/main" -ForegroundColor Green
