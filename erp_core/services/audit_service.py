"""Audit service — enriched logging with old/new values."""

from __future__ import annotations

import json
import socket


def audit(
    table_name: str,
    record_id: int,
    action: str,
    *,
    user_id=None,
    module: str = "",
    document_no: str = "",
    summary: str = "",
    old_values: dict | None = None,
    new_values: dict | None = None,
) -> None:
    from db_audit import log_event

    extra = {}
    if old_values:
        extra["old_values"] = old_values
    if new_values:
        extra["new_values"] = new_values
    try:
        extra["machine"] = socket.gethostname()
    except Exception:
        pass

    log_event(
        table_name,
        record_id,
        action,
        details=extra if extra else None,
        user_id=user_id,
        module=module,
        document_no=document_no,
        summary=summary,
    )

    try:
        from database import get_connection

        with get_connection() as conn:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(audit_log)").fetchall()]
            if "old_values" in cols and old_values is not None:
                conn.execute(
                    """UPDATE audit_log SET old_values=?, new_values=?, machine_name=?
                       WHERE id=(SELECT MAX(id) FROM audit_log)""",
                    (
                        json.dumps(old_values, default=str)[:4000],
                        json.dumps(new_values or {}, default=str)[:4000],
                        extra.get("machine"),
                    ),
                )
    except Exception:
        pass
