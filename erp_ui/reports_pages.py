"""Reports & Printing Center — professional hub for all business reports."""

from __future__ import annotations

from datetime import date, timedelta
import pandas as pd
import streamlit as st
from application import data_gateway as db
import db_reports as rpt_db
from erp_ui.helpers import std_page_header, smart_select, fmt_money
from erp_ui.report_print import report_toolbar, itemwise_detail_toolbar, prettify_columns, daily_activity_groups
from erp_ui.report_profiles import (
    prepare_report_dataframe,
    profit_loss_dataframe,
    report_layout,
    summary_keys_for_report,
)
from erp_ui.document_print import PRINTERS, document_print_toolbar
from erp_ui.report_grouping import report_group_filter_row
from db_groups import group_label

# ---------------------------------------------------------------------------
# Report catalog (title must match _run_report keys)
# ---------------------------------------------------------------------------

def _r(title: str, desc: str, *, date=True, customer=False, supplier=False, product=False,
       warehouse=False, employee=False, account=False, payroll_period=False, production=False,
       party_required=None,
       customer_group=False, supplier_group=False, product_group=False,
       account_group=False, group_view=False, party_group_view=False):
    return {
        "title": title,
        "description": desc,
        "filters": {
            "date": date,
            "customer": customer,
            "supplier": supplier,
            "product": product,
            "warehouse": warehouse,
            "employee": employee,
            "account": account,
            "payroll_period": payroll_period,
            "production": production,
            "customer_group": customer_group,
            "supplier_group": supplier_group,
            "product_group": product_group,
            "account_group": account_group,
            "group_view": group_view,
            "party_group_view": party_group_view,
        },
        "party_required": party_required,  # "customer" | "supplier" | "employee" | "account" | "product" | "production"
    }


REPORT_CATALOG = {
    "Sales": [
        _r("Sales Register", "All sales invoices in date range."),
        _r("Sales Invoice Register", "Detailed sales lines with customer and product filters.",
           customer_group=True, product_group=True),
        _r("Customer Ledger", "Customer account summary (one line per voucher).", customer=True, party_required="customer"),
        _r(
            "Customer Ledger (Detailed)",
            "Customer ledger: invoice lines, qty/rate/amount, receipts (FMYE layout).",
            customer=True,
            party_required="customer",
        ),
        _r("Customer Outstanding", "Balances due from customers.", date=False,
           customer_group=True, party_group_view=True),
        _r(
            "Customer Due Aging",
            "Net customer balance due by age (dual-role parties netted like Outstanding): "
            "0-15, 16-30, 31-45, 46-60, 61-90, and Over 90 days.",
            customer=True, customer_group=True,
        ),
        _r("Product Sales Analysis", "Qty and value sold by product.",
           product_group=True, party_group_view=True),
        _r(
            "Item Wise Sale (Detail)",
            "Each sale line grouped by item: date, invoice, customer, city, qty, rate, amount (FMYE layout).",
            customer=True, product=True, customer_group=True, product_group=True,
        ),
        _r("Tax Sales Report", "Sales tax summary for the period."),
        _r("Sales Returns", "Sale return documents.", customer_group=True),
        _r("Pending Sale Invoices", "Invoices awaiting approval.", date=False),
        _r("Approved Sale Invoices", "Approved sales ready to post/dispatch.", date=False),
        _r("Sale Weight Variance Report", "Standard vs actual weight on sales.", customer=True,
           customer_group=True),
    ],
    "Purchase": [
        _r("Purchase Register", "All purchase invoices in date range."),
        _r("Purchase Invoice Register", "Purchase lines with supplier and product filters.",
           supplier_group=True, product_group=True),
        _r("Supplier Ledger", "Supplier account summary (one line per voucher).", supplier=True, party_required="supplier"),
        _r(
            "Supplier Ledger (Detailed)",
            "Supplier ledger: invoice lines, qty/rate/amount, payments (FMYE layout).",
            supplier=True,
            party_required="supplier",
        ),
        _r("Supplier Outstanding", "Balances due to suppliers.", date=False,
           supplier_group=True, party_group_view=True),
        _r("Purchase Analysis", "Purchases by product and supplier.",
           supplier_group=True, product_group=True, party_group_view=True),
        _r(
            "Item Wise Purchase (Detail)",
            "Each purchase line grouped by item: date, invoice, supplier, city, qty, rate, amount (FMYE layout).",
            supplier=True, product=True, supplier_group=True, product_group=True,
        ),
        _r("Tax Purchase Report", "Purchase tax summary."),
        _r("Purchase Returns", "Purchase return documents.", supplier_group=True),
        _r("GRN Register", "Goods receipt notes."),
        _r("Pending Purchase Invoices", "Purchases awaiting approval.", date=False),
        _r("Approved Purchase Invoices", "Approved purchases.", date=False),
        _r("Purchase Weight Variance Report", "Standard vs actual weight on purchases.", supplier=True,
           supplier_group=True),
    ],
    "Inventory": [
        _r("Stock Position", "Current qty and value for all items.", date=False,
           product_group=True, party_group_view=True),
        _r("Stock Ledger", "In/out movements for one product.", product=True, party_required="product",
           product_group=True),
        _r("Stock Valuation", "Stock value by item.", date=False,
           product_group=True, party_group_view=True),
        _r("Warehouse Stock", "Qty by warehouse.", warehouse=True, date=False),
        _r("Batch Stock", "Batch-wise stock balances.", date=False),
        _r("Reorder Report", "Items at or below reorder level.", date=False),
        _r("Negative Stock Report", "Items with qty below zero.", date=False),
    ],
    "Production": [
        _r("BOM Cost Sheet", "Formula lines and material costs.", date=False),
        _r("Production Register", "Production orders and output."),
        _r("Production Variance", "Planned vs actual production qty."),
        _r("Raw Material Consumption", "RM issued to production."),
        _r(
            "Production Consumption",
            "RM consumption by production number, or print the day register for a selected date.",
            production=True,
        ),
        _r("Finished Goods Report", "FG output by period."),
    ],
    "Finance": [
        _r("Cash Book", "Cash receipts and payments."),
        _r("Bank Book", "Bank receipts and payments."),
        _r(
            "Account Ledger",
            "Single GL account statement with opening, debit, credit, and closing (income, expense, tax, etc.).",
            account=True,
            party_required="account",
        ),
        _r("General Ledger", "GL entries by account and period (all accounts, or pick one).", account=True,
           account_group=True),
        _r("Trial Balance", "Debit/credit balances by account.",
           account_group=True, group_view=True),
        _r("Profit & Loss", "Income and expense summary.", date=True),
        _r("Balance Sheet", "Assets, liabilities, equity — use period end date as “as at”.", date=True,
           account_group=True, group_view=True),
        _r("Journal Register", "Manual journal vouchers."),
        _r(
            "Daily Activity Report",
            "One-day financial register, heading-wise by module and voucher type "
            "(sales, purchases, cash/bank, journals) with section subtotals.",
            date=True,
        ),
    ],
    "HR & Payroll": [
        _r("Employee List", "Active employees master.", date=False),
        _r("Employee Ledger", "Advances, loans, payroll per employee.", employee=True, party_required="employee"),
        _r("Attendance Report", "Daily attendance summary.", employee=True),
        _r("Overtime Report", "Overtime hours and amounts."),
        _r("Payroll Register", "Payroll runs and totals."),
        _r("Leave Report", "Leave applications and balances."),
        _r("Department Salary Cost", "Salary cost by department for one payroll.", payroll_period=True, date=False),
        _r("Outstanding Advances", "Employee advances not fully recovered.", date=False),
        _r("Outstanding Loans", "Employee loans outstanding.", date=False),
    ],
    "Weight Scale": [
        _r("Daily Weight Report", "Weighbridge slips for the period.", customer=True, supplier=True, product=True,
           customer_group=True, supplier_group=True, product_group=True),
        _r("Vehicle Report", "Weights grouped by vehicle."),
        _r("Customer Weight Report", "Weights by customer.", customer_group=True),
        _r("Supplier Weight Report", "Weights by supplier.", supplier_group=True),
        _r("Weight Variance Report", "Weight differences vs standard."),
    ],
    "Gate Pass": [
        _r("Inward Register", "Material inward gate passes."),
        _r("Outward Register", "Material outward gate passes."),
        _r("Gate Pass Register", "All gate passes in period."),
        _r("Distributor Orders", "Portal orders from distributors.", customer_group=True),
        _r("Distributor Outstanding", "Balances for portal-enabled customers.", date=False,
           customer_group=True),
        _r("Portal Activity Log", "Portal order activity by date."),
    ],
}

ITEMWISE_DETAIL_REPORTS = frozenset({
    "Item Wise Sale (Detail)",
    "Item Wise Purchase (Detail)",
})

POPULAR_REPORTS = [
    "Daily Activity Report",
    "Item Wise Sale (Detail)",
    "Item Wise Purchase (Detail)",
    "Customer Outstanding",
    "Customer Due Aging",
    "Supplier Outstanding",
    "Customer Ledger (Detailed)",
    "Supplier Ledger (Detailed)",
    "Stock Position",
    "Stock Ledger",
    "Customer Ledger",
    "Supplier Ledger",
    "Trial Balance",
    "Profit & Loss",
    "Payroll Register",
    "Account Ledger",
    "General Ledger",
]

_REPORT_BY_TITLE = {
    item["title"]: {**item, "category": cat}
    for cat, items in REPORT_CATALOG.items()
    for item in items
}
# Favorites / recent may still store the previous title
if "Production Consumption" in _REPORT_BY_TITLE:
    _REPORT_BY_TITLE["Production Consumption (by Order)"] = {
        **_REPORT_BY_TITLE["Production Consumption"],
        "title": "Production Consumption",
    }


def _flat_report_titles():
    return [item["title"] for items in REPORT_CATALOG.values() for item in items]


def _init_report_state():
    if "rpt_category" not in st.session_state:
        st.session_state["rpt_category"] = "Sales"
    if "rpt_report" not in st.session_state:
        st.session_state["rpt_report"] = REPORT_CATALOG["Sales"][0]["title"]
    if st.session_state.get("rpt_report") == "Production Consumption (by Order)":
        st.session_state["rpt_report"] = "Production Consumption"
        st.session_state["rpt_category"] = "Production"
    today = date.today()
    st.session_state.setdefault("rpt_fd", today.replace(day=1))
    st.session_state.setdefault("rpt_td", today)


def _apply_pending_report_nav():
    """Apply popular/search navigation before report widgets render."""
    pending = st.session_state.pop("rpt_nav_to", None)
    if not pending:
        return
    if pending == "Production Consumption (by Order)":
        pending = "Production Consumption"
    if pending not in _REPORT_BY_TITLE:
        return
    st.session_state["rpt_report"] = pending
    st.session_state["rpt_category"] = _REPORT_BY_TITLE[pending]["category"]


def _set_period(start: date, end: date):
    st.session_state["rpt_fd"] = start
    st.session_state["rpt_td"] = end


def _period_preset_bar(key_prefix: str = "rpt"):
    today = date.today()
    with st.container(key="rpt_period_bar"):
        c0, c1, c2, c3, c4, c5 = st.columns(6)
        if c0.button("Today", key=f"{key_prefix}_p_today"):
            _set_period(today, today)
            st.rerun()
        if c1.button("This month", key=f"{key_prefix}_p_month"):
            _set_period(today.replace(day=1), today)
            st.rerun()
        if c2.button("Last month", key=f"{key_prefix}_p_lmonth"):
            first = today.replace(day=1)
            last_end = first - timedelta(days=1)
            _set_period(last_end.replace(day=1), last_end)
            st.rerun()
        if c3.button("This year", key=f"{key_prefix}_p_year"):
            _set_period(date(today.year, 1, 1), today)
            st.rerun()
        if c4.button("Last 30 days", key=f"{key_prefix}_p_30"):
            _set_period(today - timedelta(days=30), today)
            st.rerun()
        if c5.button("Clear results", key=f"{key_prefix}_p_clear"):
            st.session_state.pop("rpt_result", None)
            st.session_state.pop("rpt_meta", None)
            st.rerun()
    s1, s2, s3 = st.columns([1, 1, 3])
    if s1.button("Save period", key=f"{key_prefix}_save_period", help="Remember From/To for next visit"):
        st.session_state["rpt_saved_period"] = {
            "fd": st.session_state.get("rpt_fd"),
            "td": st.session_state.get("rpt_td"),
            "report": st.session_state.get("rpt_report"),
        }
        st.toast("Period preset saved.")
    if s2.button("Load saved", key=f"{key_prefix}_load_period", disabled="rpt_saved_period" not in st.session_state):
        saved = st.session_state.get("rpt_saved_period") or {}
        if saved.get("fd") is not None:
            st.session_state["rpt_fd"] = saved["fd"]
        if saved.get("td") is not None:
            st.session_state["rpt_td"] = saved["td"]
        if saved.get("report"):
            st.session_state["rpt_nav_to"] = saved["report"]
        st.rerun()
    saved = st.session_state.get("rpt_saved_period")
    if saved:
        s3.caption(
            f"Saved preset: **{saved.get('report') or 'current'}** "
            f"{saved.get('fd') or '…'} → {saved.get('td') or '…'}"
        )


def _report_search_matches(query: str) -> list[str]:
    q = (query or "").strip().lower()
    if not q:
        return []
    out = []
    for title in _flat_report_titles():
        meta = _REPORT_BY_TITLE[title]
        blob = f"{title} {meta['description']} {meta['category']}".lower()
        if q in blob or all(tok in blob for tok in q.split()):
            out.append(title)
    return out


def _render_filters(meta: dict, key: str = "rpt"):
    fcfg = meta["filters"]
    fd = td = None
    cid = sid = pid = wid = eid = aid = payroll_id = po_id = None
    include_linked = True
    cons_view = "order"

    if fcfg.get("date"):
        st.markdown("**Period**")
        if meta.get("title") == "Daily Activity Report":
            st.caption(
                "Set **From** and **To** to the same day. Lists **financial vouchers only**, "
                "grouped heading-wise by module and voucher type (with section subtotals)."
            )
        if meta.get("title") == "Customer Due Aging":
            st.caption(
                "**To** date is the as-of date for aging. Unpaid amounts are bucketed into "
                "0-15, 16-30, 31-45, 46-60, 61-90, and Over 90 days. "
                "Dual-role parties (same code as customer + supplier) use **net** receivable, "
                "same as Customer Outstanding."
            )
        title_early = meta.get("title") or ""
        cons_view = "order"
        if title_early in ("Production Consumption", "Production Consumption (by Order)"):
            cons_view = st.radio(
                "View",
                ["By production number", "Day register"],
                horizontal=True,
                key=f"{key}_prod_cons_view",
                help="Day register prints all RM consumption for the selected date.",
            )
            if cons_view.startswith("Day"):
                st.caption("Pick the register date, then Run report / Print.")
                reg_date = st.date_input("Register date", key=f"{key}_prod_cons_day")
                fd, td = reg_date, reg_date
            else:
                st.caption(
                    "Use the period to narrow production numbers, then select a "
                    "**production order** for its consumption note."
                )
                _period_preset_bar(key)
                c1, c2 = st.columns(2)
                fd = c1.date_input("From", key=f"{key}_fd")
                td = c2.date_input("To", key=f"{key}_td")
        else:
            _period_preset_bar(key)
            c1, c2 = st.columns(2)
            # Widget keys own session state — do not assign rpt_fd/rpt_td after instantiation.
            fd = c1.date_input("From", key=f"{key}_fd")
            td = c2.date_input("To", key=f"{key}_td")
    else:
        fd = str(date.today().replace(day=1))
        td = str(date.today())
        cons_view = "order"

    party_cols = []
    if fcfg.get("customer"):
        party_cols.append("customer")
    if fcfg.get("supplier"):
        party_cols.append("supplier")
    if fcfg.get("product"):
        party_cols.append("product")
    if fcfg.get("warehouse"):
        party_cols.append("warehouse")
    if fcfg.get("employee"):
        party_cols.append("employee")
    if fcfg.get("account"):
        party_cols.append("account")

    req = meta.get("party_required")
    if party_cols:
        st.markdown("**Filters**")
        with st.container(key="rpt_filter_party"):
            ncol = min(len(party_cols), 3)
            pcols = st.columns(ncol)
            pi = 0
            if "customer" in party_cols:
                with pcols[pi % ncol]:
                    _, cid, _ = smart_select(
                        "Customer", db.get_customers(), f"{key}_c", "id",
                        lambda r: f"{r['code']} - {r['name']}",
                        placeholder="Customer code or name…",
                        allow_all=req != "customer",
                        all_label="(All customers)",
                    )
                pi += 1
            if "supplier" in party_cols:
                with pcols[pi % ncol]:
                    _, sid, _ = smart_select(
                        "Supplier", db.get_suppliers(), f"{key}_s", "id",
                        lambda r: f"{r['code']} - {r['name']}",
                        placeholder="Supplier code or name…",
                        allow_all=req != "supplier",
                        all_label="(All suppliers)",
                    )
                pi += 1
            if "product" in party_cols:
                with pcols[pi % ncol]:
                    _, pid, _ = smart_select(
                        "Product", db.get_items(), f"{key}_p", "id",
                        lambda r: f"{r['code']} - {r['name']}",
                        placeholder="Product code or name…",
                        allow_all=req != "product",
                        all_label="(All products)",
                    )
                pi += 1
            if "warehouse" in party_cols:
                with pcols[pi % ncol]:
                    wh_opts = {f"{w['code']} - {w['name']}": w["id"] for w in db.get_warehouses()}
                    wh_lbl = st.selectbox("Warehouse", ["All"] + list(wh_opts.keys()), key=f"{key}_wh")
                    wid = wh_opts.get(wh_lbl) if wh_lbl != "All" else None
                pi += 1
            if "employee" in party_cols:
                with pcols[pi % ncol]:
                    _, eid, _ = smart_select(
                        "Employee", db.get_employees(active_only=False), f"{key}_e", "id",
                        lambda r: f"{r.get('code', '')} - {r.get('full_name', r.get('name', ''))}",
                        placeholder="Employee code or name…",
                    )
                pi += 1
            if "account" in party_cols:
                with pcols[pi % ncol]:
                    _, aid, _ = smart_select(
                        "Account", db.get_accounts(active_only=False), f"{key}_a", "id",
                        lambda r: f"{r['code']} - {r['name']}",
                        placeholder="Account code or name…",
                        allow_all=req != "account",
                        all_label="(All accounts)",
                    )
                pi += 1
        if req != "customer" and "customer" in party_cols:
            st.caption("Customer: choose **(All customers)** for every customer.")

    title = meta.get("title") or ""
    if title in ("Customer Ledger", "Customer Ledger (Detailed)") and cid:
        linked = db.find_linked_counterparty("customer", cid)
        if linked:
            st.success(
                f"Dual-role party — Customer + Supplier **{linked['code']} — {linked['name']}** "
                f"share one **combined ledger**."
            )
            split_books = st.checkbox(
                "Show customer book only (not combined)",
                value=False,
                key=f"{key}_split_link_c",
            )
            include_linked = not split_books
    elif title in ("Supplier Ledger", "Supplier Ledger (Detailed)") and sid:
        linked = db.find_linked_counterparty("supplier", sid)
        if linked:
            st.success(
                f"Dual-role party — Supplier + Customer **{linked['code']} — {linked['name']}** "
                f"share one **combined ledger**."
            )
            split_books = st.checkbox(
                "Show supplier book only (not combined)",
                value=False,
                key=f"{key}_split_link_s",
            )
            include_linked = not split_books

    if fcfg.get("production"):
        show_po = True
        rpt_title = meta.get("title") or ""
        if rpt_title in ("Production Consumption", "Production Consumption (by Order)"):
            show_po = not str(cons_view).startswith("Day")
        if show_po:
            st.markdown("**Production**")
            orders = rpt_db.list_production_orders_with_consumption(
                str(fd) if fcfg.get("date") else None,
                str(td) if fcfg.get("date") else None,
            )
            if not orders:
                st.warning("No production orders with material issues in this period.")
            else:
                _, po_id, _ = smart_select(
                    "Production No *",
                    orders,
                    f"{key}_po",
                    "id",
                    lambda r: (
                        f"{r.get('document_no')} — {r.get('batch_no') or '—'} — "
                        f"{r.get('product_name') or ''} — {r.get('order_date') or ''} "
                        f"({r.get('status') or '—'})"
                    ),
                    placeholder="Type PRO-… / batch / product…",
                    allow_all=False,
                    all_label="(Select production)",
                )

    if fcfg.get("payroll_period"):
        runs = db.get_payroll_runs()
        if not runs:
            st.warning("No payroll runs found.")
        else:
            opts = {
                f"{r['document_no']} — {r.get('payroll_month', '')}/{r.get('payroll_year', '')} [{r.get('status', '')}]": r["id"]
                for r in runs
            }
            sel = st.selectbox("Payroll period", list(opts.keys()), key=f"{key}_payroll")
            payroll_id = opts.get(sel)

    if req == "customer" and not cid:
        st.caption("Tip: select a **customer** for this report.")
    elif req == "supplier" and not sid:
        st.caption("Tip: select a **supplier** for this report.")
    elif req == "product" and not pid:
        st.caption("Tip: select a **product** for stock ledger.")
    elif req == "employee" and not eid:
        st.caption("Tip: select an **employee** for this report.")
    elif req == "account" and not aid:
        st.caption("Tip: select a **GL account** for Account Ledger.")
    elif (
        (meta.get("title") or "") in ("Production Consumption", "Production Consumption (by Order)")
        and not str(cons_view).startswith("Day")
        and not po_id
    ):
        st.caption("Tip: select a **production number** to view its consumption.")

    gf = report_group_filter_row(meta, key)
    gf = dict(gf or {})
    gf["include_linked"] = bool(include_linked)
    if (meta.get("title") or "") in ("Production Consumption", "Production Consumption (by Order)"):
        gf["consumption_view"] = "day" if str(cons_view).startswith("Day") else "order"
    return str(fd), str(td), cid, sid, pid, wid, eid, payroll_id, gf, aid, po_id


def _resolve_export_filters(cid, sid, pid, wid, eid, gf=None, aid=None, po_id=None) -> dict:
    """Human-readable filter labels for print/export (no raw IDs)."""
    f = {}
    if cid:
        row = next((c for c in db.get_customers(active_only=False) if c["id"] == cid), None)
        if row:
            f["Customer"] = f"{row.get('code', '')} — {row.get('name', '')}".strip(" —")
    if sid:
        row = next((s for s in db.get_suppliers(active_only=False) if s["id"] == sid), None)
        if row:
            f["Supplier"] = f"{row.get('code', '')} — {row.get('name', '')}".strip(" —")
    if pid:
        row = next((p for p in db.get_items() if p["id"] == pid), None)
        if row:
            f["Product"] = f"{row.get('code', '')} — {row.get('name', '')}".strip(" —")
    if wid:
        row = next((w for w in db.get_warehouses() if w["id"] == wid), None)
        if row:
            f["Warehouse"] = row.get("name", str(wid))
    if eid:
        row = next((e for e in db.get_employees(active_only=False) if e["id"] == eid), None)
        if row:
            f["Employee"] = row.get("full_name") or row.get("name", str(eid))
    if aid:
        row = next((a for a in db.get_accounts(active_only=False) if a["id"] == aid), None)
        if row:
            f["Account"] = f"{row.get('code', '')} — {row.get('name', '')}".strip(" —")
    if po_id:
        try:
            po = db.get_production_order(po_id) or {}
            if po:
                f["Production"] = (
                    f"{po.get('document_no') or po_id} — {po.get('batch_no') or '—'} — "
                    f"{po.get('order_date') or ''}"
                ).strip(" —")
        except Exception:
            f["Production"] = str(po_id)
    gf = gf or {}
    if gf.get("customer_group_id"):
        f["Customer group"] = group_label(gf["customer_group_id"])
    if gf.get("supplier_group_id"):
        f["Supplier group"] = group_label(gf["supplier_group_id"])
    if gf.get("product_group_id"):
        f["Product group"] = group_label(gf["product_group_id"])
    if gf.get("account_group_id"):
        f["Chart account group"] = group_label(gf["account_group_id"])
    if gf.get("view_mode") and gf["view_mode"] != "detail":
        f["View"] = gf["view_mode"].replace("_", " ").title()
    if gf.get("include_linked"):
        f["Ledger mode"] = "Combined dual party"
    return f


def _result_summary(df: pd.DataFrame, report: str):
    if df is None or df.empty:
        return
    from html import escape

    n = len(df)
    ledger_titles = (
        "Customer Ledger", "Supplier Ledger",
        "Customer Ledger (Detailed)", "Supplier Ledger (Detailed)",
        "Account Ledger",
    )
    if report in ledger_titles:
        totals = summary_keys_for_report(report, df)
        note = (df.attrs.get("ledger_summary") or {}).get("note")
        if note:
            st.caption(note)
        cols = st.columns(5, gap="small")
        cols[0].markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Rows</p>"
            f"<p class='txn-kpi-val'>{n:,}</p></div>",
            unsafe_allow_html=True,
        )
        if totals:
            for i, (label, key) in enumerate(
                (("Opening", "Opening"), ("Debit", "Total Debit"), ("Credit", "Total Credit"), ("Closing", "Closing")),
                start=1,
            ):
                cols[i].markdown(
                    f"<div class='txn-kpi-card'><p class='txn-kpi'>{label}</p>"
                    f"<p class='txn-kpi-val'>{escape(str(totals.get(key, '0.00')))}</p></div>",
                    unsafe_allow_html=True,
                )
        st.divider()
        return
    cols = st.columns(4, gap="small")
    cols[0].markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Rows</p>"
        f"<p class='txn-kpi-val'>{n:,}</p></div>",
        unsafe_allow_html=True,
    )
    if report == "Daily Activity Report" and "voucher_type" in df.columns:
        cols[1].markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Vouchers</p>"
            f"<p class='txn-kpi-val'>{n:,}</p></div>",
            unsafe_allow_html=True,
        )
        if "amount" in df.columns:
            try:
                tot = pd.to_numeric(df["amount"], errors="coerce").sum()
                cols[2].markdown(
                    f"<div class='txn-kpi-card'><p class='txn-kpi'>Total Amount</p>"
                    f"<p class='txn-kpi-val'>{tot:,.2f}</p></div>",
                    unsafe_allow_html=True,
                )
            except Exception:
                pass
        try:
            n_types = df["voucher_type"].nunique()
            cols[3].markdown(
                f"<div class='txn-kpi-card'><p class='txn-kpi'>Voucher Types</p>"
                f"<p class='txn-kpi-val'>{n_types:,}</p></div>",
                unsafe_allow_html=True,
            )
        except Exception:
            pass
    else:
        totals = summary_keys_for_report(report, df)
        if report in (
            "Item Wise Purchase (Detail)", "Item Wise Sale (Detail)",
            "Purchase Analysis", "Product Sales Analysis",
        ):
            qty_col = next(
                (c for c in ("quantity", "qty", "Quantity", "Qty") if c in df.columns),
                None,
            )
            amt_col = next(
                (c for c in ("amount", "Amount") if c in df.columns),
                None,
            )
            if qty_col is not None:
                try:
                    qsum = float(pd.to_numeric(df[qty_col], errors="coerce").sum() or 0)
                    totals["Total Quantity"] = f"{qsum:,.2f}"
                except Exception:
                    pass
            if amt_col is not None:
                try:
                    asum = float(pd.to_numeric(df[amt_col], errors="coerce").sum() or 0)
                    totals["Total Amount"] = f"{asum:,.2f}"
                except Exception:
                    pass
            prefer = ["Total Quantity", "Total Qty", "Total Amount"]
        else:
            prefer = []
        keys = []
        for k in prefer:
            if k in totals:
                keys.append(k)
        for k in totals:
            if k not in keys:
                keys.append(k)
        for i, k in enumerate(keys[:3]):
            cols[i + 1].markdown(
                f"<div class='txn-kpi-card'><p class='txn-kpi'>{k.replace('Total ', '')}</p>"
                f"<p class='txn-kpi-val'>{escape(str(totals[k]))}</p></div>",
                unsafe_allow_html=True,
            )
    if report in ("Negative Stock Report", "Reorder Report") and "stock_qty" in df.columns:
        cols[3].markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Items Listed</p>"
            f"<p class='txn-kpi-val'>{n:,}</p></div>",
            unsafe_allow_html=True,
        )
    st.divider()


def _render_daily_activity_screen(df: pd.DataFrame) -> None:
    """Heading-wise / voucher-type sections on screen (matches print layout)."""
    groups = daily_activity_groups(df)
    if not groups:
        st.info("No vouchers for this day.")
        return
    display_cols = [
        c for c in (
            "voucher_no", "voucher_date", "party", "amount",
            "status", "user", "particulars", "time",
        )
        if c in df.columns
    ]
    current_module = None
    for module, vtype, chunk in groups:
        if module and module != current_module:
            current_module = module
            st.markdown(f"### {module}")
        sub_amt = 0.0
        if "amount" in chunk.columns:
            sub_amt = float(pd.to_numeric(chunk["amount"], errors="coerce").fillna(0).sum())
        n = len(chunk)
        with st.expander(
            f"{vtype}  ·  {n} voucher{'s' if n != 1 else ''}  ·  {sub_amt:,.2f}",
            expanded=True,
        ):
            show = chunk[display_cols].copy() if display_cols else chunk.copy()
            if "party" in show.columns:
                show = show.rename(columns={"party": "party_gl_head"})
            show.insert(0, "#", range(1, len(show) + 1))
            # Human label for GL-aware party column
            pretty = prettify_columns(show)
            if "Party Gl Head" in pretty.columns:
                pretty = pretty.rename(columns={"Party Gl Head": "Party / GL Head"})
            from erp_ui.helpers import render_dataframe_html_table
            render_dataframe_html_table(pretty)
            st.caption(f"Subtotal — {vtype}: **{sub_amt:,.2f}**")

def _display_report_df(df: pd.DataFrame, report: str) -> pd.DataFrame:
    """Screen + export: drop internal fields, keep business columns only."""
    return prettify_columns(prepare_report_dataframe(df, report))


def _favorite_reports(user_id) -> list[str]:
    if not user_id:
        return []
    try:
        with db.get_connection() as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='erp_favorite_reports'").fetchone():
                return []
            rows = conn.execute(
                "SELECT report_title FROM erp_favorite_reports WHERE user_id=? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
            return [r[0] for r in rows]
    except Exception:
        return []


def _add_favorite_report(user_id, title: str) -> None:
    if not user_id or not title:
        return
    try:
        with db.get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO erp_favorite_reports(user_id, report_title) VALUES(?,?)",
                (user_id, title),
            )
    except Exception:
        pass


def _recent_reports(user_id, limit: int = 8) -> list[str]:
    if not user_id:
        return []
    try:
        with db.get_connection() as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='erp_recent_reports'").fetchone():
                return []
            rows = conn.execute(
                """SELECT report_title FROM erp_recent_reports
                   WHERE user_id=? ORDER BY opened_at DESC LIMIT ?""",
                (user_id, limit),
            ).fetchall()
            seen = []
            for r in rows:
                if r[0] not in seen:
                    seen.append(r[0])
            return seen
    except Exception:
        return []


def _record_recent_report(user_id, title: str) -> None:
    if not user_id or not title:
        return
    try:
        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO erp_recent_reports(user_id, report_title) VALUES(?,?)",
                (user_id, title),
            )
    except Exception:
        pass


def page_reports_center():
    _init_report_state()
    _apply_pending_report_nav()
    std_page_header("Reports Center", status="register", status_kind="shell")
    st.caption(
        "Find any report by category or search · set filters · preview · export to PDF, Excel, or CSV"
    )

    from erp_ui.helpers import sticky_page_tabs

    tab = sticky_page_tabs(["Business reports", "Document printing"], "rpt_center_tab")

    if tab == "Business reports":
        _business_reports_tab()
    else:
        _document_printing_tab()


def _business_reports_tab():
    _apply_pending_report_nav()

    active_report = REPORT_CATALOG["Sales"][0]["title"]
    with st.container(key="rpt_hub_row"):
        nav_col, main_col = st.columns([1.15, 2.85], gap="medium")

        with nav_col:
            with st.container(key="rpt_nav_sidebar"):
                st.markdown("##### Browse")
                search = st.text_input(
                    "Search reports",
                    placeholder="Search…",
                    key="rpt_search",
                    label_visibility="collapsed",
                )
                matches = _report_search_matches(search)
                if search.strip() and matches:
                    active_report = st.radio(
                        "Search results",
                        matches,
                        key="rpt_search_pick",
                        format_func=lambda t: f"{t}  ·  {_REPORT_BY_TITLE[t]['category']}",
                    )
                else:
                    if search.strip() and not matches:
                        st.caption("No match.")

                    st.radio(
                        "Category",
                        list(REPORT_CATALOG.keys()),
                        key="rpt_category",
                        label_visibility="collapsed",
                    )
                    cat = st.session_state["rpt_category"]
                    titles = [x["title"] for x in REPORT_CATALOG[cat]]
                    if st.session_state.get("rpt_report") not in titles:
                        st.session_state["rpt_report"] = titles[0]
                    active_report = st.radio(
                        "Report",
                        titles,
                        key="rpt_report",
                        label_visibility="collapsed",
                    )

                st.markdown("##### Popular")
                uid = st.session_state.get("user", {}).get("id")
                favs = _favorite_reports(uid)
                if favs:
                    st.caption("★ Favorites")
                    for ft in favs[:5]:
                        if st.button(ft, key=f"rpt_fav_{ft}", use_container_width=True):
                            # Must not touch rpt_report after the radio exists — defer via rpt_nav_to.
                            st.session_state["rpt_nav_to"] = ft
                            _record_recent_report(uid, ft)
                            st.rerun()
                recent = _recent_reports(uid)
                if recent:
                    st.caption("Recent")
                    for rt in recent[:5]:
                        if st.button(rt, key=f"rpt_rec_{rt}", use_container_width=True):
                            st.session_state["rpt_nav_to"] = rt
                            st.rerun()
                if st.button("★ Favorite current report", key="rpt_add_fav", use_container_width=True):
                    _add_favorite_report(uid, st.session_state.get("rpt_report", active_report))
                    st.toast("Added to favorites.")
                pop_pick = st.selectbox(
                    "Popular report",
                    POPULAR_REPORTS,
                    key="rpt_pop_pick",
                    label_visibility="collapsed",
                )
                if st.button("Open", key="rpt_pop_go", use_container_width=True):
                    st.session_state["rpt_nav_to"] = pop_pick
                    st.rerun()

        with main_col:
            report = active_report or st.session_state.get("rpt_report") or REPORT_CATALOG["Sales"][0]["title"]
            meta = _REPORT_BY_TITLE.get(report)
            if not meta:
                st.error("Unknown report.")
                return

            st.markdown(
                f'<div class="rpt-hub-card"><h4>{report}</h4>'
                f'<p>{meta["description"]}</p>'
                f'<p style="font-size:0.8rem;margin-top:6px;"><b>Category:</b> {meta["category"]}</p></div>',
                unsafe_allow_html=True,
            )

            with st.container():
                st.markdown('<div class="rpt-filter-box">', unsafe_allow_html=True)
                fd, td, cid, sid, pid, wid, eid, payroll_id, gf, aid, po_id = _render_filters(meta)
                st.markdown("</div>", unsafe_allow_html=True)

            with st.container(key="rpt_run_row"):
                run_col, _ = st.columns([0.28, 2.72])
                run_clicked = run_col.button("Run report", type="primary", key="run_rpt")
            if run_clicked:
                need_po = (
                    report in ("Production Consumption", "Production Consumption (by Order)")
                    and (gf or {}).get("consumption_view") != "day"
                )
                if need_po and not po_id:
                    st.error("Select a production number before running this report.")
                else:
                    period_lbl = f"{fd} to {td}" if meta["filters"].get("date") else "All dates"
                    if report in ("Production Consumption", "Production Consumption (by Order)"):
                        if (gf or {}).get("consumption_view") == "day":
                            period_lbl = f"Register date: {fd}"
                            report_print_title = "Production Consumption Register"
                        else:
                            report_print_title = "Production Consumption"
                    else:
                        report_print_title = report
                    st.session_state["rpt_result"] = _run_report(
                        report, fd, td, cid, sid, pid, wid, eid, payroll_id, gf, aid=aid, po_id=po_id,
                    )
                    _record_recent_report(st.session_state.get("user", {}).get("id"), report)
                    export_filters = _resolve_export_filters(
                        cid, sid, pid, wid, eid, gf, aid=aid, po_id=po_id,
                    )
                    if (gf or {}).get("consumption_view") == "day":
                        export_filters["View"] = "Day register"
                    elif report in ("Production Consumption", "Production Consumption (by Order)"):
                        export_filters["View"] = "By production number"
                    st.session_state["rpt_meta"] = (
                        report,
                        period_lbl,
                        export_filters,
                        report_print_title,
                    )
                    st.rerun()

            df = st.session_state.get("rpt_result")
            rpt_meta = st.session_state.get("rpt_meta")
            if df is not None and rpt_meta and rpt_meta[0] == report:
                st.markdown("##### Results")
                if df.empty:
                    st.info("No data for the selected filters. Widen the date range or change filters.")
                else:
                    _result_summary(df, report)
                    if report == "Daily Activity Report":
                        _render_daily_activity_screen(df)
                    else:
                        from erp_ui.helpers import render_dataframe_html_table
                        show_df = _display_report_df(df, report)
                        render_dataframe_html_table(show_df)
                    export_name = report.replace(" ", "_").lower()
                    print_title = rpt_meta[3] if len(rpt_meta) > 3 else report
                    if report in ITEMWISE_DETAIL_REPORTS:
                        itemwise_detail_toolbar(
                            df, print_title, export_name, rpt_meta[1], rpt_meta[2],
                            key_prefix=f"rpt_{report}",
                        )
                    else:
                        report_toolbar(
                            df,
                            print_title,
                            export_name,
                            rpt_meta[1],
                            rpt_meta[2],
                            key_prefix=f"rpt_{report}",
                            layout=report_layout(print_title) or report_layout(report),
                        )


def _document_printing_tab():
    st.markdown("Print individual vouchers and documents (invoices, job cards, gate passes, etc.).")
    doc_type = st.selectbox("Document type", list(PRINTERS.keys()), key="doc_type")
    if doc_type == "Gate Pass":
        gp_rows = db.get_gate_passes()
        if gp_rows:
            gp_opts = {
                f"{r['document_no']} — {r.get('party_name', '')} ({r.get('pass_date', '')})": r["id"]
                for r in gp_rows
            }
            gp_sel = st.selectbox("Select gate pass", list(gp_opts.keys()), key="doc_gp_sel")
            doc_id = gp_opts[gp_sel]
        else:
            st.info("No gate passes found.")
            doc_id = None
    else:
        doc_id = st.number_input("Document ID", min_value=1, value=1, step=1, key="doc_id")
    if doc_id:
        document_print_toolbar(doc_type, int(doc_id), key_prefix="doc_print")


def page_hr_reports_hub():
    """Legacy nav entry → Reports Center (HR category)."""
    try:
        from erp_ui.hr_pages import require_hr
        require_hr("view")
    except Exception:
        pass
    st.session_state["rpt_nav_to"] = "Employee List"
    page_reports_center()


def page_gate_pass_reports_hub():
    """Legacy nav entry → Reports Center (Gate Pass category)."""
    st.session_state["rpt_nav_to"] = "Gate Pass Register"
    page_reports_center()


# ---------------------------------------------------------------------------
# Report runners (unchanged logic + HR extensions)
# ---------------------------------------------------------------------------

def _attach_party_attrs(df, party, kind):
    if df is None or getattr(df, "empty", True):
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
        if p.get("ledger_summary") is not None:
            df.attrs["ledger_summary"] = party.get("ledger_summary") or {}
    except Exception:
        pass
    return df


def _detailed_ledger_dataframe(entries):
    """Finance Manager layout: Date, Type, Vr.#, Narration, Qty, Rate, Amount, Debit, Credit, Balance."""
    cols = ["date", "type", "vr_no", "narration", "qty", "rate", "amount", "debit", "credit", "balance"]
    df = pd.DataFrame(entries)
    for c in cols:
        if c not in df.columns:
            df[c] = None
    out = df[cols].copy()
    out.columns = ["Date", "Type", "Vr. #", "Narration", "Qty", "Rate", "Amount", "Debit", "Credit", "Balance"]
    return out


def _filter_df_date(df, col, fd, td):
    if df.empty or col not in df.columns:
        return df
    return df[(df[col] >= fd) & (df[col] <= td)]


def _run_report(report, fd, td, cid, sid, pid, wid, eid, payroll_id=None, gf=None, aid=None, po_id=None):
    gf = gf or {}
    pvm = gf.get("party_view_mode") or "detail"
    fvm = gf.get("view_mode") or "detail"
    if report == "Sales Register":
        df = pd.DataFrame(db.get_sales())
        return _filter_df_date(df, "sale_date", fd, td)
    if report == "Sales Invoice Register":
        return pd.DataFrame(rpt_db.get_sales_invoice_register(
            fd, td, cid, pid,
            customer_group_id=gf.get("customer_group_id"),
            product_group_id=gf.get("product_group_id"),
        ))
    if report == "Customer Outstanding":
        return pd.DataFrame(db.get_customer_outstanding(
            customer_group_id=gf.get("customer_group_id"), view_mode=pvm,
        ))
    if report == "Customer Due Aging":
        as_of = td or str(date.today())
        return pd.DataFrame(rpt_db.get_customer_due_aging(
            as_of,
            customer_id=cid,
            customer_group_id=gf.get("customer_group_id"),
        ))
    if report == "Customer Ledger":
        if not cid:
            st.warning("Select a customer for Customer Ledger.")
            return pd.DataFrame()
        party, entries = db.get_customer_ledger(
            cid, fd, td, include_linked=bool(gf.get("include_linked")),
        )
        df = pd.DataFrame(entries)
        df.attrs["ledger_summary"] = party.get("ledger_summary") or {}
        return _attach_party_attrs(df, party, "customer")
    if report == "Customer Ledger (Detailed)":
        if not cid:
            st.warning("Select a customer for Customer Ledger (Detailed).")
            return pd.DataFrame()
        party, entries = db.get_customer_ledger_detailed(
            cid, fd, td, include_linked=bool(gf.get("include_linked")),
        )
        df = _detailed_ledger_dataframe(entries)
        df.attrs["ledger_summary"] = party.get("ledger_summary") or {}
        try:
            from database import last_detailed_ledger_balance
            df.attrs["ledger_summary"] = {
                **(df.attrs.get("ledger_summary") or {}),
                "closing": last_detailed_ledger_balance(entries),
            }
        except Exception:
            pass
        return _attach_party_attrs(df, party, "customer")
    if report == "Product Sales Analysis":
        return pd.DataFrame(db.get_product_wise_sales(
            fd, td, product_group_id=gf.get("product_group_id"), view_mode=pvm,
        ))
    if report == "Item Wise Sale (Detail)":
        return pd.DataFrame(rpt_db.get_item_wise_sale_detail(
            fd, td, cid, pid,
            customer_group_id=gf.get("customer_group_id"),
            product_group_id=gf.get("product_group_id"),
        ))
    if report == "Tax Sales Report":
        return pd.DataFrame(db.get_tax_report(fd, td))
    if report == "Sales Returns":
        return pd.DataFrame(rpt_db.get_sales_returns_report(
            fd, td, cid, customer_group_id=gf.get("customer_group_id"),
        ))
    if report == "Pending Sale Invoices":
        return pd.DataFrame(db.get_sales_by_status("pending_approval"))
    if report == "Approved Sale Invoices":
        return pd.DataFrame(db.get_sales_by_status("approved"))
    if report == "Sale Weight Variance Report":
        return pd.DataFrame(rpt_db.get_weight_variance_report(fd, td, "sales"))

    if report == "Purchase Register":
        df = pd.DataFrame(db.get_purchases())
        return _filter_df_date(df, "purchase_date", fd, td)
    if report == "Purchase Invoice Register":
        return pd.DataFrame(rpt_db.get_purchase_invoice_register(
            fd, td, sid, pid,
            supplier_group_id=gf.get("supplier_group_id"),
            product_group_id=gf.get("product_group_id"),
        ))
    if report == "Supplier Outstanding":
        return pd.DataFrame(db.get_supplier_outstanding(
            supplier_group_id=gf.get("supplier_group_id"), view_mode=pvm,
        ))
    if report == "Supplier Ledger":
        if not sid:
            st.warning("Select a supplier for Supplier Ledger.")
            return pd.DataFrame()
        party, entries = db.get_supplier_ledger(
            sid, fd, td, include_linked=bool(gf.get("include_linked")),
        )
        df = pd.DataFrame(entries)
        df.attrs["ledger_summary"] = party.get("ledger_summary") or {}
        return _attach_party_attrs(df, party, "supplier")
    if report == "Supplier Ledger (Detailed)":
        if not sid:
            st.warning("Select a supplier for Supplier Ledger (Detailed).")
            return pd.DataFrame()
        party, entries = db.get_supplier_ledger_detailed(
            sid, fd, td, include_linked=bool(gf.get("include_linked")),
        )
        df = _detailed_ledger_dataframe(entries)
        df.attrs["ledger_summary"] = party.get("ledger_summary") or {}
        try:
            from database import last_detailed_ledger_balance
            df.attrs["ledger_summary"] = {
                **(df.attrs.get("ledger_summary") or {}),
                "closing": last_detailed_ledger_balance(entries, kind="supplier"),
            }
        except Exception:
            pass
        return _attach_party_attrs(df, party, "supplier")
    if report == "Purchase Analysis":
        return pd.DataFrame(rpt_db.get_product_wise_purchase(
            fd, td, sid,
            supplier_group_id=gf.get("supplier_group_id"),
            product_group_id=gf.get("product_group_id"),
            view_mode=pvm,
        ))
    if report == "Item Wise Purchase (Detail)":
        return pd.DataFrame(rpt_db.get_item_wise_purchase_detail(
            fd, td, sid, pid,
            supplier_group_id=gf.get("supplier_group_id"),
            product_group_id=gf.get("product_group_id"),
        ))
    if report == "Tax Purchase Report":
        return pd.DataFrame(rpt_db.get_purchase_tax_report(fd, td))
    if report == "Purchase Returns":
        return pd.DataFrame(rpt_db.get_purchase_returns_report(
            fd, td, sid, supplier_group_id=gf.get("supplier_group_id"),
        ))
    if report == "GRN Register":
        df = pd.DataFrame(db.get_grns())
        return _filter_df_date(df, "grn_date", fd, td)
    if report == "Pending Purchase Invoices":
        return pd.DataFrame(db.get_purchases_by_status("pending_approval"))
    if report == "Approved Purchase Invoices":
        return pd.DataFrame(db.get_purchases_by_status("approved"))
    if report == "Purchase Weight Variance Report":
        return pd.DataFrame(rpt_db.get_weight_variance_report(fd, td, "purchase"))

    if report in ("Stock Position", "Stock Valuation"):
        return pd.DataFrame(db.get_stock_report(
            product_group_id=gf.get("product_group_id"), view_mode=pvm,
        ))
    if report == "Stock Ledger":
        return pd.DataFrame(rpt_db.get_stock_ledger(pid, fd, td))
    if report == "Warehouse Stock":
        return pd.DataFrame(rpt_db.get_warehouse_stock(wid))
    if report == "Batch Stock":
        return pd.DataFrame(db.get_batch_stock())
    if report == "Reorder Report":
        return pd.DataFrame(rpt_db.get_reorder_report())
    if report == "Negative Stock Report":
        return pd.DataFrame(rpt_db.get_negative_stock_report())

    if report == "BOM Cost Sheet":
        return pd.DataFrame(rpt_db.get_bom_cost_sheet())
    if report == "Production Register":
        return pd.DataFrame(rpt_db.get_production_register(fd, td))
    if report == "Production Variance":
        df = pd.DataFrame(rpt_db.get_production_register(fd, td))
        if not df.empty:
            df["variance_qty"] = df["actual_qty"] - df["planned_qty"]
        return df
    if report == "Raw Material Consumption":
        return pd.DataFrame(rpt_db.get_rm_consumption(fd, td))
    if report in ("Production Consumption", "Production Consumption (by Order)"):
        if (gf or {}).get("consumption_view") == "day":
            return pd.DataFrame(rpt_db.get_rm_consumption(fd, td))
        if not po_id:
            return pd.DataFrame()
        return pd.DataFrame(rpt_db.get_production_consumption_by_order(po_id))
    if report == "Finished Goods Report":
        return pd.DataFrame(rpt_db.get_finished_goods_report(fd, td))

    if report == "Cash Book":
        return pd.DataFrame(db.get_cash_book(fd, td))
    if report == "Bank Book":
        return pd.DataFrame(db.get_bank_book(fd, td))
    if report == "Account Ledger":
        if not aid:
            st.warning("Select a GL account for Account Ledger.")
            return pd.DataFrame()
        account, entries = db.get_account_ledger(aid, fd, td)
        if not account:
            st.warning("Account not found.")
            return pd.DataFrame()
        df = pd.DataFrame(entries)
        df.attrs["ledger_summary"] = account.get("ledger_summary") or {}
        return _attach_party_attrs(df, account, "account")
    if report == "General Ledger":
        return pd.DataFrame(db.get_general_ledger(
            aid, fd, td, account_group_id=gf.get("account_group_id"),
        ))
    if report == "Trial Balance":
        return pd.DataFrame(db.get_trial_balance(
            fd, td, account_group_id=gf.get("account_group_id"), view_mode=fvm,
        ))
    if report == "Profit & Loss":
        return profit_loss_dataframe(db.get_profit_loss(fd, td))
    if report == "Balance Sheet":
        bs = db.get_balance_sheet(
            td, account_group_id=gf.get("account_group_id"), view_mode=fvm,
        )
        return pd.DataFrame(bs.get("rows", []))
    if report == "Journal Register":
        return pd.DataFrame(rpt_db.get_journal_register(fd, td))
    if report == "Daily Activity Report":
        return pd.DataFrame(rpt_db.get_daily_activity_report(str(fd)))

    if report == "Employee List":
        return pd.DataFrame(db.report_employee_list())
    if report == "Employee Ledger":
        if not eid:
            st.warning("Select an employee for Employee Ledger.")
            return pd.DataFrame()
        import db_hr
        _, entries = db_hr.get_employee_ledger(eid, fd, td)
        return pd.DataFrame(entries)
    if report == "Attendance Report":
        return pd.DataFrame(db.report_attendance(fd, td, eid))
    if report == "Overtime Report":
        return pd.DataFrame(db.report_overtime(fd, td))
    if report == "Payroll Register":
        return pd.DataFrame(db.report_payroll_register(fd, td))
    if report == "Leave Report":
        return pd.DataFrame(db.report_leave(fd, td))
    if report == "Department Salary Cost":
        if not payroll_id:
            st.warning("Select a payroll period.")
            return pd.DataFrame()
        return pd.DataFrame(db.report_dept_salary_cost(payroll_id))
    if report == "Outstanding Advances":
        return pd.DataFrame(db.report_outstanding_advances())
    if report == "Outstanding Loans":
        return pd.DataFrame(db.report_outstanding_loans())

    if report == "Daily Weight Report":
        return pd.DataFrame(db.get_weight_slips_pro(fd, td, cid, sid, pid))
    if report == "Vehicle Report":
        return pd.DataFrame(rpt_db.get_weight_report_by_vehicle(fd, td))
    if report == "Customer Weight Report":
        return pd.DataFrame(rpt_db.get_weight_report_by_party(fd, td, "customer"))
    if report == "Supplier Weight Report":
        return pd.DataFrame(rpt_db.get_weight_report_by_party(fd, td, "supplier"))
    if report == "Weight Variance Report":
        return pd.DataFrame(rpt_db.get_weight_variance_report(fd, td))

    if report == "Inward Register":
        return pd.DataFrame(rpt_db.get_gate_pass_register("material_in", fd, td))
    if report == "Outward Register":
        return pd.DataFrame(rpt_db.get_gate_pass_register("material_out", fd, td))
    if report == "Gate Pass Register":
        return pd.DataFrame(rpt_db.get_gate_pass_register(None, fd, td))

    return pd.DataFrame()
