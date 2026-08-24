"""V13.14 — enterprise-wide search across documents and masters."""

from __future__ import annotations

from dataclasses import dataclass

from erp_core.transaction_engine import all_document_specs, document_label, search_documents


@dataclass
class SearchHit:
    category: str
    label: str
    key: str
    record_id: int | None
    nav_group: str | None = None
    nav_screen: str | None = None
    doc_type: str | None = None
    extra: str = ""


def _search_masters(query: str, *, limit: int = 8) -> list[SearchHit]:
    import database as db

    q = query.strip().lower()
    if not q:
        return []
    hits: list[SearchHit] = []

    def _match_rows(rows, category, nav_group, nav_screen, code_field="code"):
        for r in rows:
            blob = " ".join(
                str(r.get(k) or "")
                for k in (code_field, "name", "phone", "city", "ntn", "strn", "document_no")
            ).lower()
            if q in blob:
                hits.append(
                    SearchHit(
                        category=category,
                        label=f"{r.get(code_field, '')} — {r.get('name', '')}".strip(" —"),
                        key=f"{category}:{r['id']}",
                        record_id=r["id"],
                        nav_group=nav_group,
                        nav_screen=nav_screen,
                    )
                )
                if len(hits) >= limit:
                    return

    try:
        _match_rows(db.get_customers(), "Customer", "Masters", "Customers")
        _match_rows(db.get_suppliers(), "Supplier", "Masters", "Suppliers")
        _match_rows(db.get_products(active_only=False), "Item", "Masters", "Products")
        _match_rows(db.get_employees(active_only=False), "Employee", "HR", "Employees")
    except Exception:
        pass

    try:
        import db_v3
        for r in db_v3.get_vehicles() if hasattr(db_v3, "get_vehicles") else []:
            blob = f"{r.get('registration_no', '')} {r.get('name', '')}".lower()
            if q in blob:
                hits.append(SearchHit("Vehicle", f"{r.get('registration_no')} — {r.get('name')}", f"veh:{r['id']}", r["id"], "Masters", "Vehicles"))
        for r in db_v3.get_machines() if hasattr(db_v3, "get_machines") else []:
            blob = f"{r.get('code', '')} {r.get('name', '')}".lower()
            if q in blob:
                hits.append(SearchHit("Machine", f"{r.get('code')} — {r.get('name')}", f"mach:{r['id']}", r["id"], "Production", "Machines"))
    except Exception:
        pass

    try:
        with db.get_connection() as conn:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='chart_of_accounts'").fetchone():
                for r in conn.execute(
                    "SELECT id, code, name FROM chart_of_accounts WHERE active=1 OR active IS NULL"
                ).fetchall():
                    blob = f"{r['code']} {r['name']}".lower()
                    if q in blob:
                        hits.append(SearchHit("Account", f"{r['code']} — {r['name']}", f"acct:{r['id']}", r["id"], "Finance", "Chart of Accounts"))
    except Exception:
        pass

    return hits[:limit]


def enterprise_search(query: str, *, limit: int = 20) -> list[SearchHit]:
    """Search invoices, vouchers, masters, production, vehicles, accounts."""
    q = (query or "").strip()
    if not q:
        return []

    hits: list[SearchHit] = []
    per_doc = max(3, limit // 4)

    for spec in all_document_specs():
        if not spec.search_fn:
            continue
        for row in search_documents(spec, q, limit=per_doc):
            rid = row.get("id")
            hits.append(
                SearchHit(
                    category=spec.label,
                    label=document_label(row, spec),
                    key=f"{spec.key}:{rid}",
                    record_id=rid,
                    nav_group=spec.nav_group,
                    nav_screen=spec.nav_screen,
                    doc_type=spec.key,
                    extra=str(row.get("status") or ""),
                )
            )
        if len(hits) >= limit:
            return hits[:limit]

    hits.extend(_search_masters(q, limit=limit - len(hits)))
    return hits[:limit]
