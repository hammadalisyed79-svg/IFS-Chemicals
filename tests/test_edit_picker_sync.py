"""Regression: edit forms must not reuse header/lines from a previously picked record."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import streamlit as st  # noqa: E402

from erp_ui import form_flow as ff  # noqa: E402


def test_sync_edit_record_clears_stale_buffer():
    st.session_state.clear()
    st.session_state["sal_edit_id"] = 10
    st.session_state["sal_edit_header"] = {"customer_id": 826}
    st.session_state["sal_edit_lines"] = [{"item_id": 1}]
    st.session_state["sal_edit_picker_id"] = 10

    ff.sync_edit_record("sal_edit", 11)

    assert st.session_state.get("sal_edit_id") is None
    assert st.session_state.get("sal_edit_header") is None
    assert st.session_state.get("sal_edit_lines") is None
    assert st.session_state["sal_edit_picker_id"] == 11
    assert ff.form_generation("sal_edit_hdr") == 1


def test_edit_record_loaded():
    st.session_state.clear()
    st.session_state["sal_edit_id"] = 99
    assert ff.edit_record_loaded("sal_edit", 99)
    assert not ff.edit_record_loaded("sal_edit", 100)


if __name__ == "__main__":
    test_sync_edit_record_clears_stale_buffer()
    test_edit_record_loaded()
    print("PASS edit picker sync")
