"""Background job queue — email, sync, reports, backup."""

from __future__ import annotations

import json
from datetime import datetime

from infrastructure.logging.structured import get_logger

_log = get_logger("jobs")


def enqueue(
    job_type: str,
    payload: dict | None = None,
    *,
    priority: int = 5,
    scheduled_at: str | None = None,
    company_id: int = 1,
    created_by: int | None = None,
    max_attempts: int = 3,
) -> int:
    from database import get_connection
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO erp_job_queue(
                job_type,payload,status,priority,scheduled_at,company_id,created_by,max_attempts)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                job_type,
                json.dumps(payload or {}),
                "pending",
                priority,
                scheduled_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                company_id,
                created_by,
                max_attempts,
            ),
        )
        return cur.lastrowid


def fetch_pending(limit: int = 10) -> list[dict]:
    from database import get_connection, rows_to_list
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            """SELECT * FROM erp_job_queue
               WHERE status='pending' AND (scheduled_at IS NULL OR scheduled_at<=?)
               ORDER BY priority ASC, id ASC LIMIT ?""",
            (now, limit),
        ).fetchall())


def mark_running(job_id: int) -> None:
    from database import get_connection
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute(
            "UPDATE erp_job_queue SET status='running', started_at=? WHERE id=?",
            (now, job_id),
        )


def mark_done(job_id: int) -> None:
    from database import get_connection
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute(
            "UPDATE erp_job_queue SET status='completed', completed_at=? WHERE id=?",
            (now, job_id),
        )


def mark_failed(job_id: int, error: str) -> None:
    from database import get_connection
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT attempts, max_attempts FROM erp_job_queue WHERE id=?", (job_id,)
        ).fetchone()
        attempts = (row[0] or 0) + 1 if row else 1
        max_a = row[1] if row else 3
        status = "failed" if attempts >= max_a else "pending"
        conn.execute(
            """UPDATE erp_job_queue SET status=?, attempts=?, error_message=?, completed_at=?
               WHERE id=?""",
            (status, attempts, error[:2000], now if status == "failed" else None, job_id),
        )


_HANDLERS: dict[str, callable] = {}


def register_handler(job_type: str, fn: callable) -> None:
    _HANDLERS[job_type] = fn


def process_jobs(limit: int = 10) -> int:
    processed = 0
    for job in fetch_pending(limit):
        jid = job["id"]
        jtype = job["job_type"]
        mark_running(jid)
        handler = _HANDLERS.get(jtype)
        if not handler:
            mark_failed(jid, f"No handler for {jtype}")
            continue
        try:
            payload = json.loads(job.get("payload") or "{}")
            handler(payload, job)
            mark_done(jid)
            processed += 1
        except Exception as exc:
            _log.exception("Job %s failed", jid)
            mark_failed(jid, str(exc))
    return processed


def _handle_notification(payload: dict, job: dict) -> None:
    from erp_core import notifications as ntf
    ntf.create_notification(**payload)


def _handle_backup(payload: dict, job: dict) -> None:
    from erp_core.maintenance import _auto_backup
    import database as db
    _auto_backup(db)


register_handler("send_notification", _handle_notification)
register_handler("backup", _handle_backup)
register_handler("cleanup_sessions", lambda p, j: None)
