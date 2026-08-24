"""Invoice approval workflow UI — sales & purchase."""

import streamlit as st
from application import data_gateway as db
from erp_ui.helpers import uid, std_page_header, sticky_page_tabs
from erp_ui import transaction_list as txn
from erp_ui.invoice_status_ui import render_invoice_review, invoice_action_bar


def _sale_pending_actions(inv_id, _extra):
    inv = render_invoice_review("sale", inv_id, key_prefix=f"sal_wf_pend_rev_{inv_id}")
    if inv:
        invoice_action_bar(
            "sale", inv_id, "pending_approval",
            key_prefix=f"sal_wf_pend_{inv_id}", show_print=False,
        )


def page_sale_approval():
    peek = st.session_state.get("sal_appr_tab") or "Pending Approval"
    status_map = {
        "Pending Approval": "pending_approval",
        "Approved": "approved",
        "Draft / Rejected": "draft",
    }
    std_page_header(
        "Sale Approval",
        status=status_map.get(peek, "pending_approval"),
        status_kind="invoice",
    )
    tab = sticky_page_tabs(
        ["Pending Approval", "Approved", "Draft / Rejected"],
        "sal_appr_tab",
    )

    if tab == "Pending Approval":
        txn.invoice_workflow_tab(
            "sal_wf_pending", db.search_sales_invoices, "pending_approval", "Customer",
            _sale_pending_actions,
        )
    elif tab == "Approved":
        def _sale_approved_actions(inv_id, _extra):
            inv = render_invoice_review("sale", inv_id, key_prefix=f"sal_wf_appr_rev_{inv_id}")
            if inv:
                invoice_action_bar("sale", inv_id, "approved", key_prefix=f"sal_wf_appr_{inv_id}", show_print=False)
        txn.invoice_workflow_tab(
            "sal_wf_approved", db.search_sales_invoices, "approved", "Customer", _sale_approved_actions,
        )
    else:
        for status in ("draft", "rejected"):
            from erp_ui.invoice_status_ui import status_badge_html
            st.markdown(
                f'<div class="txn-status-strip">{status_badge_html(status)}</div>',
                unsafe_allow_html=True,
            )

            def _draft_actions(inv_id, _ea, s=status):
                inv = render_invoice_review("sale", inv_id, key_prefix=f"sal_wf_{s}_rev_{inv_id}")
                if inv:
                    invoice_action_bar("sale", inv_id, s, key_prefix=f"sal_wf_{s}_{inv_id}", show_print=False)

            txn.invoice_workflow_tab(
                f"sal_wf_{status}", db.search_sales_invoices, status, "Customer",
                _draft_actions,
            )


def _pur_pending_actions(inv_id, _extra):
    inv = render_invoice_review("purchase", inv_id, key_prefix=f"pur_wf_pend_rev_{inv_id}")
    if inv:
        invoice_action_bar(
            "purchase", inv_id, "pending_approval",
            key_prefix=f"pur_wf_pend_{inv_id}", show_print=False,
        )


def page_purchase_approval():
    peek = st.session_state.get("pur_appr_tab") or "Pending Approval"
    status_map = {
        "Pending Approval": "pending_approval",
        "Approved": "approved",
        "Draft / Rejected": "draft",
    }
    std_page_header(
        "Purchase Approval",
        status=status_map.get(peek, "pending_approval"),
        status_kind="invoice",
    )
    tab = sticky_page_tabs(
        ["Pending Approval", "Approved", "Draft / Rejected"],
        "pur_appr_tab",
    )

    if tab == "Pending Approval":
        txn.invoice_workflow_tab(
            "pur_wf_pending", db.search_purchases, "pending_approval", "Supplier", _pur_pending_actions,
        )
    elif tab == "Approved":
        def _pur_approved_actions(inv_id, _extra):
            inv = render_invoice_review("purchase", inv_id, key_prefix=f"pur_wf_appr_rev_{inv_id}")
            if inv:
                invoice_action_bar("purchase", inv_id, "approved", key_prefix=f"pur_wf_appr_{inv_id}", show_print=False)
        txn.invoice_workflow_tab(
            "pur_wf_approved", db.search_purchases, "approved", "Supplier", _pur_approved_actions,
        )
    else:
        for status in ("draft", "rejected"):
            from erp_ui.invoice_status_ui import status_badge_html
            st.markdown(
                f'<div class="txn-status-strip">{status_badge_html(status)}</div>',
                unsafe_allow_html=True,
            )

            def _draft_actions(inv_id, _ea, s=status):
                inv = render_invoice_review("purchase", inv_id, key_prefix=f"pur_wf_{s}_rev_{inv_id}")
                if inv:
                    invoice_action_bar("purchase", inv_id, s, key_prefix=f"pur_wf_{s}_{inv_id}", show_print=False)

            txn.invoice_workflow_tab(
                f"pur_wf_{status}", db.search_purchases, status, "Supplier",
                _draft_actions,
            )
