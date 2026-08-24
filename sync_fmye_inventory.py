"""
Post inventory movements for FMYE-imported invoices (2024-2026).

Imported invoices are status=approved but bypass approve workflow, so stock
was never updated. This applies warehouse_stock + inventory_movements only
(no party balance changes).

Usage:
  python sync_fmye_inventory.py
  python sync_fmye_inventory.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import database as db

IMPORT_YEARS = ("2024", "2025", "2026")


def _record_mov(conn, product_id, wh, mov_type, qty, ref_type, ref_id, reason, uid, mov_date):
    conn.execute(
        """INSERT INTO inventory_movements(movement_date, product_id, warehouse_id,
           movement_type, quantity, reference_type, reference_id, reason, created_by)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (mov_date, product_id, wh, mov_type, qty, ref_type, ref_id, reason, uid),
    )


def _already_posted(conn):
    return {
        (r[0], r[1])
        for r in conn.execute(
            "SELECT reference_type, reference_id FROM inventory_movements WHERE reference_id IS NOT NULL"
        ).fetchall()
    }


def sync_inventory(uid: int, dry_run: bool = False):
    stats = defaultdict(int)
    prev_neg = db.get_setting("allow_negative_stock", "0")
    # Migration: FMYE opening stock may not cover every SKU sold — allow temporary negative.
    if not dry_run:
        db.set_setting("allow_negative_stock", "1")

    try:
        with db.get_connection() as conn:
            wh = db._default_warehouse_id(conn)
            posted = _already_posted(conn)

            def post_lines(ref_type, ref_id, doc_no, mov_date, lines, direction):
                """direction: 'in' adds stock, 'out' removes."""
                if (ref_type, ref_id) in posted:
                    stats["skipped"] += 1
                    return
                for pid, qty in lines:
                    if qty <= 0:
                        continue
                    delta = qty if direction == "in" else -qty
                    mov = "in" if direction == "in" else "out"
                    if not dry_run:
                        db._adjust_warehouse_stock(conn, pid, wh, delta, user_id=uid)
                        _record_mov(conn, pid, wh, mov, qty, ref_type, ref_id, doc_no, uid, mov_date)
                    stats["movements"] += 1
                    stats[f"{ref_type}_{direction}"] += 1
                posted.add((ref_type, ref_id))
                stats[ref_type] += 1

            # Purchases first so stock is available for sales where possible
            for inv in conn.execute(
                """SELECT id, document_no, invoice_date FROM purchase_invoices
                   WHERE status='approved' AND substr(invoice_date,1,4) IN (?,?,?)
                   ORDER BY invoice_date, id""",
                IMPORT_YEARS,
            ):
                lines = conn.execute(
                    "SELECT product_id, quantity FROM purchase_invoice_items WHERE invoice_id=?",
                    (inv["id"],),
                ).fetchall()
                post_lines(
                    "purchase_invoice", inv["id"], inv["document_no"], inv["invoice_date"],
                    [(r["product_id"], float(r["quantity"])) for r in lines], "in",
                )

            for inv in conn.execute(
                """SELECT id, document_no, invoice_date FROM sales_invoices
                   WHERE status='approved' AND substr(invoice_date,1,4) IN (?,?,?)
                   ORDER BY invoice_date, id""",
                IMPORT_YEARS,
            ):
                lines = conn.execute(
                    "SELECT product_id, quantity FROM sales_invoice_items WHERE invoice_id=?",
                    (inv["id"],),
                ).fetchall()
                post_lines(
                    "sales_invoice", inv["id"], inv["document_no"], inv["invoice_date"],
                    [(r["product_id"], float(r["quantity"])) for r in lines], "out",
                )

            for ret in conn.execute(
                """SELECT id, document_no, return_date FROM sales_returns
                   WHERE substr(return_date,1,4) IN (?,?,?) ORDER BY return_date, id""",
                IMPORT_YEARS,
            ):
                lines = conn.execute(
                    "SELECT product_id, quantity FROM sales_return_items WHERE return_id=?",
                    (ret["id"],),
                ).fetchall()
                post_lines(
                    "sales_return", ret["id"], ret["document_no"], ret["return_date"],
                    [(r["product_id"], float(r["quantity"])) for r in lines], "in",
                )

            for ret in conn.execute(
                """SELECT id, document_no, return_date FROM purchase_returns
                   WHERE substr(return_date,1,4) IN (?,?,?) ORDER BY return_date, id""",
                IMPORT_YEARS,
            ):
                lines = conn.execute(
                    "SELECT product_id, quantity FROM purchase_return_items WHERE return_id=?",
                    (ret["id"],),
                ).fetchall()
                post_lines(
                    "purchase_return", ret["id"], ret["document_no"], ret["return_date"],
                    [(r["product_id"], float(r["quantity"])) for r in lines], "out",
                )
    finally:
        if not dry_run:
            db.set_setting("allow_negative_stock", prev_neg)

    return dict(stats)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    user = db.authenticate("admin", "admin123")
    if not user:
        raise SystemExit("Login failed")
    print("Syncing inventory from 2024-2026 transactions...")
    stats = sync_inventory(user["id"], dry_run=args.dry_run)
    print("Done:", stats)
    if not args.dry_run:
        with db.get_connection() as conn:
            n = conn.execute("SELECT COUNT(*) FROM inventory_movements").fetchone()[0]
            nz = conn.execute("SELECT COUNT(*) FROM warehouse_stock WHERE quantity != 0").fetchone()[0]
            print(f"  inventory_movements: {n:,}")
            print(f"  products with stock: {nz:,}")


if __name__ == "__main__":
    main()
