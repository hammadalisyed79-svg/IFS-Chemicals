"""V13.13 — central Draft / Pending Documents Center."""

from __future__ import annotations

import streamlit as st
from erp_ui import form_flow as ff
import pandas as pd
from application import data_gateway as db
from erp_ui.helpers import fmt_money, std_page_header, section_header, sticky_page_tabs, render_dataframe_html_table
from erp_ui.nav import request_nav


_NAV_MAP = {
    "Sales Invoice": ("Sales", "Sales Invoices"),
    "Purchase Invoice": ("Purchases", "Purchase Invoices"),
    "Sales Return": ("Sales", "Sales Returns"),
    "Purchase Return": ("Purchases", "Purchase Returns"),
    "Sales Order": ("Sales", "Sales Orders"),
    "Purchase Order": ("Purchases", "Purchase Orders"),
    "Quotation": ("Sales", "Quotations"),
    "GRN": ("Purchases", "GRN"),
    "Production Order": ("Production", "Production Orders"),
    "Journal Voucher": ("Finance", "Journal Voucher"),
}


def _fetch_drafts(category: str | None = None) -> list[dict]:
    with db.get_connection() as conn:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='erp_draft_registry'"
        ).fetchone():
            return []
        q = """SELECT r.*, u.full_name AS created_by_name
               FROM erp_draft_registry r
               LEFT JOIN users u ON u.id = r.created_by
               WHERE 1=1"""
        params: list = []
        if category == "Sales":
            q += " AND (r.doc_type LIKE 'Sales%' OR r.doc_type = 'Quotation')"
        elif category == "Purchase":
            q += " AND (r.doc_type LIKE 'Purchase%' OR r.doc_type = 'GRN')"
        elif category == "Inventory":
            q += " AND r.doc_type IN ('GRN', 'Stock Adjustment')"
        elif category == "Production":
            q += " AND r.doc_type LIKE 'Production%'"
        elif category == "HR":
            q += " AND (r.doc_type LIKE 'Payroll%' OR r.doc_type LIKE 'Leave%')"
        q += " ORDER BY COALESCE(r.updated_at, r.created_at) DESC, r.id DESC"
        return db.rows_to_list(conn.execute(q, params).fetchall())


def _open_document(row: dict) -> None:
    nav = _NAV_MAP.get(row.get("doc_type", ""))
    if nav:
        request_nav(nav[0], nav[1])
        st.session_state["draft_open_id"] = row.get("record_id")
        st.session_state["draft_open_table"] = row.get("doc_table")
        st.rerun()
    else:
        st.warning(f"No navigation configured for {row.get('doc_type')}.")


def _delete_draft(row: dict) -> None:
    table = row.get("doc_table")
    rid = row.get("record_id")
    deleters = {
        "sales_invoices": db.delete_sale,
        "purchase_invoices": db.delete_purchase,
        "sales_returns": db.delete_sale_return,
        "purchase_returns": db.delete_purchase_return,
    }
    fn = deleters.get(table)
    if not fn:
        st.error("Delete not supported for this document type from Draft Center.")
        return
    fn(rid)
    with db.get_connection() as conn:
        from db_v13_13 import sync_draft_registry_row
        sync_draft_registry_row(
            conn, doc_type=row["doc_type"], doc_table=table, record_id=rid, status="deleted",
        )
    ff.action_done("Draft deleted.")


def _approve_draft(row: dict) -> None:
    table = row.get("doc_table")
    rid = row.get("record_id")
    uid = st.session_state.get("user", {}).get("id")
    try:
        if table == "sales_invoices":
            from db_invoice_workflow import submit_sale_invoice, approve_sale_invoice
            submit_sale_invoice(rid, uid)
            approve_sale_invoice(rid, uid)
        elif table == "purchase_invoices":
            from db_invoice_workflow import submit_purchase_invoice, approve_purchase_invoice
            submit_purchase_invoice(rid, uid)
            approve_purchase_invoice(rid, uid)
        else:
            st.info("Approve from the document screen for this type.")
            return
        ff.action_done("Document approved.")
    except Exception as exc:
        st.error(str(exc))


def page_draft_center():
    std_page_header("Draft Center", status="register", status_kind="shell")
    tab = sticky_page_tabs(["All", "Sales", "Purchase", "Inventory", "Production"], "draft_center_tab")
    cat_map = {
        "All": None,
        "Sales": "Sales",
        "Purchase": "Purchase",
        "Inventory": "Inventory",
        "Production": "Production",
    }
    cat = cat_map.get(tab)
    rows = _fetch_drafts(cat)
    if not rows:
        st.info("No drafts in this category.")
        return
    df = pd.DataFrame(rows)
    show_cols = [
        c for c in (
            "document_no", "doc_type", "doc_date", "party_name", "amount",
            "status", "approval_status", "created_by_name", "updated_at",
        )
        if c in df.columns
    ]
    view = df[show_cols].copy()
    view.columns = [c.replace("_", " ").title() for c in view.columns]
    render_dataframe_html_table(view)
    section_header("Actions")
    labels = [
        f"{r.get('doc_type')} {r.get('document_no')} — {r.get('party_name') or '—'}"
        for r in rows
    ]
    pick = st.selectbox("Select draft", labels, key=f"draft_pick_{cat or 'all'}")
    idx = labels.index(pick)
    row = rows[idx]
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    if c1.button("Open", key=f"dr_open_{cat}_{idx}", use_container_width=True):
        _open_document(row)
    if c2.button("Delete", key=f"dr_del_{cat}_{idx}", use_container_width=True):
        _delete_draft(row)
    if c3.button("Approve", key=f"dr_app_{cat}_{idx}", use_container_width=True):
        _approve_draft(row)
    if c4.button("Print Preview", key=f"dr_prt_{cat}_{idx}", use_container_width=True):
        st.session_state["draft_print_id"] = row.get("record_id")
        st.info("Open the document and use Print from the list tab.")
    st.caption(
        f"Status: **{row.get('status')}** · Approval: **{row.get('approval_status') or '—'}** · "
        f"Amount: **{fmt_money(row.get('amount'))}**"
    )
