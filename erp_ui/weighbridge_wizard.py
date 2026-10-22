"""Weighbridge completed slip → draft invoice or return wizard."""

from __future__ import annotations

import streamlit as st

from application import data_gateway as db
from db_commercial import (
    create_draft_invoice_from_weight_slip,
    create_draft_return_from_weight_slip,
    slip_transaction_type,
    weight_slip_is_linked,
)
from erp_ui import form_flow as ff
from erp_ui.doc_workflow import (
    open_purchase_from_register,
    open_purchase_return_from_register,
    open_sale_from_register,
    open_sale_return_from_register,
)
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
    """One-screen flow: pick slip → product → draft invoice or return → open edit."""
    slips = _unlinked_slips()
    if not slips:
        st.caption("No completed slips waiting for a draft invoice or return.")
        return

    st.markdown("**Slip → draft invoice / return**")
    st.caption(
        "Pick a completed slip, confirm item if needed, then create a **draft** sale/purchase "
        "invoice **or** sale/purchase return with net weight applied."
    )

    rows = [
        {
            "id": int(r["id"]),
            "code": r.get("document_no") or "",
            "name": _party_label(r),
            "label": (
                f"{r.get('document_no')} — {_party_label(r)} — "
                f"{float(r.get('net_weight') or 0):,.3f} kg — {r.get('vehicle_no') or '—'} — "
                f"{slip_transaction_type(r)}"
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

    tx = slip_transaction_type(slip)
    is_sale_side = tx in ("SALE", "SALE_RETURN") or (
        bool(slip.get("customer_id")) or slip.get("party_type") == "customer"
    )
    default_doc = "Return" if tx in ("SALE_RETURN", "PURCHASE_RETURN") else "Invoice"
    doc_choice = st.radio(
        "Create",
        ["Invoice", "Return"],
        index=0 if default_doc == "Invoice" else 1,
        horizontal=True,
        key=f"{key_prefix}_doc",
        help="Invoice = Sales/Purchase invoice. Return = Sale/Purchase return linked to this slip.",
    )
    make_return = doc_choice == "Return"

    c1, c2, c3 = st.columns(3)
    c1.metric("Net weight", f"{float(slip.get('net_weight') or 0):,.3f} kg")
    c2.metric("Vehicle", (slip.get("vehicle_no") or "—")[:20])
    c3.metric(
        "Type",
        (
            ("Sale return" if is_sale_side else "Purchase return")
            if make_return
            else ("Sale" if is_sale_side else "Purchase")
        ),
    )

    product_id = slip.get("product_id")
    if not product_id:
        _, product_id, _ = smart_select(
            "Item on document *",
            db.get_items(),
            f"{key_prefix}_item",
            "id",
            lambda r: f"{r['code']} - {r['name']}",
        )
    else:
        st.caption(f"Item: **{slip.get('product_name') or product_id}**")

    btn_lbl = "Create draft return" if make_return else "Create draft invoice"
    if st.button(btn_lbl, type="primary", key=f"{key_prefix}_create"):
        if not product_id:
            st.error("Select an item for the line.")
        else:
            try:
                if make_return:
                    ret_id = create_draft_return_from_weight_slip(
                        int(slip_id),
                        user_id=uid(),
                        product_id=int(product_id),
                    )
                    if is_sale_side:
                        ret = db.get_sale_return(ret_id)
                        request_nav("Sales", "Sales Returns")
                        open_sale_return_from_register(
                            {"id": ret_id, "return_no": ret.get("return_no")}
                        )
                        ff.action_done(
                            f"Sale return **{ret.get('return_no')}** created from slip "
                            f"**{slip.get('document_no')}**."
                        )
                    else:
                        ret = db.get_purchase_return(ret_id)
                        request_nav("Purchases", "Purchase Returns")
                        open_purchase_return_from_register(
                            {"id": ret_id, "return_no": ret.get("return_no")}
                        )
                        ff.action_done(
                            f"Purchase return **{ret.get('return_no')}** created from slip "
                            f"**{slip.get('document_no')}**."
                        )
                else:
                    inv_id = create_draft_invoice_from_weight_slip(
                        int(slip_id),
                        user_id=uid(),
                        product_id=int(product_id),
                    )
                    if is_sale_side:
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
