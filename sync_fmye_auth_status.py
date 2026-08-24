"""Sync FMYE authorization (Status/Approved) onto IFS invoices and reverse stock if unposted.

FMYE Post/Unpost screens use Status='1' (posted) / Status='0' (under authorization).
Import previously forced everything to approved — this corrects status and undoes
stock/balance effects for still-unposted documents.

Usage:
  python sync_fmye_auth_status.py              # preview
  python sync_fmye_auth_status.py --apply      # write changes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import database as db
from import_fmye_from_dat import EXPORT_DIR, FMYEExport, _d, _f, _in_years, ifs_status_from_fmye
from migrate_fmye import IMPORT_YEARS


def _adjust_qty(conn, product_id, warehouse_id, qty_change):
    """Direct stock adjust for auth sync (may go negative when reversing unposted purchases)."""
    row = conn.execute(
        "SELECT quantity FROM warehouse_stock WHERE warehouse_id=? AND product_id=?",
        (warehouse_id, product_id),
    ).fetchone()
    ts = db._now()
    if row:
        conn.execute(
            "UPDATE warehouse_stock SET quantity=quantity+?, modified_at=? WHERE warehouse_id=? AND product_id=?",
            (qty_change, ts, warehouse_id, product_id),
        )
    else:
        conn.execute(
            "INSERT INTO warehouse_stock (warehouse_id, product_id, quantity, modified_at) VALUES (?, ?, ?, ?)",
            (warehouse_id, product_id, qty_change, ts),
        )


def _reverse_sale_stock(conn, inv_id: int, user_id: int | None):
    inv = conn.execute("SELECT * FROM sales_invoices WHERE id=?", (inv_id,)).fetchone()
    if not inv:
        return
    wh = inv["warehouse_id"] or db._default_warehouse_id(conn)
    moves = conn.execute(
        """SELECT id, product_id, warehouse_id, quantity, movement_type
           FROM inventory_movements
           WHERE reference_type='sales_invoice' AND reference_id=?""",
        (inv_id,),
    ).fetchall()
    for m in moves:
        qty = float(m["quantity"] or 0)
        # Sales were 'out' — reverse by putting stock back
        if (m["movement_type"] or "out") == "out":
            _adjust_qty(conn, m["product_id"], m["warehouse_id"] or wh, qty)
        else:
            _adjust_qty(conn, m["product_id"], m["warehouse_id"] or wh, -qty)
        conn.execute("DELETE FROM inventory_movements WHERE id=?", (m["id"],))
    total = float(inv["total"] or 0)
    paid = float(inv["paid_amount"] or 0)
    conn.execute(
        "UPDATE customers SET current_balance=current_balance-? WHERE id=?",
        (total - paid, inv["customer_id"]),
    )


def _reverse_purchase_stock(conn, inv_id: int, user_id: int | None):
    inv = conn.execute("SELECT * FROM purchase_invoices WHERE id=?", (inv_id,)).fetchone()
    if not inv:
        return
    wh = inv["warehouse_id"] or db._default_warehouse_id(conn)
    moves = conn.execute(
        """SELECT id, product_id, warehouse_id, quantity, movement_type
           FROM inventory_movements
           WHERE reference_type='purchase_invoice' AND reference_id=?""",
        (inv_id,),
    ).fetchall()
    for m in moves:
        qty = float(m["quantity"] or 0)
        # Purchases were 'in' — reverse by removing stock
        if (m["movement_type"] or "in") == "in":
            _adjust_qty(conn, m["product_id"], m["warehouse_id"] or wh, -qty)
        else:
            _adjust_qty(conn, m["product_id"], m["warehouse_id"] or wh, qty)
        conn.execute("DELETE FROM inventory_movements WHERE id=?", (m["id"],))
    total = float(inv["total"] or 0)
    paid = float(inv["paid_amount"] or 0)
    conn.execute(
        "UPDATE suppliers SET current_balance=current_balance-? WHERE id=?",
        (total - paid, inv["supplier_id"]),
    )


def preview_and_apply(*, apply: bool):
    exp = FMYEExport(EXPORT_DIR)
    sales = exp.rows("SaleInvoiceHeader")
    purch = exp.rows("PurchaseHeader")
    stats = {
        "sale_pending": 0, "sale_ok": 0, "sale_missing": 0,
        "purch_pending": 0, "purch_ok": 0, "purch_missing": 0,
        "stock_reversed_si": 0, "stock_reversed_pi": 0,
    }

    db.init_db()
    with db.get_connection() as conn:
        uid = conn.execute(
            "SELECT id FROM users WHERE LOWER(username)='admin' AND is_active=1"
        ).fetchone()
        uid = uid[0] if uid else None

        for h in sales:
            if not _in_years(h.get("InvoiceDate"), IMPORT_YEARS):
                continue
            doc = (h.get("DocumentNo") or "").strip()
            if not doc or not doc.isdigit():
                continue
            want = ifs_status_from_fmye(h.get("Status"))
            row = conn.execute(
                "SELECT id, status FROM sales_invoices WHERE document_no=?", (doc,)
            ).fetchone()
            if not row:
                stats["sale_missing"] += 1
                continue
            cur = (row["status"] or "approved").lower()
            if want == "approved":
                stats["sale_ok"] += 1
                continue
            # under authorization
            stats["sale_pending"] += 1
            if apply and cur == "approved":
                _reverse_sale_stock(conn, row["id"], uid)
                conn.execute(
                    "UPDATE sales_invoices SET status=?, approval_status=NULL WHERE id=?",
                    ("pending_approval", row["id"]),
                )
                stats["stock_reversed_si"] += 1
            elif apply and cur != "pending_approval":
                conn.execute(
                    "UPDATE sales_invoices SET status=? WHERE id=?",
                    ("pending_approval", row["id"]),
                )

        for h in purch:
            if not _in_years(h.get("PurchaseInvoiceDate"), IMPORT_YEARS):
                continue
            code = h.get("PurchaseInvoiceCode")
            if not code:
                continue
            doc = f"PI-{code}"
            want = ifs_status_from_fmye(h.get("Status"))
            row = conn.execute(
                "SELECT id, status FROM purchase_invoices WHERE document_no=?", (doc,)
            ).fetchone()
            if not row:
                stats["purch_missing"] += 1
                continue
            cur = (row["status"] or "approved").lower()
            if want == "approved":
                stats["purch_ok"] += 1
                continue
            stats["purch_pending"] += 1
            if apply and cur == "approved":
                _reverse_purchase_stock(conn, row["id"], uid)
                conn.execute(
                    "UPDATE purchase_invoices SET status=?, approval_status=NULL WHERE id=?",
                    ("pending_approval", row["id"]),
                )
                stats["stock_reversed_pi"] += 1
            elif apply and cur != "pending_approval":
                conn.execute(
                    "UPDATE purchase_invoices SET status=? WHERE id=?",
                    ("pending_approval", row["id"]),
                )

        # Returns — set approval_status if column exists
        sr_cols = [r[1] for r in conn.execute("PRAGMA table_info(sales_returns)")]
        pr_cols = [r[1] for r in conn.execute("PRAGMA table_info(purchase_returns)")]
        if "approval_status" in sr_cols:
            for h in exp.rows("SrHeader"):
                if not _in_years(h.get("SrDate"), IMPORT_YEARS):
                    continue
                doc = f"SR-{h.get('SrNo', '').strip()}"
                want = ifs_status_from_fmye(h.get("Approved"))
                if want != "approved":
                    if apply:
                        conn.execute(
                            "UPDATE sales_returns SET approval_status=? WHERE document_no=?",
                            ("pending", doc),
                        )
        if "approval_status" in pr_cols:
            for h in exp.rows("PrHeader"):
                if not _in_years(h.get("PrDate"), IMPORT_YEARS):
                    continue
                doc = f"PR-{h.get('PrNo', '').strip()}"
                want = ifs_status_from_fmye(h.get("Approved"))
                if want != "approved":
                    if apply:
                        conn.execute(
                            "UPDATE purchase_returns SET approval_status=? WHERE document_no=?",
                            ("pending", doc),
                        )

    mode = "APPLIED" if apply else "PREVIEW"
    print(f"[{mode}] FMYE authorization sync ({EXPORT_DIR})")
    print(f"  Sales under auth (Status=0): {stats['sale_pending']}  (missing IFS: {stats['sale_missing']})")
    print(f"  Purchases under auth:        {stats['purch_pending']}  (missing IFS: {stats['purch_missing']})")
    if apply:
        print(f"  Stock reversed SI: {stats['stock_reversed_si']}  PI: {stats['stock_reversed_pi']}")
        print("  Status set to pending_approval — appear in Sale/Purchase Approval queues.")
    else:
        print("  Run with --apply to set pending_approval and reverse stock for unposted docs.")
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    preview_and_apply(apply=args.apply)


if __name__ == "__main__":
    main()
