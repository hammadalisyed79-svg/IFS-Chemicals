"""V17.3 — Commercial certification: security tables, admin hash upgrade."""

from __future__ import annotations


def _meta_get(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM schema_meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def _meta_set(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO schema_meta(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def migrate_v17_3_certification(conn, db_module=None) -> None:
    from erp_version import SCHEMA_V17_3_KEY, SCHEMA_V17_3_VALUE

    # All users: expire session after 15 minutes idle (one-shot policy bump).
    if _meta_get(conn, "session_idle_15_policy") != "1":
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='system_settings'"
        ).fetchone():
            conn.execute(
                "INSERT INTO system_settings(key,value) VALUES('session_idle_minutes','15') "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
            )
        _meta_set(conn, "session_idle_15_policy", "1")

    # Bump default idle timeout 15 → 30 minutes (one-shot). Keeps a custom value
    # if an admin already changed it away from the previous default of 15.
    if _meta_get(conn, "session_idle_30_policy") != "1":
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='system_settings'"
        ).fetchone():
            row = conn.execute(
                "SELECT value FROM system_settings WHERE key='session_idle_minutes'"
            ).fetchone()
            cur = (row[0] if row else None)
            if cur is None or str(cur).strip() in ("", "15"):
                conn.execute(
                    "INSERT INTO system_settings(key,value) VALUES('session_idle_minutes','30') "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
                )
        _meta_set(conn, "session_idle_30_policy", "1")

    if _meta_get(conn, SCHEMA_V17_3_KEY) == SCHEMA_V17_3_VALUE:
        return

    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='users'").fetchone():
        cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "password_changed_at" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN password_changed_at TEXT")

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_password_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            password_hash TEXT NOT NULL,
            recorded_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS warehouse_product_avg_cost (
            warehouse_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            avg_cost REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (warehouse_id, product_id)
        )"""
    )

    defaults = {
        "password_min_length": "12",
        "password_expiry_days": "90",
        "password_history_count": "5",
        "session_idle_minutes": "30",
        "force_password_change_on_first_login": "1",
        "csrf_protection_enabled": "1",
    }
    for k, v in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO system_settings(key,value) VALUES(?,?)", (k, v)
        )

    # Upgrade default admin to Argon2id with forced change (no default password in UI)
    try:
        from erp_core.password_v173 import hash_password_argon2id
        row = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
        if row:
            # Bootstrap password stored in schema_meta for first install only — not shown in UI
            bootstrap = _meta_get(conn, "bootstrap_admin_password")
            if not bootstrap:
                import secrets
                bootstrap = secrets.token_urlsafe(16)
                _meta_set(conn, "bootstrap_admin_password", bootstrap)
            h = hash_password_argon2id(bootstrap)
            conn.execute(
                """UPDATE users SET password_hash=?, must_change_password=1,
                   password_changed_at=datetime('now') WHERE username='admin'""",
                (h,),
            )
    except Exception:
        pass

    _meta_set(conn, SCHEMA_V17_3_KEY, SCHEMA_V17_3_VALUE)
    _meta_set(conn, "erp_version", "V17.3")
