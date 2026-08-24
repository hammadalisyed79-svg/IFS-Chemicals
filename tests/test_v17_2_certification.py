"""V17.2 certification smoke tests."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def test_v17_2_tables():
    import tempfile
    import database as db
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db.DB_PATH = __import__("pathlib").Path(path)
    db.reset_runtime_state()
    db.init_db()
    try:
        with db.get_connection() as conn:
            for t in ("erp_uat_scenarios", "erp_uat_runs", "erp_validation_runs"):
                assert conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone(), t
        print("PASS v17.2 tables")
    finally:
        os.unlink(path)


def test_discovery():
    from tools.v17_2.discovery import run_discovery
    rep = run_discovery()
    assert rep.passed > 0
    print("PASS discovery")


def test_database_health():
    from tools.v17_2.database_health import run_database_health
    rep = run_database_health()
    assert rep.failed == 0
    print("PASS database health")


def test_manufacturing_gate():
    from tools.v17_2.manufacturing import run_manufacturing_certification
    rep = run_manufacturing_certification()
    assert rep.failed == 0
    print("PASS manufacturing gate")


if __name__ == "__main__":
    test_v17_2_tables()
    test_discovery()
    test_database_health()
    test_manufacturing_gate()
    print("All V17.2 certification smoke tests passed.")
