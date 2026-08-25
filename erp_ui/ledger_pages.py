"""Party / account ledger pages — extracted from app.py."""

from datetime import date

import pandas as pd
import streamlit as st
from application import data_gateway as db
from erp_ui import helpers as hlp
from erp_ui import form_flow as ff


def customer_options(active_only=True):
    rows = db.get_customers(active_only=active_only)
    return {f"{r['code']} - {r['name']}": r["id"] for r in rows}


def supplier_options(active_only=True):
    rows = db.get_suppliers(active_only=active_only)
    return {f"{r['code']} - {r['name']}": r["id"] for r in rows}


def account_options(active_only=True):
    rows = db.get_accounts(active_only=active_only)
    return {f"{r['code']} - {r['name']}": r["id"] for r in rows}


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


def _attach_ledger_party(df, party, kind):
    """Store party block for professional ledger print."""
    if df is None:
        return df
    try:
        p = party or {}
        df.attrs["ledger_party"] = {
            "id": p.get("id"),
            "customer_id": p.get("id") if kind == "customer" else None,
            "supplier_id": p.get("id") if kind == "supplier" else None,
            "code": p.get("code") or "",
            "name": p.get("name") or "",
            "phone": p.get("phone") or "",
            "mobile": p.get("mobile") or "",
            "dispatch_phone": p.get("dispatch_phone") or "",
            "accounts_phone": p.get("accounts_phone") or "",
            "owner_phone": p.get("owner_phone") or "",
            "contact_person": p.get("contact_person") or "",
            "address": p.get("address") or p.get("city") or "",
            "kind": kind,
        }
        if p.get("ledger_summary"):
            df.attrs["ledger_summary"] = party["ledger_summary"]
    except Exception:
        pass
    return df


def page_customer_ledger():
    from erp_ui.ledger_shared import render_party_ledger

    render_party_ledger(
        "customer",
        page_title="Customer Ledger",
        party_select_key="cl_cust",
        from_key="cl_from",
        to_key="cl_to",
        tab_state_key="cl_ledger_tab",
        split_books_key="cl_split_books",
        export_summary_name="customer_ledger",
        export_detailed_name="customer_ledger_detailed",
        export_summary_title="Customer Ledger",
        export_detailed_title="Customer Ledger (Detailed)",
        attach_ledger_party_fn=_attach_ledger_party,
        export_df_fn=export_df,
    )


def page_supplier_ledger():
    from erp_ui.ledger_shared import render_party_ledger

    render_party_ledger(
        "supplier",
        page_title="Supplier Ledger",
        party_select_key="sl_sup",
        from_key="sl_from",
        to_key="sl_to",
        tab_state_key="sl_ledger_tab",
        split_books_key="sl_split_books",
        export_summary_name="supplier_ledger",
        export_detailed_name="supplier_ledger_detailed",
        export_summary_title="Supplier Ledger",
        export_detailed_title="Supplier Ledger (Detailed)",
        attach_ledger_party_fn=_attach_ledger_party,
        export_df_fn=export_df,
    )


def page_account_ledger():
    from erp_ui.helpers import render_ledger_summary_table

    hlp.std_page_header("Account Ledger", status="posted", status_kind="shell")
    st.caption(
        "Opening, period debit/credit, and closing for any chart account "
        "(income, expense, tax, cash, bank, and other GL heads)."
    )
    if not db.get_accounts(active_only=False):
        st.info("Add accounts in Chart of Accounts first.")
        return
    c1, c2, c3 = st.columns(3)
    with c1:
        acc_id = hlp.account_select("al_acc")
    fd = c2.date_input("From", value=None, key="al_from")
    td = c3.date_input("To", value=None, key="al_to")
    if not acc_id:
        st.info("Select an account.")
        return
    fd_s = str(fd) if fd else None
    td_s = str(td) if td else None
    account, entries = db.get_account_ledger(acc_id, fd_s, td_s)
    if not account:
        st.warning("Account not found.")
        return
    summary = (account or {}).get("ledger_summary") or {}
    opening = float(summary.get("opening") or 0)
    pdeb = float(summary.get("period_debit") or 0)
    pcred = float(summary.get("period_credit") or 0)
    closing = float(summary.get("closing") if summary else (
        entries[-1]["balance"] if entries else account.get("balance") or 0
    ))
    type_lbl = (account.get("account_type") or "").title()
    st.subheader(f"{account['code']} — {account['name']}")
    if type_lbl:
        st.caption(f"Type: {type_lbl}")
    hlp.render_ledger_kpi_strip(opening, pdeb, pcred, closing, signed_open_close=False)
    if entries:
        df = pd.DataFrame(entries)[["date", "ref", "description", "debit", "credit", "balance"]]
        df.columns = ["Date", "Ref", "Description", "Debit", "Credit", "Balance"]
        render_ledger_summary_table(entries)
        export_df(df, "account_ledger", f"Account Ledger — {account['code']} {account['name']}")
    else:
        st.info("No ledger entries.")

