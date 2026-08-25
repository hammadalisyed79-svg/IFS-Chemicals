"""V13.14 — enterprise search toolbar widget."""

from __future__ import annotations

import streamlit as st

from erp_core.enterprise_search import enterprise_search
from erp_ui.nav import go_screen, request_nav
from erp_ui.register_prefs import list_recent_searches, track_recent_search


def render_enterprise_search(*, key_prefix: str = "ent_srch") -> None:
    """Search box — open first match or pick from results; remembers recent queries."""
    recent = list_recent_searches()
    if recent:
        chips = " · ".join(f"`{q}`" for q in recent[:6])
        st.caption(f"Recent: {chips}")

    with st.form(key=f"{key_prefix}_form", clear_on_submit=False):
        q = st.text_input(
            "Enterprise Search",
            key=f"{key_prefix}_q",
            placeholder="Invoice, voucher, customer, supplier, item, employee, batch…",
            label_visibility="collapsed",
        )
        b1, b2 = st.columns(2)
        open_first = b1.form_submit_button("Open first match", type="primary", use_container_width=True)
        show_all = b2.form_submit_button("Show results", use_container_width=True)

    query = (q or "").strip()
    if not query:
        return

    if open_first:
        hits = enterprise_search(query, limit=12)
        if hits:
            track_recent_search(query)
            _open_hit(hits[0])
        else:
            st.caption("No results.")
        return

    if not show_all:
        return

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
                track_recent_search(query)
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
