"""V14 RC1 — unified document lifecycle actions."""

from __future__ import annotations

from erp_core.transaction_engine import DocumentSpec, get_document_spec, is_editable


DOC_SHORT_TO_KEY = {
    "SO": "sales_order",
    "PO": "purchase_order",
    "QT": "quotation",
    "DN": "delivery_note",
    "PRQ": "purchase_requisition",
    "GRN": "grn",
    "JV": "journal_voucher",
    "SI": "sales_invoice",
    "PI": "purchase_invoice",
    "SR": "sales_return",
    "PR": "purchase_return",
}


def resolve_doc_type(key_or_short: str) -> str:
    return DOC_SHORT_TO_KEY.get(key_or_short, key_or_short)


def _doc_date(spec: DocumentSpec, row: dict) -> str:
    for f in ("invoice_date", "purchase_date", "order_date", "grn_date", "dn_date",
              "voucher_date", "return_date", "quote_date", "req_date", "sale_date"):
        if row.get(f):
            return str(row[f])
    return str(row.get("created_at") or "")[:10]


def execute_action(
    doc_type: str,
    action: str,
    record_id: int,
    user_id: int | None,
    *,
    reason: str = "",
    override_reason: str = "",
) -> None:
    """approve | reject | post | delete | submit."""
    key = resolve_doc_type(doc_type)
    spec = get_document_spec(key)
    if not spec:
        raise ValueError(f"Unknown document type: {doc_type}")

    row = spec.get_fn(record_id) if spec.get_fn else None
    if not row and action != "delete":
        raise ValueError("Document not found.")

    if action in ("post", "approve", "delete") and row:
        from erp_core.period_lock import assert_period_open
        assert_period_open(
            _doc_date(spec, row), user_id,
            action=action, override_reason=override_reason or None,
        )

    if action == "submit":
        if not spec.submit_fn:
            raise ValueError(f"Submit not supported for {spec.label}.")
        spec.submit_fn(record_id, user_id)
        _log_approval(spec, record_id, row, "submit", user_id, reason)
        return

    if action == "approve":
        if spec.submit_fn and row and (row.get("status") or "draft") in ("draft", "rejected"):
            spec.submit_fn(record_id, user_id)
        if spec.approve_fn:
            from erp_core.approval_engine import user_can_approve, record_approval_history
            amount = float(row.get("total") or row.get("subtotal") or 0)
            if not user_can_approve({"id": user_id, "role": _user_role(user_id)}, spec.key, amount=amount):
                raise ValueError("You are not authorized to approve this document at the current level.")
            spec.approve_fn(record_id, user_id)
            record_approval_history(spec.key, spec.table, record_id, row.get(spec.no_field, ""), "approved", user_id, reason)
            return
        if spec.post_fn:
            execute_action(key, "post", record_id, user_id, override_reason=override_reason)
            return
        raise ValueError(f"Approve not supported for {spec.label}.")

    if action == "reject":
        import database as db
        if spec.key == "sales_invoice":
            db.reject_sale_invoice(record_id, user_id, reason or "Rejected")
        elif spec.key == "purchase_invoice":
            db.reject_purchase_invoice(record_id, user_id, reason or "Rejected")
        else:
            raise ValueError(f"Reject not supported for {spec.label}.")
        from erp_core.approval_engine import record_approval_history
        record_approval_history(spec.key, spec.table, record_id, row.get(spec.no_field, ""), "rejected", user_id, reason)
        return

    if action == "post":
        if spec.post_fn:
            spec.post_fn(record_id, user_id)
            _audit_post(spec, record_id, user_id)
            return
        if spec.approve_fn:
            spec.approve_fn(record_id, user_id)
            return
        raise ValueError(f"Post not supported for {spec.label}.")

    if action == "delete":
        if not spec.delete_fn:
            raise ValueError(f"Delete not supported for {spec.label}.")
        if row and not is_editable(row, spec):
            raise ValueError("Only draft documents can be deleted.")
        spec.delete_fn(record_id)
        return

    raise ValueError(f"Unknown action: {action}")


def _user_role(user_id) -> str:
    if not user_id:
        return ""
    from database import get_connection
    with get_connection() as conn:
        r = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
        return r[0] if r else ""


def _log_approval(spec, record_id, row, action, user_id, comments):
    from erp_core.approval_engine import record_approval_history
    if row:
        record_approval_history(
            spec.key, spec.table, record_id,
            row.get(spec.no_field, ""), action, user_id, comments,
        )


def _audit_post(spec, record_id, user_id):
    try:
        from db_audit import log_event
        log_event(spec.table, record_id, "post", user_id=user_id, module=spec.nav_group,
                  summary=f"Posted {spec.label}")
    except Exception:
        pass


def get_document_history(spec: DocumentSpec, record_id: int, limit: int = 20) -> list[dict]:
    from db_audit import search_audit_log
    rows = search_audit_log(table_name=spec.table, search=str(record_id), limit=limit)
    return [r for r in rows if str(r.get("record_id")) == str(record_id)]
