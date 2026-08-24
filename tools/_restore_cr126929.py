"""Restore CR-126929 to yesterday: GL only, remove cash book row."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import database as db

DOC = "CR-126929"
DATE = "2026-08-23"

with db.get_connection() as conn:
    cr = conn.execute(
        "SELECT id, document_no, receipt_date, amount, created_at FROM cash_receipts WHERE document_no=?",
        (DOC,),
    ).fetchone()
    gl_count = conn.execute(
        "SELECT COUNT(*) FROM general_ledger WHERE reference_no=?", (DOC,)
    ).fetchone()[0]

    coa = conn.execute(
        "SELECT COALESCE(opening_balance,0) FROM chart_of_accounts WHERE code='000000'"
    ).fetchone()[0]

    def opening(conn):
        rec = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM cash_receipts WHERE receipt_date<?", (DATE,)
        ).fetchone()[0]
        pay = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM cash_payments WHERE payment_date<?", (DATE,)
        ).fetchone()[0]
        return float(coa) + float(rec) - float(pay)

    ob_before = opening(conn)
    print("Before:")
    print("  cash_book:", dict(cr) if cr else None)
    print("  GL rows:", gl_count)
    print("  opening 23-08:", f"{ob_before:,.2f}")

    if cr:
        conn.execute("DELETE FROM cash_receipts WHERE id=?", (cr["id"],))
        print("  Removed cash_receipts id", cr["id"])
    else:
        print("  No cash book row — already GL-only")

    cr_after = conn.execute(
        "SELECT id FROM cash_receipts WHERE document_no=?", (DOC,)
    ).fetchone()
    gl_after = conn.execute(
        "SELECT COUNT(*) FROM general_ledger WHERE reference_no=?", (DOC,)
    ).fetchone()[0]
    ob_after = opening(conn)

    print("\nAfter:")
    print("  cash_book:", "none" if not cr_after else dict(cr_after))
    print("  GL rows:", gl_after)
    print("  opening 23-08:", f"{ob_after:,.2f}")
