"""Register UX — saved filters, density mode, recent searches (session)."""

from __future__ import annotations

import streamlit as st

_SAVED_KEY = "erp_saved_register_filters"
_DENSITY_KEY = "erp_density_compact"
_RECENT_SEARCH_KEY = "erp_recent_searches"
_MAX_SAVED = 8
_MAX_RECENT = 8


def is_density_compact() -> bool:
    return bool(st.session_state.get(_DENSITY_KEY))


def set_density_compact(compact: bool) -> None:
    st.session_state[_DENSITY_KEY] = bool(compact)


def list_saved_filters(key_prefix: str) -> list[dict]:
    bucket = st.session_state.get(_SAVED_KEY) or {}
    rows = bucket.get(key_prefix) or []
    return list(rows) if isinstance(rows, list) else []


def save_register_filter(key_prefix: str, label: str, snapshot: dict) -> None:
    label = (label or "").strip() or "Saved filter"
    bucket = dict(st.session_state.get(_SAVED_KEY) or {})
    rows = list(bucket.get(key_prefix) or [])
    rows = [r for r in rows if (r.get("label") or "").strip() != label]
    rows.insert(0, {"label": label, "snapshot": dict(snapshot)})
    bucket[key_prefix] = rows[:_MAX_SAVED]
    st.session_state[_SAVED_KEY] = bucket


def apply_register_filter(key_prefix: str, snapshot: dict) -> None:
    for widget_key, val in (snapshot or {}).items():
        if widget_key and val is not None:
            st.session_state[str(widget_key)] = val
    st.session_state.pop(f"{key_prefix}_period_applied", None)
    st.session_state[f"{key_prefix}_page"] = 1


def track_recent_search(query: str) -> None:
    q = (query or "").strip()
    if len(q) < 2:
        return
    rows = list(st.session_state.get(_RECENT_SEARCH_KEY) or [])
    rows = [r for r in rows if r != q]
    rows.insert(0, q)
    st.session_state[_RECENT_SEARCH_KEY] = rows[:_MAX_RECENT]


def list_recent_searches() -> list[str]:
    return list(st.session_state.get(_RECENT_SEARCH_KEY) or [])


def capture_filter_widgets(key_prefix: str) -> dict:
    """Snapshot Streamlit widget keys for a register filter bar."""
    keys = [
        f"{key_prefix}_q",
        f"{key_prefix}_period",
        f"{key_prefix}_fd",
        f"{key_prefix}_td",
        f"{key_prefix}_party",
        f"{key_prefix}_status",
        f"{key_prefix}_pay",
        f"{key_prefix}_ps",
        f"{key_prefix}_sort_label",
    ]
    snap = {}
    for k in keys:
        if k in st.session_state:
            val = st.session_state[k]
            if hasattr(val, "isoformat"):
                snap[k] = str(val)
            else:
                snap[k] = val
    return snap
