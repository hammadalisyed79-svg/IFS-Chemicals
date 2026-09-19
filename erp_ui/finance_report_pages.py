"""Finance report pages — extracted from app.py."""

from datetime import date

import pandas as pd
import streamlit as st
from application import data_gateway as db
from erp_ui import helpers as hlp
from erp_ui import form_flow as ff


def export_df(df, name, title=None, period="", filters=None, summary=None):
    if df is None or getattr(df, "empty", True):
        return
    from erp_ui.report_print import report_toolbar
    from erp_ui.report_profiles import report_layout, _report_profile_key
    lbl = title or name.replace("_", " ").title()
    layout_key = _report_profile_key(lbl) or lbl
    report_toolbar(
        df, lbl, name,
        period=period or "",
        filters=filters,
        summary=summary,
        key_prefix=f"ex_{name}",
        layout=report_layout(layout_key),
    )


def page_zero_movement_accounts():
    """Accounts with no debit, no credit, or neither in the selected period."""
    from erp_ui.helpers import render_dataframe_html_table

    hlp.std_page_header(
        "Zero Movement Accounts",
        subtitle="Accounts with no debit, no credit, or no activity in the selected period",
        status="register",
        status_kind="shell",
    )
    st.caption(
        "**Debit** = no period debits (credits may exist). "
        "**Credit** = no period credits (debits may exist). "
        "**Both** = no debit and no credit (zero movement, including accounts with no GL lines)."
    )

    c1, c2, c3 = st.columns(3)
    fd = c1.date_input("From", value=date(date.today().year, 1, 1), key="zna_from")
    td = c2.date_input("To", value=date.today(), key="zna_to")
    mode_label = c3.selectbox(
        "Filter",
        ["Debit", "Credit", "Both"],
        index=2,
        key="zna_mode",
        help="Debit: no debits · Credit: no credits · Both: no activity either side",
    )
    mode_map = {"Debit": "debit", "Credit": "credit", "Both": "both"}
    mode = mode_map.get(mode_label, "both")

    o1, o2 = st.columns(2)
    include_inactive = o1.checkbox("Include inactive accounts", value=False, key="zna_inactive")
    run = o2.button("Run report", type="primary", key="zna_run")

    if run:
        st.session_state["zna_last"] = {
            "fd": str(fd),
            "td": str(td),
            "mode": mode,
            "mode_label": mode_label,
            "include_inactive": include_inactive,
        }

    last = st.session_state.get("zna_last")
    if not last:
        st.info("Set From / To and Filter (Debit / Credit / Both), then click **Run report**.")
        return

    rows = db.get_accounts_no_activity(
        last["fd"],
        last["td"],
        mode=last["mode"],
        include_inactive=last.get("include_inactive", False),
    )
    if not rows:
        st.info(
            f"No accounts match **{last['mode_label']}** for {last['fd']} to {last['td']}."
        )
        return

    df = pd.DataFrame(rows)
    show_cols = [
        c for c in ("code", "name", "group_type", "group_name", "period_debit", "period_credit")
        if c in df.columns
    ]
    df = df[show_cols]

    k1, k2, k3 = st.columns(3, gap="small")
    k1.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Accounts</p>"
        f"<p class='txn-kpi-val'>{len(df):,}</p></div>",
        unsafe_allow_html=True,
    )
    k2.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Filter</p>"
        f"<p class='txn-kpi-val'>{last['mode_label']}</p></div>",
        unsafe_allow_html=True,
    )
    k3.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Period</p>"
        f"<p class='txn-kpi-val' style='font-size:0.95rem'>{last['fd']} → {last['td']}</p></div>",
        unsafe_allow_html=True,
    )

    render_dataframe_html_table(df)
    export_df(
        df,
        "zero_movement_accounts",
        f"Zero Movement Accounts — {last['mode_label']}",
        period=f"{last['fd']} to {last['td']}",
        filters={"Filter": last["mode_label"]},
    )


def page_profit_loss():
    hlp.std_page_header("Profit & Loss Report", status="posted", status_kind="shell")
    c1, c2 = st.columns(2)
    fd = c1.date_input("From", value=date(date.today().year, 1, 1), key="pl_from")
    td = c2.date_input("To", value=date.today(), key="pl_to")
    pl = db.get_profit_loss(str(fd), str(td))

    k1, k2, k3, k4 = st.columns(4, gap="small")
    k1.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Net Sales</p>"
        f"<p class='txn-kpi-val'>{hlp.fmt_money(pl['net_sales'])}</p></div>",
        unsafe_allow_html=True,
    )
    k2.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Net Purchases</p>"
        f"<p class='txn-kpi-val'>{hlp.fmt_money(pl['net_purchases'])}</p></div>",
        unsafe_allow_html=True,
    )
    k3.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Gross Profit</p>"
        f"<p class='txn-kpi-val'>{hlp.fmt_money(pl['gross_profit'])}</p></div>",
        unsafe_allow_html=True,
    )
    net_cls = "inv-badge-approved" if pl["net_profit"] >= 0 else "inv-badge-rejected"
    k4.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Net Profit</p>"
        f"<p class='txn-kpi-val'>{hlp.fmt_money(pl['net_profit'])}</p>"
        f"<p><span class='inv-badge {net_cls}'>"
        f"{'Profit' if pl['net_profit'] >= 0 else 'Loss'}</span></p></div>",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.markdown("**Income**")
        st.write(f"Gross Sales: **{hlp.fmt_money(pl['gross_sales'])}**")
        st.write(f"Less: Sale Returns: **({hlp.fmt_money(pl['sale_returns'])})**")
        st.write(f"**Net Sales: {hlp.fmt_money(pl['net_sales'])}**")
        st.markdown("**Cost of Goods**")
        st.write(f"Gross Purchases: **{hlp.fmt_money(pl['gross_purchases'])}**")
        st.write(f"Less: Purchase Returns: **({hlp.fmt_money(pl['purchase_returns'])})**")
        st.write(f"**Net Purchases: {hlp.fmt_money(pl['net_purchases'])}**")
        st.write(f"Posted inventory COGS (GL 5000): **{hlp.fmt_money(pl.get('cogs_posted', 0))}**")
        basis = pl.get("cogs_basis") or "gl_5000"
        cov = pl.get("cogs_coverage_pct")
        with_n = pl.get("cogs_invoices_with")
        tot_n = pl.get("cogs_invoices_total")
        if basis == "net_purchases_proxy":
            st.warning(
                f"Inventory COGS is posted on only {with_n}/{tot_n} sales invoices "
                f"({cov}%). P&L **Cost of Goods** is using **net purchases** as a temporary proxy."
            )
        else:
            st.caption(
                f"COGS basis: GL account 5000 · coverage {with_n}/{tot_n} invoices ({cov}%)."
            )
        st.write(f"**Cost of Goods (P&L): {hlp.fmt_money(pl['cogs'])}**")
        st.markdown("**Operating**")
        st.write(f"Operating Expenses: **{hlp.fmt_money(pl['operating_expenses'])}**")
    export_df(pd.DataFrame([pl]), "profit_loss", f"Profit & Loss {fd} to {td}")

