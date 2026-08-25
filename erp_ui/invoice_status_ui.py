"""Professional invoice status chrome — badges, banners, actions, shared review."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from application import data_gateway as db
from erp_ui.helpers import fmt_money, fmt_datetime_from_record, uid, user_role, render_dataframe_html_table
from erp_ui import helpers as hlp
from erp_ui import form_flow as ff

STATUS_META = {
    "draft": {
        "label": "Draft",
        "css": "inv-badge-draft",
        "hint": "Edit freely, then submit for approval.",
    },
    "pending_approval": {
        "label": "Pending Approval",
        "css": "inv-badge-pending",
        "hint": "To change qty or rates: click Return for Edit → open Edit tab → change lines → Submit for Approval again.",
    },
    "approved": {
        "label": "Approved",
        "css": "inv-badge-approved",
        "hint": "Posted to ledger and stock. Admin can unapprove to amend.",
    },
    "rejected": {
        "label": "Rejected",
        "css": "inv-badge-rejected",
        "hint": "Correct the invoice and submit again.",
    },
    "cancelled": {
        "label": "Cancelled",
        "css": "inv-badge-cancelled",
        "hint": "Voided — read only.",
    },
    # Document statuses (orders / quotes / etc.) — avoid label "Open" which looks like an action button
    "open": {
        "label": "Active",
        "css": "inv-badge-approved",
        "hint": "Order is open. Use Open order to edit.",
    },
    "partial": {
        "label": "Partial",
        "css": "inv-badge-pending",
        "hint": "Partially delivered / invoiced.",
    },
    "closed": {
        "label": "Closed",
        "css": "inv-badge-cancelled",
        "hint": "Fully completed.",
    },
    "converted": {
        "label": "Converted",
        "css": "inv-badge-approved",
        "hint": "Converted to another document.",
    },
    "posted": {
        "label": "Posted",
        "css": "inv-badge-approved",
        "hint": "Posted.",
    },
    "sent": {
        "label": "Sent",
        "css": "inv-badge-pending",
        "hint": "Sent to customer.",
    },
}


def status_label(status: str | None) -> str:
    key = (status or "draft").lower()
    return STATUS_META.get(key, {}).get("label") or (status or "draft").replace("_", " ").title()


def status_badge_html(status: str | None) -> str:
    key = (status or "draft").lower()
    meta = STATUS_META.get(key, {"label": status_label(status), "css": "inv-badge-draft"})
    return f'<span class="inv-badge {meta["css"]}">{meta["label"]}</span>'


def status_badge(status: str | None):
    """Render a status pill."""
    st.markdown(status_badge_html(status), unsafe_allow_html=True)


def status_hint(status: str | None) -> str:
    key = (status or "draft").lower()
    return STATUS_META.get(key, {}).get("hint", "")


def _doc_fields(kind: str, doc: dict):
    if kind == "sale":
        return {
            "no": doc.get("invoice_no") or doc.get("document_no") or "—",
            "party": doc.get("customer_name") or "—",
            "date": fmt_datetime_from_record(
                {**doc, "sale_date": doc.get("sale_date") or doc.get("invoice_date")},
                "sale_date",
            ),
            "total": doc.get("total"),
            "status": doc.get("status") or "draft",
        }
    return {
        "no": doc.get("invoice_no") or doc.get("document_no") or "—",
        "party": doc.get("supplier_name") or "—",
        "date": fmt_datetime_from_record(
            {**doc, "purchase_date": doc.get("purchase_date") or doc.get("invoice_date")},
            "purchase_date",
        ),
        "total": doc.get("total"),
        "status": doc.get("status") or "draft",
    }


def invoice_status_banner(kind: str, doc: dict | None):
    """One-strip status banner: doc · party · date · badge · total · next step."""
    if not doc:
        return
    f = _doc_fields(kind, doc)
    badge = status_badge_html(f["status"])
    hint = status_hint(f["status"])
    st.markdown(
        f"""
        <div class="inv-status-banner">
          <div class="inv-status-banner-main">
            <span class="inv-status-doc">{f["no"]}</span>
            <span class="inv-status-sep">·</span>
            <span class="inv-status-party">{f["party"]}</span>
            <span class="inv-status-sep">·</span>
            <span class="inv-status-date">{f["date"]}</span>
            {badge}
            <span class="inv-status-total">{fmt_money(f["total"])}</span>
          </div>
          <div class="inv-status-hint">{hint}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    from erp_ui.voucher_validation import render_document_audit_meta
    render_document_audit_meta(doc)


def weight_status_badge(status: str | None) -> str:
    labels = {
        "matched": "Matched",
        "minor_variance": "Minor Variance",
        "excess_variance": "Excess Variance",
    }
    return labels.get(status, status or "—")


def render_invoice_review(kind: str, inv_id: int, *, show_print: bool = True, key_prefix: str | None = None):
    """Full checker view for sales or purchase invoice.

    key_prefix must be unique per screen/tab — Streamlit runs all tabs, so the same
    invoice can appear in Pending and Edit in one run.
    """
    if kind == "sale":
        inv = db.get_sale(inv_id)
        party_key = "customer_name"
        date_key = "sale_date"
        print_type = "Sales Invoice"
        gps = db.get_gate_passes(sales_invoice_id=inv_id) if inv else []
    else:
        inv = db.get_purchase(inv_id)
        party_key = "supplier_name"
        date_key = "purchase_date"
        print_type = "Purchase Invoice"
        gps = db.get_gate_passes(purchase_invoice_id=inv_id) if inv else []

    if not inv:
        st.error("Invoice not found.")
        return None

    # Unique widget namespace for this review instance (print buttons, etc.)
    kp = key_prefix or f"{kind}_rev_{inv_id}"
    from erp_ui.voucher_validation import render_stock_policy_banner
    render_stock_policy_banner()
    invoice_status_banner(kind, inv)

    st.markdown("##### Invoice Lines")
    items = inv.get("items") or []
    if items:
        df = pd.DataFrame([{
            "Product": i.get("item_name"),
            "Qty": float(i.get("quantity") or 0),
            "Net Wt (kg)": float(i.get("net_weight") or 0),
            "Rate": float(i.get("rate") or 0),
            "Disc %": float(i.get("discount_pct") or 0),
            "Amount": float(i.get("amount") or 0),
        } for i in items])
        render_dataframe_html_table(df)
    else:
        st.caption("No line items.")

    st.markdown("##### Tax & Amount")
    t1, t2, t3, t4, t5 = st.columns(5)
    t1.metric("Subtotal", fmt_money(inv.get("subtotal")))
    t2.metric("Discount", fmt_money(inv.get("discount")))
    t3.metric("Tax", fmt_money(inv.get("tax")))
    t4.metric("Net Total", fmt_money(inv.get("total")))
    t5.metric("Paid", fmt_money(inv.get("paid_amount")))

    st.markdown("##### Weight Verification")
    st.markdown(f"**Match status:** {weight_status_badge(inv.get('weight_match_status'))}")
    w1, w2, w3, w4 = st.columns(4)
    inv_wt = float(inv.get("total_net_weight") or inv.get("invoice_weight_kg") or 0)
    phys = float(inv.get("physical_weight_kg") or 0)
    var_kg = float(inv.get("weight_variance_kg") or 0)
    var_pct = float(inv.get("weight_variance_pct") or 0)
    w1.metric("Invoice Weight (kg)", f"{inv_wt:,.3f}")
    w2.metric("Physical Weight (kg)", f"{phys:,.3f}")
    w3.metric("Variance (kg)", f"{var_kg:+,.3f}")
    w4.metric("Variance (%)", f"{var_pct:.2f}%")

    if inv.get("weight_slip_id"):
        st.markdown("##### Weight Slip")
        ws = db.get_weight_slip_pro(inv["weight_slip_id"])
        if ws:
            ws_df = pd.DataFrame([{
                "Slip No": ws.get("document_no"),
                "Date / Time": fmt_datetime_from_record(ws, "slip_date", time_field="slip_time"),
                "Vehicle": ws.get("vehicle_no"),
                "Driver": ws.get("driver_name"),
                "First Wt": float(ws.get("first_weight") or 0),
                "Second Wt": float(ws.get("second_weight") or 0),
                "Net Physical": float(ws.get("net_weight") or 0),
            }])
            render_dataframe_html_table(ws_df)

    if gps:
        st.markdown("##### Gate Pass")
        gp = gps[0]
        gp_df = pd.DataFrame([{
            "Gate Pass No": gp.get("document_no"),
            "Date / Time": fmt_datetime_from_record(gp, "pass_date", time_field="pass_time"),
            "Vehicle": gp.get("vehicle_no"),
            "Driver": gp.get("driver_name"),
            "Weight Slip": gp.get("weight_slip_no"),
        }])
        render_dataframe_html_table(gp_df)
    elif inv.get("weighbridge_required", 1) != 0:
        st.caption("No gate pass linked yet.")

    if show_print:
        st.markdown("##### Print")
        from erp_ui.document_print import document_print_toolbar
        pc1, pc2, pc3 = st.columns(3)
        with pc1:
            document_print_toolbar(print_type, inv_id, key_prefix=f"{kp}_inv")
        if inv.get("weight_slip_id"):
            with pc2:
                document_print_toolbar(
                    "Weight Slip", inv["weight_slip_id"], key_prefix=f"{kp}_ws",
                )
        if gps:
            with pc3:
                document_print_toolbar("Gate Pass", gps[0]["id"], key_prefix=f"{kp}_gp")

    return inv


def invoice_action_bar(
    kind: str,
    inv_id: int,
    status: str | None,
    *,
    key_prefix: str,
    show_print: bool = True,
    on_after_action=None,
):
    """
    Context actions by status. Hides invalid buttons instead of dead-end messages.
    kind: 'sale' | 'purchase'
    """
    status = (status or "draft").lower()
    inv = db.get_sale(inv_id) if kind == "sale" else db.get_purchase(inv_id)
    if not inv:
        return

    # Warn early when cash day is closed — cash invoices cannot submit/approve
    try:
        inv_date = inv.get("invoice_date") or inv.get("sale_date") or inv.get("purchase_date")
        mode = (inv.get("payment_mode") or "credit").lower()
        paid = float(inv.get("paid_amount") or 0)
        is_cash = paid > 0.009 and mode == "cash"
        if kind == "sale" and not is_cash:
            # SALE IN CASH master still posts cash on approval
            from db_invoice_workflow import _is_counter_cash_customer
            with db.get_connection() as conn:
                is_cash = _is_counter_cash_customer(conn, inv.get("customer_id"))
        if is_cash and inv_date and db.is_cash_day_closed(str(inv_date)[:10]):
            st.error(
                f"Cash day **{str(inv_date)[:10]}** is closed — this cash invoice will **not** be posted. "
                f"**Open the day** in Finance > Cash Book to post this transaction."
            )
    except Exception:
        pass

    excess = inv.get("weight_match_status") == "excess_variance"
    cols = st.columns(6)
    idx = 0

    def _next_col():
        nonlocal idx
        c = cols[idx % 6]
        idx += 1
        return c

    if show_print:
        with _next_col():
            from erp_ui.document_print import document_print_toolbar
            ptype = "Sales Invoice" if kind == "sale" else "Purchase Invoice"
            document_print_toolbar(ptype, inv_id, key_prefix=f"{key_prefix}_prt")

    if status in ("draft", "rejected"):
        if _next_col().button("Submit for Approval", type="primary", key=f"{key_prefix}_submit",
                              use_container_width=True):
            try:
                if kind == "sale":
                    db.submit_sale_invoice(inv_id, uid())
                else:
                    db.submit_purchase_invoice(inv_id, uid())
                if on_after_action:
                    on_after_action()
                ff.action_done("Submitted for approval.")
            except Exception as e:
                st.error(str(e))
        if _next_col().button("Delete", key=f"{key_prefix}_del", use_container_width=True):
            try:
                if kind == "sale":
                    db.delete_sale(inv_id)
                else:
                    db.delete_purchase(inv_id)
                if on_after_action:
                    on_after_action()
                ff.action_done("Invoice deleted successfully.")
            except Exception as e:
                st.error(str(e))

    if status == "pending_approval":
        override = None
        if excess:
            st.error(
                f"Weight variance {float(inv.get('weight_variance_pct') or 0):.2f}% exceeds limit. "
                "Admin override required."
            )
            if user_role() != "admin":
                st.warning("Only administrators can approve excess-variance invoices.")
            else:
                override = st.text_input(
                    "Admin override reason (required)", key=f"{key_prefix}_ov",
                )
        else:
            override = st.text_input(
                "Override reason (only if needed)", key=f"{key_prefix}_ov",
            )

        can_approve = not (excess and user_role() != "admin")
        if _next_col().button(
            "Approve", type="primary", key=f"{key_prefix}_appr",
            disabled=not can_approve, use_container_width=True,
        ):
            try:
                if kind == "sale":
                    db.approve_sale_invoice(inv_id, uid(), override or None)
                    msg = "Approved — posted to ledger, stock, and accounting."
                else:
                    db.approve_purchase_invoice(inv_id, uid(), override or None)
                    try:
                        gid = db.generate_gate_pass_from_purchase(inv_id, uid())
                        msg = f"Approved. Inward gate pass ID {gid}."
                    except Exception:
                        msg = "Approved."
                if on_after_action:
                    on_after_action()
                ff.action_done(msg)
            except Exception as e:
                st.error(str(e))

        # Unlock editing: pending → rejected (editable), then user edits and resubmits
        if _next_col().button(
            "Return for Edit",
            key=f"{key_prefix}_edit_back",
            use_container_width=True,
            help="Unlock this invoice so qty/rates can be changed on the Edit tab.",
        ):
            try:
                reason = "Returned for editing (qty/rate change)"
                if kind == "sale":
                    db.reject_sale_invoice(inv_id, uid(), reason)
                else:
                    db.reject_purchase_invoice(inv_id, uid(), reason)
                if on_after_action:
                    on_after_action()
                ff.action_done(
                    "Invoice unlocked for editing. Open the **Edit** tab (or **Drafts**), "
                    "change quantities/rates, then **Submit for Approval** again.",
                    title="Returned",
                )
            except Exception as e:
                st.error(str(e))

        if _next_col().button(
            "Reject",
            key=f"{key_prefix}_rej",
            use_container_width=True,
            help="Reject permanently from this approval cycle (also unlocks for correction).",
        ):
            try:
                if kind == "sale":
                    db.reject_sale_invoice(inv_id, uid(), "Rejected from workflow")
                else:
                    db.reject_purchase_invoice(inv_id, uid(), "Rejected")
                st.warning("Invoice rejected — correct it on Edit / Drafts, then resubmit if needed.")
                if on_after_action:
                    on_after_action()
                st.rerun()
            except Exception as e:
                st.error(str(e))

    if status == "approved":
        hlp.admin_unapprove_panel(kind, inv_id, inv.get("invoice_no") or "", key_prefix)
        hlp.admin_cancel_panel(kind, inv_id, inv.get("invoice_no") or "", key_prefix)


def section_step(title: str, step: int | None = None):
    """Labeled section for New invoice guided flow."""
    label = f"Step {step} — {title}" if step else title
    st.markdown(f'<div class="inv-step-header">{label}</div>', unsafe_allow_html=True)
