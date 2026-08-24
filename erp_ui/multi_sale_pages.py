"""Multi-dispatch sales — one party, one weight slip, many towns → invoices + gate passes."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from application import data_gateway as db
from erp_ui import form_flow as ff
from erp_ui import helpers as hlp
from erp_ui.helpers import std_page_header, uid, smart_select


def _msal_state_key():
    return "msal_dispatches"


def _ensure_dispatches(n_min=2):
    sk = _msal_state_key()
    if sk not in st.session_state or not st.session_state[sk]:
        st.session_state[sk] = [{"town": "", "notes": "", "order_id": None} for _ in range(n_min)]
    return st.session_state[sk]


def _open_sales_orders_for_customer(customer_id):
    """Open/partial SOs with pending qty for this party."""
    try:
        rows = db.get_sales_orders_for_invoice(customer_id) or []
    except Exception:
        rows = []
    return rows


def page_multi_dispatch_sale(items_dict=None, customer_opts=None, *, embedded: bool = False):
    """Render multi-dispatch form (also used as Sales Invoices tab)."""
    if not embedded:
        std_page_header(
            "Sales Invoices",
            title="Multi Dispatch Sale",
            subtitle="One customer · one weight slip · several dispatch towns → separate invoices & gate passes",
            status="register",
            status_kind="shell",
        )
    else:
        st.caption(
            "**Multi Dispatch** — one customer · one weight slip · several towns → separate invoices & gate passes"
        )
    st.caption(
        "Use when one truck is weighed once but goods go to **different towns** for the same party. "
        "Each town invoice can optionally link its own **Sales Order**. "
        "Allocated kg across towns should match the slip net weight."
    )

    items_dict = items_dict or {}
    if not items_dict:
        rows = db.get_items(active_only=True) or []
        items_dict = {
            f"{r.get('code') or ''} - {r.get('name') or ''}": r
            for r in rows
        }
    if not items_dict:
        st.warning("Add products first.")
        return

    customers = db.get_customers(active_only=True) or []
    if not customers:
        st.warning("Add customers first.")
        return

    _, cust_id, cust_row = smart_select(
        "Customer / Party *",
        customers,
        "msal_cust",
        "id",
        lambda r: f"{r.get('code') or ''} — {r.get('name') or ''}",
    )
    if not cust_id:
        st.info("Select the party (same for all invoices).")
        return

    inv_date = st.date_input("Invoice date", value=date.today(), key="msal_date")
    pay_mode = st.selectbox("Payment mode", ["credit", "cash"], key="msal_pay")

    # Weight slip — completed & not attached to any invoice (this party only)
    from db_commercial import (
        get_unlinked_slips_for_party,
        get_weight_slip_pro,
    )

    slips = get_unlinked_slips_for_party("customer", cust_id) or []
    if not slips:
        st.error(
            "No **unlinked** completed weight slip for this customer. "
            "Only slips that are **not** already on any sales/purchase invoice are listed here. "
            "Complete 1st + 2nd weight on **Weight Scale**, or detach the slip from a draft invoice first."
        )
        return

    slip_opts = {
        (
            f"{r.get('document_no')} — "
            f"{(r.get('customer_name') or r.get('supplier_name') or '—')} — "
            f"{r.get('vehicle_no') or '—'} — "
            f"{float(r.get('net_weight') or 0):,.3f} kg — {r.get('slip_date') or ''}"
        ): r["id"]
        for r in slips
    }
    slip_lbl = st.selectbox(
        "Weight slip * (unlinked — single for all invoices)",
        list(slip_opts.keys()),
        key="msal_slip",
    )
    slip_id = slip_opts[slip_lbl]
    slip = get_weight_slip_pro(slip_id) or {}
    slip_net = float(slip.get("net_weight") or 0)
    party_nm = slip.get("customer_name") or slip.get("supplier_name") or "—"
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Slip", slip.get("document_no") or "—")
    m2.metric("Party", party_nm)
    m3.metric("Vehicle", slip.get("vehicle_no") or "—")
    m4.metric("Net weight", f"{slip_net:,.3f} kg")
    st.caption("This slip is free (not on any invoice) — multi-dispatch will claim it as primary.")

    st.divider()
    st.subheader("Dispatch towns")
    dispatches = _ensure_dispatches(2)
    open_sos = _open_sales_orders_for_customer(cust_id)
    so_opts = {
        hlp.sales_order_picker_label(o): o["id"]
        for o in open_sos
    }

    allocated_total = 0.0
    collected = []

    for i, d in enumerate(list(dispatches)):
        with st.expander(f"Invoice / town #{i + 1}" + (f" — {d.get('town')}" if d.get("town") else ""), expanded=True):
            c1, c2 = st.columns([3, 1])
            town = c1.text_input(
                "Dispatch town / destination *",
                value=d.get("town") or "",
                key=f"msal_town_{i}",
                placeholder="e.g. LAHORE, FAISALABAD",
            )
            if c2.button("Remove", key=f"msal_rm_{i}", disabled=len(dispatches) <= 1):
                dispatches.pop(i)
                st.session_state[_msal_state_key()] = dispatches
                st.session_state.pop(f"msal_d{i}_lines", None)
                st.rerun()

            # Optional Sales Order per invoice
            so_labels = ["— No sales order —"] + list(so_opts.keys())
            cur_oid = d.get("order_id")
            default_so = "— No sales order —"
            if cur_oid:
                default_so = next(
                    (lbl for lbl, oid in so_opts.items() if int(oid) == int(cur_oid)),
                    "— No sales order —",
                )
            so_idx = so_labels.index(default_so) if default_so in so_labels else 0
            so_c1, so_c2 = st.columns([3, 1])
            so_lbl = so_c1.selectbox(
                "Sales Order (optional — one SO per invoice)",
                so_labels,
                index=so_idx,
                key=f"msal_so_{i}",
                help="Links this town invoice to an open SO and can load pending lines.",
            )
            order_id = None if so_lbl == "— No sales order —" else so_opts.get(so_lbl)
            if so_c2.button("Load SO lines", key=f"msal_so_load_{i}", disabled=not order_id):
                try:
                    lines = db.sales_order_invoice_lines(order_id)
                    if not lines:
                        raise ValueError("No pending quantity left on this sales order.")
                    order = db.get_sales_order(order_id)
                    # Reset line-editor widgets for this town so SO qty/rates show
                    prefix = f"msal_d{i}"
                    for k in list(st.session_state.keys()):
                        if str(k).startswith(prefix):
                            st.session_state.pop(k, None)
                    st.session_state[f"{prefix}_lines"] = lines
                    # Suggest town from SO.dispatch_town / notes if town empty
                    new_town = town
                    if order and not (town or "").strip():
                        dest = (order.get("dispatch_town") or "").strip()
                        if not dest:
                            try:
                                from erp_core.dispatch_planning import resolve_dispatch_to
                                city = ""
                                with db.get_connection() as conn:
                                    crow = conn.execute(
                                        "SELECT city FROM customers WHERE id=?", (cust_id,),
                                    ).fetchone()
                                    if crow:
                                        city = crow[0] or ""
                                dest = resolve_dispatch_to(order.get("notes"), city)
                                if dest == "-":
                                    dest = ""
                            except Exception:
                                dest = ""
                        if dest:
                            new_town = dest
                            st.session_state[f"msal_town_{i}"] = dest
                    dispatches[i] = {
                        "town": new_town,
                        "notes": d.get("notes") or "",
                        "order_id": order_id,
                    }
                    st.session_state[_msal_state_key()] = dispatches
                    ff.action_done(
                        f"Loaded **{order.get('document_no') if order else 'SO'}** lines into town #{i + 1}. "
                        "Adjust qty/weight if this town is only part of the order."
                    )
                except Exception as e:
                    st.error(str(e).replace("**", ""))

            if not open_sos:
                st.caption("No open sales orders with pending qty for this party.")
            elif order_id:
                st.caption("SO linked — delivery qty will update when this draft is saved.")

            notes = st.text_input("Notes (optional)", value=d.get("notes") or "", key=f"msal_notes_{i}")
            lines, _sub = hlp.smart_line_item_editor(
                items_dict,
                f"msal_d{i}",
                show_weight=True,
                party_id=cust_id,
            )
            inv_wt = sum(float(l.get("net_weight") or 0) for l in (lines or []))
            allocated_total += inv_wt
            st.caption(f"This invoice weight: **{inv_wt:,.3f} kg**")
            dispatches[i] = {"town": town, "notes": notes, "order_id": order_id}
            collected.append({
                "town": town,
                "notes": notes,
                "lines": lines or [],
                "inv_wt": inv_wt,
                "order_id": order_id,
            })

    st.session_state[_msal_state_key()] = dispatches

    if st.button("+ Add another town / invoice", key="msal_add"):
        dispatches.append({"town": "", "notes": "", "order_id": None})
        st.session_state[_msal_state_key()] = dispatches
        st.rerun()

    rem = slip_net - allocated_total
    c_a, c_b, c_c = st.columns(3)
    c_a.metric("Allocated", f"{allocated_total:,.3f} kg")
    c_b.metric("Slip net", f"{slip_net:,.3f} kg")
    c_c.metric("Remaining", f"{rem:,.3f} kg")
    if rem < -0.001:
        st.error(
            "Allocated weight exceeds slip net — reduce town weights, "
            "or tick **Allow save if allocated exceeds slip net** below."
        )
    elif abs(rem) <= 1.0:
        st.success("Allocated weight matches slip (within 1 kg).")
    else:
        st.warning(f"**{rem:,.3f} kg** still unallocated — add to a town or tick allow short below.")

    allow_short = st.checkbox(
        "Allow save if allocated weight is short of slip net",
        value=False,
        key="msal_allow_short",
    )
    allow_over = st.checkbox(
        "Allow save if allocated weight exceeds slip net",
        value=False,
        key="msal_allow_over",
        help="Use when invoice line weights are slightly over the weighbridge slip (e.g. packing variance).",
    )

    if st.button("Create all invoices & gate passes", type="primary", key="msal_save"):
        try:
            from db_commercial import create_multi_dispatch_sales

            result = create_multi_dispatch_sales(
                customer_id=cust_id,
                weight_slip_id=slip_id,
                invoice_date=str(inv_date),
                dispatches=collected,
                user_id=uid(),
                payment_mode=pay_mode,
                allow_weight_short=allow_short,
                allow_weight_over=allow_over,
            )
            # Clear form state
            st.session_state.pop(_msal_state_key(), None)
            for k in list(st.session_state.keys()):
                if str(k).startswith("msal_d") and str(k).endswith("_lines"):
                    st.session_state.pop(k, None)
            rows = result.get("invoices") or []
            msg = (
                f"Created **{len(rows)}** draft invoice(s) on slip **{result.get('slip_no')}** "
                f"({result.get('allocated'):,.3f} / {result.get('slip_net'):,.3f} kg)."
            )
            ff.action_done(msg)
            hlp.render_dataframe_html_table(pd.DataFrame([{
                "Town": r.get("town"),
                "Sales Order": r.get("order_no") or "—",
                "Invoice": r.get("invoice_no"),
                "Weight kg": float(r.get("net_weight") or 0),
                "Gate pass": r.get("gate_pass_no") or "—",
                "Link": "Primary" if r.get("is_primary") else "Reference",
            } for r in rows]))
            st.info("Open **Drafts** to submit each invoice for approval.")
        except Exception as e:
            st.error(str(e).replace("**", ""))
