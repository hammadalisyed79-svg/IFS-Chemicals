# Configure Windows Git to use Origin auth via WSL (Origin CLI is WSL-only on Windows).
# Run from repo root:  powershell -ExecutionPolicy Bypass -File tools\setup_origin_windows.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "=== Origin auth for Windows (via WSL) ===" -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot"
Write-Host ""

# 1) WSL + Origin CLI
$wslCheck = wsl -e bash -lc "command -v origin && origin --version" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Origin CLI not found in WSL. Installing..." -ForegroundColor Yellow
    wsl -e bash -lc "curl -fsSL https://downloads.cursor.com/origin/install.sh | sh"
    wsl -e bash -lc 'grep -q ".local/bin" ~/.bashrc || echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> ~/.bashrc'
}

Write-Host "WSL Origin:" -ForegroundColor Green
wsl -e bash -lc "origin --version; origin auth status" 2>&1

$auth = wsl -e bash -lc "origin auth status 2>&1" | Out-String
if ($auth -notmatch "Token:\s+valid") {
    Write-Host ""
    Write-Host "Origin token not valid in WSL. Run login (browser or URL):" -ForegroundColor Yellow
    Write-Host '  wsl -e bash -lc "origin auth login"'
    wsl -e bash -lc "origin auth login"
}

# 2) Optional: WSL metadata for /mnt/c (reduces chmod warnings on git config)
Write-Host ""
Write-Host "Tip: if git reports chmod errors on /mnt/c, add metadata to /etc/wsl.conf and run wsl --shutdown" -ForegroundColor Gray

# 3) Repo-local Git credential helper (does not change other repos)
$helper = Join-Path $RepoRoot "tools\origin_credential_helper.cmd"
if (-not (Test-Path $helper)) {
    throw "Missing $helper"
}
$helperGit = ($helper -replace '\\', '/') -replace ' ', '\ '

Write-Host ""
Write-Host "Configuring repo-local Git credential helper..." -ForegroundColor Cyan
Push-Location $RepoRoot

$userBin = Join-Path $env:USERPROFILE "bin"
New-Item -ItemType Directory -Force -Path $userBin | Out-Null
$helperSrc = Join-Path $RepoRoot "tools\origin_credential_helper.cmd"
$helperDst = Join-Path $userBin "origin_credential_helper.cmd"
Copy-Item $helperSrc $helperDst -Force

git config --local --unset-all credential.https://origin.cursor.com.helper 2>$null
git config --local --unset-all credential.https://origin.cursor.com/git.helper 2>$null
$helperGit = ($helperDst -replace '\\', '/')
git config --local credential.https://origin.cursor.com.helper "!$helperGit"
git config --local credential.https://origin.cursor.com/git.helper "!$helperGit"
git config --local --add safe.directory "C:/MY ERPS"

Write-Host "credential helper: $(git config --local --get credential.https://origin.cursor.com.helper)"

Write-Host ""
Write-Host "Testing fetch from Windows Git..." -ForegroundColor Cyan
git fetch origin 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "OK - Windows Git can authenticate to Cursor Origin." -ForegroundColor Green
} else {
    Write-Host "Fetch failed. Re-run: wsl origin auth login" -ForegroundColor Red
}
Pop-Location

Write-Host ""
Write-Host 'Done. Use tools\origin_git.ps1 push | pull | fetch | status' -ForegroundColor Cyan
