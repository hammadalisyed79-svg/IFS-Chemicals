"""V17.2 — UAT tracking tables (validation infrastructure, not business module)."""

from __future__ import annotations


def _table_exists(conn, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _meta_get(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM schema_meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def _meta_set(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO schema_meta(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def migrate_v17_2_validation(conn, db_module=None) -> None:
    from erp_version import SCHEMA_V17_2_KEY, SCHEMA_V17_2_VALUE

    if _meta_get(conn, SCHEMA_V17_2_KEY) == SCHEMA_V17_2_VALUE:
        return

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_uat_scenarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            department TEXT NOT NULL,
            module TEXT NOT NULL,
            steps_json TEXT NOT NULL,
            is_active INTEGER DEFAULT 1
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_uat_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_id INTEGER NOT NULL,
            tester TEXT,
            department TEXT,
            status TEXT DEFAULT 'pending',
            comments TEXT,
            evidence_json TEXT,
            tested_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(scenario_id) REFERENCES erp_uat_scenarios(id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_validation_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            suite TEXT NOT NULL,
            pass_count INTEGER DEFAULT 0,
            fail_count INTEGER DEFAULT 0,
            report_path TEXT,
            run_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    _meta_set(conn, SCHEMA_V17_2_KEY, SCHEMA_V17_2_VALUE)
    _meta_set(conn, "erp_version", "V17.2")
