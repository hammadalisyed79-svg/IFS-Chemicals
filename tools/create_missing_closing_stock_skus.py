"""Create 5 missing closing-stock SKUs and set Jul 31 closing qty."""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import database as db

ITEMS = [
    ("DW0004", "BAHAR DISHWASH GOLA (80/36)", 93.0),
    ("DW008", "BAHAR DISHWASH 120/24 (GOLA QUALITY)", 34.0),
    ("DW2011", "RING DISHWASH 80/48 MLB", 204.0),
    ("DW2014", "RING DISHWASH 60/48", 244.0),
    ("DW7015", "SAGA DISHWASH 150/24 LONGBAR", 82.0),
]
ADJ_DATE = "2026-07-31"
AS_OF_NEXT = "2026-08-01"
REASON = "Closing stock take 31.07.2026 (Excel) — create missing SKU"


def _template(conn, code: str) -> dict:
    prefix = "".join(ch for ch in code if ch.isalpha()) or "DW"
    row = conn.execute(
        """
        SELECT category_id, unit_id, product_type, purchase_price, sale_price,
               reorder_level, min_stock, tax_rate_id, group_id, weight_unit,
               packing_size
        FROM products
        WHERE UPPER(code) LIKE ? AND is_active=1
        ORDER BY id DESC LIMIT 1
        """,
        (f"{prefix}%",),
    ).fetchone()
    if not row:
        row = conn.execute(
            """
            SELECT category_id, unit_id, product_type, purchase_price, sale_price,
                   reorder_level, min_stock, tax_rate_id, group_id, weight_unit,
                   packing_size
            FROM products WHERE UPPER(code) LIKE 'DW%' AND is_active=1
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
    return dict(row) if row else {}


def main():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = ROOT / "backups" / f"pre_create_missing_dw_{stamp}.db"
    bak.parent.mkdir(exist_ok=True)
    with db.get_connection() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    shutil.copy2(db.DB_PATH, bak)
    print("Backup:", bak)

    uid = None
    with db.get_connection() as conn:
        u = conn.execute(
            "SELECT id FROM users WHERE LOWER(username)='admin' AND is_active=1 LIMIT 1"
        ).fetchone()
        uid = int(u["id"]) if u else None

    for code, name, qty in ITEMS:
        with db.get_connection() as conn:
            existing = conn.execute(
                "SELECT id, code, name FROM products WHERE UPPER(TRIM(code))=?",
                (code.upper(),),
            ).fetchone()
            tpl = _template(conn, code)
            wh = db._default_warehouse_id(conn)

        if existing:
            pid = int(existing["id"])
            print(f"EXISTS {code} id={pid}")
        else:
            pid = db.add_item(
                {
                    "code": code,
                    "name": name,
                    "category_id": tpl.get("category_id"),
                    "unit_id": tpl.get("unit_id"),
                    "item_type": tpl.get("product_type") or "finished",
                    "purchase_price": float(tpl.get("purchase_price") or 0),
                    "sale_price": float(tpl.get("sale_price") or 0),
                    "reorder_level": float(tpl.get("reorder_level") or 0),
                    "min_stock": float(tpl.get("min_stock") or 0),
                    "tax_rate_id": tpl.get("tax_rate_id"),
                    "group_id": tpl.get("group_id"),
                    "weight_unit": tpl.get("weight_unit") or "kg",
                    "packing_size": tpl.get("packing_size"),
                    "stock_qty": 0,
                },
                created_by=uid,
            )
            print(f"CREATED {code} id={pid}  {name}")

        with db.get_connection() as conn:
            wh = db._default_warehouse_id(conn)
            cur_qty = float(
                conn.execute(
                    "SELECT COALESCE(SUM(quantity),0) FROM warehouse_stock WHERE product_id=?",
                    (pid,),
                ).fetchone()[0]
            )
            net = float(
                conn.execute(
                    """
                    SELECT COALESCE(SUM(
                      CASE LOWER(COALESCE(movement_type,''))
                        WHEN 'in' THEN quantity
                        WHEN 'out' THEN -quantity
                        ELSE 0 END
                    ),0)
                    FROM inventory_movements
                    WHERE product_id=? AND movement_date >= ?
                    """,
                    (pid, AS_OF_NEXT),
                ).fetchone()[0]
            )
            target_current = round(qty + net, 4)
            delta = round(target_current - cur_qty, 4)
            print(f"  cur={cur_qty} net_since={net} target_open={qty} delta={delta}")
            if abs(delta) < 0.0005:
                print("  already aligned")
                continue
            db._adjust_warehouse_stock(conn, pid, wh, delta, user_id=uid)
            mov = "in" if delta > 0 else "out"
            conn.execute(
                """INSERT INTO inventory_movements(
                       movement_date, product_id, warehouse_id, movement_type, quantity,
                       reference_type, reference_id, reason, created_by)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    ADJ_DATE, pid, wh, mov, abs(delta),
                    "adjustment", None,
                    f"{REASON} → closing={qty:g}",
                    uid,
                ),
            )
            print(f"  adjusted {mov} {abs(delta)}")

    db.invalidate_stock()
    print("\nVerify opening as of Aug 1:")
    with db.get_connection() as conn:
        for code, name, qty in ITEMS:
            p = conn.execute(
                "SELECT id, code, name FROM products WHERE UPPER(TRIM(code))=?",
                (code.upper(),),
            ).fetchone()
            pid = int(p["id"])
            cur_qty = float(
                conn.execute(
                    "SELECT COALESCE(SUM(quantity),0) FROM warehouse_stock WHERE product_id=?",
                    (pid,),
                ).fetchone()[0]
            )
            net = float(
                conn.execute(
                    """
                    SELECT COALESCE(SUM(
                      CASE LOWER(COALESCE(movement_type,''))
                        WHEN 'in' THEN quantity
                        WHEN 'out' THEN -quantity
                        ELSE 0 END
                    ),0)
                    FROM inventory_movements
                    WHERE product_id=? AND movement_date >= ?
                    """,
                    (pid, AS_OF_NEXT),
                ).fetchone()[0]
            )
            opening = round(cur_qty - net, 4)
            ok = abs(opening - qty) < 0.01
            print(f"  {code}: opening={opening} excel={qty} cur={cur_qty} {'OK' if ok else 'FAIL'}")
    print("Done.")


if __name__ == "__main__":
    main()
