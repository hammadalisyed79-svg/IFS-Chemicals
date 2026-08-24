"""Enhanced caching with TTL and domain invalidation."""

from __future__ import annotations

import time
from typing import Any, Callable

from application.config import config

_store: dict[str, tuple[Any, float]] = {}


def _ttl() -> int:
    try:
        return int(config.get("cache", "ttl_seconds", "300") or 300)
    except ValueError:
        return 300


def get(key: str) -> Any | None:
    if key in _store:
        val, exp = _store[key]
        if time.time() < exp:
            return val
        del _store[key]
    return None


def set(key: str, value: Any, ttl: int | None = None) -> None:
    _store[key] = (value, time.time() + (ttl or _ttl()))


def cached(key: str, loader: Callable[[], Any], ttl: int | None = None) -> Any:
    hit = get(key)
    if hit is not None:
        return hit
    val = loader()
    set(key, val, ttl)
    return val


def invalidate_prefix(prefix: str) -> None:
    for k in list(_store.keys()):
        if k.startswith(prefix):
            del _store[k]


def invalidate_masters() -> None:
    invalidate_prefix("master:")
    try:
        import db_cache
        db_cache.invalidate_masters()
    except Exception:
        pass


def invalidate_permissions() -> None:
    invalidate_prefix("perm:")


def invalidate_dashboard() -> None:
    invalidate_prefix("dash:")


def invalidate_price_lists() -> None:
    invalidate_prefix("price:")
