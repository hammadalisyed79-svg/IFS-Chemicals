"""Change password screen — V15 strong password policy."""

from __future__ import annotations

import streamlit as st

from application import data_gateway as db
from erp_core.v15_security import validate_password_strength, verify_password


def render_change_password(user: dict, *, force: bool = False) -> bool:
    """Render change-password form.

    Returns True when the password was updated successfully this run
    (or when a forced change is no longer required).
    """
    must = force or bool(user.get("must_change_password"))
    if must:
        st.warning("You must change your password before continuing.")

    with st.form("change_password_form"):
        current = st.text_input("Current password", type="password")
        new_pw = st.text_input("New password", type="password")
        confirm = st.text_input("Confirm new password", type="password")
        submitted = st.form_submit_button("Update password", type="primary", use_container_width=True)
        if submitted:
            if not verify_password(current, _user_hash(user["id"])):
                st.error("Current password is incorrect.")
                return False
            if new_pw != confirm:
                st.error("New passwords do not match.")
                return False
            ok, msg = validate_password_strength(new_pw)
            if not ok:
                st.error(msg)
                return False
            try:
                db.change_user_password(user["id"], new_pw)
                st.session_state.user = db.get_user_by_id(user["id"]) or user
                st.success("Password updated.")
                return True
            except Exception as e:
                st.error(str(e))
                return False
    return False


def _user_hash(user_id: int) -> str:
    with db.get_connection() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id=?", (user_id,)).fetchone()
        return row[0] if row else ""
