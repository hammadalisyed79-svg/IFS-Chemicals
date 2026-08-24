"""V14 RC1 — master data shared operations."""

from __future__ import annotations

import csv
import io
from typing import Any


MASTER_TABLES = {
    "customer": ("customers", "Masters", "Customers", ("code", "name", "phone", "city", "ntn")),
    "supplier": ("suppliers", "Masters", "Suppliers", ("code", "name", "phone", "city", "ntn")),
    "product": ("products", "Masters", "Products", ("code", "name")),
    "warehouse": ("warehouses", "Masters", "Warehouses", ("code", "name")),
    "employee": ("employees", "HR", "Employees", ("code", "full_name")),
    "account": ("chart_of_accounts", "Finance", "Chart of Accounts", ("code", "name")),
}


def deactivate_record(table: str, record_id: int, user_id: int | None = None) -> None:
    from database import get_connection, _now

    with get_connection() as conn:
        if not conn.execute(
            f"SELECT 1 FROM pragma_table_info('{table}') WHERE name='is_active'"
        ).fetchone():
            raise ValueError("This master does not support deactivate.")
        conn.execute(
            f"UPDATE {table} SET is_active=0, modified_at=? WHERE id=?",
            (_now(), record_id),
        )


def reactivate_record(table: str, record_id: int) -> None:
    from database import get_connection, _now

    with get_connection() as conn:
        conn.execute(
            f"UPDATE {table} SET is_active=1, modified_at=? WHERE id=?",
            (_now(), record_id),
        )


def export_rows_csv(rows: list[dict], columns: list[str] | None = None) -> str:
    if not rows:
        return ""
    columns = columns or list(rows[0].keys())
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in columns})
    return buf.getvalue()


def find_duplicates(rows: list[dict], *fields: str) -> list[list[dict]]:
    buckets: dict[tuple, list] = {}
    for r in rows:
        key = tuple((str(r.get(f) or "").strip().lower() for f in fields))
        if not any(key):
            continue
        buckets.setdefault(key, []).append(r)
    return [grp for grp in buckets.values() if len(grp) > 1]


def merge_customers(keep_id: int, merge_ids: list[int], user_id: int | None = None) -> None:
    """Repoint foreign keys from duplicates to keep_id, then deactivate merged rows."""
    from database import get_connection

    with get_connection() as conn:
        for mid in merge_ids:
            if mid == keep_id:
                continue
            for table, col in (
                ("sales_invoices", "customer_id"),
                ("sales_orders", "customer_id"),
                ("quotations", "customer_id"),
            ):
                if conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE name=?", (table,)
                ).fetchone():
                    conn.execute(
                        f"UPDATE {table} SET {col}=? WHERE {col}=?", (keep_id, mid),
                    )
            conn.execute("UPDATE customers SET is_active=0 WHERE id=?", (mid,))
