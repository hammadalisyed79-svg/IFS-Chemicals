"""Weighbridge completed slip → draft invoice wizard (Phase 5)."""

from __future__ import annotations

import streamlit as st

from application import data_gateway as db
from db_commercial import create_draft_invoice_from_weight_slip, weight_slip_is_linked
from erp_ui import form_flow as ff
from erp_ui.doc_workflow import open_purchase_from_register, open_sale_from_register
from erp_ui.helpers import smart_select, uid
from erp_ui.nav import request_nav


def _party_label(r: dict) -> str:
    name = r.get("customer_name") or r.get("supplier_name") or "—"
    code = (r.get("customer_code") or r.get("supplier_code") or "").strip()
    return f"{code} - {name}" if code else name


def _unlinked_slips() -> list[dict]:
    slips = db.get_completed_unlinked_slips()
    return [r for r in slips if not weight_slip_is_linked(r)]


def render_slip_to_invoice_wizard(key_prefix: str = "wb_wiz") -> None:
    """One-screen flow: pick slip → product (if needed) → draft invoice → open edit."""
    slips = _unlinked_slips()
    if not slips:
        st.caption("No completed slips waiting for a draft invoice.")
        return

    st.markdown("**Slip → draft invoice**")
    st.caption(
        "Pick a completed slip, confirm item if needed, then create a **draft** sale or purchase "
        "with net weight applied — opens the invoice for rates and approval."
    )

    rows = [
        {
            "id": int(r["id"]),
            "code": r.get("document_no") or "",
            "name": _party_label(r),
            "label": (
                f"{r.get('document_no')} — {_party_label(r)} — "
                f"{float(r.get('net_weight') or 0):,.3f} kg — {r.get('vehicle_no') or '—'}"
            ),
            "_row": r,
        }
        for r in slips
    ]

    _, slip_id, slip_pick = smart_select(
        "Completed slip",
        rows,
        f"{key_prefix}_slip",
        "id",
        lambda r: r["label"],
    )
    if not slip_id:
        return

    slip = slip_pick.get("_row") or next((r for r in slips if r["id"] == slip_id), None)
    if not slip:
        return

    is_sale = bool(slip.get("customer_id")) or slip.get("party_type") == "customer"
    kind = "sale" if is_sale else "purchase"
    c1, c2, c3 = st.columns(3)
    c1.metric("Net weight", f"{float(slip.get('net_weight') or 0):,.3f} kg")
    c2.metric("Vehicle", (slip.get("vehicle_no") or "—")[:20])
    c3.metric("Type", "Sale" if is_sale else "Purchase")

    product_id = slip.get("product_id")
    if not product_id:
        _, product_id, _ = smart_select(
            "Item on invoice *",
            db.get_items(),
            f"{key_prefix}_item",
            "id",
            lambda r: f"{r['code']} - {r['name']}",
        )
    else:
        st.caption(f"Item: **{slip.get('product_name') or product_id}**")

    if st.button("Create draft invoice", type="primary", key=f"{key_prefix}_create"):
        if not product_id:
            st.error("Select an item for the invoice line.")
        else:
            try:
                inv_id = create_draft_invoice_from_weight_slip(
                    int(slip_id),
                    user_id=uid(),
                    product_id=int(product_id),
                )
                if is_sale:
                    sale = db.get_sale(inv_id)
                    request_nav("Sales", "Sales Invoices")
                    open_sale_from_register({"id": inv_id, "invoice_no": sale.get("invoice_no")})
                    ff.action_done(
                        f"Draft sale **{sale.get('invoice_no')}** created from slip "
                        f"**{slip.get('document_no')}**."
                    )
                else:
                    pur = db.get_purchase(inv_id)
                    request_nav("Purchases", "Purchase Invoices")
                    open_purchase_from_register({"id": inv_id, "invoice_no": pur.get("invoice_no")})
                    ff.action_done(
                        f"Draft purchase **{pur.get('invoice_no')}** created from slip "
                        f"**{slip.get('document_no')}**."
                    )
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
