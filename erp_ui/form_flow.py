"""Consistent post-action behaviour: flash prompt, blank new forms, refreshed edit panels."""

from __future__ import annotations

import re

import streamlit as st

_FLASH_KEY = "_erp_flash"

_ACTION_TITLES = (
    ("deactivat", "Deactivated"),
    ("deleted", "Deleted"),
    ("delete", "Deleted"),
    ("removed", "Removed"),
    ("updated", "Updated"),
    ("update", "Updated"),
    ("edited", "Updated"),
    ("posted", "Posted"),
    ("post", "Posted"),
    ("approved", "Approved"),
    ("approve", "Approved"),
    ("rejected", "Rejected"),
    ("reject", "Rejected"),
    ("cancelled", "Cancelled"),
    ("cancel", "Cancelled"),
    ("submitted", "Submitted"),
    ("submit", "Submitted"),
    ("issued", "Issued"),
    ("issue", "Issued"),
    ("paid", "Paid"),
    ("reimbursed", "Reimbursed"),
    ("completed", "Completed"),
    ("complete", "Completed"),
    ("saved", "Saved"),
    ("added", "Saved"),
    ("created", "Saved"),
    ("loaded", "Loaded"),
    ("applied", "Applied"),
    ("synced", "Synced"),
    ("generated", "Generated"),
    ("reversed", "Reversed"),
    ("returned", "Returned"),
)


def clear_session_prefix(*prefixes: str) -> None:
    skip_suffixes = ("_inv_tab", "_open_tab", "_page_tab")
    skip_exact = {"sal_edit_id", "pur_edit_id", "inv_tab_sales", "inv_tab_purchase"}
    for prefix in prefixes:
        if not prefix:
            continue
        for key in list(st.session_state.keys()):
            if key in skip_exact or any(str(key).endswith(s) for s in skip_suffixes):
                continue
            if key == prefix or key.startswith(f"{prefix}_"):
                del st.session_state[key]


def clear_keys(*keys: str) -> None:
    for key in keys:
        st.session_state.pop(key, None)


# Kept across "Refresh" so the user stays logged in on the same screen.
_REFRESH_PRESERVE_EXACT = frozenset({
    "user",
    "portal_mode",
    "_auth_session_token",
    "sidebar_group",
    "sidebar_screen",
    "show_change_password",
    "launcher_group",
    "_portal_keep_page",
    "sal_inv_tab",
    "pur_inv_tab",
    "inv_tab_sales",
    "inv_tab_purchase",
    "sal_edit_id",
    "pur_edit_id",
})
_REFRESH_PRESERVE_PREFIXES = (
    "_auth_session",
)
_REFRESH_PRESERVE_SUFFIXES = (
    "_inv_tab",
    "_open_tab",
    "_page_tab",
)


def refresh_current_page(*, message: str = "Form and data reloaded.") -> None:
    """Clear form/widget state, invalidate read caches, stay on the same screen, then rerun."""
    try:
        from db_cache import invalidate_all
        invalidate_all()
    except Exception:
        pass
    for key in list(st.session_state.keys()):
        if key in _REFRESH_PRESERVE_EXACT:
            continue
        sk = str(key)
        if any(sk.startswith(p) for p in _REFRESH_PRESERVE_PREFIXES):
            continue
        if any(sk.endswith(s) for s in _REFRESH_PRESERVE_SUFFIXES):
            continue
        try:
            del st.session_state[key]
        except Exception:
            pass
    set_flash(message, level="info", title="Refreshed")
    st.rerun()


def form_generation(form_id: str) -> int:
    """Counter embedded in widget keys — increment to remount inputs with defaults."""
    return int(st.session_state.get(f"_ff_gen_{form_id}", 0))


def bump_form_generation(form_id: str) -> None:
    st.session_state[f"_ff_gen_{form_id}"] = form_generation(form_id) + 1


def widget_key(form_id: str, name: str) -> str:
    """Stable widget key that resets when form generation is bumped after post."""
    return f"{form_id}_{name}_{form_generation(form_id)}"


def infer_action_title(message: str) -> str:
    m = (message or "").lower()
    for needle, title in _ACTION_TITLES:
        if needle in m:
            return title
    return "Done"


def _plain_text(message: str) -> str:
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", message or "")
    text = re.sub(r"<[^>]+>", "", text)
    return " ".join(text.split())


def set_flash(message: str, *, level: str = "success", title: str | None = None) -> None:
    """Queue a professional banner + toast for the next script run (survives st.rerun)."""
    st.session_state[_FLASH_KEY] = {
        "message": message or "Action completed.",
        "level": level if level in ("success", "error", "warning", "info") else "success",
        "title": title or infer_action_title(message or ""),
    }


def render_flash() -> None:
    """Show queued action feedback. Call once near the top of each Streamlit entrypoint."""
    flash = st.session_state.pop(_FLASH_KEY, None)
    if not flash:
        return
    level = flash.get("level") or "success"
    title = flash.get("title") or "Done"
    message = flash.get("message") or ""
    plain = _plain_text(message)
    icons = {"success": "✅", "error": "🚫", "warning": "⚠️", "info": "ℹ️"}
    toast_body = f"{title}: {plain}" if plain else title
    try:
        st.toast(toast_body, icon=icons.get(level, "✅"))
    except Exception:
        pass
    # Banner stays visible for the full page view (toast alone is easy to miss)
    plain_l = plain.lower()
    title_l = title.lower()
    if plain_l.startswith(title_l):
        banner = message
    else:
        banner = f"**{title}.** {message}"
    fn = getattr(st, level, st.success)
    fn(banner)


def action_done(
    message: str = "Saved successfully.",
    *,
    level: str = "success",
    title: str | None = None,
    form_id: str | None = None,
    prefixes=(),
    also=(),
    retain: dict | None = None,
) -> None:
    """Flash a professional prompt, clear form state when asked, then rerun."""
    if form_id:
        bump_form_generation(form_id)
        # Clear leftover keys for this form id (money_input seeds, group select, etc.)
        clear_session_prefix(form_id)
    clear_session_prefix(*prefixes)
    clear_keys(*also)
    # Retain after clears so print-toolbar / picker state survives
    if retain:
        for key, val in retain.items():
            st.session_state[key] = val
    set_flash(message, level=level, title=title)
    st.rerun()


def finish_post_new_form(
    form_id: str,
    message: str = "Posted successfully.",
    *,
    prefixes=(),
    also=(),
    retain: dict | None = None,
) -> None:
    """After post/save: bump form keys (blank form) and rerun."""
    action_done(
        message,
        title=infer_action_title(message),
        form_id=form_id,
        prefixes=prefixes,
        also=also,
        retain=retain,
    )


def finish_new_entry(
    *prefixes: str,
    also=(),
    message: str = "Saved successfully.",
    form_id: str | None = None,
) -> None:
    """Clear form state and rerun — ready for the next new document."""
    action_done(message, form_id=form_id, prefixes=prefixes, also=also)


def prime_edit_refresh(edit_prefix: str, record_id: int, picker_prefix: str | None = None) -> None:
    """Drop cached lines/header; reload from DB on next run."""
    rid = int(record_id)
    clear_keys(f"{edit_prefix}_header", f"{edit_prefix}_lines")
    st.session_state[f"{edit_prefix}_id"] = rid
    st.session_state[f"{edit_prefix}_reload"] = rid
    if picker_prefix:
        from erp_ui.transaction_list import reselect_transaction_picker
        reselect_transaction_picker(picker_prefix, rid)


def finish_edit_refresh(
    edit_prefix: str,
    record_id: int,
    picker_prefix: str | None = None,
    message: str = "Updated successfully.",
) -> None:
    prime_edit_refresh(edit_prefix, record_id, picker_prefix)
    set_flash(message, title=infer_action_title(message))
    st.rerun()


def edit_panel_active(edit_prefix: str, record_id: int, *, load_clicked: bool = False) -> bool:
    rid = int(record_id)
    if load_clicked:
        return True
    if st.session_state.get(f"{edit_prefix}_reload") == rid:
        return True
    return st.session_state.get(f"{edit_prefix}_id") == rid


def consume_edit_reload(edit_prefix: str, record_id: int) -> bool:
    rid = int(record_id)
    if st.session_state.get(f"{edit_prefix}_reload") == rid:
        st.session_state.pop(f"{edit_prefix}_reload", None)
        return True
    return False


def finish_after_delete(
    edit_prefix: str,
    picker_prefix: str | None = None,
    message: str = "Deleted successfully.",
) -> None:
    clear_session_prefix(edit_prefix)
    if picker_prefix:
        clear_keys(
            f"{picker_prefix}_pick_sel",
            f"{picker_prefix}_pick_pending",
            f"{picker_prefix}_pick_q",
        )
    set_flash(message, title=infer_action_title(message))
    st.rerun()
