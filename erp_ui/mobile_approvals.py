"""V15 — Mobile-friendly approval queue for internal users."""

from __future__ import annotations

import streamlit as st

from erp_ui import form_flow as ff
from application import data_gateway as db
from erp_core import portal_service as ps
from application.data_gateway import user_can
from erp_ui.helpers import std_page_header, sticky_page_tabs


def _pending_portal_orders():
    return ps.list_all_portal_orders(status="Under Review")


def _pending_sales_orders():
    with db.get_connection() as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='sales_orders'").fetchone():
            return []
        from application.data_gateway import rows_to_list
        return rows_to_list(conn.execute(
            """SELECT so.id, so.document_no, so.order_date, so.total, so.status,
                      c.name AS customer_name, so.source_channel
               FROM sales_orders so
               JOIN customers c ON c.id=so.customer_id
               WHERE COALESCE(so.status,'open') IN ('open','partial')
               AND so.source_channel='portal'
               ORDER BY so.order_date DESC LIMIT 50"""
        ).fetchall())


def page_mobile_approvals():
    user = st.session_state.get("user") or {}
    st.markdown('<div class="mobile-approval-root"></div>', unsafe_allow_html=True)
    std_page_header("Mobile Approvals", status="register", status_kind="shell")

    if not user_can(user, "Sales", "approve") and user.get("role") != "admin":
        st.warning("You do not have approval permission.")
        return

    tab = sticky_page_tabs(["Distributor Orders", "Portal Sales Orders"], "mobile_appr_tab")

    if tab == "Distributor Orders":
        orders = _pending_portal_orders()
        if not orders:
            st.success("No distributor orders awaiting review.")
        for o in orders:
            with st.container(border=True):
                st.markdown(f"### {o['order_no']}")
                st.write(f"**Customer:** {o.get('customer_name')}")
                st.write(f"**Amount:** Rs. {float(o.get('total') or 0):,.2f}")
                st.write(f"**Date:** {o.get('order_date')} · **Status:** {o.get('status')}")
                comment = st.text_area("Comment", key=f"pc_{o['id']}", height=68)
                c1, c2 = st.columns(2)
                if c1.button("Approve", key=f"ap_{o['id']}", type="primary", use_container_width=True):
                    ps.update_portal_status(o["id"], "Approved", user_id=user.get("id"))
                    ff.action_done("Approved")
                if c2.button("Reject", key=f"rj_{o['id']}", use_container_width=True):
                    try:
                        ps.reject_portal_order(o["id"], comment, user_id=user.get("id"))
                        ff.action_done("Rejected — distributor notified.")
                    except Exception as e:
                        st.error(str(e))

    elif tab == "Portal Sales Orders":
        sos = _pending_sales_orders()
        if not sos:
            st.info("No portal-linked sales orders.")
        for so in sos:
            with st.container(border=True):
                st.markdown(f"### {so['document_no']}")
                st.write(f"**Party:** {so.get('customer_name')}")
                st.write(f"**Amount:** Rs. {float(so.get('total') or 0):,.2f}")
                st.caption(f"Channel: {so.get('source_channel')}")
                if st.button("Open in Sales Orders", key=f"so_{so['id']}", use_container_width=True):
                    from erp_ui.nav import request_nav
                    request_nav("Sales", "Sales Orders")
