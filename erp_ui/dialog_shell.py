"""Readable light shell for Streamlit @st.dialog modals (Phase 6)."""

from __future__ import annotations

import streamlit as st


def dialog_shell_marker() -> None:
    """Inject marker so theme CSS applies portal-style light dialog contrast."""
    st.markdown(
        '<div class="erp-dialog-card erp-css-inject" aria-hidden="true">&#8203;</div>',
        unsafe_allow_html=True,
    )
