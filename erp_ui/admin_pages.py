"""Admin pages — users and backup — extracted from app.py."""

from datetime import date

import streamlit as st
from application import data_gateway as db
from erp_ui import helpers as hlp
from erp_ui import form_flow as ff


def page_users():
    from erp_ui.helpers import sticky_page_tabs
    from html import escape

    hlp.std_page_header("User Management")
    tab = sticky_page_tabs(["Users", "Add User", "Edit / Delete"], "users_page_tab")

    if tab == "Users":
        rows = db.get_users()
        if rows:
            ths = "".join(f"<th>{h}</th>" for h in ("Username", "Full Name", "Role", "Active"))
            body = []
            for r in rows:
                active = bool(r.get("is_active"))
                badge = (
                    '<span class="inv-badge inv-badge-approved">Active</span>'
                    if active
                    else '<span class="inv-badge inv-badge-cancelled">Inactive</span>'
                )
                body.append(
                    "<tr>"
                    f"<td>{escape(str(r.get('username') or ''))}</td>"
                    f"<td>{escape(str(r.get('full_name') or ''))}</td>"
                    f"<td>{escape(str(r.get('role') or ''))}</td>"
                    f"<td class='txn-status-cell'>{badge}</td>"
                    "</tr>"
                )
            st.markdown(
                f"<div class='txn-kpi-card'><p class='txn-kpi'>Users</p>"
                f"<p class='txn-kpi-val'>{len(rows):,}</p></div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="txn-reg-wrap"><table class="txn-reg-table">'
                f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
                unsafe_allow_html=True,
            )
        else:
            st.info("No users.")

    elif tab == "Add User":
        if st.session_state.pop("user_add_success", None):
            st.success("User created. Add another below.")
        form_key = f"add_user_{st.session_state.get('user_add_form_id', 0)}"
        with st.form(form_key):
            username = st.text_input("Username *")
            full_name = st.text_input("Full Name *")
            password = st.text_input("Password *", type="password")
            role = st.selectbox("Role", ["admin", "user"])
            if st.form_submit_button("Create User", type="primary"):
                if not username or not full_name or not password:
                    st.error("All fields required.")
                else:
                    try:
                        db.add_user(username, password, full_name, role)
                        st.session_state["user_add_success"] = True
                        st.session_state["user_add_form_id"] = st.session_state.get("user_add_form_id", 0) + 1
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

    elif tab == "Edit / Delete":
        rows = db.get_users()
        if not rows:
            st.info("No users.")
            return
        opts = {f"{r['username']} - {r['full_name']}": r for r in rows}
        sel = st.selectbox("Select User", list(opts.keys()))
        if not sel:
            return
        u = opts[sel]
        with st.form("edit_user"):
            full_name = st.text_input("Full Name", value=u["full_name"])
            role = st.selectbox("Role", ["admin", "user"], index=0 if u["role"] == "admin" else 1)
            active = st.checkbox("Active", value=bool(u["is_active"]))
            new_pass = st.text_input("New Password (leave blank to keep)", type="password")
            c1, c2 = st.columns(2)
            if c1.form_submit_button("Update"):
                db.update_user(u["id"], full_name, role, int(active), new_pass or None)
                ff.action_done("User updated.")
            if c2.form_submit_button("Delete") and u["username"] != "admin":
                db.delete_user(u["id"])
                ff.action_done("User deleted.")


def page_backup_restore():
    hlp.std_page_header("Backup & Restore")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Backup Database")
        if st.button("Create Backup Now"):
            path = db.backup_database()
            st.success(f"Backup saved: {path}")
    with c2:
        st.subheader("Restore Database")
        st.warning("Restore will overwrite the current database. Restart the app after restore.")
        uploaded = st.file_uploader("Select backup .db file", type=["db"])
        if uploaded and st.button("Restore from Upload"):
            import tempfile, os
            tmp = os.path.join(tempfile.gettempdir(), uploaded.name)
            with open(tmp, "wb") as f:
                f.write(uploaded.getbuffer())
            db.restore_database(tmp)
            st.success("Database restored. Please restart the application.")

