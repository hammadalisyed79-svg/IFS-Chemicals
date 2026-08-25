"""Compact BI KPI strip for CEO home — shared with Business Overview data."""

from __future__ import annotations

import streamlit as st

from application import data_gateway as db
from erp_ui.helpers import fmt_money
from erp_ui.nav import can_view_screen, go_screen
from erp_ui.theme import BLUE, RED


def render_home_kpi_strip(nav: dict, user: dict) -> None:
    """Top-of-home business pulse — same stats as Business Overview, compact row."""
    if not can_view_screen(user, "Business Overview"):
        return
    try:
        stats = db.get_dashboard_stats()
    except Exception as exc:
        st.caption(f"Business KPIs unavailable: {exc}")
        return

    mtd_s = float(stats.get("mtd_sales") or 0)
    mtd_p = float(stats.get("mtd_purchases") or 0)
    pending = stats.get("pending_breakdown") or {}
    approvals = int(pending.get("sales_approval", 0)) + int(pending.get("purchase_approval", 0))

    kpis = [
        ("Today Sales", fmt_money(stats.get("today_sales", 0)), BLUE, "📈"),
        ("Today Purchases", fmt_money(stats.get("today_purchases", 0)), RED, "📦"),
        ("Cash + Bank", fmt_money(stats.get("liquid_balance", 0)), BLUE, "💰"),
        ("Receivables", fmt_money(stats.get("receivables", 0)), RED, "📥"),
        ("Payables", fmt_money(stats.get("payables", 0)), BLUE, "📤"),
        ("Pending Approvals", str(approvals), RED if approvals else BLUE, "✓"),
    ]

    head, btn = st.columns([5, 1])
    with head:
        st.markdown('<p class="erp-desk-section">Business Pulse</p>', unsafe_allow_html=True)
    with btn:
        if st.button("Full BI", key="desk_bi_full", use_container_width=True, help="Open Business Overview"):
            if "Overview" in nav and "Business Overview" in nav.get("Overview", []):
                go_screen("Overview", "Business Overview")

    cols = st.columns(len(kpis))
    for col, (title, value, accent, icon) in zip(cols, kpis):
        with col:
            st.markdown(
                f"""
                <div class="dash-kpi dash-kpi-compact" style="border-left-color:{accent};">
                    <div class="dash-kpi-title">{icon} {title}</div>
                    <div class="dash-kpi-value">{value}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.caption(
        f"MTD sales **{fmt_money(mtd_s)}** · purchases **{fmt_money(mtd_p)}** · "
        f"net **{fmt_money(mtd_s - mtd_p)}**"
    )
