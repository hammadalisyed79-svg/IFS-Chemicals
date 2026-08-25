# Push/pull/fetch to Cursor Origin via WSL (works when Windows Git auth is not configured).
# Usage:  powershell -File tools\origin_git.ps1 push
#         powershell -File tools\origin_git.ps1 pull
#         powershell -File tools\origin_git.ps1 fetch

param(
    [Parameter(Position = 0)]
    [ValidateSet("push", "pull", "fetch", "status", "auth")]
    [string]$Action = "push"
)

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$WslPath = "/mnt/c/MY ERPS"

switch ($Action) {
    "auth" {
        wsl -e bash -lc "origin auth status; echo; origin auth login"
        exit $LASTEXITCODE
    }
    "status" {
        wsl -e bash -lc "cd '$WslPath' && git status -sb && echo && origin auth status"
        exit $LASTEXITCODE
    }
    "push" {
        $branch = git -C $RepoRoot branch --show-current
        wsl -e bash -lc "cd '$WslPath' && git push -u origin '$branch'"
        exit $LASTEXITCODE
    }
    "pull" {
        wsl -e bash -lc "cd '$WslPath' && git pull origin"
        exit $LASTEXITCODE
    }
    "fetch" {
        wsl -e bash -lc "cd '$WslPath' && git fetch origin"
        exit $LASTEXITCODE
    }
}
