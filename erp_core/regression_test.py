"""V14 RC1 — automated regression test suite (rolled back)."""

from __future__ import annotations

import time
import uuid
from datetime import date


def run_regression_suite() -> list[tuple[str, str, str]]:
    """Execute end-to-end smoke tests. Returns (status, name, detail)."""
    results: list[tuple[str, str, str]] = []
    import database as db

    tag = uuid.uuid4().hex[:6].upper()
    cust_id = sup_id = prod_id = None

    def _run(name: str, fn):
        try:
            fn()
            results.append(("pass", name, "OK"))
        except Exception as exc:
            results.append(("fail", name, str(exc)))

    with db.get_connection() as conn:
        conn.execute("BEGIN")
        try:
            def create_customer():
                nonlocal cust_id
                cur = conn.execute(
                    "INSERT INTO customers(code,name,is_active,created_at) VALUES(?,?,1,datetime('now'))",
                    (f"RCT{tag}", f"Regression Customer {tag}"),
                )
                cust_id = cur.lastrowid
                assert cust_id

            def create_supplier():
                nonlocal sup_id
                cur = conn.execute(
                    "INSERT INTO suppliers(code,name,is_active,created_at) VALUES(?,?,1,datetime('now'))",
                    (f"RSP{tag}", f"Regression Supplier {tag}"),
                )
                sup_id = cur.lastrowid
                assert sup_id

            def create_product():
                nonlocal prod_id
                wh = conn.execute("SELECT id FROM warehouses LIMIT 1").fetchone()
                cur = conn.execute(
                    """INSERT INTO products(code,name,sale_price,purchase_price,is_active,created_at)
                       VALUES(?,?,10,8,1,datetime('now'))""",
                    (f"RIT{tag}", f"Regression Item {tag}"),
                )
                prod_id = cur.lastrowid
                if wh:
                    conn.execute(
                        "INSERT OR IGNORE INTO warehouse_stock(warehouse_id,product_id,quantity) VALUES(?,?,100)",
                        (wh[0], prod_id),
                    )

            def validation_blocks_blank_sale():
                from erp_core.transaction_validation import validate_sale_invoice
                r = validate_sale_invoice({"customer_id": cust_id}, [], None)
                assert not r.ok

            def period_lock_check():
                from erp_core.period_lock import is_period_locked
                assert is_period_locked("2099-01-01") is False

            def inventory_guard():
                from erp_core.inventory_guards import validate_stock_movement
                wh = conn.execute("SELECT id FROM warehouses LIMIT 1").fetchone()
                if prod_id and wh:
                    try:
                        validate_stock_movement(conn, prod_id, wh[0], -1000, user_id=None)
                        raise AssertionError("expected insufficient stock error")
                    except ValueError:
                        pass

            def gl_drilldown():
                from erp_core.gl_drilldown import gl_entries_for_document
                gl_entries_for_document("sales_invoice", 0)

            def document_workflow_registry():
                from erp_core.transaction_engine import all_document_specs
                assert len(all_document_specs()) >= 12

            def enterprise_search():
                from erp_core.enterprise_search import enterprise_search
                enterprise_search("RCT", limit=5)

            def journal_search():
                import db_v3
                rows = db_v3.search_journal_vouchers(q="JV", page_size=5)
                assert rows is not None
                items = rows["items"] if isinstance(rows, dict) else rows
                assert isinstance(items, list)

            for fn in (
                create_customer, create_supplier, create_product,
                validation_blocks_blank_sale, period_lock_check,
                inventory_guard, gl_drilldown, document_workflow_registry,
                enterprise_search, journal_search,
            ):
                _run(fn.__name__.replace("_", " ").title(), fn)
        finally:
            conn.execute("ROLLBACK")

    return results
