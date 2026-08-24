"""Centralized configuration — erp_config + system_settings + environment."""

from __future__ import annotations

import os


class AppConfig:
    """Hierarchical config: env > erp_config > system_settings > default."""

    def __init__(self):
        self._cache: dict[tuple, str] = {}

    def get(self, section: str, key: str, default: str = "", *, company_id: int = 1) -> str:
        cache_key = (section, key, company_id)
        if cache_key in self._cache:
            return self._cache[cache_key]
        env_key = f"IFS_{section.upper()}_{key.upper()}"
        if env_key in os.environ:
            val = os.environ[env_key]
            self._cache[cache_key] = val
            return val
        try:
            from database import get_connection
            with get_connection() as conn:
                if conn.execute("SELECT 1 FROM sqlite_master WHERE name='erp_config'").fetchone():
                    row = conn.execute(
                        "SELECT value FROM erp_config WHERE section=? AND key=? AND company_id=?",
                        (section, key, company_id),
                    ).fetchone()
                    if row and row[0] is not None:
                        self._cache[cache_key] = str(row[0])
                        return str(row[0])
                row = conn.execute(
                    "SELECT value FROM system_settings WHERE key=?", (f"{section}.{key}",)
                ).fetchone()
                if row:
                    self._cache[cache_key] = str(row[0])
                    return str(row[0])
                row = conn.execute("SELECT value FROM system_settings WHERE key=?", (key,)).fetchone()
                if row:
                    self._cache[cache_key] = str(row[0])
                    return str(row[0])
        except Exception:
            pass
        self._cache[cache_key] = default
        return default

    def set(self, section: str, key: str, value: str, *, company_id: int = 1) -> None:
        from database import get_connection
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO erp_config(section,key,value,company_id)
                   VALUES(?,?,?,?)
                   ON CONFLICT(section,key,company_id,branch_id) DO UPDATE SET value=excluded.value""",
                (section, key, str(value), company_id),
            )
        self._cache.pop((section, key, company_id), None)

    def section(self, section: str, company_id: int = 1) -> dict[str, str]:
        try:
            from database import get_connection, rows_to_list
            with get_connection() as conn:
                rows = rows_to_list(conn.execute(
                    "SELECT key, value FROM erp_config WHERE section=? AND company_id=?",
                    (section, company_id),
                ).fetchall())
                return {r["key"]: r["value"] for r in rows}
        except Exception:
            return {}

    def invalidate(self) -> None:
        self._cache.clear()


config = AppConfig()
