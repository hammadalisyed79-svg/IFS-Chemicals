"""Plant shift view — batches, RM shortage, QC pending (Phase 5)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from application import data_gateway as db
from erp_ui.helpers import std_page_header, export_buttons, render_dataframe_html_table
from erp_ui.nav import request_nav


def _qc_pending() -> tuple[int, list[dict]]:
    try:
        with db.get_connection() as conn:
            if not conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ifs_qc_inspections'"
            ).fetchone():
                return 0, []
            from database import rows_to_list
            rows = rows_to_list(
                conn.execute(
                    """SELECT id, inspection_no, inspection_date, status, batch_no, product_id
                       FROM ifs_qc_inspections
                       WHERE COALESCE(status, 'pending') IN ('pending', 'open', 'draft')
                       ORDER BY inspection_date DESC, id DESC LIMIT 20"""
                ).fetchall()
            )
            return len(rows), rows
    except Exception:
        return 0, []


def _today_production_orders() -> list[dict]:
    today = str(date.today())
    orders = db.get_production_orders()
    active = {"draft", "issued", "in_progress"}
    return [
        o for o in orders
        if (str(o.get("order_date") or "")[:10] == today or (o.get("status") or "").lower() in active)
        and (o.get("status") or "").lower() != "completed"
    ][:25]


def page_plant_shift():
    std_page_header("Plant Shift", status="register", status_kind="shell")
    st.caption("Today's plant floor — production batches, material shortage, and QC queue.")

    try:
        stats = db.get_dashboard_stats()
    except Exception as exc:
        st.warning(f"Dashboard stats unavailable: {exc}")
        stats = {}

    pending = stats.get("pending_breakdown") or {}
    qc_n, qc_rows = _qc_pending()
    unlinked_slips = len(db.get_completed_unlinked_slips())
    low_stock = stats.get("low_stock") or []

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Active production", int(pending.get("production_active") or 0))
    k2.metric("Low stock items", len(low_stock))
    k3.metric("QC pending", qc_n)
    k4.metric("Slips → invoice", unlinked_slips)
    k5.metric("Open gate passes", int(pending.get("gate_pass_open") or 0))

    qa1, qa2, qa3, qa4 = st.columns(4)
    if qa1.button("Weight Entry", key="ps_weight", use_container_width=True):
        request_nav("Weight Scale", "Weight Entry")
        st.rerun()
    if qa2.button("Dispatch Planning", key="ps_dispatch", use_container_width=True):
        request_nav("Production", "Dispatch Planning")
        st.rerun()
    if qa3.button("Gate Pass", key="ps_gate", use_container_width=True):
        request_nav("Gate Pass", "Gate Pass Entry")
        st.rerun()
    if qa4.button("Production Orders", key="ps_prod", use_container_width=True):
        request_nav("Production", "Production Orders")
        st.rerun()

    st.markdown("### Today's production orders")
    prod_rows = _today_production_orders()
    if not prod_rows:
        st.info("No active production orders for today.")
    else:
        show = pd.DataFrame([
            {
                "Order": r.get("document_no"),
                "Batch": r.get("batch_no") or "—",
                "Product": r.get("product_name") or "—",
                "Status": str(r.get("status") or "").title(),
                "Planned": float(r.get("planned_qty") or 0),
                "Date": (r.get("order_date") or "")[:10],
            }
            for r in prod_rows
        ])
        render_dataframe_html_table(show)

    st.markdown("### RM shortage (reorder level)")
    if not low_stock:
        st.success("No items below reorder level.")
    else:
        ls_df = pd.DataFrame([
            {
                "Code": r.get("code"),
                "Product": r.get("name"),
                "Stock": float(r.get("stock_qty") or 0),
                "Reorder": float(r.get("reorder_level") or 0),
                "Unit": r.get("unit") or "",
            }
            for r in low_stock[:20]
        ])
        render_dataframe_html_table(ls_df)
        export_buttons(ls_df, "plant_shift_low_stock", "Low Stock")

    st.markdown("### QC pending")
    if not qc_rows:
        st.caption("No pending QC inspections.")
    else:
        qc_df = pd.DataFrame([
            {
                "Inspection": r.get("inspection_no") or r.get("id"),
                "Date": (r.get("inspection_date") or "")[:10],
                "Batch": r.get("batch_no") or "—",
                "Status": r.get("status") or "pending",
            }
            for r in qc_rows
        ])
        render_dataframe_html_table(qc_df)
