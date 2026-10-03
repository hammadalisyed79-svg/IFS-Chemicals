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
