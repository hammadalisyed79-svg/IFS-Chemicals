"""IFS ERP — system audit log (who did what, when)."""

from __future__ import annotations

import json
import re
from datetime import datetime

TABLE_LABELS = {
    "customers": "Customer",
    "suppliers": "Supplier",
    "products": "Product",
    "users": "User",
    "sales_invoices": "Sales Invoice",
    "purchase_invoices": "Purchase Invoice",
    "sales_returns": "Sales Return",
    "purchase_returns": "Purchase Return",
    "cash_receipts": "Cash Receipt",
    "cash_payments": "Cash Payment",
    "bank_receipts": "Bank Receipt",
    "bank_payments": "Bank Payment",
    "journal_vouchers": "Journal Voucher",
    "general_ledger": "GL Entry",
    "fiscal_years": "Fiscal Year",
    "employees": "Employee",
    "payroll_runs": "Payroll",
    "system_settings": "System Setting",
    "roles": "Role",
    "chart_of_accounts": "Account",
    "gate_passes": "Gate Pass",
    "weight_slips": "Weight Slip",
    "production_orders": "Production Order",
    "job_cards": "Job Card",
}

ACTION_LABELS = {
    "create": "Created",
    "update": "Updated",
    "delete": "Deleted",
    "login": "Signed in",
    "login_failed": "Failed sign-in",
    "logout": "Signed out",
    "approve": "Approved",
    "unapprove": "Unapproved",
    "reject": "Rejected",
    "post": "Posted",
    "reverse": "Reversed",
    "close": "Closed",
    "reopen": "Reopened",
    "settings": "Settings changed",
    "deactivate": "Deactivated",
    "backup": "Backup",
    "restore": "Restore",
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _details_json(details=None, *, module=None, document_no=None, summary=None, extra=None) -> str | None:
    payload = {}
    if isinstance(details, dict):
        payload.update(details)
    elif details not in (None, ""):
        payload["message"] = str(details)
    if module:
        payload["module"] = module
    if document_no:
        payload["document_no"] = str(document_no)
    if summary:
        payload["summary"] = str(summary)
    if extra and isinstance(extra, dict):
        payload.update(extra)
    return json.dumps(payload, ensure_ascii=False) if payload else None


def ensure_audit_schema(conn=None):
    """Indexes for fast audit search."""
    from database import get_connection

    def _run(c):
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at DESC)"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_log_table_action ON audit_log(table_name, action)"
        )

    if conn is not None:
        _run(conn)
        return
    with get_connection() as c:
        _run(c)


def log_event(
    table_name: str,
    record_id=None,
    action: str = "update",
    details=None,
    user_id=None,
    *,
    module: str | None = None,
    document_no: str | None = None,
    summary: str | None = None,
):
    """Write one audit row. Safe to call from any layer; never raises to caller."""
    try:
        from database import get_connection

        details_str = _details_json(
            details, module=module, document_no=document_no, summary=summary,
        )
        with get_connection() as conn:
            ensure_audit_schema(conn)
            conn.execute(
                """INSERT INTO audit_log(table_name, record_id, action, details, user_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (table_name, record_id, action, details_str, user_id, _now()),
            )
    except Exception:
        pass


def log_audit(table_name, record_id, action, details, user_id):
    """Backward-compatible alias used by db_v3 / db_hr."""
    log_event(table_name, record_id, action, details, user_id)


def _parse_details(raw) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"message": str(raw)}


def _display_summary(row: dict) -> str:
    d = _parse_details(row.get("details"))
    if d.get("summary"):
        return d["summary"]
    if d.get("document_no"):
        return f"{d['document_no']}"
    if d.get("message"):
        return d["message"]
    tbl = TABLE_LABELS.get(row.get("table_name"), row.get("table_name", ""))
    rid = row.get("record_id")
    if tbl and rid:
        return f"{tbl} #{rid}"
    return tbl or "—"


def search_audit_log(
    from_date=None,
    to_date=None,
    user_id=None,
    table_name=None,
    action=None,
    search=None,
    limit=500,
):
    from database import get_connection, rows_to_list

    ensure_audit_schema()
    q = """SELECT a.id, a.table_name, a.record_id, a.action, a.details, a.user_id, a.created_at,
                  u.username, u.full_name AS user_name
           FROM audit_log a
           LEFT JOIN users u ON a.user_id = u.id
           WHERE 1=1"""
    p = []
    if from_date:
        q += " AND date(a.created_at) >= date(?)"
        p.append(from_date)
    if to_date:
        q += " AND date(a.created_at) <= date(?)"
        p.append(to_date)
    if user_id:
        q += " AND a.user_id = ?"
        p.append(user_id)
    if table_name and table_name != "All":
        q += " AND a.table_name = ?"
        p.append(table_name)
    if action and action != "All":
        q += " AND a.action = ?"
        p.append(action)
    if search:
        like = f"%{search.strip()}%"
        q += """ AND (
            a.details LIKE ? OR a.table_name LIKE ? OR u.username LIKE ?
            OR u.full_name LIKE ? OR CAST(a.record_id AS TEXT) LIKE ?
        )"""
        p.extend([like, like, like, like, like])
    q += " ORDER BY a.created_at DESC LIMIT ?"
    p.append(min(int(limit or 500), 5000))
    with get_connection() as conn:
        rows = rows_to_list(conn.execute(q, p).fetchall())
    for r in rows:
        r["entity"] = TABLE_LABELS.get(r.get("table_name"), r.get("table_name", ""))
        r["action_label"] = ACTION_LABELS.get(r.get("action"), (r.get("action") or "").title())
        r["summary"] = _display_summary(r)
        d = _parse_details(r.get("details"))
        r["module"] = d.get("module", "")
        r["document_no"] = d.get("document_no", "")
    return rows


def audit_table_options():
    from database import get_connection

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT table_name FROM audit_log ORDER BY table_name"
        ).fetchall()
    known = list(TABLE_LABELS.keys())
    seen = {r[0] for r in rows}
    return ["All"] + sorted(seen.union(known))
