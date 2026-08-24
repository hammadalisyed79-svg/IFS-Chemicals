"""Shared API dependencies and pagination."""

from __future__ import annotations

from fastapi import HTTPException, Query
from pydantic import BaseModel

import database as db
from security.jwt_auth import decode_token
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
    pages: int


class CustomerCreate(BaseModel):
    code: str
    name: str
    phone: str | None = None
    email: str | None = None
    credit_limit: float = 0

    model_config = {"json_schema_extra": {"examples": [{"code": "CUS001", "name": "Acme Ltd", "credit_limit": 500000}]}}


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.get_user_by_id(int(payload["sub"]))
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=401, detail="User inactive")
    from application.tenant import set_scope
    set_scope(
        company_id=int(user.get("default_company_id") or 1),
        branch_id=int(user.get("default_branch_id") or 1),
        user_id=user["id"],
        enforce=True,
    )
    return user


def pagination(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500)):
    return {"page": page, "page_size": page_size, "offset": (page - 1) * page_size}
