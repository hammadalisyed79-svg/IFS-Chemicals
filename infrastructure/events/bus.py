"""Event bus V17 — multi-subscriber, webhooks, plugin dispatch."""

from __future__ import annotations

import json
import logging
from typing import Callable

from domain.events import DomainEvent

_log = logging.getLogger("ifs.events")
_handlers: dict[str, list[Callable[[DomainEvent], None]]] = {}


def subscribe(event_type: str, handler: Callable[[DomainEvent], None]) -> None:
    _handlers.setdefault(event_type, []).append(handler)


def subscribe_all(handler: Callable[[DomainEvent], None]) -> None:
    subscribe("*", handler)


def publish(event: DomainEvent) -> int | None:
    from database import get_connection
    from infrastructure.observability.tracing import get_trace_id

    if not event.trace_id:
        event.trace_id = get_trace_id()

    event_id = None
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='erp_domain_events'").fetchone():
            cur = conn.execute(
                """INSERT INTO erp_domain_events(
                    event_type,aggregate_type,aggregate_id,payload,
                    company_id,branch_id,user_id)
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    event.event_type, event.aggregate_type, event.aggregate_id,
                    json.dumps({**event.payload, "trace_id": event.trace_id}),
                    event.company_id, event.branch_id, event.user_id,
                ),
            )
            event_id = cur.lastrowid

    _log.info("event=%s id=%s trace=%s", event.event_type, event_id, event.trace_id)

    for handler in list(_handlers.get(event.event_type, [])):
        try:
            handler(event)
        except Exception as exc:
            _log.exception("Handler failed %s: %s", event.event_type, exc)

    for handler in list(_handlers.get("*", [])):
        try:
            handler(event)
        except Exception:
            pass

    _dispatch_db_subscribers(event)
    _dispatch_webhooks(event)
    _dispatch_plugins(event)
    return event_id


def publish_simple(event_type: str, **kwargs) -> int | None:
    from domain.events import DomainEvent
    return publish(DomainEvent(event_type=event_type, **kwargs))


def _dispatch_db_subscribers(event: DomainEvent) -> None:
    try:
        from database import get_connection, rows_to_list
        with get_connection() as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='erp_event_subscriptions'").fetchone():
                return
            subs = rows_to_list(conn.execute(
                """SELECT * FROM erp_event_subscriptions
                   WHERE is_active=1 AND (event_type=? OR event_type='*')""",
                (event.event_type,),
            ).fetchall())
        for sub in subs:
            st = sub.get("subscriber_type")
            if st == "webhook":
                _fire_webhook_url(sub.get("subscriber_ref"), event)
            elif st == "job":
                from infrastructure.jobs.worker import enqueue
                enqueue("event_handler", {"event": event.event_type, "payload": event.payload})
    except Exception:
        pass


def _dispatch_webhooks(event: DomainEvent) -> None:
    try:
        from database import get_connection, rows_to_list
        with get_connection() as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='erp_webhooks'").fetchone():
                return
            hooks = rows_to_list(conn.execute(
                "SELECT * FROM erp_webhooks WHERE is_active=1"
            ).fetchall())
        for h in hooks:
            types = (h.get("event_types") or "").split(",")
            if "*" in types or event.event_type in types:
                _fire_webhook_url(h.get("url"), event)
    except Exception:
        pass


def _fire_webhook_url(url: str | None, event: DomainEvent) -> None:
    if not url:
        return
    try:
        import urllib.request
        body = json.dumps({
            "event_type": event.event_type,
            "aggregate_type": event.aggregate_type,
            "aggregate_id": event.aggregate_id,
            "payload": event.payload,
            "trace_id": event.trace_id,
        }).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=5)
    except Exception as exc:
        _log.warning("Webhook failed %s: %s", url, exc)


def _dispatch_plugins(event: DomainEvent) -> None:
    try:
        from plugins.loader import dispatch_event
        dispatch_event(event)
    except Exception:
        pass
