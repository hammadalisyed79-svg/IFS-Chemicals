"""V13.14 Enterprise Workflow & Integration — safe additive migration."""

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


def migrate_v13_14_enterprise_workflow_integration(conn, db_module=None) -> None:
    """
    Add V13.14 enterprise tables and columns. Never drops user data.
  Safe to run multiple times.
    """
    from erp_version import SCHEMA_V13_14_KEY, SCHEMA_V13_14_VALUE

    if _meta_get(conn, SCHEMA_V13_14_KEY) == SCHEMA_V13_14_VALUE:
        return

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_approval_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            department TEXT,
            min_amount REAL DEFAULT 0,
            max_amount REAL,
            warehouse_id INTEGER,
            role TEXT,
            user_id INTEGER,
            approval_level INTEGER DEFAULT 1,
            active INTEGER DEFAULT 1,
            created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_error_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            error_type TEXT,
            message TEXT,
            traceback TEXT,
            screen TEXT,
            user_id INTEGER,
            machine_name TEXT,
            ip_address TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_erp_error_log_at ON erp_error_log(created_at)"
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_print_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_type TEXT,
            doc_table TEXT,
            record_id INTEGER,
            document_no TEXT,
            print_count INTEGER DEFAULT 1,
            is_reprint INTEGER DEFAULT 0,
            is_draft INTEGER DEFAULT 0,
            printed_by INTEGER,
            printed_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_favorite_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            report_title TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, report_title)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_recent_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            report_title TEXT NOT NULL,
            opened_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_period_locks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            locked INTEGER DEFAULT 1,
            locked_by INTEGER,
            locked_at TEXT,
            notes TEXT,
            UNIQUE(period_start, period_end)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_document_open_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_type TEXT,
            record_id INTEGER,
            document_no TEXT,
            user_id INTEGER,
            opened_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    if _table_exists(conn, "audit_log"):
        for col, ddl in (
            ("machine_name", "TEXT"),
            ("ip_address", "TEXT"),
            ("old_values", "TEXT"),
            ("new_values", "TEXT"),
        ):
            _add_col(conn, "audit_log", col, ddl)

    if not conn.execute(
        "SELECT 1 FROM erp_approval_rules LIMIT 1"
    ).fetchone():
        conn.execute(
            """INSERT INTO erp_approval_rules
               (name, doc_type, min_amount, role, approval_level, active)
               VALUES
               ('Sales invoice default', 'sales_invoice', 0, 'admin', 1, 1),
               ('Purchase invoice default', 'purchase_invoice', 0, 'admin', 1, 1)"""
        )

    _meta_set(conn, SCHEMA_V13_14_KEY, SCHEMA_V13_14_VALUE)
    _meta_set(conn, "erp_version", "V13.14")
