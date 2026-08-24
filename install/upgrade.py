#!/usr/bin/env python3
"""Upgrade utility — backup DB, migrate, rollback on failure."""

from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import database as db
    import erp_version

    db_path = db.DB_PATH
    backup_dir = ROOT / "backups"
    backup_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = backup_dir / f"pre_upgrade_{ts}.db"

    print(f"Backing up {db_path} -> {backup}")
    shutil.copy2(db_path, backup)

    try:
        db.reset_runtime_state()
        db.init_db()
        print(f"Upgrade complete: {erp_version.APP_VERSION_FULL}")
    except Exception as exc:
        print(f"Migration failed: {exc}")
        print(f"Restoring from {backup}")
        shutil.copy2(backup, db_path)
        db.reset_runtime_state()
        sys.exit(1)


if __name__ == "__main__":
    main()
