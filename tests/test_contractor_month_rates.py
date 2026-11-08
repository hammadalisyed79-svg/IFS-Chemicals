"""Changing contractor SKU rates for one month must not rewrite earlier paid months."""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import database as db  # noqa: E402


def _cleanup(path: Path) -> None:
    db.reset_runtime_state()
    for suffix in ("", "-wal", "-shm"):
        p = Path(f"{path}{suffix}") if suffix else path
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass


def test_october_rate_change_does_not_rewrite_paid_august():
    path = Path(tempfile.gettempdir()) / f"erp_cl_rate_{uuid.uuid4().hex}.db"
    os.environ["IFS_DB_PATH"] = str(path)
    db.DB_PATH = path
    db.reset_runtime_state()
    db.init_db()

    try:
        with db.get_connection() as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(products)").fetchall()}
            if "product_type" in cols:
                conn.execute(
                    "INSERT INTO products(code, name, product_type, is_active) "
                    "VALUES ('DWTEST', 'Dishwash test', 'finished', 1)"
                )
            else:
                conn.execute(
                    "INSERT INTO products(code, name, is_active) "
                    "VALUES ('DWTEST', 'Dishwash test', 1)"
                )
            pid = int(conn.execute("SELECT id FROM products WHERE code='DWTEST'").fetchone()[0])
            conn.execute(
                "INSERT INTO suppliers(code, name, is_active) VALUES ('CLRATE1', 'Rate Contr', 1)"
            )
            sid = int(conn.execute("SELECT id FROM suppliers WHERE code='CLRATE1'").fetchone()[0])
            from db_contractors import apply_contract_labour

            apply_contract_labour(conn)

        from db_contractors import (
            add_contractor,
            calculate_contractor_month,
            month_bounds,
            save_contractor_month_run,
            save_contractor_products,
        )

        cid = add_contractor(
            {"supplier_id": sid, "payment_type": "sku_carton", "default_rate": 14},
            user_id=1,
        )
        save_contractor_products(
            cid, [pid], rates={pid: 14.0}, billing_basis={pid: "closing"},
            user_id=1, effective_month="2026-08",
        )
        save_contractor_month_run(
            cid,
            "2026-08",
            [{
                "product_id": pid,
                "product_code": "DWTEST",
                "product_name": "Dishwash test",
                "sold_qty": 100,
                "stock_qty": 0,
                "sale_return_qty": 0,
                "manual_qty": 0,
                "quantity": 100,
                "rate": 14.0,
                "amount": 1400.0,
            }],
            user_id=1,
        )

        save_contractor_products(
            cid, [pid], rates={pid: 16.0}, billing_basis={pid: "closing"},
            user_id=1, effective_month="2026-10",
        )

        fd8, td8 = month_bounds(2026, 8)
        aug = calculate_contractor_month(cid, fd8, td8)
        assert aug["lines"][0]["rate"] == 14.0, aug["lines"][0]

        fd10, td10 = month_bounds(2026, 10)
        oct_ = calculate_contractor_month(cid, fd10, td10)
        assert oct_["lines"][0]["rate"] == 16.0, oct_["lines"][0]
    finally:
        _cleanup(path)
