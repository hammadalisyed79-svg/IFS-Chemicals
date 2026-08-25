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
        st.markdown("**Operating**")
        st.write(f"Operating Expenses: **{hlp.fmt_money(pl['operating_expenses'])}**")
    export_df(pd.DataFrame([pl]), "profit_loss", f"Profit & Loss {fd} to {td}")

