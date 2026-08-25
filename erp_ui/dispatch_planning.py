"""Production & Dispatch Planning — combine open SOs for loading & production."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from application import data_gateway as db
from erp_core import dispatch_planning as dp
from erp_ui.helpers import std_page_header, export_buttons, render_dataframe_html_table


@st.dialog("Sales Order", width="large")
def _sales_order_view_dialog(so_id: int):
    """Full SO view + print (opened from Dispatch Planning)."""
    from erp_ui.document_print import document_print_toolbar

    order = db.get_sales_order(so_id)
    if not order:
        st.error("Sales order not found.")
        return

    doc = order.get("document_no") or "—"
    st.markdown(f"### {doc}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Customer", order.get("customer_name") or "—")
    m2.metric("Order date", str(order.get("order_date") or "—")[:10])
    m3.metric("Delivery", str(order.get("delivery_date") or "—")[:10] or "—")
    m4.metric("Status", str(order.get("status") or "open").replace("_", " ").title())

    try:
        from erp_core.dispatch_planning import resolve_dispatch_to
        city = ""
        try:
            with db.get_connection() as conn:
                crow = conn.execute(
                    "SELECT city FROM customers WHERE id=?", (order.get("customer_id"),)
                ).fetchone()
                if crow:
                    city = crow[0] or ""
        except Exception:
            city = ""
        dest = resolve_dispatch_to(order.get("notes"), city)
        if dest and dest != "-":
            st.caption(f"Dispatch To: **{dest}**")
    except Exception:
        pass

    if order.get("notes"):
        st.info(f"Notes: {order['notes']}")

    document_print_toolbar(
        "Sales Order", so_id, key_prefix=f"dsp_so_dlg_{so_id}", hide_rates=True,
    )

    items = order.get("items") or []
    if not items:
        st.warning("No line items on this sales order.")
        return

    rows = []
    for it in items:
        qty = float(it.get("quantity") or 0)
        delivered = float(it.get("delivered_qty") or 0)
        pending = max(qty - delivered, 0)
        sw = float(it.get("standard_weight") or 0)
        rows.append({
            "Code": it.get("product_code") or "",
            "Product": it.get("product_name") or "",
            "Unit": it.get("unit") or "",
            "Qty": qty,
            "Delivered": delivered,
            "Pending": pending,
            "Pending kg": round(pending * sw, 3) if sw else 0,
        })
    render_dataframe_html_table(pd.DataFrame(rows))

    status = (order.get("status") or "open").lower()
    pending_total = sum(
        max(float(it.get("quantity") or 0) - float(it.get("delivered_qty") or 0), 0)
        for it in items
    )
    if status in ("open", "partial") and pending_total > 0.0001:
        st.divider()
        st.markdown("**Abandon remaining quantity**")
        st.caption(
            "Marks this order **Closed**. Undelivered balance will not appear in "
            "Dispatch Planning or **Create invoice from Sales Order**."
        )
        reason = st.text_input(
            "Reason (optional)",
            key=f"dsp_abandon_reason_{so_id}",
            placeholder="e.g. Customer cancelled balance / will not take remaining",
        )
        if st.button(
            "Mark complete — do not reuse",
            type="primary",
            key=f"dsp_abandon_btn_{so_id}",
        ):
            try:
                from erp_ui.helpers import uid
                db.abandon_sales_order_remaining(so_id, reason, uid())
                st.success(f"**{doc}** closed — remaining qty abandoned.")
                st.rerun()
            except Exception as e:
                st.error(str(e))


def page_dispatch_planning():
    std_page_header("Dispatch Planning", status="register", status_kind="shell")

    d_from_default, d_to_default = dp.default_delivery_window(7)
    all_open = dp.list_dispatch_sales_orders()
    if not all_open:
        st.info("No open or partial sales orders with pending quantity.")
        return

    with st.expander("Filters", expanded=True):
        if not st.session_state.get("_dsp_all_pending_default_v1"):
            st.session_state["dsp_use_window"] = False
            st.session_state["_dsp_all_pending_default_v1"] = True
        c1, c2, c3 = st.columns([1, 1, 1])
        use_window = c1.checkbox(
            "Filter by delivery / order date",
            value=False,
            key="dsp_use_window",
            help="Off by default: all open/partial SOs with pending qty. Turn on to limit by date.",
        )
        d_from = c2.date_input(
            "From",
            value=date.fromisoformat(d_from_default),
            key="dsp_from",
            disabled=not use_window,
        )
        d_to = c3.date_input(
            "To",
            value=date.fromisoformat(d_to_default),
            key="dsp_to",
            disabled=not use_window,
        )

    if use_window:
        orders = dp.list_dispatch_sales_orders(
            delivery_from=str(d_from),
            delivery_to=str(d_to),
        )
        if not orders:
            st.info(
                "No open/partial sales orders in this delivery window. "
                "Widen the dates or turn off the date filter."
            )
            orders = []
    else:
        orders = all_open

    if not orders:
        st.warning("No matching sales orders in this filter. Widen the date range or turn the filter off.")
        return

    # --- Order picker ---
    st.markdown("### Sales orders")
    st.caption(
        "Tick **Include** for the plan. Select an SO and click **Open SO** "
        "to view the full order, lines, and print."
    )

    picker_rows = []
    for o in orders:
        picker_rows.append({
            "Include": True,
            "SO": o["document_no"],
            "Customer": o.get("customer_name") or "",
            "Delivery": (o.get("delivery_date") or o.get("order_date") or "")[:10],
            "Dispatch To": o.get("dispatch_to") or "-",
            "Status": str(o.get("status") or "").title(),
            "Pending Qty": float(o.get("pending_qty") or 0),
            "Pending kg": float(o.get("pending_kg") or 0),
            "_id": int(o["id"]),
        })
    base_df = pd.DataFrame(picker_rows)

    edit_df = st.data_editor(
        base_df,
        hide_index=True,
        use_container_width=True,
        disabled=[c for c in base_df.columns if c != "Include"],
        column_config={
            "Include": st.column_config.CheckboxColumn("Include", default=True),
            "Pending Qty": st.column_config.NumberColumn(format="%.3f"),
            "Pending kg": st.column_config.NumberColumn(format="%.3f"),
            "_id": None,
        },
        key="dsp_order_editor",
    )

    id_by_label = {
        f"{r['SO']} — {r['Customer']}": int(r["_id"])
        for _, r in edit_df.iterrows()
    }
    labels = list(id_by_label.keys())
    oc1, oc2, oc3, oc4 = st.columns([3, 1, 1, 1])
    choice = oc1.selectbox("Sales order", labels, key="dsp_so_open_sel")
    if oc2.button("Open SO", type="primary", key="dsp_so_open_btn", use_container_width=True):
        if choice in id_by_label:
            _sales_order_view_dialog(id_by_label[choice])
    sel_order = next((o for o in orders if o["id"] == id_by_label.get(choice)), None)
    can_abandon = (
        sel_order
        and (sel_order.get("status") or "open").lower() in ("open", "partial")
        and float(sel_order.get("pending_qty") or 0) > 0.0001
    )
    if oc3.button(
        "Mark complete",
        key="dsp_so_abandon_btn",
        use_container_width=True,
        disabled=not can_abandon,
        help="Close SO and abandon remaining qty — removes from pending lists",
    ):
        if choice in id_by_label:
            _sales_order_view_dialog(id_by_label[choice])
    if oc4.button(
        "Gate Pass",
        key="dsp_so_gp_btn",
        use_container_width=True,
        disabled=not sel_order,
        help="Prefill gate pass from this sales order (or its invoice)",
    ):
        if sel_order:
            from db_commercial import gate_pass_defaults_from_sales_invoice
            from erp_ui.helpers import sales_order_dispatch_to
            from erp_ui.nav import request_nav

            prefill = {}
            with db.get_connection() as conn:
                inv = conn.execute(
                    "SELECT id FROM sales_invoices WHERE order_id=? ORDER BY id DESC LIMIT 1",
                    (int(sel_order["id"]),),
                ).fetchone()
            if inv:
                prefill = gate_pass_defaults_from_sales_invoice(int(inv["id"]))
            else:
                dest = sales_order_dispatch_to(sel_order)
                prefill = {
                    "customer_id": sel_order.get("customer_id"),
                    "party_name": sel_order.get("customer_name"),
                    "remarks": f"SO {sel_order.get('document_no')} | Dispatch to {dest}" if dest else f"SO {sel_order.get('document_no')}",
                }
            st.session_state["gp_prefill"] = prefill
            request_nav("Gate Pass", "Gate Pass Entry")
            st.rerun()

    selected_ids = [
        int(r["_id"]) for _, r in edit_df.iterrows() if bool(r.get("Include"))
    ]
    selected_orders = [o for o in orders if o["id"] in set(selected_ids)]

    if not selected_orders:
        st.info("Select at least one sales order.")
        return

    # --- KPIs ---
    kpi = dp.dispatch_kpis(selected_orders)
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Orders", f"{kpi['order_count']}")
    k2.metric("Customers", f"{kpi['customer_count']}")
    k3.metric("Pending qty", f"{kpi['pending_qty']:,.3f}")
    k4.metric("Pending net kg", f"{kpi['pending_kg']:,.3f}")
    k5.metric("Earliest delivery", kpi["earliest_delivery"] or "—")

    # --- By destination ---
    st.markdown("### By destination")
    dest_rows = dp.summarize_by_destination(selected_orders)
    if dest_rows:
        dest_df = pd.DataFrame(dest_rows).rename(columns={
            "dispatch_to": "Dispatch To",
            "order_count": "Orders",
            "customer_count": "Customers",
            "pending_qty": "Pending Qty",
            "pending_kg": "Pending kg",
        })
        cols = st.columns(min(4, max(1, len(dest_rows))))
        for i, d in enumerate(dest_rows[:4]):
            with cols[i % len(cols)]:
                st.markdown(
                    f"**Dispatch to {d['dispatch_to']}**  \n"
                    f"{d['order_count']} order(s) · {d['pending_kg']:,.3f} kg"
                )
        render_dataframe_html_table(dest_df)

    # --- Combined requirements ---
    st.markdown("### Combined item requirements")
    reqs = dp.aggregate_dispatch_requirements(selected_ids)
    if not reqs:
        st.info("No pending line items on the selected orders.")
        return

    req_df = pd.DataFrame(reqs)
    show = req_df.rename(columns={
        "product_code": "Code",
        "product_name": "Product",
        "unit": "Unit",
        "ordered_qty": "Ordered",
        "delivered_qty": "Delivered",
        "pending_qty": "Pending Qty",
        "pending_kg": "Pending kg",
        "stock_qty": "Stock",
        "shortfall_qty": "Shortfall",
        "standard_weight": "Std wt (kg)",
    })[[
        "Code", "Product", "Unit", "Ordered", "Delivered",
        "Pending Qty", "Pending kg", "Stock", "Shortfall", "Std wt (kg)",
    ]]
    render_dataframe_html_table(show)
    total_kg = sum(float(r["pending_kg"]) for r in reqs)
    total_qty = sum(float(r["pending_qty"]) for r in reqs)
    short_n = sum(1 for r in reqs if float(r.get("shortfall_qty") or 0) > 0.0001)
    st.caption(
        f"**{len(reqs)}** products · pending **{total_qty:,.3f}** units · "
        f"**{total_kg:,.3f} kg** net · **{short_n}** with stock shortfall"
    )
    export_buttons(show, filename="dispatch_requirements", title="Dispatch Requirements")
