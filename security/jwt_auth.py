"""JWT authentication for REST API."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from application.config import config

try:
    from jose import JWTError, jwt
except ImportError:
    jwt = None
    JWTError = Exception

ALGORITHM = "HS256"


def _secret() -> str:
    s = config.get("security", "jwt_secret", "")
    if not s:
        import secrets
        s = secrets.token_urlsafe(48)
        config.set("security", "jwt_secret", s)
    return s


def _expire_minutes() -> int:
    try:
        return int(config.get("security", "jwt_expire_minutes", "60") or 60)
    except ValueError:
        return 60


def create_access_token(data: dict[str, Any]) -> str:
    if jwt is None:
        raise RuntimeError("Install python-jose: pip install python-jose[cryptography]")
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=_expire_minutes())
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    if jwt is None:
        return None
    try:
        return jwt.decode(token, _secret(), algorithms=[ALGORITHM])
    except JWTError:
        return None


def authenticate_user(username: str, password: str) -> dict | None:
    import database as db
    from erp_core.v15_security import client_context
    ip, ua = client_context()
    user = db.authenticate(username, password, ip=ip, user_agent=ua)
    if not user or user.get("_error"):
        return None
    return user
