"""Session-only UX preferences — favorites & recents (no database)."""

from __future__ import annotations

import streamlit as st

_FAV_KEY = "erp_ui_favorites"
_RECENT_SCREENS_KEY = "erp_ui_recent_screens"
_RECENT_DOCS_KEY = "erp_ui_recent_docs"
_MAX_FAV = 12
_MAX_RECENT_SCREENS = 8
_MAX_RECENT_DOCS = 10


def _favorites() -> list[dict]:
    raw = st.session_state.get(_FAV_KEY)
    if not isinstance(raw, list):
        raw = []
        st.session_state[_FAV_KEY] = raw
    return raw


def is_favorite(group: str, screen: str) -> bool:
    g, s = (group or "").strip(), (screen or "").strip()
    return any(f.get("group") == g and f.get("screen") == s for f in _favorites())


def toggle_favorite(group: str, screen: str, label: str) -> bool:
    """Toggle favorite; returns True if now favorited."""
    g, s = (group or "").strip(), (screen or "").strip()
    if not g or not s or s == "Dashboard":
        return False
    favs = _favorites()
    for i, f in enumerate(favs):
        if f.get("group") == g and f.get("screen") == s:
            favs.pop(i)
            return False
    favs.insert(0, {"group": g, "screen": s, "label": label or s})
    st.session_state[_FAV_KEY] = favs[:_MAX_FAV]
    return True


def list_favorites() -> list[dict]:
    return list(_favorites())


def track_recent_screen(group: str, screen: str) -> None:
    g, s = (group or "").strip(), (screen or "").strip()
    if not g or not s or s == "Dashboard":
        return
    from erp_ui.nav import module_title, screen_title

    label = f"{module_title(g)} / {screen_title(s)}"
    rows = st.session_state.get(_RECENT_SCREENS_KEY) or []
    rows = [r for r in rows if not (r.get("group") == g and r.get("screen") == s)]
    rows.insert(0, {"group": g, "screen": s, "label": label})
    st.session_state[_RECENT_SCREENS_KEY] = rows[:_MAX_RECENT_SCREENS]


def list_recent_screens() -> list[dict]:
    return list(st.session_state.get(_RECENT_SCREENS_KEY) or [])


def track_recent_doc(doc_no: str, *, label: str = "", group: str = "", screen: str = "") -> None:
    doc = (doc_no or "").strip()
    if not doc:
        return
    rows = st.session_state.get(_RECENT_DOCS_KEY) or []
    rows = [r for r in rows if r.get("doc_no") != doc]
    rows.insert(0, {
        "doc_no": doc,
        "label": label or doc,
        "group": group,
        "screen": screen,
    })
    st.session_state[_RECENT_DOCS_KEY] = rows[:_MAX_RECENT_DOCS]


def list_recent_docs() -> list[dict]:
    return list(st.session_state.get(_RECENT_DOCS_KEY) or [])


# --- Home dashboard section visibility (per browser session) ---
_HOME_LAYOUT_KEY = "erp_home_layout"


def _home_layout() -> dict:
    raw = st.session_state.get(_HOME_LAYOUT_KEY)
    if not isinstance(raw, dict):
        raw = {}
        st.session_state[_HOME_LAYOUT_KEY] = raw
    # Defaults (merge so older sessions pick up new keys)
    for key, default in (
        ("show_business_pulse", True),
        ("show_books_health", True),
        ("show_quick_actions", True),
        ("show_my_work", True),
    ):
        raw.setdefault(key, default)
    return raw


def home_section_visible(section: str) -> bool:
    """section: business_pulse | books_health | quick_actions | my_work"""
    layout = _home_layout()
    return bool(layout.get(f"show_{section}", True))


def set_home_section_visible(section: str, visible: bool) -> None:
    layout = _home_layout()
    layout[f"show_{section}"] = bool(visible)
    st.session_state[_HOME_LAYOUT_KEY] = layout


def render_home_layout_controls() -> None:
    """Toggle Business Pulse / Books Health / Quick Actions / My Work on home."""
    layout = _home_layout()
    with st.expander("Home layout — show / hide sections", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        pulse = c1.checkbox(
            "Business Pulse",
            value=bool(layout.get("show_business_pulse", True)),
            key="home_layout_pulse",
        )
        health = c2.checkbox(
            "Books Health",
            value=bool(layout.get("show_books_health", True)),
            key="home_layout_books_health",
        )
        qa = c3.checkbox(
            "Quick Actions",
            value=bool(layout.get("show_quick_actions", True)),
            key="home_layout_qa",
        )
        mw = c4.checkbox(
            "My Work",
            value=bool(layout.get("show_my_work", True)),
            key="home_layout_mywork",
        )
        changed = (
            pulse != bool(layout.get("show_business_pulse", True))
            or health != bool(layout.get("show_books_health", True))
            or qa != bool(layout.get("show_quick_actions", True))
            or mw != bool(layout.get("show_my_work", True))
        )
        if changed:
            set_home_section_visible("business_pulse", pulse)
            set_home_section_visible("books_health", health)
            set_home_section_visible("quick_actions", qa)
            set_home_section_visible("my_work", mw)
            st.rerun()
        st.caption("These choices apply on this device until you sign out.")
