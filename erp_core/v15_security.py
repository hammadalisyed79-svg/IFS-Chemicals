"""V15 security — passwords, lockout, session idle, access logging."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta

_PBKDF2_ITERS = 260_000
_HASH_PREFIX = "pbkdf2_sha256"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_setting(key: str, default: str = "") -> str:
    try:
        from db_v3 import get_setting as gs
        return gs(key, default)
    except Exception:
        return default


def hash_password_secure(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ITERS
    ).hex()
    return f"{_HASH_PREFIX}${_PBKDF2_ITERS}${salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    from erp_core.password_v173 import verify_password_v173
    return verify_password_v173(password, stored_hash)


def validate_password_strength(password: str) -> tuple[bool, str]:
    min_len = int(get_setting("password_min_length", "8") or 8)
    if len(password or "") < min_len:
        return False, f"Password must be at least {min_len} characters."
    if not re.search(r"[A-Za-z]", password):
        return False, "Password must contain at least one letter."
    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit."
    return True, ""


def needs_rehash(stored_hash: str) -> bool:
    from erp_core.password_v173 import needs_rehash as nr
    return nr(stored_hash)


def max_failed_logins() -> int:
    return int(get_setting("max_failed_logins", "5") or 5)


def lockout_minutes() -> int:
    return int(get_setting("lockout_minutes", "30") or 30)


def session_idle_minutes() -> int:
    """Minutes of no activity before the session is revoked (all users).

    Default 30. Adjustable in Admin → System Settings → Session idle timeout.
    """
    try:
        mins = int(get_setting("session_idle_minutes", "30") or 30)
    except (TypeError, ValueError):
        mins = 30
    return max(1, min(mins, 480))


_last_session_fail_reason: str | None = None


def last_session_fail_reason() -> str | None:
    """Reason for the most recent failed touch_session ('idle' | 'missing')."""
    return _last_session_fail_reason


def is_account_locked(user: dict) -> tuple[bool, str]:
    until = user.get("locked_until")
    if not until:
        return False, ""
    try:
        if datetime.strptime(until, "%Y-%m-%d %H:%M:%S") > datetime.now():
            return True, f"Account locked until {until}."
    except ValueError:
        pass
    return False, ""


def record_login_attempt(
    username: str,
    success: bool,
    *,
    user_id=None,
    ip: str | None = None,
    user_agent: str | None = None,
    reason: str | None = None,
) -> None:
    from database import get_connection
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO login_attempts(username,user_id,success,ip_address,user_agent,failure_reason)
               VALUES(?,?,?,?,?,?)""",
            (username, user_id, int(success), ip, (user_agent or "")[:500], reason),
        )


def register_failed_login(user_id: int) -> None:
    from database import get_connection, _now
    with get_connection() as conn:
        row = conn.execute(
            "SELECT failed_login_count FROM users WHERE id=?", (user_id,)
        ).fetchone()
        count = (row[0] or 0) + 1 if row else 1
        locked_until = None
        if count >= max_failed_logins():
            locked_until = (
                datetime.now() + timedelta(minutes=lockout_minutes())
            ).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE users SET failed_login_count=?, locked_until=? WHERE id=?",
            (count, locked_until, user_id),
        )


def reset_failed_login(user_id: int) -> None:
    from database import get_connection
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET failed_login_count=0, locked_until=NULL WHERE id=?",
            (user_id,),
        )


def update_last_login(user_id: int, ip: str | None, device: str | None) -> None:
    from database import get_connection, _now
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET last_login_at=?, last_login_ip=?, last_login_device=? WHERE id=?",
            (_now(), ip, (device or "")[:500], user_id),
        )


def touch_session(token: str, ip: str | None = None, user_agent: str | None = None) -> bool:
    """Update last activity; return False if idle timeout exceeded or token missing."""
    global _last_session_fail_reason
    from database import get_connection, _now

    _last_session_fail_reason = None
    idle = session_idle_minutes()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT last_activity_at, created_at FROM user_sessions WHERE token=?",
            (token.strip(),),
        ).fetchone()
        if not row:
            _last_session_fail_reason = "missing"
            return False
        last = row[0] or row[1]
        if last and idle > 0:
            try:
                last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
                if datetime.now() - last_dt > timedelta(minutes=idle):
                    conn.execute("DELETE FROM user_sessions WHERE token=?", (token.strip(),))
                    _last_session_fail_reason = "idle"
                    return False
            except ValueError:
                pass
        conn.execute(
            "UPDATE user_sessions SET last_activity_at=?, ip_address=?, user_agent=? WHERE token=?",
            (_now(), ip, (user_agent or "")[:500], token.strip()),
        )
    return True


def log_access(user_id, action: str, module: str = "", ip: str | None = None,
               user_agent: str | None = None, details: str | None = None) -> None:
    from database import get_connection
    with get_connection() as conn:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='access_log'"
        ).fetchone():
            return
        conn.execute(
            """INSERT INTO access_log(user_id,action,module,ip_address,user_agent,details)
               VALUES(?,?,?,?,?,?)""",
            (user_id, action, module, ip, (user_agent or "")[:500], details),
        )


def is_ssl_configured() -> bool:
    return get_setting("ssl_configured", "0") in ("1", "true", "yes")


def external_access_warning() -> str | None:
    if is_ssl_configured():
        return None
    return (
        "External access is not secured. Configure SSL before live use. "
        "See SSL_SETUP_GUIDE.md and REMOTE_ACCESS_SECURITY.md."
    )


def is_portal_user(user: dict | None) -> bool:
    if not user:
        return False
    ut = (user.get("user_type") or "internal").lower()
    return ut in ("distributor", "distributor_staff")


def is_internal_user(user: dict | None) -> bool:
    return bool(user) and not is_portal_user(user)


def client_context() -> tuple[str | None, str | None]:
    """Best-effort IP and user-agent from Streamlit runtime."""
    ip, ua = None, None
    try:
        import streamlit as st
        ctx = getattr(st, "context", None)
        if ctx:
            ip = getattr(ctx, "ip_address", None)
            ua = getattr(ctx, "user_agent", None)
            if ua and hasattr(ua, "to_str"):
                ua = ua.to_str()
    except Exception:
        pass
    return ip, ua
