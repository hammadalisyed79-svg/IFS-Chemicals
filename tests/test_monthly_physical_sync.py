"""Shared month-end physical stock sync (contractor ↔ Sale & Production)."""

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


def test_physical_sync_contractor_and_production():
    path = Path(tempfile.gettempdir()) / f"erp_phy_sync_{uuid.uuid4().hex}.db"
    os.environ["IFS_DB_PATH"] = str(path)
    db.DB_PATH = path
    db.reset_runtime_state()
    db.init_db()

    try:
        with db.get_connection() as conn:
            # Ensure warehouse + products
            wh = conn.execute("SELECT id FROM warehouses ORDER BY id LIMIT 1").fetchone()
            assert wh, "need warehouse"
            wh_id = int(wh[0])
            cols = {r[1] for r in conn.execute("PRAGMA table_info(products)").fetchall()}
            unit_id = None
            if "unit_id" in cols:
                unit = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='units'"
                ).fetchone()
                if unit:
                    urow = conn.execute("SELECT id FROM units LIMIT 1").fetchone()
                    if not urow:
                        ucols = {r[1] for r in conn.execute("PRAGMA table_info(units)").fetchall()}
                        if "code" in ucols:
                            conn.execute(
                                "INSERT INTO units(code, name) VALUES ('PCS', 'Pieces')"
                            )
                        else:
                            conn.execute("INSERT INTO units(name) VALUES ('Pieces')")
                        urow = conn.execute("SELECT id FROM units LIMIT 1").fetchone()
                    unit_id = int(urow[0]) if urow else None
                if unit_id is not None:
                    conn.execute(
                        "INSERT INTO products(code, name, product_type, is_active, unit_id) "
                        "VALUES ('PHYT01', 'Phy Sync Test', 'finished', 1, ?)",
                        (unit_id,),
                    )
                else:
                    conn.execute(
                        "INSERT INTO products(code, name, product_type, is_active) "
                        "VALUES ('PHYT01', 'Phy Sync Test', 'finished', 1)"
                    )
            else:
                conn.execute(
                    "INSERT INTO products(code, name, is_active) "
                    "VALUES ('PHYT01', 'Phy Sync Test', 1)"
                )
            pid = int(conn.execute("SELECT id FROM products WHERE code='PHYT01'").fetchone()[0])
            # Supplier + sku_carton contractor
            conn.execute(
                "INSERT INTO suppliers(code, name, is_active) VALUES ('PHYC01', 'Phy Contr', 1)"
            )
            sid = int(conn.execute("SELECT id FROM suppliers WHERE code='PHYC01'").fetchone()[0])
            from db_contractors import apply_contract_labour, add_contractor, save_contractor_products

            apply_contract_labour(conn)

        cid = add_contractor(
            {"supplier_id": sid, "payment_type": "sku_carton", "default_rate": 5},
            user_id=1,
        )
        save_contractor_products(
            cid,
            [{"product_id": pid, "rate": 5, "billing_basis": "closing"}],
            user_id=1,
        )

        from db_contractors import save_contractor_month_run, get_contractor_month_run
        from db_monthly_physical import get_physical_map
        from db_production_stock import (
            calculate_production_month,
            save_production_month_run,
            get_production_month_run,
        )

        save_contractor_month_run(
            cid,
            "2026-08",
            [{
                "product_id": pid,
                "product_code": "PHYT01",
                "product_name": "Phy Sync Test",
                "sold_qty": 100,
                "stock_qty": 20,
                "sale_return_qty": 0,
                "manual_qty": 55,
                "closing_stock": 135,
                "rate": 5,
                "amount": 675,
            }],
            user_id=1,
        )
        shared = get_physical_map("2026-08", warehouse_id=wh_id, product_ids=[pid])
        assert abs(shared.get(pid, 0) - 55.0) < 0.001, shared

        calc = calculate_production_month(
            wh_id, "2026-08-01", "2026-08-31", [pid], physical_map={},
        )
        assert abs(float(calc["lines"][0]["physical_qty"]) - 55.0) < 0.001

        save_production_month_run(
            wh_id,
            "2026-08",
            [{
                "product_id": pid,
                "product_code": "PHYT01",
                "product_name": "Phy Sync Test",
                "opening_qty": 20,
                "sold_qty": 100,
                "return_qty": 0,
                "adj_qty": 0,
                "physical_qty": 80,
            }],
            user_id=1,
        )
        shared2 = get_physical_map("2026-08", warehouse_id=wh_id, product_ids=[pid])
        assert abs(shared2.get(pid, 0) - 80.0) < 0.001, shared2

        cl = get_contractor_month_run(cid, "2026-08")
        assert abs(float(cl["lines"][0]["manual_qty"]) - 80.0) < 0.001
        assert abs(float(cl["lines"][0]["closing_stock"]) - 160.0) < 0.001

        pr = get_production_month_run(wh_id, "2026-08")
        assert abs(float(pr["lines"][0]["physical_qty"]) - 80.0) < 0.001
    finally:
        _cleanup(path)
