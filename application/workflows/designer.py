"""Workflow designer runtime — state machine from JSON definitions."""

from __future__ import annotations

import json
from typing import Any


def get_workflow(doc_type: str, code: str = "", *, company_id: int = 1) -> dict | None:
    from database import get_connection, row_to_dict
    with get_connection() as conn:
        if code:
            row = conn.execute(
                "SELECT * FROM erp_workflow_definitions WHERE code=? AND company_id=? AND is_active=1",
                (code, company_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM erp_workflow_definitions WHERE doc_type=? AND company_id=? AND is_active=1 LIMIT 1",
                (doc_type, company_id),
            ).fetchone()
        if not row:
            return None
        d = row_to_dict(row)
        d["definition"] = json.loads(d.get("definition_json") or "{}")
        return d


def list_workflows(company_id: int = 1) -> list[dict]:
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            "SELECT id,code,name,doc_type,is_active FROM erp_workflow_definitions WHERE company_id=?",
            (company_id,),
        ).fetchall())


def save_workflow(code: str, name: str, doc_type: str, definition: dict, company_id: int = 1) -> None:
    from database import get_connection
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO erp_workflow_definitions(code,name,doc_type,definition_json,company_id)
               VALUES(?,?,?,?,?)
               ON CONFLICT(code,company_id) DO UPDATE SET
               name=excluded.name, definition_json=excluded.definition_json""",
            (code, name, doc_type, json.dumps(definition), company_id),
        )


def can_transition(doc_type: str, current_state: str, action: str, *, company_id: int = 1) -> tuple[bool, str]:
    wf = get_workflow(doc_type, company_id=company_id)
    if not wf:
        return True, current_state
    for tr in wf["definition"].get("transitions", []):
        if tr.get("from") == current_state and tr.get("action") == action:
            return True, tr.get("to", current_state)
    return False, current_state


def apply_transition(doc_type: str, current_state: str, action: str, context: dict | None = None, *, company_id: int = 1) -> str:
    ok, new_state = can_transition(doc_type, current_state, action, company_id=company_id)
    if not ok:
        raise ValueError(f"Transition '{action}' not allowed from '{current_state}'")
    wf = get_workflow(doc_type, company_id=company_id)
    if wf and context:
        notifs = wf["definition"].get("notifications", {})
        if new_state in notifs:
            from infrastructure.events.bus import publish_simple
            publish_simple(
                f"Workflow{new_state.title()}",
                aggregate_type=doc_type,
                payload={"notification": notifs[new_state], **(context or {})},
                company_id=company_id,
            )
    return new_state
