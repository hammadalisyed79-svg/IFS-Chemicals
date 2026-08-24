"""V13.14 — background maintenance services (safe, non-destructive)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path


def run_startup_maintenance(db_module=None) -> dict:
    """Run lightweight maintenance on ERP startup. Never deletes user transactions."""
    results = {"backup": False, "optimize": False, "log_cleanup": 0, "temp_cleanup": 0}
    db = db_module
    if db is None:
        import database as db

    try:
        if db.get_setting("auto_backup_on_start", "0") == "1":
            results["backup"] = _auto_backup(db)
    except Exception:
        pass

    try:
        with db.get_connection() as conn:
            conn.execute("PRAGMA optimize")
            results["optimize"] = True
    except Exception:
        pass

    try:
        results["log_cleanup"] = _cleanup_old_logs(db)
    except Exception:
        pass

    try:
        results["temp_cleanup"] = _cleanup_temp_files()
    except Exception:
        pass

    return results


def _auto_backup(db) -> bool:
    backup_dir = Path(__file__).parent.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"auto_{stamp}.db"
    src = db.DB_PATH
    if src.exists():
        import shutil
        shutil.copy2(src, dest)
        return True
    return False


def _cleanup_old_logs(db, days: int = 90) -> int:
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    removed = 0
    with db.get_connection() as conn:
        for table, col in (("erp_error_log", "created_at"), ("erp_document_open_log", "opened_at")):
            if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name=?", (table,)
            ).fetchone():
                cur = conn.execute(
                    f"DELETE FROM {table} WHERE {col} < ?",
                    (cutoff,),
                )
                removed += cur.rowcount
    return removed


def _cleanup_temp_files() -> int:
    root = Path(__file__).parent.parent
    removed = 0
    for pattern in ("*.tmp", "__pycache__"):
        for p in root.rglob(pattern) if "*" in pattern else [root / pattern]:
            try:
                if p.is_file():
                    p.unlink()
                    removed += 1
            except Exception:
                pass
    return removed


def rebuild_indexes(db_module=None) -> bool:
    db = db_module or __import__("database")
    try:
        with db.get_connection() as conn:
            conn.execute("REINDEX")
        return True
    except Exception:
        return False
