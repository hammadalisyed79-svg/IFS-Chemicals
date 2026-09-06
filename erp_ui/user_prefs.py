"""UX preferences — favorites/recents (session) + home layout (persisted per user)."""

from __future__ import annotations

import json

import streamlit as st

_FAV_KEY = "erp_ui_favorites"
_RECENT_SCREENS_KEY = "erp_ui_recent_screens"
_RECENT_DOCS_KEY = "erp_ui_recent_docs"
_MAX_FAV = 12
_MAX_RECENT_SCREENS = 8
_MAX_RECENT_DOCS = 10

_HOME_LAYOUT_KEY = "erp_home_layout"
_HOME_LAYOUT_LOADED_KEY = "erp_home_layout_loaded_uid"
_HOME_LAYOUT_PREF = "home_layout"
_HOME_LAYOUT_DEFAULTS = {
    "show_business_pulse": True,
    "show_books_health": True,
    "show_quick_actions": True,
    "show_my_work": True,
}


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


# --- Home dashboard section visibility (persisted per user in DB) ---

def _ensure_ui_prefs_table(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS user_ui_prefs (
               user_id INTEGER NOT NULL,
               pref_key TEXT NOT NULL,
               pref_value TEXT NOT NULL,
               updated_at TEXT,
               PRIMARY KEY (user_id, pref_key)
           )"""
    )


def _current_user_id() -> int | None:
    u = st.session_state.get("user") or {}
    try:
        uid = int(u.get("id") or 0)
    except (TypeError, ValueError):
        return None
    return uid or None


def _load_home_layout_from_db(user_id: int) -> dict | None:
    from database import get_connection

    try:
        with get_connection() as conn:
            _ensure_ui_prefs_table(conn)
            row = conn.execute(
                """SELECT pref_value FROM user_ui_prefs
                   WHERE user_id=? AND pref_key=?""",
                (int(user_id), _HOME_LAYOUT_PREF),
            ).fetchone()
        if not row or not row[0]:
            return None
        data = json.loads(row[0])
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _save_home_layout_to_db(user_id: int, layout: dict) -> None:
    from database import get_connection
    from datetime import datetime

    payload = json.dumps({k: bool(layout.get(k, True)) for k in _HOME_LAYOUT_DEFAULTS})
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        _ensure_ui_prefs_table(conn)
        conn.execute(
            """INSERT INTO user_ui_prefs(user_id, pref_key, pref_value, updated_at)
               VALUES(?,?,?,?)
               ON CONFLICT(user_id, pref_key) DO UPDATE SET
                 pref_value=excluded.pref_value,
                 updated_at=excluded.updated_at""",
            (int(user_id), _HOME_LAYOUT_PREF, payload, ts),
        )


_HOME_LAYOUT_WIDGET_KEYS = (
    "home_layout_pulse",
    "home_layout_books_health",
    "home_layout_qa",
    "home_layout_mywork",
)


def _sync_home_layout_widgets(layout: dict) -> None:
    """Keep Streamlit checkbox widget state aligned with saved prefs."""
    st.session_state["home_layout_pulse"] = bool(layout.get("show_business_pulse", True))
    st.session_state["home_layout_books_health"] = bool(layout.get("show_books_health", True))
    st.session_state["home_layout_qa"] = bool(layout.get("show_quick_actions", True))
    st.session_state["home_layout_mywork"] = bool(layout.get("show_my_work", True))


def clear_home_layout_session() -> None:
    """Drop in-memory home layout so the next login reloads from DB."""
    st.session_state.pop(_HOME_LAYOUT_KEY, None)
    st.session_state.pop(_HOME_LAYOUT_LOADED_KEY, None)
    for key in _HOME_LAYOUT_WIDGET_KEYS:
        st.session_state.pop(key, None)


def load_home_layout_for_user(user: dict | None = None) -> None:
    """Load saved home layout into session (call after login / session restore)."""
    u = user or st.session_state.get("user") or {}
    try:
        uid = int(u.get("id") or 0)
    except (TypeError, ValueError):
        uid = 0
    if not uid:
        return
    saved = _load_home_layout_from_db(uid) or {}
    layout = dict(_HOME_LAYOUT_DEFAULTS)
    for k in _HOME_LAYOUT_DEFAULTS:
        if k in saved:
            layout[k] = bool(saved[k])
    st.session_state[_HOME_LAYOUT_KEY] = layout
    st.session_state[_HOME_LAYOUT_LOADED_KEY] = uid
    _sync_home_layout_widgets(layout)


def _home_layout() -> dict:
    uid = _current_user_id()
    loaded_for = st.session_state.get(_HOME_LAYOUT_LOADED_KEY)
    if uid and loaded_for != uid:
        load_home_layout_for_user()
    raw = st.session_state.get(_HOME_LAYOUT_KEY)
    if not isinstance(raw, dict):
        raw = {}
        st.session_state[_HOME_LAYOUT_KEY] = raw
    for key, default in _HOME_LAYOUT_DEFAULTS.items():
        raw.setdefault(key, default)
    return raw


def home_section_visible(section: str) -> bool:
    """section: business_pulse | books_health | quick_actions | my_work"""
    layout = _home_layout()
    return bool(layout.get(f"show_{section}", True))


def save_home_layout(layout: dict) -> None:
    """Persist full home layout to session + DB."""
    cleaned = dict(_HOME_LAYOUT_DEFAULTS)
    for k in _HOME_LAYOUT_DEFAULTS:
        cleaned[k] = bool(layout.get(k, cleaned[k]))
    st.session_state[_HOME_LAYOUT_KEY] = cleaned
    uid = _current_user_id()
    if uid:
        st.session_state[_HOME_LAYOUT_LOADED_KEY] = uid
        try:
            _save_home_layout_to_db(uid, cleaned)
        except Exception:
            pass


def set_home_section_visible(section: str, visible: bool) -> None:
    layout = _home_layout()
    layout[f"show_{section}"] = bool(visible)
    save_home_layout(layout)


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
            save_home_layout({
                "show_business_pulse": pulse,
                "show_books_health": health,
                "show_quick_actions": qa,
                "show_my_work": mw,
            })
            st.rerun()
        st.caption("Saved to your account — stays after sign-out until you change it.")
