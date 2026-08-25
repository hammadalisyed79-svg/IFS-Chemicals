"""Universal page shell — breadcrumb, title, KPIs, status badges, footer (Option D)."""

from __future__ import annotations

from html import escape

import streamlit as st

from erp_ui.invoice_status_ui import status_badge_html

SHELL_STATUS_META = {
    "draft": ("Draft", "erp-shell-badge-draft"),
    "pending_approval": ("Pending", "erp-shell-badge-pending"),
    "approved": ("Posted", "erp-shell-badge-posted"),
    "posted": ("Posted", "erp-shell-badge-posted"),
    "partial": ("Partial", "erp-shell-badge-pending"),
    "open": ("Open", "erp-shell-badge-pending"),
    "register": ("Register", "erp-shell-badge-shadow"),
    "settled": ("Settled", "erp-shell-badge-posted"),
    "shadow": ("Shadow", "erp-shell-badge-shadow"),
    "cancelled": ("Cancelled", "erp-shell-badge-muted"),
    "rejected": ("Rejected", "erp-shell-badge-rejected"),
}


def shell_status_badge(status: str | None, *, kind: str = "invoice") -> str:
    if kind == "invoice":
        return status_badge_html(status)
    key = (status or "").lower()
    meta = SHELL_STATUS_META.get(key, (status or "—", "erp-shell-badge-muted"))
    label, css = meta
    return f'<span class="erp-shell-badge {css}">{escape(label)}</span>'


def breadcrumb_from_session() -> list[str]:
    group = st.session_state.get("sidebar_group")
    screen = st.session_state.get("sidebar_screen")
    if not group or screen == "Dashboard":
        return []
    from erp_ui.nav import module_title, screen_title
    return ["Home", module_title(group), screen_title(screen)]


def render_breadcrumb(crumbs: list[str] | None = None, *, clickable: bool = True) -> None:
    parts = crumbs if crumbs is not None else breadcrumb_from_session()
    if not parts:
        return
    if not clickable:
        trail = " › ".join(escape(p) for p in parts)
        st.markdown(f'<p class="erp-shell-crumb">{trail}</p>', unsafe_allow_html=True)
        return

    from erp_ui.nav import go_home, go_module

    group = st.session_state.get("sidebar_group")
    cols = st.columns(len(parts))
    for i, part in enumerate(parts):
        with cols[i]:
            label = part
            if i == 0 and part == "Home":
                if st.button(label, key=f"erp_crumb_home_{id(parts)}", use_container_width=True):
                    go_home()
            elif i == 1 and group and len(parts) > 2:
                if st.button(label, key=f"erp_crumb_mod_{group}", use_container_width=True):
                    go_module(group)
            else:
                st.markdown(
                    f'<p class="erp-shell-crumb-active">{escape(label)}</p>',
                    unsafe_allow_html=True,
                )


def render_page_header_block(
    title: str,
    subtitle: str = "",
    *,
    compact: bool = True,
    status: str | None = None,
    status_kind: str = "shell",
    crumbs: list[str] | None = None,
) -> None:
    crumbs_list = crumbs if crumbs is not None else breadcrumb_from_session()
    render_breadcrumb(crumbs_list)
    t = escape(title)
    s = escape(subtitle) if subtitle else ""
    badge = ""
    if status:
        badge = shell_status_badge(status, kind=status_kind)
    # Screen name is already the active breadcrumb — avoid repeating it in the title line.
    dedupe_title = bool(crumbs_list) and crumbs_list[-1] == title
    if dedupe_title:
        if s and compact:
            st.markdown(
                f'<div class="page-header-wrap page-header-compact erp-page-shell">'
                f'<p class="sub-header erp-shell-sub-only">{s}{badge}</p></div>',
                unsafe_allow_html=True,
            )
        elif s:
            st.markdown(
                f'<div class="page-header-wrap erp-page-shell">'
                f'<p class="sub-header">{s}{badge}</p></div>',
                unsafe_allow_html=True,
            )
        elif badge:
            st.markdown(
                f'<div class="page-header-wrap page-header-compact erp-page-shell">'
                f'<p class="main-header">{badge}</p></div>',
                unsafe_allow_html=True,
            )
        return
    if s and compact:
        st.markdown(
            f'<div class="page-header-wrap page-header-compact erp-page-shell">'
            f'<p class="main-header">{t}'
            f'{badge}'
            f'<span class="page-header-sub-inline"> — {s}</span></p>'
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        sub = f'<p class="sub-header">{s}</p>' if s else ""
        st.markdown(
            f'<div class="page-header-wrap erp-page-shell">'
            f'<p class="main-header">{t}{badge}</p>{sub}</div>',
            unsafe_allow_html=True,
        )


def render_kpi_strip(metrics: list[dict], *, columns: int | None = None) -> None:
    """metrics: [{label, value, help?}]"""
    if not metrics:
        return
    n = columns or min(len(metrics), 6)
    cols = st.columns(n, gap="small")
    for col, m in zip(cols, metrics):
        with col:
            col.metric(
                m.get("label", ""),
                m.get("value", ""),
                help=m.get("help"),
            )


def render_page_footer(
    *,
    doc_no: str = "",
    posted_by: str = "",
    extra: str = "",
) -> None:
    bits = []
    if doc_no:
        bits.append(f"Document **{doc_no}**")
    if posted_by:
        bits.append(f"Posted by **{posted_by}**")
    if extra:
        bits.append(extra)
    if bits:
        st.markdown(
            f'<p class="erp-shell-footer">{" · ".join(bits)}</p>',
            unsafe_allow_html=True,
        )


def render_sticky_action_bar(
    actions: list[dict],
    *,
    key_prefix: str = "shell_act",
) -> str | None:
    """Render a horizontal action row. Returns label of clicked button, if any."""
    if not actions:
        return None
    st.markdown('<div class="erp-shell-action-bar-marker"></div>', unsafe_allow_html=True)
    clicked = None
    with st.container(key=f"{key_prefix}_bar"):
        cols = st.columns(len(actions))
        for col, act in zip(cols, actions):
            with col:
                key = act.get("key") or f"{key_prefix}_{act.get('label','')}"
                if st.button(
                    act.get("label", "Action"),
                    key=key,
                    type=act.get("type", "secondary"),
                    help=act.get("help"),
                    disabled=bool(act.get("disabled")),
                    use_container_width=True,
                ):
                    clicked = act.get("label", "Action")
    return clicked


def render_favorites_bar(nav: dict, *, key_prefix: str = "fav") -> None:
    from erp_ui.user_prefs import is_favorite, list_favorites, list_recent_docs, list_recent_screens, toggle_favorite
    from erp_ui.nav import go_screen, screen_title
    from erp_ui.doc_workflow import open_recent_document

    group = st.session_state.get("sidebar_group", "")
    screen = st.session_state.get("sidebar_screen", "")
    if screen and screen != "Dashboard":
        fav_now = is_favorite(group, screen)
        pin_label = "Unpin screen" if fav_now else "Pin screen"
        if st.button(pin_label, key=f"{key_prefix}_toggle", help="Pin this screen to the shortcut bar"):
            toggle_favorite(group, screen, screen_title(screen))
            st.rerun()

    favs = [
        f for f in list_favorites()
        if f.get("group") in nav and f.get("screen") in nav.get(f["group"], [])
    ]
    recents = list_recent_screens()
    recents = [r for r in recents if r.get("group") in nav and r.get("screen") in nav.get(r["group"], [])]
    docs = list_recent_docs()

    if not favs and not recents and not docs:
        return

    if favs:
        st.caption("Pinned")
        pcols = st.columns(min(len(favs), 6))
        for col, f in zip(pcols, favs[:6]):
            with col:
                lbl = f.get("label") or screen_title(f.get("screen", ""))
                if st.button(lbl, key=f"{key_prefix}_pin_{f['group']}_{f['screen']}", use_container_width=True):
                    go_screen(f["group"], f["screen"])

    if recents:
        st.caption("Recent screens")
        rcols = st.columns(min(len(recents), 6))
        for col, r in zip(rcols, recents[:6]):
            with col:
                lbl = r.get("label") or screen_title(r.get("screen", ""))
                if st.button(lbl, key=f"{key_prefix}_rc_{r['group']}_{r['screen']}", use_container_width=True):
                    go_screen(r["group"], r["screen"])

    if docs:
        st.caption("Recent documents")
        dcols = st.columns(min(len(docs), 5))
        for col, d in zip(dcols, docs[:5]):
            with col:
                lbl = d.get("label") or d.get("doc_no") or "Document"
                if st.button(lbl, key=f"{key_prefix}_doc_{d.get('doc_no', lbl)}", use_container_width=True):
                    open_recent_document(d)
                    st.rerun()
