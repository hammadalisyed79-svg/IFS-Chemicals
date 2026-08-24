"""ERP staff — right-side sliding notification panel."""

from __future__ import annotations

import streamlit as st

from erp_ui.theme import BLUE, BLUE_DARK, BLUE_LIGHT, BLACK, RED, RED_LIGHT, WHITE


_PANEL_STATE = "_erp_notif_panel_open"


def unread_notification_count(user: dict) -> int:
    try:
        from erp_core import notifications as ntf
        uid = user.get("id")
        if not uid:
            return 0
        return len(ntf.get_notifications_for_user(uid, unread_only=True, limit=99))
    except Exception:
        return 0


def open_notification_panel() -> None:
    st.session_state[_PANEL_STATE] = True


def close_notification_panel() -> None:
    st.session_state[_PANEL_STATE] = False


def toggle_notification_panel() -> None:
    st.session_state[_PANEL_STATE] = not bool(st.session_state.get(_PANEL_STATE))


def notification_bell_label(user: dict) -> str:
    n = unread_notification_count(user)
    return f"🔔 ({n})" if n else "🔔"


def render_notification_bell(user: dict, *, key: str, use_container_width: bool = True) -> None:
    """Top-bar / toolbar button that opens the notification slide panel."""
    label = notification_bell_label(user)
    n = unread_notification_count(user)
    help_txt = f"{n} unread notification(s)" if n else "Open notifications"
    if st.button(label, key=key, use_container_width=use_container_width, help=help_txt):
        toggle_notification_panel()
        st.rerun()


def _inject_css(open_panel: bool) -> None:
    open_cls = "erp-notif-open" if open_panel else "erp-notif-closed"
    # When closed, do not leave any drawer/backdrop chrome in the layout.
    if not open_panel:
        st.markdown(
            f'<div class="erp-notif-root {open_cls}" aria-hidden="true">&#8203;</div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f"""
<style>
body:has(.erp-notif-root.erp-notif-open) {{
  overflow-x: hidden;
}}

/* Dim overlay — pure HTML, no Streamlit button (avoids leftover widgets on the page) */
.erp-notif-overlay {{
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.4);
  z-index: 1000000;
}}

/* Slide panel hosted inside Streamlit container */
div[class*="st-key-erp_notif_drawer"] {{
  position: fixed !important;
  top: 0 !important;
  right: 0 !important;
  width: min(380px, 94vw) !important;
  height: 100vh !important;
  max-height: 100vh !important;
  z-index: 1000001 !important;
  background: {WHITE} !important;
  border-left: 3px solid {BLUE} !important;
  box-shadow: -12px 0 32px rgba(15, 23, 42, 0.22) !important;
  overflow-y: auto !important;
  overflow-x: hidden !important;
  padding: 0.75rem 0.85rem 1.25rem 0.85rem !important;
  margin: 0 !important;
  box-sizing: border-box !important;
  animation: erpNotifSlideIn 0.2s ease-out;
}}
@keyframes erpNotifSlideIn {{
  from {{ transform: translateX(100%); }}
  to {{ transform: translateX(0); }}
}}

/* Kill Streamlit empty bordered blocks inside the drawer */
div[class*="st-key-erp_notif_drawer"] [data-testid="stVerticalBlockBorderWrapper"],
div[class*="st-key-erp_notif_drawer"] [data-testid="stVerticalBlock"] > div {{
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
}}
div[class*="st-key-erp_notif_drawer"] [data-testid="stMarkdownContainer"] {{
  margin: 0 !important;
  padding: 0 !important;
}}
div[class*="st-key-erp_notif_drawer"] [data-testid="stMarkdownContainer"] p {{
  margin: 0 !important;
}}
div[class*="st-key-erp_notif_drawer"] .stButton {{
  margin-bottom: 0.35rem !important;
}}
div[class*="st-key-erp_notif_drawer"] button {{
  border-radius: 8px !important;
  min-height: 2.1rem !important;
  padding-top: 0.25rem !important;
  padding-bottom: 0.25rem !important;
}}
div[class*="st-key-erp_notif_drawer"] .stCaption {{
  margin: 0.25rem 0 0.5rem 0 !important;
}}

.erp-notif-head {{
  margin: 0 0 0.5rem 0;
  padding-bottom: 0.45rem;
  border-bottom: 2px solid {BLUE_LIGHT};
}}
.erp-notif-title {{
  margin: 0 !important;
  font-size: 1.05rem;
  font-weight: 800;
  color: {BLUE_DARK};
}}
.erp-notif-badge {{
  display: inline-block;
  background: {RED};
  color: {WHITE};
  font-size: 0.72rem;
  font-weight: 700;
  border-radius: 999px;
  padding: 0.12rem 0.5rem;
  margin-left: 0.35rem;
  vertical-align: middle;
}}
.erp-notif-list {{
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  margin-top: 0.35rem;
}}
.erp-notif-card {{
  border: 1px solid {BLUE_LIGHT};
  border-radius: 8px;
  padding: 0.55rem 0.65rem;
  background: #F8FAFC;
}}
.erp-notif-card.unread {{
  border-color: {BLUE};
  background: {BLUE_LIGHT};
}}
.erp-notif-card.deleted {{
  border-color: {RED};
  background: {RED_LIGHT};
}}
.erp-notif-card-title {{
  font-weight: 700;
  color: {BLACK};
  font-size: 0.88rem;
  margin: 0 0 0.15rem 0 !important;
  line-height: 1.3;
}}
.erp-notif-card-meta {{
  font-size: 0.7rem;
  color: #64748B;
  margin: 0 0 0.25rem 0 !important;
}}
.erp-notif-card-msg {{
  font-size: 0.78rem;
  color: #334155;
  margin: 0 !important;
  line-height: 1.35;
}}
.erp-notif-empty {{
  color: #64748B;
  font-size: 0.88rem;
  padding: 0.75rem 0;
}}
</style>
<div class="erp-notif-root erp-notif-open" style="display:none"></div>
<div class="erp-notif-overlay" aria-hidden="true"></div>
""",
        unsafe_allow_html=True,
    )


def render_erp_notification_sidebar(user: dict) -> None:
    """Right-side sliding notification bar for internal ERP users."""
    if not user or not user.get("id"):
        return

    open_panel = bool(st.session_state.get(_PANEL_STATE))
    _inject_css(open_panel)

    if not open_panel:
        return

    from erp_core import notifications as ntf
    from html import escape

    uid = int(user["id"])
    unread = ntf.get_notifications_for_user(uid, unread_only=True, limit=50)
    unread_n = len(unread)
    show_history = bool(st.session_state.get("_erp_notif_show_history"))

    with st.container(key="erp_notif_drawer"):
        badge_html = (
            f'<span class="erp-notif-badge">{unread_n}</span>' if unread_n else ""
        )
        st.markdown(
            f'<div class="erp-notif-head">'
            f'<p class="erp-notif-title">Notifications{badge_html}</p>'
            f"</div>",
            unsafe_allow_html=True,
        )

        b1, b2 = st.columns(2)
        with b1:
            if st.button("Close", key="erp_notif_close", use_container_width=True):
                close_notification_panel()
                st.rerun()
        with b2:
            if st.button(
                "Mark all read",
                key="erp_notif_mark_all",
                use_container_width=True,
                disabled=unread_n == 0,
            ):
                ntf.mark_all_read(uid)
                st.session_state["_erp_notif_show_history"] = False
                st.rerun()

        show_history = st.checkbox(
            "Show read history",
            value=show_history,
            key="erp_notif_history_cb",
            help="When off, only unread alerts are listed. Mark all read clears this list.",
        )
        st.session_state["_erp_notif_show_history"] = show_history

        rows = (
            ntf.get_notifications_for_user(uid, unread_only=False, limit=50)
            if show_history
            else unread
        )

        if not rows:
            st.markdown(
                '<p class="erp-notif-empty">'
                + (
                    "All caught up — no unread notifications."
                    if not show_history
                    else "No notifications yet."
                )
                + "</p>",
                unsafe_allow_html=True,
            )
            return

        st.caption(
            "Unread alerts only — use Mark all read to clear. "
            "Turn on Show read history to see older items."
            if not show_history
            else "Showing unread and read history."
        )

        # One HTML list — avoids empty Streamlit widget boxes under each card
        cards = ['<div class="erp-notif-list">']
        for n in rows:
            is_unread = not n.get("is_read")
            cat = (n.get("category") or "").strip()
            title = escape(str(n.get("title") or "Alert"))
            when = escape(str(n.get("created_at") or ""))
            msg = escape(str(n.get("message") or ""))
            classes = ["erp-notif-card"]
            if is_unread:
                classes.append("unread")
            if cat == "order_deleted":
                classes.append("deleted")
            cls = " ".join(classes)
            prefix = "● " if is_unread else ""
            cat_label = escape(cat.replace("_", " ")) if cat else ""
            meta = when + (f" · {cat_label}" if cat_label else "")
            msg_html = f'<p class="erp-notif-card-msg">{msg}</p>' if msg else ""
            cards.append(
                f'<div class="{cls}">'
                f'<p class="erp-notif-card-title">{prefix}{title}</p>'
                f'<p class="erp-notif-card-meta">{meta}</p>'
                f"{msg_html}"
                f"</div>"
            )
        cards.append("</div>")
        st.markdown("".join(cards), unsafe_allow_html=True)
