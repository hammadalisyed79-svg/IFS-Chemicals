"""Standard document navigation — open register rows, switch tabs."""

from __future__ import annotations

import streamlit as st

from erp_ui import transaction_list as txn

from application import data_gateway as db
# Standard tab labels for invoice-style screens (Phase 1)
DOC_TABS_INVOICE = ["Register", "Drafts", "Pending", "New", "Edit"]


def go_sale_register() -> None:
    st.session_state["sal_inv_tab"] = "Register"


def go_sale_new() -> None:
    st.session_state["sal_inv_tab"] = "New"


def go_sale_edit() -> None:
    st.session_state["sal_inv_tab"] = "Edit"
    st.session_state["sal_open_tab"] = "Edit"


def go_purchase_register() -> None:
    st.session_state["pur_inv_tab"] = "Register"


def go_purchase_new() -> None:
    st.session_state["pur_inv_tab"] = "New"


def go_purchase_edit() -> None:
    st.session_state["pur_inv_tab"] = "Edit"
    st.session_state["pur_open_tab"] = "Edit"


def open_sale_from_register(row: dict) -> None:
    txn.reselect_transaction_picker("sal_edit", row["id"])
    go_sale_edit()


def open_purchase_from_register(row: dict) -> None:
    txn.reselect_transaction_picker("pur_edit", row["id"])
    go_purchase_edit()


def open_recent_document(entry: dict) -> None:
    """Navigate to screen and open a recently viewed document when possible."""
    group = (entry.get("group") or "").strip()
    screen = (entry.get("screen") or "").strip()
    doc_no = (entry.get("doc_no") or "").strip()

    if screen == "Sales Invoices" and doc_no:
        result = db.search_sales_invoices(q=doc_no, page_size=20)
        items = result.get("items") or []
        match = next((r for r in items if r.get("invoice_no") == doc_no), None)
        if not match and items:
            match = items[0]
        if match:
            open_sale_from_register(match)
            return

    if screen == "Purchase Invoices" and doc_no:
        result = db.search_purchases(q=doc_no, page_size=20)
        items = result.get("items") or []
        match = next((r for r in items if r.get("invoice_no") == doc_no), None)
        if not match and items:
            match = items[0]
        if match:
            open_purchase_from_register(match)
            return

    if group and screen:
        from erp_ui.nav import request_nav
        request_nav(group, screen)

