"""
Consistent SQLite backup of ifs_erp.db (online backup API).
Writes to backups/auto/ and prunes old copies.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "ifs_erp.db"
OUT_DIR = ROOT / "backups" / "auto"
LOG = ROOT / "logs" / "erp_backup.log"


def _log(msg: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def backup(*, keep_days: int = 14, keep_count: int = 42) -> Path:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = OUT_DIR / f"ifs_erp_{stamp}.db"
    src = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
            row = dst.execute("PRAGMA integrity_check").fetchone()
            if not row or str(row[0]).lower() != "ok":
                raise RuntimeError(f"integrity_check failed: {row}")
        finally:
            dst.close()
    finally:
        src.close()

    size_mb = dest.stat().st_size / (1024 * 1024)
    _log(f"OK {dest.name} ({size_mb:.2f} MB)")
    _prune(keep_days=keep_days, keep_count=keep_count)
    return dest


def _prune(*, keep_days: int, keep_count: int) -> None:
    files = sorted(OUT_DIR.glob("ifs_erp_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    cutoff = datetime.now() - timedelta(days=max(1, keep_days))
    kept = 0
    for p in files:
        kept += 1
        mtime = datetime.fromtimestamp(p.stat().st_mtime)
        if kept <= keep_count and mtime >= cutoff:
            continue
        # Always keep the newest keep_count regardless of age floor of 3
        if kept <= 3:
            continue
        try:
            p.unlink()
            _log(f"pruned {p.name}")
        except OSError as e:
            _log(f"prune fail {p.name}: {e}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Backup IFS ERP SQLite database")
    ap.add_argument("--keep-days", type=int, default=14)
    ap.add_argument("--keep-count", type=int, default=42)
    args = ap.parse_args()
    try:
        backup(keep_days=args.keep_days, keep_count=args.keep_count)
        return 0
    except Exception as e:
        _log(f"FAIL {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
