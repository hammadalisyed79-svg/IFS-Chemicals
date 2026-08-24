"""Report designer — saved layouts with role visibility."""

from __future__ import annotations

import json
from typing import Any


def save_design(
    code: str,
    name: str,
    base_report: str,
    columns: list[str],
    *,
    filters: dict | None = None,
    sort_by: str | None = None,
    group_by: str | None = None,
    role_codes: list[str] | None = None,
    company_id: int = 1,
    created_by: int | None = None,
) -> int:
    layout = {"columns": columns, "sort_by": sort_by, "group_by": group_by}
    from database import get_connection
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO erp_report_designs(code,name,base_report,layout_json,filters_json,role_codes,company_id,created_by)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(code,company_id) DO UPDATE SET
               name=excluded.name, layout_json=excluded.layout_json, filters_json=excluded.filters_json,
               role_codes=excluded.role_codes""",
            (
                code, name, base_report, json.dumps(layout), json.dumps(filters or {}),
                ",".join(role_codes or []), company_id, created_by,
            ),
        )
        return cur.lastrowid


def get_design(code: str, company_id: int = 1) -> dict | None:
    from database import get_connection, row_to_dict
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM erp_report_designs WHERE code=? AND company_id=? AND is_active=1",
            (code, company_id),
        ).fetchone()
        if not row:
            return None
        d = row_to_dict(row)
        d["layout"] = json.loads(d.get("layout_json") or "{}")
        d["filters"] = json.loads(d.get("filters_json") or "{}")
        return d


def list_designs(company_id: int = 1, role_code: str | None = None) -> list[dict]:
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        rows = rows_to_list(conn.execute(
            "SELECT id, code, name, base_report, role_codes FROM erp_report_designs WHERE company_id=? AND is_active=1",
            (company_id,),
        ).fetchall())
    if role_code:
        rows = [r for r in rows if not r.get("role_codes") or role_code in (r.get("role_codes") or "")]
    return rows


def run_design(code: str, company_id: int = 1, params: dict | None = None) -> Any:
    design = get_design(code, company_id)
    if not design:
        raise ValueError(f"Report design not found: {code}")
    import db_reports
    runner = getattr(db_reports, f"report_{design['base_report']}", None)
    if runner:
        return runner(**(params or {}))
    raise ValueError(f"Base report not implemented: {design['base_report']}")
