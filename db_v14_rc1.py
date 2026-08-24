"""V14.0 RC1 — Enterprise Release Candidate migration."""

from __future__ import annotations


def _table_exists(conn, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _col_exists(conn, table: str, col: str) -> bool:
    if not _table_exists(conn, table):
        return False
    return col in [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _add_col(conn, table: str, col: str, ddl: str) -> None:
    if _table_exists(conn, table) and not _col_exists(conn, table, col):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


def _meta_get(conn, key: str) -> str | None:
    if not _table_exists(conn, "schema_meta"):
        return None
    row = conn.execute("SELECT value FROM schema_meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def _meta_set(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO schema_meta(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def migrate_v14_rc1_enterprise(conn, db_module=None) -> None:
    """Additive V14 RC1 schema. Preserves all user data."""
    from erp_version import SCHEMA_V14_RC1_KEY, SCHEMA_V14_RC1_VALUE

    if _meta_get(conn, SCHEMA_V14_RC1_KEY) == SCHEMA_V14_RC1_VALUE:
        return

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_approval_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_type TEXT NOT NULL,
            doc_table TEXT,
            record_id INTEGER NOT NULL,
            document_no TEXT,
            approval_level INTEGER DEFAULT 1,
            action TEXT NOT NULL,
            comments TEXT,
            acted_by INTEGER,
            acted_at TEXT DEFAULT CURRENT_TIMESTAMP,
            delegated_from INTEGER
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_approval_delegation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user_id INTEGER NOT NULL,
            to_user_id INTEGER NOT NULL,
            doc_type TEXT,
            valid_from TEXT,
            valid_to TEXT,
            active INTEGER DEFAULT 1,
            created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_approval_history_doc ON erp_approval_history(doc_type, record_id)"
    )

    if _table_exists(conn, "erp_approval_rules"):
        for col, ddl in (
            ("escalate_after_hours", "INTEGER"),
            ("delegate_to_user_id", "INTEGER"),
            ("comments_required", "INTEGER DEFAULT 0"),
        ):
            _add_col(conn, "erp_approval_rules", col, ddl)

    if _table_exists(conn, "warehouses"):
        _add_col(conn, "warehouses", "is_closed", "INTEGER DEFAULT 0")

    if _table_exists(conn, "system_settings"):
        row = conn.execute(
            "SELECT 1 FROM system_settings WHERE key='auto_backup_on_start'"
        ).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO system_settings(key,value) VALUES('auto_backup_on_start','1')"
            )

    _meta_set(conn, SCHEMA_V14_RC1_KEY, SCHEMA_V14_RC1_VALUE)
    _meta_set(conn, "erp_version", "V14.0-RC1")
