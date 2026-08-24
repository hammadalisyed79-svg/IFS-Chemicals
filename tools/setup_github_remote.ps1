# One-time GitHub remote setup for IFS ERP.
# 1) Create repo on GitHub: https://github.com/new  name: IFS-Chemicals  (Private recommended)
# 2) Sign in: gh auth login   OR use a Personal Access Token when git asks
# 3) Run this script

$ErrorActionPreference = "Stop"
$Repo = "C:\MY ERPS"
$GithubUrl = "https://github.com/hammadalisyed79-svg/IFS-Chemicals.git"

Set-Location $Repo

$remotes = git remote
if ($remotes -notcontains "github") {
    git remote add github $GithubUrl
    Write-Host "Added remote: github -> $GithubUrl" -ForegroundColor Green
} else {
    git remote set-url github $GithubUrl
    Write-Host "Updated remote: github -> $GithubUrl" -ForegroundColor Green
}

Write-Host ""
Write-Host "Pushing branches to GitHub via WSL..." -ForegroundColor Cyan
wsl -d Ubuntu -e bash -lc @"
set -e
export PATH=\"\$HOME/.local/bin:\$PATH\"
cd '/mnt/c/MY ERPS'
git config --global --add safe.directory '/mnt/c/MY ERPS' 2>/dev/null || true
for b in main cursor/ledger-test-fixes cursor/fix-detailed-ledger-balance-parse; do
  if git show-ref --verify --quiet refs/heads/\"\$b\"; then
    echo \"Pushing \$b ...\"
    git push -u github \"\$b\" || echo \"WARN: push failed for \$b\"
  fi
done
"@

Write-Host ""
Write-Host "GitHub repo: https://github.com/hammadalisyed79-svg/IFS-Chemicals" -ForegroundColor Green
Write-Host "If push failed, create the repo on GitHub first, then run: gh auth login" -ForegroundColor Yellow
