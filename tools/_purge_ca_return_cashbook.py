"""Remove cash-advance settlement return rows from cash book (keep GL)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import database as db

with db.get_connection() as conn:
    rows = conn.execute(
        """SELECT cr.id, cr.document_no, cr.amount, cr.reference_no, s.document_no AS cas_no
           FROM cash_receipts cr
           JOIN cash_advance_settlements s ON s.cash_entry_id = cr.id
           ORDER BY cr.id"""
    ).fetchall()
  # also CAS-* reference
    rows2 = conn.execute(
        """SELECT id, document_no, amount, reference_no, NULL AS cas_no
           FROM cash_receipts WHERE reference_no GLOB 'CAS-*'"""
    ).fetchall()
    ids = set()
    for r in list(rows) + list(rows2):
        ids.add(r["id"])
        print(dict(r))

    for rid in ids:
        conn.execute("DELETE FROM cash_receipts WHERE id=?", (rid,))
    conn.execute(
        """UPDATE cash_advance_settlements
           SET cash_entry_id=NULL, cash_entry_source=NULL
           WHERE cash_entry_id IS NOT NULL"""
    )
    print(f"\nRemoved {len(ids)} cash receipt(s) from cash book.")

    rec = db.cash_book_receipts_sum(conn, before_date="2026-08-24")
    pay = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM cash_payments WHERE payment_date<?",
        ("2026-08-24",),
    ).fetchone()[0]
    coa = conn.execute(
        "SELECT COALESCE(opening_balance,0) FROM chart_of_accounts WHERE code='000000'"
    ).fetchone()[0]
    print(f"Opening 24-08 (book receipts excl. returns): {float(coa)+rec-float(pay):,.2f}")
