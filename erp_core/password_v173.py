"""V17.3 — Argon2id password hashing and policy."""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta

_HASH_PREFIX = "argon2id"
_ARGON2_TIME = 3
_ARGON2_MEMORY = 65536
_ARGON2_PARALLELISM = 2


def get_setting(key: str, default: str = "") -> str:
    try:
        from db_v3 import get_setting as gs
        return gs(key, default)
    except Exception:
        return default


def hash_password_argon2id(password: str) -> str:
    from argon2 import PasswordHasher
    ph = PasswordHasher(
        time_cost=_ARGON2_TIME,
        memory_cost=_ARGON2_MEMORY,
        parallelism=_ARGON2_PARALLELISM,
        hash_len=32,
        salt_len=16,
    )
    h = ph.hash(password)
    return f"{_HASH_PREFIX}${h}"


def verify_password_v173(password: str, stored_hash: str) -> bool:
    import hmac
    import hashlib
    if not password or not stored_hash:
        return False
    stored = stored_hash.strip()
    if stored.startswith(f"{_HASH_PREFIX}$"):
        from argon2 import PasswordHasher
        from argon2.exceptions import VerifyMismatchError, InvalidHash
        raw = stored.split("$", 1)[1]
        ph = PasswordHasher()
        try:
            ph.verify(raw, password)
            return True
        except (VerifyMismatchError, InvalidHash):
            return False
    if stored.startswith("pbkdf2_sha256$"):
        parts = stored.split("$")
        if len(parts) != 4:
            return False
        _, iters_s, salt, expected = parts
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iters_s)
        ).hex()
        return hmac.compare_digest(digest, expected)
    # Legacy SHA-256 hex
    return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), stored)


def needs_rehash(stored_hash: str) -> bool:
    return not (stored_hash or "").strip().startswith(f"{_HASH_PREFIX}$")


def validate_password_policy(password: str, username: str = "") -> tuple[bool, str]:
    min_len = int(get_setting("password_min_length", "12") or 12)
    if len(password or "") < min_len:
        return False, f"Password must be at least {min_len} characters."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain an uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must contain a lowercase letter."
    if not re.search(r"\d", password):
        return False, "Password must contain a digit."
    if not re.search(r"[^A-Za-z0-9]", password):
        return False, "Password must contain a special character."
    if username and username.lower() in (password or "").lower():
        return False, "Password must not contain the username."
    weak = {"password", "admin123", "admin", "12345678", "changeme"}
    if (password or "").lower() in weak:
        return False, "Password is too common."
    return True, ""


def password_expired(user: dict) -> tuple[bool, str]:
    days = int(get_setting("password_expiry_days", "90") or 90)
    changed = user.get("password_changed_at")
    if not changed:
        return True, "Password must be changed before continuing."
    try:
        dt = datetime.strptime(changed, "%Y-%m-%d %H:%M:%S")
        if datetime.now() > dt + timedelta(days=days):
            return True, f"Password expired (policy: {days} days)."
    except ValueError:
        return True, "Password change date invalid — change required."
    return False, ""


def check_password_history(user_id: int, password: str) -> tuple[bool, str]:
    hist = int(get_setting("password_history_count", "5") or 5)
    if hist <= 0:
        return True, ""
    from database import get_connection
    with get_connection() as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='erp_password_history'").fetchone():
            return True, ""
        rows = conn.execute(
            "SELECT password_hash FROM erp_password_history WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, hist),
        ).fetchall()
        for row in rows:
            if verify_password_v173(password, row[0]):
                return False, f"Cannot reuse any of the last {hist} passwords."
    return True, ""


def record_password_history(user_id: int, password_hash: str, conn=None) -> None:
    def _write(c):
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='erp_password_history'").fetchone():
            c.execute(
                "INSERT INTO erp_password_history(user_id, password_hash) VALUES(?,?)",
                (user_id, password_hash),
            )

    if conn is not None:
        _write(conn)
        return
    from database import get_connection
    with get_connection() as c:
        _write(c)
