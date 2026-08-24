"""V13.14 — centralized exception logging (no crash dialogs)."""

from __future__ import annotations

import socket
import traceback
from datetime import datetime


def _machine_name() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"


def log_exception(exc: BaseException, *, screen: str = "", user_id=None) -> int | None:
    """Write exception to erp_error_log. Returns log id or None."""
    try:
        from database import get_connection

        with get_connection() as conn:
            if not conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name='erp_error_log'"
            ).fetchone():
                return None
            cur = conn.execute(
                """INSERT INTO erp_error_log
                   (error_type, message, traceback, screen, user_id, machine_name, ip_address, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    type(exc).__name__,
                    str(exc)[:2000],
                    traceback.format_exc()[:8000],
                    screen or "",
                    user_id,
                    _machine_name(),
                    "127.0.0.1",
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            return cur.lastrowid
    except Exception:
        return None


def user_friendly_message(exc: BaseException) -> str:
    msg = str(exc).strip() or type(exc).__name__
    if len(msg) > 300:
        msg = msg[:297] + "..."
    return msg
