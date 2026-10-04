"""Reverse production_physical posts restores warehouse qty and draft status."""

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
from db_production_stock import (  # noqa: E402
    REF_TYPE_PRODUCTION,
    production_qty_formula,
    reverse_production_month_run,
)


def _cleanup(path: Path) -> None:
    db.reset_runtime_state()
    for suffix in ("", "-wal", "-shm"):
        p = Path(f"{path}{suffix}") if suffix else path
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass


def test_reverse_production_month_undoes_stock():
    path = Path(tempfile.gettempdir()) / f"erp_prod_rev_{uuid.uuid4().hex}.db"
    os.environ["IFS_DB_PATH"] = str(path)
    db.DB_PATH = path
    db.reset_runtime_state()
    db.init_db()
    try:
        with db.get_connection() as conn:
            wh = conn.execute("SELECT id FROM warehouses ORDER BY id LIMIT 1").fetchone()
            assert wh
            wh_id = int(wh[0])
            cols = {r[1] for r in conn.execute("PRAGMA table_info(products)").fetchall()}
            if "unit_id" in cols:
                urow = conn.execute("SELECT id FROM units LIMIT 1").fetchone()
                if not urow:
                    ucols = {r[1] for r in conn.execute("PRAGMA table_info(units)").fetchall()}
                    if "code" in ucols:
                        conn.execute("INSERT INTO units(code, name) VALUES ('PCS', 'Pieces')")
                    else:
                        conn.execute("INSERT INTO units(name) VALUES ('Pieces')")
                    urow = conn.execute("SELECT id FROM units LIMIT 1").fetchone()
                conn.execute(
                    "INSERT INTO products(code, name, product_type, is_active, unit_id) "
                    "VALUES ('REVT01', 'Rev Test', 'finished', 1, ?)",
                    (int(urow[0]),),
                )
            else:
                conn.execute(
                    "INSERT INTO products(code, name, is_active) VALUES ('REVT01', 'Rev Test', 1)"
                )
            pid = int(conn.execute("SELECT id FROM products WHERE code='REVT01'").fetchone()[0])
            conn.execute(
                "INSERT INTO warehouse_stock(warehouse_id, product_id, quantity) VALUES (?,?,?)",
                (wh_id, pid, 10),
            )

        rid = db.save_production_month_run(
            wh_id,
            "2026-08",
            [{
                "product_id": pid,
                "product_code": "REVT01",
                "product_name": "Rev Test",
                "opening_qty": 10,
                "sold_qty": 0,
                "return_qty": 0,
                "adj_qty": 0,
                "physical_qty": 25,
                "production_qty": 15,
                "closing_qty": 25,
                "sort_order": 0,
            }],
        )
        db.post_production_month_run(rid, allow_negative=True)
        with db.get_connection() as conn:
            qty = float(
                conn.execute(
                    "SELECT quantity FROM warehouse_stock WHERE warehouse_id=? AND product_id=?",
                    (wh_id, pid),
                ).fetchone()[0]
            )
            n = conn.execute(
                "SELECT COUNT(*) FROM inventory_movements WHERE reference_type=? AND reference_id=?",
                (REF_TYPE_PRODUCTION, rid),
            ).fetchone()[0]
        assert n >= 1
        assert abs(qty - 25) < 0.001

        result = reverse_production_month_run(rid)
        assert result["reversed_movements"] >= 1
        with db.get_connection() as conn:
            qty2 = float(
                conn.execute(
                    "SELECT quantity FROM warehouse_stock WHERE warehouse_id=? AND product_id=?",
                    (wh_id, pid),
                ).fetchone()[0]
            )
            n2 = conn.execute(
                "SELECT COUNT(*) FROM inventory_movements WHERE reference_type=? AND reference_id=?",
                (REF_TYPE_PRODUCTION, rid),
            ).fetchone()[0]
            st = conn.execute(
                "SELECT status, posted_at FROM production_month_runs WHERE id=?", (rid,)
            ).fetchone()
        assert n2 == 0
        assert abs(qty2 - 10) < 0.001
        assert st["status"] == "draft"
        assert not st["posted_at"]
    finally:
        _cleanup(path)


def test_formula_reverse_of_sales_ignores_adj():
    prod, closing = production_qty_formula(172, 4477, 0, 23071, 1726)
    assert closing == 1726
    assert abs(prod - (1726 - 172 - 0 + 4477)) < 0.001
    assert prod > 0


def test_post_production_is_stock_in_when_sales_went_out():
    """Sale already OUT; reverse-calculated production posts IN."""
    path = Path(tempfile.gettempdir()) / f"erp_prod_in_{uuid.uuid4().hex}.db"
    os.environ["IFS_DB_PATH"] = str(path)
    db.DB_PATH = path
    db.reset_runtime_state()
    db.init_db()
    try:
        with db.get_connection() as conn:
            wh_id = int(conn.execute("SELECT id FROM warehouses ORDER BY id LIMIT 1").fetchone()[0])
            cols = {r[1] for r in conn.execute("PRAGMA table_info(products)").fetchall()}
            if "unit_id" in cols:
                urow = conn.execute("SELECT id FROM units LIMIT 1").fetchone()
                if not urow:
                    conn.execute("INSERT INTO units(name) VALUES ('Pieces')")
                    urow = conn.execute("SELECT id FROM units LIMIT 1").fetchone()
                conn.execute(
                    "INSERT INTO products(code, name, product_type, is_active, unit_id) "
                    "VALUES ('SALE01', 'Sale Rev', 'finished', 1, ?)",
                    (int(urow[0]),),
                )
            else:
                conn.execute(
                    "INSERT INTO products(code, name, is_active) VALUES ('SALE01', 'Sale Rev', 1)"
                )
            pid = int(conn.execute("SELECT id FROM products WHERE code='SALE01'").fetchone()[0])
            conn.execute(
                "INSERT INTO warehouse_stock(warehouse_id, product_id, quantity) VALUES (?,?,?)",
                (wh_id, pid, 10),
            )
            conn.execute(
                """INSERT INTO inventory_movements
                   (movement_date, product_id, warehouse_id, movement_type,
                    quantity, reference_type, reason)
                   VALUES ('2026-08-15', ?, ?, 'out', 5, 'sales_invoice', 'SI-1')""",
                (pid, wh_id),
            )
            conn.execute(
                "UPDATE warehouse_stock SET quantity=5 WHERE warehouse_id=? AND product_id=?",
                (wh_id, pid),
            )

        rid = db.save_production_month_run(
            wh_id,
            "2026-08",
            [{
                "product_id": pid,
                "product_code": "SALE01",
                "product_name": "Sale Rev",
                "opening_qty": 10,
                "sold_qty": 5,
                "return_qty": 0,
                "adj_qty": 0,
                "physical_qty": 12,
                "production_qty": 7,
                "closing_qty": 12,
                "sort_order": 0,
            }],
        )
        db.post_production_month_run(rid, allow_negative=True)
        with db.get_connection() as conn:
            mv = list(conn.execute(
                """SELECT movement_type, quantity, reason
                   FROM inventory_movements
                   WHERE reference_type=? AND reference_id=?
                   ORDER BY id""",
                (REF_TYPE_PRODUCTION, rid),
            ))
            qty = float(
                conn.execute(
                    "SELECT quantity FROM warehouse_stock WHERE warehouse_id=? AND product_id=?",
                    (wh_id, pid),
                ).fetchone()[0]
            )
            prod = float(
                conn.execute(
                    "SELECT production_qty FROM production_month_lines WHERE run_id=?",
                    (rid,),
                ).fetchone()[0]
            )
        types = [str(r["movement_type"]).lower() for r in mv]
        assert "in" in types
        inn = sum(float(r["quantity"]) for r in mv if str(r["movement_type"]).lower() == "in")
        assert abs(inn - 7) < 0.001
        assert abs(prod - 7) < 0.001
        assert abs(qty - 12) < 0.001
        reasons = " ".join(str(r["reason"] or "") for r in mv)
        assert "production" in reasons.lower()
    finally:
        _cleanup(path)
