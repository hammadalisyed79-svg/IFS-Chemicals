"""Standard document navigation — open register rows, switch tabs."""

from __future__ import annotations

import streamlit as st

from erp_ui import transaction_list as txn

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

