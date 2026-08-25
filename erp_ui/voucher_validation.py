"""Inline voucher validation — Phase 4 trust & compliance affordances."""

from __future__ import annotations

import streamlit as st

from application import data_gateway as db
from erp_core.transaction_validation import (
    validate_purchase_invoice,
    validate_sale_invoice,
    ValidationResult,
)


def _default_warehouse_id() -> int | None:
    with db.get_connection() as conn:
        return db._default_warehouse_id(conn)


def _stock_shortfalls(lines: list[dict], warehouse_id: int | None) -> list[str]:
    if not warehouse_id or not lines:
        return []
    short = []
    with db.get_connection() as conn:
        for i, ln in enumerate(lines, start=1):
            pid = ln.get("product_id") or ln.get("item_id")
            qty = float(ln.get("quantity") or 0)
            if not pid or qty <= 0:
                continue
            row = conn.execute(
                "SELECT COALESCE(quantity,0) FROM warehouse_stock WHERE warehouse_id=? AND product_id=?",
                (warehouse_id, pid),
            ).fetchone()
            on_hand = float(row[0] if row else 0)
            if qty > on_hand + 0.0001:
                prod = conn.execute(
                    "SELECT code, name FROM products WHERE id=?", (pid,),
                ).fetchone()
                code = (prod["code"] if prod else pid) or pid
                short.append(
                    f"Line {i} **{code}**: need {qty:,.3f}, on hand {on_hand:,.3f}"
                )
    return short


def collect_sale_issues(
    header: dict,
    lines: list[dict],
    totals: dict | None,
    *,
    flow: dict | None = None,
    stage: str = "draft",
) -> ValidationResult:
    res = validate_sale_invoice(header, lines, totals, stage=stage)
    if not header.get("customer_id"):
        res.fail("Customer is required — select a customer before saving.")
    if flow and flow.get("show_weight") and not header.get("weight_slip_id"):
        res.fail("Weight slip is required for this sale — complete weighbridge first.")
    if db.get_setting("allow_negative_stock", "0") == "1":
        for msg in _stock_shortfalls(lines, _default_warehouse_id()):
            res.warn(f"Stock may go negative — {msg}")
    return res


def collect_purchase_issues(
    header: dict,
    lines: list[dict],
    totals: dict | None,
    *,
    direct_purchase: bool = False,
    stage: str = "draft",
) -> ValidationResult:
    res = validate_purchase_invoice(header, lines, totals, stage=stage)
    if not header.get("supplier_id"):
        res.fail("Supplier is required — select a supplier before saving.")
    if not direct_purchase and not header.get("weight_slip_id"):
        res.fail("Weight slip is required for this purchase — complete weighbridge first.")
    return res


def render_validation_panel(result: ValidationResult) -> None:
    if not result.errors and not result.warnings:
        return
    for err in result.errors:
        st.markdown(
            f'<p class="erp-field-error">{err}</p>',
            unsafe_allow_html=True,
        )
    if result.warnings:
        msgs = " · ".join(result.warnings[:6])
        extra = len(result.warnings) - 6
        if extra > 0:
            msgs += f" · +{extra} more"
        st.warning(f"Posting may exceed stock (negative stock allowed): {msgs}")


def render_stock_policy_banner() -> None:
    if db.get_setting("allow_negative_stock", "0") == "1":
        st.markdown(
            '<div class="erp-stock-policy-banner">'
            "⚠️ <strong>Negative stock allowed</strong> — postings may reduce inventory below zero. "
            "Review quantities before approve."
            "</div>",
            unsafe_allow_html=True,
        )


def render_document_audit_meta(doc: dict | None) -> None:
    if not doc:
        return
    from erp_ui.helpers import fmt_datetime_from_record

    bits = []
    cb = doc.get("created_by")
    if cb:
        u = db.get_user_by_id(int(cb))
        name = (u or {}).get("full_name") or (u or {}).get("username") or f"User #{cb}"
        bits.append(f"Created by **{name}**")
    created_at = doc.get("created_at")
    if created_at:
        bits.append(f"created {fmt_datetime_from_record(doc, 'created_at')}")
    updated = doc.get("updated_at") or doc.get("modified_at")
    if updated:
        from erp_ui.helpers import fmt_datetime
        bits.append(f"last saved {fmt_datetime(str(updated)[:10], updated)}")
    ab = doc.get("approved_by")
    if ab:
        u = db.get_user_by_id(int(ab))
        name = (u or {}).get("full_name") or (u or {}).get("username") or f"User #{ab}"
        bits.append(f"approved by **{name}**")
    if doc.get("approved_at"):
        bits.append(f"at {fmt_datetime_from_record(doc, 'approved_at')}")
    if bits:
        st.caption(" · ".join(bits))
