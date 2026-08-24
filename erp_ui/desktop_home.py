"""CEO-style desktop — IFS Chemicals red / blue / white professional theme."""

from __future__ import annotations

from datetime import datetime

import streamlit as st
from application import data_gateway as db
from erp_ui.theme import BLACK, BLUE, BLUE_DARK, BLUE_LIGHT, RED, RED_DARK, RED_LIGHT, WHITE
from erp_ui.nav import (
    GROUP_ICONS,
    SCREEN_ICONS,
    can_view_screen,
    go_home,
    go_module,
    go_screen,
    module_tagline,
    module_title,
    request_nav,
    screen_tagline,
    screen_title,
    _icon_for,
)
from erp_ui.mobile_layout import grid_columns, qa_columns, is_mobile_client

DESKTOP_CSS = f"""
<style>
/* Desktop — desktop-only layout (workspace shell in theme.py) */
body:has(.erp-desktop-root) section[data-testid="stSidebar"] {{ display: none !important; }}
body:has(.erp-desktop-root) [data-testid="stSidebarCollapsedControl"] {{ display: none !important; }}

.erp-desktop-root {{ color: {BLACK}; }}

/* Top command bar — compact, full-bleed within shell */
div[class*="st-key-desk_topbar"] {{
  width: 100% !important;
  max-width: 100% !important;
  box-sizing: border-box !important;
  margin-top: 0 !important;
  margin-bottom: 0.45rem !important;
  background: {WHITE};
  border: 1px solid rgba(29, 78, 216, 0.35);
  border-radius: 8px;
  padding: 0.35rem 0.55rem;
  box-shadow: none;
}}
div[class*="st-key-desk_topbar"] .stTextInput input {{
  border: 1px solid rgba(29, 78, 216, 0.45) !important;
  border-radius: 8px !important;
  background: {WHITE} !important;
  color: {BLACK} !important;
  min-height: 2.35rem !important;
}}
div[class*="st-key-desk_topbar"] [data-testid="stHorizontalBlock"] {{
  align-items: center !important;
  gap: 0.35rem !important;
}}
div[class*="st-key-desk_topbar"] [data-testid="column"] {{
  min-width: 0 !important;
}}
.erp-desk-brand {{
  font-size: 1.15rem;
  font-weight: 800;
  color: {BLUE_DARK};
  letter-spacing: 0.04em;
  margin: 0;
  line-height: 1.15;
}}
.erp-desk-crumb {{
  font-size: 0.75rem;
  color: {BLACK} !important;
  margin: 0.12rem 0 0 0;
  opacity: 0.72;
}}
div[class*="st-key-desk_topbar"] button {{
  color: {BLACK} !important;
  border-radius: 8px !important;
  font-weight: 600 !important;
  font-size: 0.8rem !important;
  white-space: nowrap !important;
  line-height: 1.2 !important;
  min-height: 2.35rem !important;
  padding: 0.35rem 0.55rem !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
}}
div[class*="st-key-desk_topbar"] button p {{
  white-space: nowrap !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  margin: 0 !important;
}}
div[class*="st-key-desk_approvals"] button {{
  background: {RED_LIGHT} !important;
  border: 1px solid {RED} !important;
  color: {RED_DARK} !important;
}}

/* Hero welcome strip — restrained accent */
.erp-desk-hero {{
  background: linear-gradient(105deg, {BLUE_DARK} 0%, {BLUE} 70%, #3B82F6 100%);
  border-radius: 10px;
  padding: 0.95rem 1.2rem;
  margin-bottom: 0.75rem;
  border-bottom: 2px solid {RED};
  box-shadow: 0 4px 14px rgba(30, 58, 138, 0.14);
}}
.erp-desk-hero-title {{
  font-size: clamp(1.35rem, 2.4vw, 1.75rem);
  font-weight: 800;
  color: {WHITE} !important;
  margin: 0 0 0.2rem 0;
  letter-spacing: 0.02em;
}}
.erp-desk-hero-sub {{
  color: {WHITE} !important;
  font-size: 0.9rem;
  margin: 0;
  opacity: 0.95;
  line-height: 1.4;
}}
.erp-desk-hero-sub strong {{
  color: {WHITE} !important;
  font-weight: 800;
}}
.erp-desk-hero-meta {{
  text-align: right;
  color: {WHITE} !important;
  font-size: 0.85rem;
  margin: 0;
  opacity: 0.95;
  font-weight: 600;
}}

.erp-desk-alert {{
  border: 1px solid {RED};
  background: {RED_LIGHT};
  border-radius: 8px;
  padding: 0.55rem 0.9rem;
  color: {BLACK};
  font-size: 0.85rem;
  margin-bottom: 0.75rem;
  font-weight: 600;
}}

/* Quick actions panel */
div[class*="st-key-desk_qa_panel"] {{
  background: {WHITE};
  border: 1px solid rgba(29, 78, 216, 0.35);
  border-radius: 10px;
  padding: 0.55rem 0.65rem 0.65rem;
  margin-bottom: 0.35rem;
}}
div[class*="st-key-dsk_qa_"] button {{
  background: {WHITE} !important;
  border: 1px solid rgba(29, 78, 216, 0.45) !important;
  color: {BLACK} !important;
  font-size: 0.8rem !important;
  font-weight: 700 !important;
  padding: 0.5rem 0.4rem !important;
  min-height: 2.5rem !important;
  border-radius: 8px !important;
  white-space: nowrap !important;
  line-height: 1.2 !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
}}
div[class*="st-key-dsk_qa_"] button:hover {{
  background: {BLUE_LIGHT} !important;
  border-color: {RED} !important;
}}

/* Workspace tiles */
div[class*="st-key-dsk_tile_"],
div[class*="st-key-dsk_scr_"] {{
  height: 100%;
}}
div[class*="st-key-dsk_tile_"] .stButton,
div[class*="st-key-dsk_scr_"] .stButton {{
  margin-bottom: 0;
  height: 100%;
}}
div[class*="st-key-dsk_tile_"] button,
div[class*="st-key-dsk_scr_"] button {{
  background: {WHITE} !important;
  border: 1px solid rgba(29, 78, 216, 0.4) !important;
  color: {BLACK} !important;
  min-height: 148px !important;
  height: 100% !important;
  padding: 1rem 0.9rem 0.9rem !important;
  text-align: left !important;
  white-space: pre-line !important;
  line-height: 1.45 !important;
  font-size: 0.9rem !important;
  font-weight: 700 !important;
  border-radius: 10px !important;
  box-shadow: 0 2px 10px rgba(29, 78, 216, 0.07) !important;
  transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease !important;
}}
div[class*="st-key-dsk_tile_"][class*="_red"] button,
div[class*="st-key-dsk_tile_"][class*="_hero"] button {{
  background: {WHITE} !important;
  border: 2px solid {RED} !important;
}}
div[class*="st-key-dsk_tile_"][class*="_blue"] button {{
  background: {WHITE} !important;
  border: 2px solid {BLUE} !important;
}}
div[class*="st-key-dsk_tile_"] button:hover,
div[class*="st-key-dsk_scr_"] button:hover {{
  border-color: {RED} !important;
  box-shadow: 0 6px 18px rgba(220, 38, 38, 0.12) !important;
  transform: translateY(-1px);
}}
div[class*="st-key-dsk_tile_"] button p,
div[class*="st-key-dsk_scr_"] button p {{
  margin: 0 !important;
  text-align: left !important;
  white-space: pre-line !important;
  line-height: 1.35 !important;
  color: {BLACK} !important;
  font-size: 0.78rem !important;
  font-weight: 500 !important;
}}
/* First line = module name (Sale / Purchase / …) — large */
div[class*="st-key-dsk_tile_"] button p::first-line,
div[class*="st-key-dsk_scr_"] button p::first-line {{
  font-size: 1.45rem !important;
  line-height: 1.25 !important;
  font-weight: 800 !important;
}}
/* Base button size feeds the small tagline under the module name */
div[class*="st-key-dsk_tile_"] button,
div[class*="st-key-dsk_scr_"] button {{
  font-size: 0.78rem !important;
}}

.erp-desk-module-head {{
  font-size: 1.2rem;
  font-weight: 800;
  color: {BLACK};
  margin: 0.35rem 0 0.75rem 0;
  padding: 0.45rem 0.7rem;
  background: {WHITE};
  border-left: 4px solid {BLUE};
  border-radius: 0 8px 8px 0;
}}
div[class*="st-key-desk_back_row"] button {{
  font-weight: 700 !important;
}}
.erp-desk-section {{
  margin: 0.85rem 0 0.45rem 0 !important;
  letter-spacing: 0.06em;
}}

/* My Work — compact task cards (not full-width tile buttons) */
div[class*="st-key-desk_mywork_panel"] {{
  background: {WHITE};
  border: 1px solid rgba(29, 78, 216, 0.28);
  border-radius: 10px;
  padding: 0.55rem 0.65rem 0.45rem;
  margin-bottom: 0.65rem;
}}
div[class*="st-key-desk_mywork_panel"] [data-testid="stHorizontalBlock"] {{
  align-items: stretch !important;
  gap: 0.45rem !important;
}}
div[class*="st-key-desk_mywork_panel"] button {{
  background: {BLUE_LIGHT} !important;
  border: 1px solid rgba(29, 78, 216, 0.45) !important;
  color: {BLUE_DARK} !important;
  font-size: 0.72rem !important;
  font-weight: 700 !important;
  min-height: 2rem !important;
  max-height: 2.15rem !important;
  padding: 0.2rem 0.45rem !important;
  border-radius: 6px !important;
  margin-top: 0.35rem !important;
}}
div[class*="st-key-desk_pin_panel"] button {{
  background: {WHITE} !important;
  border: 1px solid rgba(220, 38, 38, 0.35) !important;
  color: {BLACK} !important;
  font-size: 0.75rem !important;
  font-weight: 700 !important;
  min-height: 2.15rem !important;
  padding: 0.35rem 0.4rem !important;
  border-radius: 8px !important;
}}
.erp-mywork-card {{
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-left: 4px solid {RED};
  border-radius: 8px;
  padding: 0.45rem 0.55rem;
  min-height: 4.2rem;
}}
.erp-mywork-card-badge {{
  margin-bottom: 0.25rem;
}}
.erp-mywork-card-title {{
  font-size: 0.8rem;
  font-weight: 700;
  color: {BLACK};
  line-height: 1.25;
  margin: 0 0 0.2rem 0;
}}
.erp-mywork-card-detail {{
  font-size: 0.7rem;
  color: #64748b;
  line-height: 1.3;
  margin: 0;
}}
</style>
"""

QUICK_ACTIONS = [
    ("Business Intelligence", "Overview", "Business Overview"),
    ("Reports", "Reports", "Reports Center"),
    ("Sale Approval", "Sales", "Sale Approval"),
    ("Purchase Approval", "Purchases", "Purchase Approval"),
    ("Sale", "Sales", "Sales Invoices"),
    ("Purchase", "Purchases", "Purchase Invoices"),
    ("Customer Receipt", "Finance", "Customer Receipt"),
    ("Customer", "Masters", "Customers"),
    ("Product", "Masters", "Products"),
    ("Stock", "Inventory", "Stock"),
]

DESKTOP_SECTIONS = [
    {
        "title": "Executive & Intelligence",
        "tiles": [
            {
                "label": "Business Intelligence",
                "desc": "Live KPIs, liquidity and system alerts",
                "group": "Overview",
                "screen": "Business Overview",
                "hero": True,
            },
            {
                "label": "Reports Hub",
                "desc": "Operational, financial and inventory reports",
                "group": "Reports",
                "screen": "Reports Center",
            },
        ],
    },
    {
        "title": "Commercial & Operations",
        "modules": ["Sales", "Purchases", "Finance", "Inventory"],
    },
    {
        "title": "Manufacturing & Logistics",
        "modules": ["Production", "Weight Scale", "Gate Pass"],
    },
    {
        "title": "Master Data & Administration",
        "modules": ["Masters", "HR", "Administration"],
    },
]

# Kept for compatibility — prefer module_tagline()
MODULE_BLURBS = {k: module_tagline(k) for k in (
    "Sales", "Purchases", "Finance", "Inventory", "Production",
    "Weight Scale", "Gate Pass", "Masters", "HR", "Administration", "Overview", "Reports",
)}

_GRID_COLS = 4
_QA_COLS = 5


def _pending_count() -> int:
    try:
        stats = db.get_dashboard_stats()
        p = stats.get("pending_breakdown") or {}
        return int(sum([
            p.get("sales_approval", 0),
            p.get("purchase_approval", 0),
            p.get("leave", 0),
            p.get("payroll_draft", 0),
            p.get("advances", 0),
            p.get("gate_pass_open", 0),
            p.get("journal_draft", 0),
        ]))
    except Exception:
        return 0


def _flat_search_index(nav: dict) -> list[tuple[str, str, str]]:
    rows = []
    for group, screens in nav.items():
        for screen in screens:
            if screen == "Dashboard":
                continue
            label = f"{module_title(group)} / {screen_title(screen)}"
            rows.append((group, screen, label))
    return rows


def _inject_desktop_theme() -> None:
    extra = " mobile-friendly" if is_mobile_client() else ""
    # Single markdown so theme CSS can collapse the wrapper (no flex-gap stack).
    st.markdown(
        DESKTOP_CSS
        + f'<div class="erp-desktop-root{extra} erp-css-inject" aria-hidden="true">&#8203;</div>',
        unsafe_allow_html=True,
    )


def _card_button_label(icon: str, title: str, desc: str) -> str:
    """Icon + module name on first (large) line; action tagline on the next (small) line."""
    title = (title or "").strip()
    desc = (desc or "").strip()
    if desc:
        return f"{icon}  {title}\n{desc}"
    return f"{icon}  {title}"


def _desk_tile_button(
    key: str, icon: str, title: str, desc: str, action, *, hero: bool = False, variant: str = "",
) -> None:
    suffix = "_hero" if hero else (f"_{variant}" if variant else "")
    container_key = f"dsk_tile_{key}{suffix}"
    with st.container(key=container_key):
        if st.button(
            _card_button_label(icon, title, desc),
            key=f"btn_{container_key}",
            use_container_width=True,
        ):
            action()


def _desk_screen_button(
    group: str, screen: str, icon: str, title: str, desc: str, action, *, variant: str = "blue",
) -> None:
    container_key = f"dsk_scr_{group}_{screen}_{variant}"
    with st.container(key=container_key):
        if st.button(
            _card_button_label(icon, title, desc),
            key=f"btn_{container_key}",
            use_container_width=True,
        ):
            action()


def _render_tile_grid(items: list, user: dict, nav: dict) -> None:
    """Render workspace cards in a responsive grid."""
    cols_n = grid_columns(_GRID_COLS, 2)
    for row_start in range(0, len(items), cols_n):
        row = items[row_start: row_start + cols_n]
        cols = st.columns(cols_n)
        for idx, col in enumerate(cols):
            with col:
                if idx >= len(row):
                    st.markdown("&nbsp;", unsafe_allow_html=True)
                    continue
                kind, data = row[idx]
                variant = "blue" if idx % 2 == 0 else "red"
                if kind == "screen":
                    icon = _icon_for(data["screen"], SCREEN_ICONS)
                    _desk_tile_button(
                        data["screen"],
                        icon,
                        data["label"],
                        data["desc"],
                        lambda g=data["group"], s=data["screen"]: go_screen(g, s),
                        hero=data.get("hero", False),
                        variant="red" if data.get("hero") else variant,
                    )
                else:
                    mod = data
                    icon = _icon_for(mod, GROUP_ICONS)
                    _desk_tile_button(
                        mod,
                        icon,
                        module_title(mod),
                        module_tagline(mod),
                        lambda m=mod: go_module(m),
                        variant=variant,
                    )


def render_module_topbar(nav: dict, user: dict, company: str, group: str, screen: str) -> None:
    """Persistent navigation bar on every ERP screen — back to desktop home."""
    from erp_ui import form_flow as ff

    nav_key = f"{group}_{screen}".replace(" ", "_")
    mobile = is_mobile_client()

    with st.container(key=f"mod_topbar_{nav_key}"):
        if mobile:
            r1c1, r1c2, r1c3, r1c4, r1c5 = st.columns(5)
            with r1c1:
                if st.button("Home", key=f"nav_desktop_{nav_key}", use_container_width=True, type="primary"):
                    go_home()
            with r1c2:
                if group in nav and screen != "Dashboard":
                    if st.button(module_title(group), key=f"nav_module_{nav_key}", use_container_width=True):
                        go_module(group)
            with r1c3:
                from erp_ui.notification_sidebar import render_notification_bell
                render_notification_bell(user, key=f"nav_notif_{nav_key}")
            with r1c4:
                if st.button("Refresh", key=f"nav_refresh_{nav_key}", use_container_width=True,
                             help="Reload this page — clear form fields and refresh data"):
                    ff.refresh_current_page()
            with r1c5:
                if st.button("Logout", key=f"nav_logout_{nav_key}", use_container_width=True):
                    logout_user()
            if st.button("Change password", key=f"nav_pwd_{nav_key}", use_container_width=True):
                open_change_password()
            st.markdown(
                f'<p class="erp-mod-crumb">{company}</p>'
                f'<p class="erp-mod-screen">{screen_title(screen)}</p>',
                unsafe_allow_html=True,
            )
            from erp_ui.enterprise_search import render_enterprise_search
            render_enterprise_search(key_prefix=f"mod_srch_{nav_key}")
        else:
            c1, c2, c3, c4 = st.columns([1.3, 1.3, 4.4, 2.2], gap="small")
            with c1:
                if st.button(
                    "← Desktop",
                    key=f"nav_desktop_{nav_key}",
                    use_container_width=True,
                    type="primary",
                    help="Return to the main application launcher",
                ):
                    go_home()
            with c2:
                if group in nav and screen != "Dashboard":
                    if st.button(
                        f"← {module_title(group)}",
                        key=f"nav_module_{nav_key}",
                        use_container_width=True,
                        help=f"Open {module_title(group)} module menu",
                    ):
                        go_module(group)
            with c3:
                from erp_ui.enterprise_search import render_enterprise_search
                render_enterprise_search(key_prefix=f"mod_srch_{nav_key}")
                from erp_ui.page_shell import render_favorites_bar
                render_favorites_bar(nav, key_prefix=f"fav_{nav_key}")
                st.markdown(
                    f'<p class="erp-mod-crumb">{company} / {module_title(group)}</p>'
                    f'<p class="erp-mod-screen">{screen_title(screen)}</p>',
                    unsafe_allow_html=True,
                )
            with c4:
                n1, n2, n3 = st.columns(3)
                with n1:
                    from erp_ui.notification_sidebar import render_notification_bell
                    render_notification_bell(user, key=f"nav_notif_{nav_key}")
                with n2:
                    if st.button(
                        "Refresh",
                        key=f"nav_refresh_{nav_key}",
                        use_container_width=True,
                        help="Reload this page — clear form fields and refresh lists from the database",
                    ):
                        ff.refresh_current_page()
                with n3:
                    if st.button("Logout", key=f"nav_logout_{nav_key}", use_container_width=True):
                        logout_user()
                if st.button("Password", key=f"nav_pwd_{nav_key}", use_container_width=True, help="Change your password"):
                    open_change_password()


def render_module_screen_chips(nav: dict, group: str, screen: str) -> None:
    screens = nav.get(group) or []
    if len(screens) <= 1:
        return
    chip_key = f"mod_chips_row_{group}".replace(" ", "_")
    max_chips = 6 if is_mobile_client() else 8
    primary = screens[:max_chips]
    overflow = screens[max_chips:]
    with st.container(key=chip_key):
        cols = st.columns(min(len(primary), max_chips))
        for col, scr in zip(cols, primary):
            with col:
                if st.button(
                    screen_title(scr),
                    key=f"mod_chip_{group}_{scr}",
                    use_container_width=True,
                    type="primary" if scr == screen else "secondary",
                ):
                    if scr != screen:
                        go_screen(group, scr)
        if overflow:
            more_labels = {screen_title(s): s for s in overflow}
            m1, m2 = st.columns([4, 1])
            with m1:
                pick = st.selectbox(
                    "More screens in this module",
                    list(more_labels.keys()),
                    key=f"mod_chip_more_{group}",
                    label_visibility="collapsed",
                )
            with m2:
                if st.button("Open", key=f"mod_chip_more_go_{group}", use_container_width=True):
                    target = more_labels.get(pick)
                    if target and target != screen:
                        go_screen(group, target)
            if screen in overflow:
                st.caption(f"Current: **{screen_title(screen)}** (also available under More screens)")
    st.divider()


def render_desktop_topbar(nav: dict, user: dict, company: str, *, sub_title: str = "Home") -> None:
    from erp_ui import form_flow as ff

    pending = _pending_count()
    display_name = (user.get("full_name") or user.get("username") or "User").split()[0]
    role = (user.get("role") or "").title()

    with st.container(key="desk_topbar"):
        t1, t2, t3 = st.columns([1.8, 3.6, 3.4], gap="small")
        with t1:
            st.markdown(
                f'<p class="erp-desk-brand">{company.upper()}</p>'
                f'<p class="erp-desk-crumb">Workspace / {sub_title}</p>',
                unsafe_allow_html=True,
            )
        with t2:
            from erp_ui.enterprise_search import render_enterprise_search
            render_enterprise_search(key_prefix="desk_ent")
            q = st.session_state.get("desk_ent_q", "")
            if q and q.strip():
                qlo = q.strip().lower()
                nav_hits = [r for r in _flat_search_index(nav) if qlo in r[2].lower()]
                if nav_hits:
                    with st.container(key="desk_search_hits"):
                        for group, screen, label in nav_hits[:4]:
                            if st.button(f"Screen: {label}", key=f"desk_srch_{group}_{screen}", use_container_width=True):
                                go_screen(group, screen)
        with t3:
            c_a, c_b, c_c, c_d, c_e, c_f = st.columns([1.35, 0.55, 0.75, 0.85, 1.0, 0.9], gap="small")
            with c_a:
                badge = f"Approvals · {pending}" if pending else "Approvals"
                with st.container(key="desk_approvals"):
                    if st.button(badge, key="desk_approvals_btn", use_container_width=True, help="Open pending approvals"):
                        if can_view_screen(user, "Sale Approval"):
                            request_nav("Sales", "Sale Approval")
                        elif can_view_screen(user, "Purchase Approval"):
                            request_nav("Purchases", "Purchase Approval")
            with c_b:
                from erp_ui.notification_sidebar import render_notification_bell
                render_notification_bell(user, key="desk_notif_bell")
            with c_c:
                if st.button("Home", key="desk_all_apps", use_container_width=True):
                    go_home()
            with c_d:
                if st.button(
                    "Refresh",
                    key="desk_refresh_btn",
                    use_container_width=True,
                    help="Reload home — refresh data and clear temporary filters",
                ):
                    ff.refresh_current_page()
            with c_e:
                if st.button("Password", key="desk_change_password", use_container_width=True, help="Change your password"):
                    open_change_password()
            with c_f:
                if st.button("Logout", key="desk_logout", use_container_width=True):
                    logout_user()
            st.caption(f"**{display_name}** · {role}")


def open_change_password() -> None:
    st.session_state["show_change_password"] = True
    st.rerun()


def logout_user() -> None:
    try:
        u = st.session_state.get("user")
        if u:
            from db_audit import log_event
            log_event(
                "users", u.get("id"), "logout", user_id=u.get("id"),
                module="Admin", summary=f"Signed out: {u.get('username', '')}",
            )
    except Exception:
        pass
    from erp_ui.auth_session import clear_session
    clear_session()
    st.rerun()


def _render_hero_banner(display_name: str, company: str) -> None:
    now = datetime.now().strftime("%A, %d %B %Y")
    st.markdown(
        f'<div class="erp-desk-hero">'
        f'<table style="width:100%;border:none;border-collapse:collapse;">'
        f'<tr><td style="border:none;vertical-align:middle;">'
        f'<p class="erp-desk-hero-title">Dashboard</p>'
        f'<p class="erp-desk-hero-sub">Welcome, <strong>{display_name}</strong> — '
        f'{company} enterprise workspace</p>'
        f'</td><td style="border:none;text-align:right;vertical-align:middle;width:30%;">'
        f'<p class="erp-desk-hero-meta">{now}</p>'
        f'</td></tr></table></div>',
        unsafe_allow_html=True,
    )


def _render_my_work_panel(nav: dict, user: dict) -> None:
    from html import escape
    from erp_ui.my_work import load_my_work_tasks
    from erp_ui.nav import go_screen
    from erp_ui.page_shell import shell_status_badge

    tasks = load_my_work_tasks(user, nav)
    st.markdown('<p class="erp-desk-section">My Work</p>', unsafe_allow_html=True)
    if not tasks:
        st.markdown(
            f'<div class="txn-status-strip">{shell_status_badge("posted", kind="shell")}'
            f'&nbsp;<span class="txn-queue-label">All clear — no pending tasks</span></div>',
            unsafe_allow_html=True,
        )
        return

    tone_badge = {
        "accent": shell_status_badge("pending_approval", kind="invoice"),
        "warning": shell_status_badge("shadow", kind="shell"),
        "neutral": shell_status_badge("open", kind="shell"),
    }
    st.markdown(
        f'<div class="txn-status-strip">{shell_status_badge("pending_approval", kind="invoice")}'
        f'&nbsp;<strong>{len(tasks)}</strong>&nbsp;'
        f'<span class="txn-queue-label">item(s) need attention</span></div>',
        unsafe_allow_html=True,
    )
    shown = tasks[:4]
    with st.container(key="desk_mywork_panel"):
        cols = st.columns(len(shown), gap="small")
        for col, t in zip(cols, shown):
            with col:
                badge = tone_badge.get(t.get("tone") or "accent", tone_badge["accent"])
                st.markdown(
                    f'<div class="erp-mywork-card">'
                    f'<div class="erp-mywork-card-badge">{badge}</div>'
                    f'<p class="erp-mywork-card-title">{escape(t["label"])}</p>'
                    f'<p class="erp-mywork-card-detail">{escape(t["detail"])}</p>'
                    f"</div>",
                    unsafe_allow_html=True,
                )
                if st.button("Open", key=f"mywork_{t['group']}_{t['screen']}", use_container_width=True):
                    go_screen(t["group"], t["screen"])


def _render_quick_actions(nav: dict, user: dict) -> None:
    st.markdown('<p class="erp-desk-section">Quick Actions</p>', unsafe_allow_html=True)
    qa_visible = [
        (label, grp, scr) for label, grp, scr in QUICK_ACTIONS
        if grp in nav and scr in nav[grp] and can_view_screen(user, scr)
    ]
    with st.container(key="desk_qa_panel"):
        qa_cols = qa_columns(_QA_COLS, 2)
        for row_start in range(0, len(qa_visible), qa_cols):
            row = qa_visible[row_start: row_start + qa_cols]
            cols = st.columns(qa_cols)
            for col, (label, grp, scr) in zip(cols, row):
                with col:
                    if st.button(label, key=f"dsk_qa_{scr}", use_container_width=True):
                        go_screen(grp, scr)


def render_ceo_desktop(nav: dict, user: dict, company: str) -> None:
    _inject_desktop_theme()
    render_desktop_topbar(nav, user, company, sub_title="Home")

    display_name = (user.get("full_name") or user.get("username") or "User").split()[0]
    _render_hero_banner(display_name, company)

    pending = _pending_count()
    if pending:
        st.markdown(
            f'<div class="erp-desk-alert">Action required: <strong>{pending}</strong> '
            f'pending approval(s) or workflow items — use Approvals in the top bar.</div>',
            unsafe_allow_html=True,
        )

    _render_quick_actions(nav, user)
    _render_my_work_panel(nav, user)

    from erp_ui.user_prefs import list_favorites
    from erp_ui.nav import go_screen, screen_title
    favs = [f for f in list_favorites() if f.get("group") in nav and f.get("screen") in nav.get(f["group"], [])]
    if favs:
        st.markdown('<p class="erp-desk-section">Pinned Screens</p>', unsafe_allow_html=True)
        with st.container(key="desk_pin_panel"):
            fcols = st.columns(min(len(favs), 6))
            for col, f in zip(fcols, favs[:6]):
                with col:
                    if st.button(screen_title(f["screen"]), key=f"pin_{f['group']}_{f['screen']}", use_container_width=True):
                        go_screen(f["group"], f["screen"])

    for section in DESKTOP_SECTIONS:
        st.markdown(f'<p class="erp-desk-section">{section["title"]}</p>', unsafe_allow_html=True)
        items = []
        for t in section.get("tiles") or []:
            if t["group"] in nav and t["screen"] in nav[t["group"]]:
                items.append(("screen", t))
        for mod in section.get("modules") or []:
            if mod in nav:
                items.append(("module", mod))
        _render_tile_grid(items, user, nav)


def render_desktop_module_launcher(nav: dict, user: dict, company: str, group: str, screens: list[str]) -> None:
    _inject_desktop_theme()
    render_desktop_topbar(nav, user, company, sub_title=module_title(group))

    icon = _icon_for(group, GROUP_ICONS)
    st.markdown(
        f'<p class="erp-desk-module-head">{icon} {module_title(group)} — select a function</p>',
        unsafe_allow_html=True,
    )

    with st.container(key="desk_back_row"):
        if st.button("← Desktop", key="desk_back_home", use_container_width=False):
            go_home()

    visible = [s for s in screens if s != "Dashboard"]
    q = st.session_state.get("desk_global_search", "").strip().lower()
    if q:
        visible = [
            s for s in visible
            if q in s.lower() or q in screen_title(s).lower() or q in screen_tagline(s).lower()
        ] or visible

    if not visible:
        st.info("No screens available in this module for your role.")
        return

    cols_n = grid_columns(_GRID_COLS, 2)
    for row_start in range(0, len(visible), cols_n):
        row = visible[row_start: row_start + cols_n]
        cols = st.columns(cols_n)
        for idx, col in enumerate(cols):
            with col:
                if idx >= len(row):
                    st.markdown("&nbsp;", unsafe_allow_html=True)
                    continue
                screen = row[idx]
                sicon = _icon_for(screen, SCREEN_ICONS)
                variant = "blue" if idx % 2 == 0 else "red"
                _desk_screen_button(
                    group,
                    screen,
                    sicon,
                    screen_title(screen),
                    screen_tagline(screen),
                    lambda s=screen: go_screen(group, s),
                    variant=variant,
                )
