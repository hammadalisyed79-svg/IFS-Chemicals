#!/bin/bash
# Auto-commit tracked changes and push to Cursor Origin (run from WSL).
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"
REPO="/mnt/c/MY ERPS"

git config --global --add safe.directory "$REPO" 2>/dev/null || true
cd "$REPO"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: not a git repo: $REPO"
  exit 1
fi

BRANCH="$(git branch --show-current)"
TS="$(date '+%Y-%m-%d %H:%M')"

# Tracked-file changes only (no new untracked secrets/db/pdf).
git add -u

if git diff --cached --quiet; then
  echo "[$TS] No tracked changes on $BRANCH"
else
  git -c user.name="IFS ERP" -c user.email="erp@ifschemicals.com" \
    commit -m "Auto-sync from server $TS"
  echo "[$TS] Committed on $BRANCH"
fi

push_branch() {
  local b="$1"
  if git push origin "$b" 2>&1; then
    echo "[$TS] Pushed origin/$b"
  else
    echo "[$TS] WARN: push failed for $b (run: origin auth login)" >&2
    return 1
  fi
}

push_branch "$BRANCH" || true

# Also push main if it has unpushed commits (even when on another branch).
if [ "$BRANCH" != "main" ]; then
  UNPUSHED="$(git log origin/main..main --oneline 2>/dev/null | wc -l | tr -d ' ')"
  if [ "${UNPUSHED:-0}" != "0" ]; then
    push_branch "main" || true
  fi
fi
