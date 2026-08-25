"""Unified approval inbox — sales, purchases, portal queues (Phase 4)."""

from __future__ import annotations

import streamlit as st

from application import data_gateway as db
from application.data_gateway import user_can
from erp_core import portal_service as ps
from erp_ui import form_flow as ff
from erp_ui.helpers import fmt_money, std_page_header, uid
from erp_ui.invoice_status_ui import render_invoice_review, invoice_action_bar, status_badge_html


def _can_approve(user: dict) -> bool:
    return user.get("role") == "admin" or user_can(user, "Sales", "approve")


def _pending_sales(limit: int = 80) -> list[dict]:
    r = db.search_sales_invoices(status="pending_approval", page_size=limit, export_all=True)
    return r.get("items") or []


def _pending_purchases(limit: int = 80) -> list[dict]:
    r = db.search_purchases(status="pending_approval", page_size=limit, export_all=True)
    return r.get("items") or []


def _pending_portal_orders():
    try:
        return ps.list_all_portal_orders(status="Under Review")
    except Exception:
        return []


def _batch_approve_sales(ids: list[int], user_id: int) -> tuple[int, list[str]]:
    ok, errs = 0, []
    for sid in ids:
        try:
            inv = db.get_sale(sid)
            if not inv or (inv.get("status") or "").lower() != "pending_approval":
                continue
            if inv.get("weight_match_status") == "excess_variance":
                errs.append(f"{inv.get('invoice_no')}: excess weight — approve individually with override.")
                continue
            db.approve_sale_invoice(sid, user_id)
            ok += 1
        except Exception as e:
            inv = db.get_sale(sid)
            label = (inv or {}).get("invoice_no") or str(sid)
            errs.append(f"{label}: {e}")
    return ok, errs


def _batch_approve_purchases(ids: list[int], user_id: int) -> tuple[int, list[str]]:
    ok, errs = 0, []
    for pid in ids:
        try:
            inv = db.get_purchase(pid)
            if not inv or (inv.get("status") or "").lower() != "pending_approval":
                continue
            if inv.get("weight_match_status") == "excess_variance":
                errs.append(f"{inv.get('invoice_no')}: excess weight — approve individually.")
                continue
            db.approve_purchase_invoice(pid, user_id)
            ok += 1
        except Exception as e:
            inv = db.get_purchase(pid)
            label = (inv or {}).get("invoice_no") or str(pid)
            errs.append(f"{label}: {e}")
    return ok, errs


def page_approval_inbox():
    user = st.session_state.get("user") or {}
    std_page_header("Approval Inbox", status="pending_approval", status_kind="invoice")

    if not _can_approve(user):
        st.warning("You do not have permission to approve documents.")
        return

    sales = _pending_sales()
    purchases = _pending_purchases()
    portal = _pending_portal_orders()

    st.markdown(
        f'<div class="txn-status-strip">{status_badge_html("pending_approval")}'
        f'&nbsp;<strong>{len(sales)}</strong> sales · '
        f'<strong>{len(purchases)}</strong> purchases · '
        f'<strong>{len(portal)}</strong> distributor orders</div>',
        unsafe_allow_html=True,
    )

    # --- Batch sales ---
    st.markdown("##### Pending sales invoices")
    if not sales:
        st.caption("No sales awaiting approval.")
    else:
        sale_pick: list[int] = []
        for inv in sales[:40]:
            sid = inv["id"]
            label = (
                f"{inv.get('invoice_no')} — {inv.get('customer_name')} "
                f"({fmt_money(inv.get('total'))})"
            )
            excess = inv.get("weight_match_status") == "excess_variance"
            if st.checkbox(
                label + (" ⚠ variance" if excess else ""),
                key=f"inbox_sal_{sid}",
                disabled=excess,
            ):
                sale_pick.append(sid)
        if st.button(
            f"Approve selected sales ({len(sale_pick)})",
            type="primary",
            key="inbox_batch_sal",
            disabled=not sale_pick,
        ):
            ok, errs = _batch_approve_sales(sale_pick, uid())
            msg = f"Approved **{ok}** sale invoice(s)."
            if errs:
                msg += " Some failed — see below."
                for e in errs[:8]:
                    st.error(e)
            ff.action_done(msg)

    st.divider()

    # --- Batch purchases ---
    st.markdown("##### Pending purchase invoices")
    if not purchases:
        st.caption("No purchases awaiting approval.")
    else:
        pur_pick: list[int] = []
        for inv in purchases[:40]:
            pid = inv["id"]
            label = (
                f"{inv.get('invoice_no')} — {inv.get('supplier_name')} "
                f"({fmt_money(inv.get('total'))})"
            )
            excess = inv.get("weight_match_status") == "excess_variance"
            if st.checkbox(
                label + (" ⚠ variance" if excess else ""),
                key=f"inbox_pur_{pid}",
                disabled=excess,
            ):
                pur_pick.append(pid)
        if st.button(
            f"Approve selected purchases ({len(pur_pick)})",
            type="primary",
            key="inbox_batch_pur",
            disabled=not pur_pick,
        ):
            ok, errs = _batch_approve_purchases(pur_pick, uid())
            msg = f"Approved **{ok}** purchase invoice(s)."
            if errs:
                msg += " Some failed — see below."
                for e in errs[:8]:
                    st.error(e)
            ff.action_done(msg)

    st.divider()

    # --- Portal distributor orders ---
    st.markdown("##### Distributor portal orders")
    if not portal:
        st.caption("No distributor orders under review.")
    else:
        for o in portal[:20]:
            with st.container(border=True):
                st.markdown(f"**{o.get('order_no')}** — {o.get('customer_name')}")
                st.caption(f"{o.get('order_date')} · {fmt_money(o.get('total'))}")
                c1, c2 = st.columns(2)
                if c1.button("Approve", key=f"inbox_po_ap_{o['id']}", type="primary", use_container_width=True):
                    ps.update_portal_status(o["id"], "Approved", user_id=user.get("id"))
                    ff.action_done("Portal order approved.")
                if c2.button("Reject", key=f"inbox_po_rj_{o['id']}", use_container_width=True):
                    try:
                        ps.reject_portal_order(o["id"], "", user_id=user.get("id"))
                        ff.action_done("Portal order rejected.")
                    except Exception as e:
                        st.error(str(e))

    st.divider()
    st.caption(
        "Open a single invoice for full review, weight check, and print — use **Sale Approval** "
        "or **Purchase Approval**, or select a row below."
    )

    detail_kind = st.radio(
        "Detail review",
        ["Sales", "Purchases"],
        horizontal=True,
        key="inbox_detail_kind",
    )
    if detail_kind == "Sales" and sales:
        opts = {f"{r['invoice_no']} — {r['customer_name']}": r["id"] for r in sales}
        pick = st.selectbox("Sales invoice", list(opts.keys()), key="inbox_sal_detail")
        sid = opts.get(pick)
        if sid:
            render_invoice_review("sale", sid, key_prefix=f"inbox_sal_rev_{sid}")
            invoice_action_bar(
                "sale", sid, "pending_approval",
                key_prefix=f"inbox_sal_act_{sid}", show_print=True,
            )
    elif detail_kind == "Purchases" and purchases:
        opts = {f"{r['invoice_no']} — {r['supplier_name']}": r["id"] for r in purchases}
        pick = st.selectbox("Purchase invoice", list(opts.keys()), key="inbox_pur_detail")
        pid = opts.get(pick)
        if pid:
            render_invoice_review("purchase", pid, key_prefix=f"inbox_pur_rev_{pid}")
            invoice_action_bar(
                "purchase", pid, "pending_approval",
                key_prefix=f"inbox_pur_act_{pid}", show_print=True,
            )
