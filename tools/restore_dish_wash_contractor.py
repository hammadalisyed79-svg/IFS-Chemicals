"""Restore Dish Wash contractor + products from latest good backup."""
from __future__ import annotations

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import database as db

SUPPLIER_ID = 502  # SUP100038


def _find_backup():
    backups = sorted(
        (ROOT / "backups").glob("*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for p in backups:
        try:
            con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            con.row_factory = sqlite3.Row
            row = con.execute(
                """SELECT id FROM contract_labourers WHERE supplier_id=?""",
                (SUPPLIER_ID,),
            ).fetchone()
            nprod = 0
            if row:
                nprod = con.execute(
                    "SELECT COUNT(*) FROM contract_labour_products WHERE contractor_id=?",
                    (row["id"],),
                ).fetchone()[0]
            con.close()
            if row and nprod > 0:
                return p, int(row["id"]), nprod
        except Exception:
            continue
    return None, None, 0


def main():
    bak, old_cid, nprod = _find_backup()
    if not bak:
        raise SystemExit("No backup with Dish Wash contractor + products found.")
    print(f"Source backup: {bak}  contractor_id={old_cid} products={nprod}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safety = ROOT / "backups" / f"pre_restore_cl_{stamp}.db"
    with db.get_connection() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    shutil.copy2(db.DB_PATH, safety)
    print("Safety backup:", safety)

    src = sqlite3.connect(f"file:{bak}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    cl = dict(src.execute(
        "SELECT * FROM contract_labourers WHERE id=?", (old_cid,)
    ).fetchone())
    products = [dict(r) for r in src.execute(
        "SELECT * FROM contract_labour_products WHERE contractor_id=? ORDER BY sort_order, id",
        (old_cid,),
    )]
    # optional month run
    runs = []
    try:
        for h in src.execute(
            "SELECT * FROM contract_labour_month_runs WHERE contractor_id=?",
            (old_cid,),
        ):
            hd = dict(h)
            hd["lines"] = [dict(r) for r in src.execute(
                "SELECT * FROM contract_labour_month_lines WHERE run_id=? ORDER BY sort_order, id",
                (hd["id"],),
            )]
            runs.append(hd)
    except Exception:
        pass
    src.close()

    with db.get_connection() as conn:
        from db_contractors import apply_contract_labour
        apply_contract_labour(conn)
        existing = conn.execute(
            "SELECT id FROM contract_labourers WHERE supplier_id=?",
            (SUPPLIER_ID,),
        ).fetchone()
        if existing:
            print("Already exists id=", existing["id"], "— skipping recreate header")
            new_cid = int(existing["id"])
        else:
            cur = conn.execute(
                """INSERT INTO contract_labourers(
                       supplier_id, payment_type, default_rate, notes, is_active,
                       created_by, created_at, modified_by, modified_at
                   ) VALUES (?,?,?,?,1,?,?,?,?)""",
                (
                    SUPPLIER_ID,
                    cl.get("payment_type") or "production_qty",
                    float(cl.get("default_rate") or 0),
                    cl.get("notes"),
                    cl.get("created_by"),
                    cl.get("created_at") or db._now(),
                    cl.get("modified_by"),
                    cl.get("modified_at"),
                ),
            )
            new_cid = int(cur.lastrowid)
            print("Restored contractor id=", new_cid)

        conn.execute(
            "DELETE FROM contract_labour_products WHERE contractor_id=?",
            (new_cid,),
        )
        for i, p in enumerate(products):
            conn.execute(
                """INSERT INTO contract_labour_products(
                       contractor_id, product_id, rate, sort_order
                   ) VALUES (?,?,?,?)""",
                (
                    new_cid,
                    int(p["product_id"]),
                    p.get("rate"),
                    int(p.get("sort_order") if p.get("sort_order") is not None else i),
                ),
            )
        print(f"Restored {len(products)} products")

        # restore month runs if any
        for run in runs:
            ym = run.get("year_month")
            if not ym:
                continue
            old = conn.execute(
                """SELECT id FROM contract_labour_month_runs
                   WHERE contractor_id=? AND year_month=?""",
                (new_cid, ym),
            ).fetchone()
            if old:
                rid = int(old["id"])
                conn.execute(
                    "DELETE FROM contract_labour_month_lines WHERE run_id=?", (rid,),
                )
                conn.execute(
                    """UPDATE contract_labour_month_runs
                       SET from_date=?, to_date=?, gross_amount=?, closing_qty=?, notes=?,
                           modified_at=?
                       WHERE id=?""",
                    (
                        run.get("from_date"), run.get("to_date"),
                        run.get("gross_amount"), run.get("closing_qty"),
                        run.get("notes"), db._now(), rid,
                    ),
                )
            else:
                cur = conn.execute(
                    """INSERT INTO contract_labour_month_runs(
                           contractor_id, year_month, from_date, to_date,
                           gross_amount, closing_qty, notes, created_by, created_at
                       ) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        new_cid, ym, run.get("from_date"), run.get("to_date"),
                        run.get("gross_amount"), run.get("closing_qty"),
                        run.get("notes"), run.get("created_by"),
                        run.get("created_at") or db._now(),
                    ),
                )
                rid = int(cur.lastrowid)
            for i, ln in enumerate(run.get("lines") or []):
                conn.execute(
                    """INSERT INTO contract_labour_month_lines(
                           run_id, product_id, product_code, product_name,
                           sold_qty, stock_qty, sale_return_qty, manual_qty,
                           closing_stock, rate, amount, sort_order
                       ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        rid, ln["product_id"], ln.get("product_code"), ln.get("product_name"),
                        ln.get("sold_qty") or 0, ln.get("stock_qty") or 0,
                        ln.get("sale_return_qty") or 0, ln.get("manual_qty") or 0,
                        ln.get("closing_stock") or 0, ln.get("rate") or 0,
                        ln.get("amount") or 0,
                        int(ln.get("sort_order") if ln.get("sort_order") is not None else i),
                    ),
                )
            print(f"Restored month run {ym} lines={len(run.get('lines') or [])}")

    print("Done.")


if __name__ == "__main__":
    main()
