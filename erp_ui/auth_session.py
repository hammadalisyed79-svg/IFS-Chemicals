"""Persist login — server-side session + browser storage (survives page refresh)."""

from __future__ import annotations

import json

import streamlit as st
from application import data_gateway as db
from erp_core.v15_security import client_context, is_portal_user, is_ssl_configured

SESSION_STATE_KEY = "_auth_session_token"
SESSION_QPARAM = "session"
BOOTSTRAP_QPARAM = "_st"
LS_KEY = "ifs_erp_sid"
SESSION_DAYS = 7
COOKIE_NAME = "ifs_erp_sid"
COOKIE_MAX_AGE = SESSION_DAYS * 86400

# Shared JS helpers — always use the top-level Streamlit page, not the component iframe.
_PARENT_JS = """
function __ifsParent() {
  try { return window.parent; } catch (e) { return window; }
}
function __ifsLS() {
  try { return __ifsParent().localStorage; } catch (e) { return null; }
}
function __ifsSS() {
  try { return __ifsParent().sessionStorage; } catch (e) { return null; }
}
function __ifsReadCookie(name) {
  try {
    var parts = (__ifsParent().document.cookie || "").split(";");
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i].trim();
      if (p.indexOf(name + "=") === 0) {
        return decodeURIComponent(p.substring(name.length + 1));
      }
    }
  } catch (e) {}
  return "";
}
function __ifsClientToken() {
  var ls = __ifsLS();
  var t = ls ? ls.getItem(__ifsLSKey) : "";
  if (t) return t;
  var ss = __ifsSS();
  t = ss ? ss.getItem(__ifsLSKey) : "";
  if (t) return t;
  return __ifsReadCookie(__ifsCookieName);
}
"""


SESSION_ENDED_KEY = "_session_ended_reason"


def create_and_persist_session(user: dict) -> None:
    """Create the only active session for this user (other devices are signed out)."""
    ip, ua = client_context()
    token = db.create_user_session(user["id"], SESSION_DAYS, ip=ip, user_agent=ua)
    st.session_state.user = user
    st.session_state.portal_mode = is_portal_user(user)
    st.session_state[SESSION_STATE_KEY] = token
    st.session_state.pop(SESSION_ENDED_KEY, None)
    _persist_client_session(token)
    _clear_url_session_param()
    _clear_bootstrap_query_param()


def restore_session() -> bool:
    """Try cookie/bootstrap restore; if missing, ask browser storage for token."""
    if try_restore_session():
        return True
    if not st.session_state.get("user"):
        bootstrap_session_from_client()
    return bool(st.session_state.get("user"))


def enforce_active_session() -> bool:
    """Re-check DB token every run — enforces one login per user + idle timeout.

    When the same username signs in on another PC/browser, this session's
    token is deleted and the user is returned to the login screen.
    Idle timeout (default 30 minutes; adjustable in System Settings) also ends the session.
    """
    if not st.session_state.get("user"):
        return False
    token = st.session_state.get(SESSION_STATE_KEY)
    if not token:
        _end_session(reason="invalid", revoke_token=False)
        return False
    ip, ua = client_context()
    user = db.get_user_by_session_token(token, ip=ip, user_agent=ua)
    if not user or int(user.get("id") or 0) != int(st.session_state.user.get("id") or 0):
        from erp_core.v15_security import last_session_fail_reason
        fail = last_session_fail_reason()
        if fail == "idle":
            reason = "idle"
        elif fail == "missing":
            reason = "signed_in_elsewhere"
        else:
            reason = "invalid"
        _end_session(reason=reason, revoke_token=False)
        return False
    st.session_state.user = user
    st.session_state.portal_mode = is_portal_user(user)
    sync_client_session()
    return True


def sync_client_session() -> None:
    """Keep browser storage aligned while the user is logged in."""
    if st.session_state.get("user"):
        token = st.session_state.get(SESSION_STATE_KEY)
        if token:
            _persist_client_session(token)


def try_restore_session() -> bool:
    if st.session_state.get("user"):
        return enforce_active_session()

    token = (
        st.session_state.get(SESSION_STATE_KEY)
        or _peek_bootstrap_token()
        or _read_browser_session_token()
    )
    if not token:
        return False

    st.session_state[SESSION_STATE_KEY] = token
    ip, ua = client_context()
    user = db.get_user_by_session_token(token, ip=ip, user_agent=ua)
    if user:
        st.session_state.user = user
        st.session_state.portal_mode = is_portal_user(user)
        st.session_state.pop(SESSION_ENDED_KEY, None)
        _persist_client_session(token)
        _clear_bootstrap_query_param()
        _clear_url_session_param()
        return True

    from erp_core.v15_security import last_session_fail_reason
    if last_session_fail_reason() == "idle":
        st.session_state[SESSION_ENDED_KEY] = "idle"
    st.session_state.pop(SESSION_STATE_KEY, None)
    _clear_client_session()
    _clear_bootstrap_query_param()
    return False


def bootstrap_session_from_client() -> None:
    """Inject JS to hand off browser token via one-time query param (not `session`)."""
    if st.session_state.get("user") or st.session_state.get(SESSION_STATE_KEY):
        return
    if _peek_bootstrap_token():
        return
    _inject_local_storage_restore_bridge()


def pop_session_ended_message() -> str | None:
    """One-shot message for login screen after forced sign-out."""
    reason = st.session_state.pop(SESSION_ENDED_KEY, None)
    if reason == "signed_in_elsewhere":
        return (
            "This account was signed in on another device. "
            "Only one login is allowed at a time — please sign in again."
        )
    if reason == "idle":
        try:
            from erp_core.v15_security import session_idle_minutes
            mins = session_idle_minutes()
        except Exception:
            mins = 30
        return (
            f"Your session expired after {mins} minutes of inactivity. "
            "Please sign in again."
        )
    if reason == "invalid":
        return "Your session ended. Please sign in again."
    return None


def _end_session(*, reason: str, revoke_token: bool = True) -> None:
    st.session_state[SESSION_ENDED_KEY] = reason
    clear_session(revoke_token=revoke_token)


def clear_session(*, revoke_token: bool = True) -> None:
    token = st.session_state.get(SESSION_STATE_KEY)
    if revoke_token and token:
        db.delete_user_session(token)
    st.session_state.user = None
    st.session_state.portal_mode = False
    st.session_state.pop(SESSION_STATE_KEY, None)
    for key in (
        "nav_group", "nav_screen", "sidebar_group", "sidebar_screen",
        "launcher_group", "portal_cart", "show_change_password",
        "_portal_sidebar_bootstrapped",
    ):
        st.session_state.pop(key, None)
    _clear_client_session()
    _clear_url_session_param()
    _clear_bootstrap_query_param()


def _peek_bootstrap_token() -> str | None:
    try:
        raw = st.query_params.get(BOOTSTRAP_QPARAM)
        if not raw:
            return None
        token = str(raw).strip()
        return token or None
    except Exception:
        return None


def _clear_bootstrap_query_param() -> None:
    try:
        if BOOTSTRAP_QPARAM in st.query_params:
            del st.query_params[BOOTSTRAP_QPARAM]
    except Exception:
        pass


def _read_browser_session_token() -> str | None:
    try:
        ctx = getattr(st, "context", None)
        if ctx is None:
            return None
        cookies = getattr(ctx, "cookies", None)
        if cookies is None:
            return None
        raw = cookies.get(COOKIE_NAME) if hasattr(cookies, "get") else None
        if raw is None and hasattr(cookies, "to_dict"):
            raw = cookies.to_dict().get(COOKIE_NAME)
        if raw is None and COOKIE_NAME in cookies:
            raw = cookies[COOKIE_NAME]
        token = (raw or "").strip()
        return token or None
    except Exception:
        return None


def _persist_client_session(token: str) -> None:
    if not token:
        return
    try:
        import streamlit.components.v1 as components

        secure = " Secure;" if is_ssl_configured() else ""
        token_js = json.dumps(token)
        ls_js = json.dumps(LS_KEY)
        cookie_js = json.dumps(COOKIE_NAME)
        components.html(
            f"""<script>
{_PARENT_JS}
(function () {{
  var t = {token_js};
  var lsKey = {ls_js};
  var cookieName = {cookie_js};
  __ifsLSKey = lsKey;
  __ifsCookieName = cookieName;
  var ls = __ifsLS();
  if (ls) {{ try {{ ls.setItem(lsKey, t); }} catch (e) {{}} }}
  var ss = __ifsSS();
  if (ss) {{ try {{ ss.setItem(lsKey, t); }} catch (e) {{}} }}
  var c = cookieName + "=" + encodeURIComponent(t)
    + "; path=/; max-age={COOKIE_MAX_AGE}; SameSite=Lax;{secure}";
  try {{ __ifsParent().document.cookie = c; }} catch (e) {{ document.cookie = c; }}
}})();
</script>""",
            height=0,
            width=0,
        )
    except Exception:
        pass


def _clear_client_session() -> None:
    try:
        import streamlit.components.v1 as components

        secure = " Secure;" if is_ssl_configured() else ""
        ls_js = json.dumps(LS_KEY)
        cookie_js = json.dumps(COOKIE_NAME)
        components.html(
            f"""<script>
{_PARENT_JS}
(function () {{
  var lsKey = {ls_js};
  var cookieName = {cookie_js};
  __ifsLSKey = lsKey;
  __ifsCookieName = cookieName;
  var ls = __ifsLS();
  if (ls) {{ try {{ ls.removeItem(lsKey); }} catch (e) {{}} }}
  var ss = __ifsSS();
  if (ss) {{ try {{ ss.removeItem(lsKey); }} catch (e) {{}} }}
  var c = cookieName + "=; path=/; max-age=0; SameSite=Lax;{secure}";
  try {{ __ifsParent().document.cookie = c; }} catch (e) {{ document.cookie = c; }}
}})();
</script>""",
            height=0,
            width=0,
        )
    except Exception:
        pass


def _inject_local_storage_restore_bridge() -> None:
    try:
        import streamlit.components.v1 as components

        ls_js = json.dumps(LS_KEY)
        qp_js = json.dumps(BOOTSTRAP_QPARAM)
        cookie_js = json.dumps(COOKIE_NAME)
        components.html(
            f"""<script>
{_PARENT_JS}
(function () {{
  var lsKey = {ls_js};
  var qp = {qp_js};
  var cookieName = {cookie_js};
  __ifsLSKey = lsKey;
  __ifsCookieName = cookieName;
  var t = __ifsClientToken();
  if (!t) return;
  var loc = __ifsParent().location;
  var u = new URL(loc.href);
  if (u.searchParams.get(qp)) return;
  u.searchParams.set(qp, t);
  loc.replace(u.toString());
}})();
</script>""",
            height=0,
            width=0,
        )
    except Exception:
        pass


def _touch() -> None:
    """Legacy helper — prefer enforce_active_session()."""
    enforce_active_session()


def _clear_url_session_param() -> None:
    try:
        if SESSION_QPARAM in st.query_params:
            del st.query_params[SESSION_QPARAM]
    except Exception:
        pass
