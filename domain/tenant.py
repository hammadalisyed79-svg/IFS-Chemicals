"""Tenant context — company and branch scope."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TenantContext:
    company_id: int = 1
    branch_id: int = 1
    user_id: int | None = None

    def sql_filter(self, alias: str = "") -> tuple[str, list]:
        prefix = f"{alias}." if alias else ""
        return (
            f"{prefix}company_id=? AND {prefix}branch_id=?",
            [self.company_id, self.branch_id],
        )


_default = TenantContext()


def get_tenant() -> TenantContext:
    return _default


def set_tenant(company_id: int, branch_id: int = 1, user_id: int | None = None) -> None:
    global _default
    _default = TenantContext(company_id, branch_id, user_id)
