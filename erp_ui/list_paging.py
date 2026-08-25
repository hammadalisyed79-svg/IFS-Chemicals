"""Client-side list paging for registers/ledgers (performance)."""

from __future__ import annotations

import streamlit as st

DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500


def page_slice(items: list, key_prefix: str, *, default_size: int = DEFAULT_PAGE_SIZE) -> list:
    """Paginate a list in session; returns the current page of items."""
    if not items:
        return []
    total = len(items)
    size_key = f"{key_prefix}_page_size"
    page_key = f"{key_prefix}_page"
    if size_key not in st.session_state:
        st.session_state[size_key] = default_size
    page_size = int(st.session_state.get(size_key) or default_size)
    page_size = max(25, min(MAX_PAGE_SIZE, page_size))
    pages = max(1, (total + page_size - 1) // page_size)
    page = int(st.session_state.get(page_key) or 1)
    page = max(1, min(page, pages))
    st.session_state[page_key] = page

    c1, c2, c3, c4 = st.columns([1.2, 2, 1, 1])
    c1.caption(f"**{total:,}** rows")
    new_size = c2.selectbox(
        "Rows per page",
        [25, 50, 100, 200, 500],
        index=[25, 50, 100, 200, 500].index(page_size) if page_size in (25, 50, 100, 200, 500) else 2,
        key=f"{key_prefix}_ps_sel",
    )
    if int(new_size) != page_size:
        st.session_state[size_key] = int(new_size)
        st.session_state[page_key] = 1
        st.rerun()
    if c3.button("◀ Prev", disabled=page <= 1, key=f"{key_prefix}_prev"):
        st.session_state[page_key] = page - 1
        st.rerun()
    c3.caption(f"Page {page}/{pages}")
    if c4.button("Next ▶", disabled=page >= pages, key=f"{key_prefix}_next"):
        st.session_state[page_key] = page + 1
        st.rerun()

    start = (page - 1) * page_size
    return items[start: start + page_size]
