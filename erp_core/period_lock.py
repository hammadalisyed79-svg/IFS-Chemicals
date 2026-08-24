"""V14 RC1 — accounting period lock enforcement."""

from __future__ import annotations

from datetime import datetime


def is_period_locked(doc_date: str) -> bool:
    """Return True if doc_date falls in a locked period."""
    if not doc_date:
        return False
    try:
        from database import get_connection

        with get_connection() as conn:
            if not conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name='erp_period_locks'"
            ).fetchone():
                return False
            row = conn.execute(
                """SELECT 1 FROM erp_period_locks
                   WHERE locked=1 AND period_start <= ? AND period_end >= ?
                   LIMIT 1""",
                (doc_date[:10], doc_date[:10]),
            ).fetchone()
            return row is not None
    except Exception:
        return False


def assert_period_open(
    doc_date: str,
    user_id: int | None,
    *,
    action: str = "post",
    override_reason: str | None = None,
) -> None:
    """Block post/edit/delete in locked periods. Admin may override with reason."""
    if not is_period_locked(doc_date):
        return
    is_admin = False
    if user_id:
        from database import get_connection

        with get_connection() as conn:
            row = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
            is_admin = row and row[0] == "admin"
    if is_admin and override_reason:
        try:
            from db_audit import log_event
            log_event(
                "erp_period_locks", 0, "override",
                user_id=user_id, module="Finance",
                summary=f"Period lock override for {action} on {doc_date}: {override_reason}",
            )
        except Exception:
            pass
        return
    if is_admin:
        raise ValueError(
            f"Accounting period containing {doc_date} is locked. "
            "Provide an override reason to proceed."
        )
    raise ValueError(
        f"Cannot {action}: accounting period containing {doc_date} is closed."
    )


def lock_period(period_start: str, period_end: str, user_id: int, notes: str = "") -> None:
    from database import get_connection

    with get_connection() as conn:
        conn.execute(
            """INSERT INTO erp_period_locks
               (period_start, period_end, locked, locked_by, locked_at, notes)
               VALUES (?,?,1,?,?,?)
               ON CONFLICT(period_start, period_end) DO UPDATE SET
                 locked=1, locked_by=excluded.locked_by,
                 locked_at=excluded.locked_at, notes=excluded.notes""",
            (
                period_start, period_end, user_id,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), notes,
            ),
        )
