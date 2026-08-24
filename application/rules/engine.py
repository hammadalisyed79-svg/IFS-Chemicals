"""Configurable business rule engine."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class RuleResult:
    passed: bool
    action: str = "allow"
    message: str = ""
    require_approval: bool = False
    approval_level: int = 0


def _eval_condition(cond: dict, context: dict) -> bool:
    field = cond.get("field", "")
    op = cond.get("op", "eq")
    val = cond.get("value")
    ref = cond.get("ref")
    actual = context.get(field)
    if ref:
        parts = ref.split(".")
        target = context
        for p in parts:
            target = target.get(p, {}) if isinstance(target, dict) else {}
        val = target
    if op == "required":
        return actual is not None and actual != ""
    if op == "gt":
        return float(actual or 0) > float(val or 0)
    if op == "gte":
        return float(actual or 0) >= float(val or 0)
    if op == "lt":
        return float(actual or 0) < float(val or 0)
    if op == "lte":
        return float(actual or 0) <= float(val or 0)
    if op == "eq":
        return actual == val
    return True


def evaluate_rules(category: str, context: dict, *, company_id: int = 1) -> list[RuleResult]:
    from database import get_connection, rows_to_list
    results = []
    with get_connection() as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='erp_business_rules'").fetchone():
            return [RuleResult(passed=True)]
        rules = rows_to_list(conn.execute(
            """SELECT * FROM erp_business_rules
               WHERE category=? AND company_id=? AND is_active=1
               ORDER BY priority ASC""",
            (category, company_id),
        ).fetchall())
    for rule in rules:
        cond = json.loads(rule.get("condition_json") or "{}")
        action = json.loads(rule.get("action_json") or "{}")
        ok = _eval_condition(cond, context)
        if not ok:
            act = action.get("action", "block")
            results.append(RuleResult(
                passed=False,
                action=act,
                message=action.get("message", rule.get("name", "Rule failed")),
                require_approval=act == "require_approval",
                approval_level=int(action.get("level", 0)),
            ))
    if not results:
        results.append(RuleResult(passed=True))
    return results


def assert_rules(category: str, context: dict, *, company_id: int = 1) -> None:
    for r in evaluate_rules(category, context, company_id=company_id):
        if not r.passed and r.action == "block":
            raise ValueError(r.message)


def list_rules(category: str | None = None, company_id: int = 1) -> list[dict]:
    from database import get_connection, rows_to_list
    where, params = ["company_id=?"], [company_id]
    if category:
        where.append("category=?")
        params.append(category)
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            f"SELECT * FROM erp_business_rules WHERE {' AND '.join(where)} ORDER BY priority",
            params,
        ).fetchall())


def save_rule(rule_code: str, name: str, category: str, condition: dict, action: dict, company_id: int = 1) -> None:
    from database import get_connection
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO erp_business_rules(rule_code,name,category,condition_json,action_json,company_id)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(rule_code,company_id) DO UPDATE SET
               name=excluded.name, condition_json=excluded.condition_json, action_json=excluded.action_json""",
            (rule_code, name, category, json.dumps(condition), json.dumps(action), company_id),
        )
