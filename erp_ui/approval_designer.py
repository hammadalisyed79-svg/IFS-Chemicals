"""V14 RC1 — Approval Designer, matrix, history, delegation."""

from __future__ import annotations

import streamlit as st
from erp_ui import form_flow as ff
import pandas as pd
from application import data_gateway as db
from erp_ui.helpers import std_page_header, section_header, uid, sticky_page_tabs, render_dataframe_html_table
from erp_core.approval_engine import (
    get_approval_history,
    list_approval_rules,
    save_approval_rule,
)
from erp_core.transaction_engine import all_document_specs


def page_approval_designer():
    std_page_header("Approval Designer", status="register", status_kind="shell")
    tab = sticky_page_tabs(["Rules", "Approval Matrix", "History", "Delegation"], "appr_design_tab")
    if tab == "Rules":
        _rules_tab()
    elif tab == "Approval Matrix":
        _matrix_tab()
    elif tab == "History":
        _history_tab()
    elif tab == "Delegation":
        _delegation_tab()


def _rules_tab():
    section_header("Approval rules")
    doc_types = sorted({s.key for s in all_document_specs()} | {"sales_invoice", "purchase_invoice"})
    with st.form("appr_rule_new"):
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("Rule name")
        doc_type = c2.selectbox("Document type", doc_types)
        level = c3.number_input("Level", min_value=1, value=1)
        c4, c5, c6 = st.columns(3)
        role = c4.selectbox("Role", ["", "admin", "manager", "user"])
        min_amt = c5.number_input("Min amount", min_value=0.0, value=0.0)
        max_amt = c6.number_input("Max amount (0=none)", min_value=0.0, value=0.0)
        dept = st.text_input("Department filter (optional)")
        escalate = st.number_input("Escalate after hours (0=off)", min_value=0, value=0)
        comments_req = st.checkbox("Comments required")
        if st.form_submit_button("Save rule") and name:
            save_approval_rule({
                "name": name, "doc_type": doc_type, "department": dept or None,
                "min_amount": min_amt, "max_amount": max_amt or None,
                "role": role or None, "approval_level": int(level),
                "active": 1, "escalate_after_hours": escalate or None,
                "comments_required": 1 if comments_req else 0,
                "created_by": uid(),
            })
            ff.action_done("Rule saved.")

    rules = list_approval_rules()
    if rules:
        df = pd.DataFrame(rules)
        show = [c for c in ("name", "doc_type", "approval_level", "role", "min_amount", "max_amount", "active") if c in df.columns]
        render_dataframe_html_table(df[show])


def _matrix_tab():
    section_header("Approval matrix by document & level")
    rules = list_approval_rules()
    if not rules:
        st.info("No rules defined.")
        return
    matrix = {}
    for r in rules:
        if not r.get("active"):
            continue
        key = (r["doc_type"], int(r.get("approval_level") or 1))
        matrix.setdefault(key, []).append(r.get("role") or f"user:{r.get('user_id')}")
    rows = [{"Document": k[0], "Level": k[1], "Approvers": ", ".join(v)} for k, v in sorted(matrix.items())]
    render_dataframe_html_table(pd.DataFrame(rows))


def _history_tab():
    section_header("Recent approval actions")
    with db.get_connection() as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='erp_approval_history'").fetchone():
            st.info("No history yet.")
            return
        rows = conn.execute(
            """SELECT h.*, u.full_name AS acted_by_name
               FROM erp_approval_history h
               LEFT JOIN users u ON u.id=h.acted_by
               ORDER BY h.acted_at DESC LIMIT 100"""
        ).fetchall()
    if rows:
        render_dataframe_html_table(pd.DataFrame([dict(r) for r in rows]))


def _delegation_tab():
    section_header("Approval delegation")
    users = {u["username"]: u["id"] for u in db.get_users() if u.get("is_active")}
    with st.form("deleg_form"):
        c1, c2 = st.columns(2)
        from_u = c1.selectbox("From user", list(users.keys()))
        to_u = c2.selectbox("Delegate to", list(users.keys()))
        doc_type = st.selectbox("Document type (blank=all)", [""] + sorted({s.key for s in all_document_specs()}))
        vfrom = st.date_input("Valid from")
        vto = st.date_input("Valid to")
        if st.form_submit_button("Save delegation") and from_u != to_u:
            with db.get_connection() as conn:
                conn.execute(
                    """INSERT INTO erp_approval_delegation
                       (from_user_id, to_user_id, doc_type, valid_from, valid_to, active, created_by)
                       VALUES (?,?,?,?,?,1,?)""",
                    (users[from_u], users[to_u], doc_type or None, str(vfrom), str(vto), uid()),
                )
            ff.action_done("Delegation saved.")

    with db.get_connection() as conn:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='erp_approval_delegation'").fetchone():
            dels = conn.execute(
                """SELECT d.*, u1.username AS from_user, u2.username AS to_user
                   FROM erp_approval_delegation d
                   JOIN users u1 ON u1.id=d.from_user_id
                   JOIN users u2 ON u2.id=d.to_user_id
                   WHERE d.active=1 ORDER BY d.id DESC"""
            ).fetchall()
            if dels:
                render_dataframe_html_table(pd.DataFrame([dict(r) for r in dels]))
