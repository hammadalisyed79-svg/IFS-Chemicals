"""Metrics, health probes, slow query logging."""

from __future__ import annotations

import time
from contextlib import contextmanager

from infrastructure.logging.structured import get_logger

_log = get_logger("observability")


def record_metric(name: str, value: float, tags: dict | None = None) -> None:
    import json
    from database import get_connection
    try:
        with get_connection() as conn:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='erp_app_metrics'").fetchone():
                conn.execute(
                    "INSERT INTO erp_app_metrics(metric_name,metric_value,tags) VALUES(?,?,?)",
                    (name, value, json.dumps(tags or {})),
                )
    except Exception:
        pass


@contextmanager
def timed_operation(name: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        ms = (time.perf_counter() - start) * 1000
        record_metric(name, ms)
        if ms > 500:
            _log.warning("slow_operation", extra={"extra_data": {"op": name, "ms": ms}})


def log_slow_query(sql: str, duration_ms: float, params: str = "") -> None:
    if duration_ms < 200:
        return
    from database import get_connection
    try:
        with get_connection() as conn:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='erp_slow_queries'").fetchone():
                conn.execute(
                    "INSERT INTO erp_slow_queries(sql_text,duration_ms,params) VALUES(?,?,?)",
                    (sql[:4000], duration_ms, params[:1000]),
                )
    except Exception:
        pass


def health_status() -> dict:
    from database import get_connection
    status = {"status": "ok", "checks": {}}
    try:
        with get_connection() as conn:
            status["checks"]["database"] = "ok"
            status["checks"]["tables"] = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
            pending = 0
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='erp_job_queue'").fetchone():
                pending = conn.execute(
                    "SELECT COUNT(*) FROM erp_job_queue WHERE status='pending'"
                ).fetchone()[0]
            status["checks"]["pending_jobs"] = pending
    except Exception as exc:
        status["status"] = "degraded"
        status["error"] = str(exc)
    return status
