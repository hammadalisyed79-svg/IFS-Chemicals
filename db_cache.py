"""In-process read caches (no UI dependency). Cleared on master/transaction writes."""

from __future__ import annotations

import time
from typing import Any, Callable

# Seconds — short enough for stock/balance freshness without rerunning every Streamlit widget
_MASTER_TTL = 90
_LIST_TTL = 60

_store: dict[str, tuple[float, Any]] = {}


def cached_read(key: str, loader: Callable[[], Any], ttl: float = _MASTER_TTL) -> Any:
    now = time.monotonic()
    hit = _store.get(key)
    if hit and (now - hit[0]) < ttl:
        return hit[1]
    val = loader()
    _store[key] = (now, val)
    return val


def invalidate(*keys: str) -> None:
    if not keys:
        _store.clear()
        return
    for k in keys:
        _store.pop(k, None)
    for k in list(_store.keys()):
        if any(k.startswith(p) for p in keys):
            _store.pop(k, None)


def invalidate_all() -> None:
    _store.clear()


def invalidate_masters() -> None:
    invalidate("customers", "suppliers", "items", "tax_rates")


def invalidate_invoices() -> None:
    invalidate("sales", "purchases")


def invalidate_stock() -> None:
    invalidate("items")
