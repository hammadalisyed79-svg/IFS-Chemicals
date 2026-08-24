"""V13.14 — enterprise search toolbar widget."""

from __future__ import annotations

import streamlit as st

from erp_core.enterprise_search import enterprise_search
from erp_ui.nav import go_screen, request_nav


def render_enterprise_search(*, key_prefix: str = "ent_srch") -> None:
    """Search box — press Enter or pick a hit to open document/master."""
    q = st.text_input(
        "Enterprise Search",
        key=f"{key_prefix}_q",
        placeholder="Invoice, voucher, customer, supplier, item, employee, batch…",
        label_visibility="collapsed",
    )
    st.caption("Type and press Enter · Tab to first result")
    submitted = q or st.session_state.get(f"{key_prefix}_q")
    if not submitted or not str(submitted).strip():
        return

    query = str(submitted).strip()
    hits = enterprise_search(query, limit=12)
    if not hits:
        st.caption("No results.")
        return

    with st.container(key=f"{key_prefix}_hits"):
        for i, hit in enumerate(hits):
            if st.button(
                f"{hit.category}: {hit.label}",
                key=f"{key_prefix}_hit_{i}",
                use_container_width=True,
            ):
                _open_hit(hit)


def _open_hit(hit) -> None:
    if hit.nav_group and hit.nav_screen:
        request_nav(hit.nav_group, hit.nav_screen)
        if hit.doc_type and hit.record_id:
            st.session_state["enterprise_open_doc_type"] = hit.doc_type
            st.session_state["enterprise_open_record_id"] = hit.record_id
            st.session_state["draft_open_id"] = hit.record_id
        elif hit.record_id:
            st.session_state["enterprise_open_master_id"] = hit.record_id
            st.session_state["enterprise_open_master_category"] = hit.category
        st.rerun()
