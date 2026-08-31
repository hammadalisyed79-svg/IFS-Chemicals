"""Executive / admin dashboard — operational intelligence for IFS Chemicals ERP."""

from datetime import datetime
import pandas as pd
import streamlit as st
from application import data_gateway as db
from erp_ui.helpers import fmt_money, std_page_header, section_header, sticky_page_tabs, render_dataframe_html_table
from erp_ui.theme import BLUE, RED
from erp_ui.nav import (
    can_view_screen,
    filtered_nav_groups,
    render_apps_home,
    render_module_launcher,
    request_nav,
)


def _kpi_card(title, value, subtitle="", accent=BLUE, icon=""):
    st.markdown(
        f"""
        <div class="dash-kpi" style="border-left-color:{accent};">
            <div class="dash-kpi-title">{icon} {title}</div>
            <div class="dash-kpi-value">{value}</div>
            <div class="dash-kpi-sub">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _severity_badge(sev):
    colors = {"high": RED, "medium": RED, "low": BLUE}
    return colors.get(sev, BLUE)


def _can(user, screen):
    return can_view_screen(user, screen)


def page_admin_dashboard():
    """Odoo-style home: module apps or screen picker inside a module."""
    user = st.session_state.get("user") or {}
    company = db.get_setting("company_name", "IFS Chemicals")
    nav = filtered_nav_groups(user)
    if not nav:
        st.error("No modules available for your role.")
        return

    launcher_group = st.session_state.get("launcher_group")
    if launcher_group and launcher_group in nav:
        render_module_launcher(launcher_group, nav[launcher_group])
        return

    render_apps_home(nav, company)


def page_business_overview():
    """KPI dashboard — charts, alerts, and quick actions."""
    user = st.session_state.get("user") or {}
    company = db.get_setting("company_name", "IFS Chemicals")
    is_admin = user.get("role") == "admin"

    std_page_header(
        "Business Overview",
        subtitle=f"{company} — live business overview as of {datetime.now().strftime('%d %b %Y, %H:%M')}",
    )

    refresh = st.button("Refresh Dashboard", type="secondary", key="dash_refresh")
    if refresh:
        st.rerun()

    try:
        stats = db.get_dashboard_stats()
    except Exception as exc:
        st.error(f"Could not load dashboard data: {exc}")
        return

    # --- Row 1: Today's performance ---
    section_header("Today's Performance")
    r1 = st.columns(4)
    with r1[0]:
        _kpi_card("Today Sales", fmt_money(stats.get("today_sales", 0)), "Approved invoices dated today", BLUE, "📈")
    with r1[1]:
        _kpi_card("Today Purchases", fmt_money(stats.get("today_purchases", 0)), "Approved bills dated today", RED, "📦")
    with r1[2]:
        mtd_s = stats.get("mtd_sales", 0)
        mtd_p = stats.get("mtd_purchases", 0)
        draft_note = ""
        d_s = float(stats.get("mtd_sales_draft") or 0)
        d_p = float(stats.get("mtd_purchases_draft") or 0)
        if d_s > 0.005 or d_p > 0.005:
            draft_note = f" · drafts excl. S {fmt_money(d_s)} / P {fmt_money(d_p)}"
        _kpi_card(
            "MTD Sales",
            fmt_money(mtd_s),
            f"Purchases {fmt_money(mtd_p)} (approved){draft_note}",
            BLUE,
            "📊",
        )
    with r1[3]:
        net = float(mtd_s or 0) - float(mtd_p or 0)
        _kpi_card("MTD Net (Sales − Purch.)", fmt_money(net), "Approved invoices · before expenses", RED, "💹")

    # --- Row 2: Liquidity & working capital ---
    section_header("Liquidity & Working Capital")
    r2 = st.columns(5)
    with r2[0]:
        _kpi_card("Cash in Hand", fmt_money(stats.get("cash_balance", 0)), "Including opening", BLUE, "💵")
    with r2[1]:
        _kpi_card("Bank Balance", fmt_money(stats.get("bank_balance", 0)), "All bank accounts", RED, "🏦")
    with r2[2]:
        _kpi_card("Total Liquid", fmt_money(stats.get("liquid_balance", 0)), "Cash + Bank", BLUE, "💰")
    with r2[3]:
        _kpi_card("Receivables", fmt_money(stats.get("receivables", 0)), f"{stats.get('customers', 0)} active customers", RED, "📥")
    with r2[4]:
        _kpi_card("Payables", fmt_money(stats.get("payables", 0)), f"{stats.get('suppliers', 0)} active suppliers", BLUE, "📤")

    # --- Row 3: Operations ---
    section_header("Operations & Inventory")
    r3 = st.columns(5)
    att = stats.get("attendance_today") or {}
    with r3[0]:
        _kpi_card("Stock Value", fmt_money(stats.get("stock_value", 0)), f"{stats.get('items', 0)} active SKUs", BLUE, "🏭")
    with r3[1]:
        low_accent = RED if stats.get("low_stock_count") else BLUE
        _kpi_card("Low Stock Items", str(stats.get("low_stock_count", 0)), "At/below reorder level", low_accent, "⚠️")
    with r3[2]:
        _kpi_card("Active Production", str(stats.get("pending_breakdown", {}).get("production_active", 0)), "Draft / issued orders", RED, "⚙️")
    with r3[3]:
        present = att.get("present", 0)
        _kpi_card("Attendance Today", str(present), f"Absent {att.get('absent', 0)} · Leave {att.get('leave', 0)}", BLUE, "👥")
    with r3[4]:
        _kpi_card("Weigh / Gate Today", f"{stats.get('today_weight_slips', 0)} / {stats.get('today_gate_passes', 0)}", "Slips / passes", RED, "⚖️")

    # --- Quick launch ---
    section_header("Quick Launch")
    ql = st.columns(6)
    actions = [
        ("Sales Invoice", "Sales", "Sales Invoices", _can(user, "Sales Invoices")),
        ("Purchase Bill", "Purchases", "Purchase Invoices", _can(user, "Purchase Invoices")),
        ("Customer Receipt", "Finance", "Customer Receipt", _can(user, "Customer Receipt")),
        ("Gate Pass", "Gate Pass", "Gate Pass Entry", _can(user, "Gate Pass Entry")),
        ("Payroll", "HR", "Payroll", _can(user, "Payroll")),
        ("Reports", "Reports", "Reports Center", _can(user, "Reports Center")),
    ]
    for col, (label, grp, scr, allowed) in zip(ql, actions):
        with col:
            if allowed:
                if st.button(label, use_container_width=True, key=f"ql_{scr}"):
                    request_nav(grp, scr)
            else:
                st.button(label, use_container_width=True, disabled=True, key=f"ql_{scr}")

    st.divider()

    # --- Charts + pending ---
    left, right = st.columns([1.4, 1])

    with left:
        st.subheader("Sales vs Purchases — Last 6 Months")
        trend = stats.get("monthly_trend") or []
        if trend:
            chart_df = pd.DataFrame(trend).set_index("month")[["sales", "purchases"]]
            st.bar_chart(chart_df, use_container_width=True, height=320)
        else:
            st.info("No transaction history yet.")

        st.subheader("Recent Activity")
        act_tab = sticky_page_tabs(["Recent Sales", "Recent Purchases"], "dash_recent_tab")
        if act_tab == "Recent Sales":
            rs = stats.get("recent_sales") or []
            if rs:
                df = pd.DataFrame(rs).rename(columns={
                    "invoice_no": "Invoice", "sale_date": "Date", "customer_name": "Customer",
                    "total": "Amount", "status": "Status",
                })
                render_dataframe_html_table(df)
            else:
                st.caption("No sales recorded.")
        elif act_tab == "Recent Purchases":
            rp = stats.get("recent_purchases") or []
            if rp:
                df = pd.DataFrame(rp).rename(columns={
                    "invoice_no": "Bill", "purchase_date": "Date", "supplier_name": "Supplier",
                    "total": "Amount", "status": "Status",
                })
                render_dataframe_html_table(df)
            else:
                st.caption("No purchases recorded.")

    with right:
        st.subheader("Pending Actions")
        pending = stats.get("pending_breakdown") or {}
        task_rows = [
            ("Sales approval", pending.get("sales_approval", 0), "Sales", "Sale Approval", "Sales Invoices"),
            ("Purchase approval", pending.get("purchase_approval", 0), "Purchases", "Purchase Approval", "Purchase Invoices"),
            ("Leave requests", pending.get("leave", 0), "HR", "Leave Management", "Leave Management"),
            ("Payroll (draft)", pending.get("payroll_draft", 0), "HR", "Payroll", "Payroll"),
            ("Employee advances", pending.get("advances", 0), "HR", "Employee Advances", "Employee Advances"),
            ("Open dispatch gate passes", pending.get("gate_pass_open", 0), "Gate Pass", "Gate Pass Entry", "Gate Pass Entry"),
            ("Draft deliveries", pending.get("delivery_draft", 0), "Sales", "Delivery Notes", "Delivery Notes"),
            ("Open sales orders", pending.get("sales_orders_open", 0), "Sales", "Sales Orders", "Sales Orders"),
            ("Draft journals", pending.get("journal_draft", 0), "Finance", "Journal Voucher", "Journal Voucher"),
        ]
        any_pending = False
        for label, count, grp, scr, _ in task_rows:
            if count:
                any_pending = True
                c1, c2 = st.columns([3, 1])
                c1.markdown(f"**{label}** — {count}")
                if c2.button("Open", key=f"pend_{scr}", use_container_width=True):
                    request_nav(grp, scr)
        if not any_pending:
            st.success("All clear — no pending workflow items.")

        st.subheader("System Alerts")
        alerts = stats.get("alerts") or []
        if alerts:
            for a in alerts:
                color = _severity_badge(a.get("severity", "low"))
                st.markdown(
                    f'<div class="dash-alert" style="border-left-color:{color};">'
                    f'<strong>{a.get("module", "")}</strong> — {a.get("message", "")}</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.success("No critical alerts.")

        fy = stats.get("fiscal_year")
        if fy:
            st.caption(f"Active fiscal year: **{fy.get('fy_code', '')}** ({fy.get('start_date', '')} → {fy.get('end_date', '')})")

        if is_admin:
            st.subheader("Master Snapshot")
            m1, m2 = st.columns(2)
            m1.metric("Employees", stats.get("employees", 0))
            m2.metric("Lifetime Sales", fmt_money(stats.get("sales_total", 0)))

    # --- Bottom panels ---
    st.divider()
    b1, b2, b3 = st.columns(3)

    with b1:
        st.subheader("Top Receivables")
        st.caption("Dual-role parties (same code) shown **net** — same as combined ledger.")
        tr = stats.get("top_receivables") or []
        if tr:
            df = pd.DataFrame(tr).rename(columns={"code": "Code", "name": "Customer", "balance": "Balance"})
            render_dataframe_html_table(df)
        else:
            st.caption("No outstanding receivables.")

    with b2:
        st.subheader("Top Payables")
        st.caption("Dual-role parties (same code) shown **net** — same as combined ledger.")
        tp = stats.get("top_payables") or []
        if tp:
            df = pd.DataFrame(tp).rename(columns={"code": "Code", "name": "Supplier", "balance": "Balance"})
            render_dataframe_html_table(df)
        else:
            st.caption("No outstanding payables.")

    with b3:
        st.subheader("Low Stock Alerts")
        low = stats.get("low_stock") or []
        if low:
            df = pd.DataFrame(low).rename(columns={
                "code": "Code", "name": "Product", "stock_qty": "Qty",
                "reorder_level": "Reorder", "unit": "Unit",
            })
            render_dataframe_html_table(df)
            if _can(user, "Stock Report"):
                if st.button("Open Stock Report", key="dash_stock_rpt"):
                    request_nav("Reports", "Stock Report")
        else:
            st.success("Stock levels healthy.")
