"""System audit log — view and export user activity."""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from application import data_gateway as db
import db_audit
from erp_ui.helpers import std_page_header, uid, render_dataframe_html_table
from erp_ui.report_print import report_toolbar


def _require_admin_view():
    user = st.session_state.get("user")
    if not user:
        st.error("Please sign in.")
        st.stop()
    if user.get("role") == "admin":
        return
    if db.user_can(user, "Admin", "view"):
        return
    st.error("Audit log requires **Admin** access.")
    st.stop()


def page_audit_log():
    _require_admin_view()
    std_page_header("Audit Log", status="register", status_kind="shell")

    today = date.today()
    c1, c2, c3, c4 = st.columns(4)
    fd = c1.date_input("From", value=today - timedelta(days=30), key="aud_from")
    td = c2.date_input("To", value=today, key="aud_to")
    tbl = c3.selectbox("Entity", db_audit.audit_table_options(), key="aud_tbl")
    act = c4.selectbox(
        "Action",
        ["All"] + sorted(db_audit.ACTION_LABELS.keys()),
        format_func=lambda x: db_audit.ACTION_LABELS.get(x, x) if x != "All" else "All",
        key="aud_act",
    )

    users = db.get_users()
    user_opts = {"All users": None}
    for u in users:
        user_opts[f"{u['username']} — {u['full_name']}"] = u["id"]

    c5, c6 = st.columns([2, 1])
    user_lbl = c5.selectbox("User", list(user_opts.keys()), key="aud_user")
    search = c6.text_input("Search", placeholder="Doc no, name, detail…", key="aud_q")

    if st.button("Load audit log", type="primary", key="aud_run"):
        rows = db_audit.search_audit_log(
            str(fd), str(td),
            user_id=user_opts.get(user_lbl),
            table_name=tbl,
            action=act,
            search=search or None,
            limit=1000,
        )
        st.session_state["audit_rows"] = rows

    rows = st.session_state.get("audit_rows")
    if rows is None:
        st.info("Set filters and click **Load audit log**.")
        return

    if not rows:
        st.warning("No audit entries for these filters.")
        return

    df = pd.DataFrame([{
        "When": (r.get("created_at") or "")[:19],
        "User": r.get("user_name") or r.get("username") or "—",
        "Action": r.get("action_label"),
        "Entity": r.get("entity"),
        "Record ID": r.get("record_id") if r.get("record_id") is not None else "",
        "Document": r.get("document_no") or "",
        "Summary": r.get("summary"),
        "Module": r.get("module") or "",
    } for r in rows])

    st.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Entries</p>"
        f"<p class='txn-kpi-val'>{len(df):,}</p></div>",
        unsafe_allow_html=True,
    )
    render_dataframe_html_table(df)

    with st.expander("Raw detail (last 50)", expanded=False):
        for r in rows[:50]:
            st.markdown(
                f"**{r.get('created_at', '')[:19]}** — {r.get('user_name', '—')} — "
                f"{r.get('action_label')} — {r.get('summary')}"
            )
            if r.get("details"):
                st.caption(r["details"])

    report_toolbar(
        df,
        "System Audit Log",
        "audit_log",
        period=f"{fd} to {td}",
        filters={"Entity": tbl, "Action": act, "User": user_lbl},
        key_prefix="aud_export",
        layout="landscape",
    )
