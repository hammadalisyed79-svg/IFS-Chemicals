"""IFS Industrial ERP — Distributor Portal entry (/portal via reverse proxy)."""

from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from erp_version import APP_NAME, APP_VERSION_FULL
from erp_ui.layout_styles import inject_layout_styles
from erp_ui.auth_session import restore_session, clear_session, enforce_active_session, pop_session_ended_message
from erp_ui import portal_pages
from application import data_gateway as db

try:
    st.set_page_config(
        page_title=f"{APP_NAME} Portal {APP_VERSION_FULL}",
        page_icon="🏪",
        layout="wide",
        initial_sidebar_state="expanded",
    )
except Exception:
    pass


inject_layout_styles()
db.init_db()

if "user" not in st.session_state:
    st.session_state.user = None

if st.session_state.user:
    enforce_active_session()
else:
    restore_session()

from erp_ui import form_flow as ff
ff.render_flash()

if not st.session_state.user:
    from erp_core.v15_security import client_context
    st.markdown(f"## {APP_NAME} — Distributor Portal")
    ended = pop_session_ended_message()
    if ended:
        st.warning(ended)
    with st.form("portal_login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in", type="primary", use_container_width=True):
            ip, ua = client_context()
            user = db.authenticate(username, password, ip=ip, user_agent=ua)
            if user and user.get("_error"):
                st.error(user["_error"])
            elif user:
                from erp_core.v15_security import is_portal_user
                if not is_portal_user(user):
                    st.error("This login is for distributor accounts only.")
                else:
                    from erp_ui.auth_session import create_and_persist_session
                    create_and_persist_session(user)
                    st.rerun()
            else:
                st.error("Invalid credentials.")
else:
    from erp_core.v15_security import is_portal_user
    if not is_portal_user(st.session_state.user):
        st.error("Internal ERP users must use the main application.")
        if st.button("Sign out"):
            clear_session()
            st.rerun()
    else:
        portal_pages.render_portal_app(st.session_state.user)
