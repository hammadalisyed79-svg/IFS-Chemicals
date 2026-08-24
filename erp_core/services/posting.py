"""Posting service — unified GL posting entry points."""

from __future__ import annotations


def post_document(doc_type: str, record_id: int, user_id: int) -> None:
    """Post a document via its registered handler."""
    from erp_core.transaction_engine import get_document_spec

    spec = get_document_spec(doc_type)
    if not spec:
        raise ValueError(f"Unknown document type: {doc_type}")
    if spec.approve_fn and doc_type in ("sales_invoice", "purchase_invoice"):
        spec.approve_fn(record_id, user_id)
        return
    if spec.post_fn:
        spec.post_fn(record_id, user_id)
        return
    raise ValueError(f"Posting is not available for {spec.label}.")


def reverse_voucher(voucher_table: str, record_id: int, user_id: int, *, reason: str = "") -> None:
    """Reverse GL entries linked to a voucher when supported."""
    if voucher_table == "journal_vouchers":
        import db_v3
        if hasattr(db_v3, "reverse_journal_voucher"):
            db_v3.reverse_journal_voucher(record_id, user_id, reason=reason)
            return
    raise ValueError("Reversal not supported for this voucher type.")
