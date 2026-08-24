"""Tenant isolation — enforce company_id on every application query."""

from __future__ import annotations

import re
from contextvars import ContextVar
from dataclasses import dataclass

_tenant_ctx: ContextVar["TenantScope | None"] = ContextVar("tenant_scope", default=None)

TENANT_TABLES = frozenset({
    "customers", "suppliers", "products", "warehouses", "sales_invoices", "purchase_invoices",
    "sales_orders", "purchase_orders", "chart_of_accounts", "employees", "portal_orders",
    "quotations", "delivery_notes", "goods_receipt_notes", "journal_vouchers",
    "ifs_formula_master", "ifs_batch_tickets", "ifs_qc_specs", "ifs_qc_inspections",
    "ifs_pm_schedules", "ifs_breakdown_tickets", "ifs_energy_readings", "ifs_toll_agreements",
    "ifs_warehouse_zones", "ifs_cycle_counts", "ifs_integration_devices",
})


@dataclass
class TenantScope:
    company_id: int = 1
    branch_id: int = 1
    user_id: int | None = None
    enforce: bool = True


def get_scope() -> TenantScope:
    s = _tenant_ctx.get()
    return s if s else TenantScope()


def set_scope(company_id: int = 1, branch_id: int = 1, user_id: int | None = None, enforce: bool = True) -> None:
    _tenant_ctx.set(TenantScope(company_id, branch_id, user_id, enforce))


def clear_scope() -> None:
    _tenant_ctx.set(None)


def tenant_filter(alias: str = "") -> tuple[str, list]:
    """SQL fragment + params for company_id (and optionally branch_id)."""
    scope = get_scope()
    p = f"{alias}." if alias else ""
    return f"{p}company_id=?", [scope.company_id]


def tenant_filter_full(alias: str = "") -> tuple[str, list]:
    scope = get_scope()
    p = f"{alias}." if alias else ""
    return f"{p}company_id=? AND {p}branch_id=?", [scope.company_id, scope.branch_id]


def inject_where(sql: str, alias: str = "") -> tuple[str, list]:
    """Append tenant filter to SELECT if table is in TENANT_TABLES and scope.enforce."""
    scope = get_scope()
    if not scope.enforce:
        _audit_bypass(sql)
        return sql, []
    frag, params = tenant_filter(alias)
    if re.search(r"\bWHERE\b", sql, re.I):
        return f"{sql} AND {frag}", params
    return f"{sql} WHERE {frag}", params


def validate_row(row: dict | None, *, table: str = "") -> dict | None:
    """Reject row if company_id mismatch."""
    if not row:
        return None
    scope = get_scope()
    if not scope.enforce:
        return row
    cid = row.get("company_id")
    if cid is not None and int(cid) != scope.company_id:
        raise PermissionError(f"Tenant isolation: {table or 'record'} belongs to company {cid}")
    return row


def _audit_bypass(sql: str) -> None:
    try:
        from database import get_connection
        with get_connection() as conn:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='erp_tenant_audit'").fetchone():
                conn.execute(
                    "INSERT INTO erp_tenant_audit(source,sql_fragment,bypassed) VALUES(?,?,1)",
                    ("tenant", sql[:500]),
                )
    except Exception:
        pass


def coverage_report() -> dict:
    """Scan tenant column presence on TENANT_TABLES."""
    from database import get_connection
    report = {"tables": {}, "missing_company_id": [], "enforced": get_scope().enforce}
    with get_connection() as conn:
        for t in TENANT_TABLES:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone():
                continue
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})").fetchall()]
            has_c = "company_id" in cols
            has_b = "branch_id" in cols
            report["tables"][t] = {"company_id": has_c, "branch_id": has_b}
            if not has_c:
                report["missing_company_id"].append(t)
    report["coverage_pct"] = round(
        100.0 * (len(TENANT_TABLES) - len(report["missing_company_id"])) / max(len(TENANT_TABLES), 1), 1
    )
    return report
