"""GL vs cash book gap analysis through 2026-08-19."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import database as db
from db_v3 import gl_account_code
from tools._diag_cash_20260819 import book_only_entries, gl_cash_balance, book_balance

THROUGH = "2026-08-19"

with db.get_connection() as conn:
    code = gl_account_code("cash")
    aid = conn.execute(
        "SELECT id, opening_balance FROM chart_of_accounts WHERE code=?", (code,)
    ).fetchone()
    print("GL cash account:", code, "id", aid["id"], "opening", aid["opening_balance"])

    bo = book_only_entries(conn, THROUGH)
    net_bo = sum(r["amount"] if r["table"] == "cash_receipts" else -r["amount"] for r in bo)
    print("Book-only cumulative through", THROUGH, ":", len(bo), "net", f"{net_bo:,.2f}")

    rows = conn.execute(
        """SELECT reference_type, COUNT(*), SUM(debit), SUM(credit), SUM(debit-credit)
           FROM general_ledger WHERE account_id=? AND entry_date<=?
           GROUP BY reference_type ORDER BY ABS(SUM(debit-credit)) DESC""",
        (aid["id"], THROUGH),
    ).fetchall()
    print("\nGL cash by reference_type through", THROUGH, ":")
    for r in rows:
        rt = r[0] or "(null)"
        print(
            f"  {rt:25} cnt={r[1]:4} dr={float(r[2] or 0):14,.2f} "
            f"cr={float(r[3] or 0):14,.2f} net={float(r[4] or 0):14,.2f}"
        )

    bb = book_balance(conn, "2026-08-20")
    gl = gl_cash_balance(conn, THROUGH)
    print("\nBook closing (open 20):", f"{bb['opening']:,.2f}")
    print("GL balance through 19:", f"{gl['balance']:,.2f}")
    print("Gap (book - GL):", f"{bb['opening'] - gl['balance']:,.2f}")

    # GL entries with no cash book row (by ref)
    orphans = conn.execute(
        """SELECT gl.id, gl.entry_date, gl.debit, gl.credit, gl.reference_type, gl.reference_no, gl.description
           FROM general_ledger gl
           WHERE gl.account_id=? AND gl.entry_date<=?
             AND NOT EXISTS (
               SELECT 1 FROM cash_receipts cr
               WHERE (cr.reference_no = gl.reference_no OR cr.document_no = gl.reference_no)
                 AND cr.receipt_date = gl.entry_date
                 AND ABS(cr.amount - gl.debit) < 0.01 AND gl.debit > 0
             )
             AND NOT EXISTS (
               SELECT 1 FROM cash_payments cp
               WHERE (cp.reference_no = gl.reference_no OR cp.document_no = gl.reference_no)
                 AND cp.payment_date = gl.entry_date
                 AND ABS(cp.amount - gl.credit) < 0.01 AND gl.credit > 0
             )
           ORDER BY ABS(gl.debit - gl.credit) DESC
           LIMIT 30""",
        (aid["id"], THROUGH),
    ).fetchall()
    orphan_net = conn.execute(
        """SELECT COALESCE(SUM(debit-credit),0), COUNT(*)
           FROM general_ledger gl
           WHERE gl.account_id=? AND gl.entry_date<=?
             AND NOT EXISTS (
               SELECT 1 FROM cash_receipts cr
               WHERE (cr.reference_no = gl.reference_no OR cr.document_no = gl.reference_no)
                 AND cr.receipt_date = gl.entry_date AND ABS(cr.amount - gl.debit) < 0.01 AND gl.debit > 0
             )
             AND NOT EXISTS (
               SELECT 1 FROM cash_payments cp
               WHERE (cp.reference_no = gl.reference_no OR cp.document_no = gl.reference_no)
                 AND cp.payment_date = gl.entry_date AND ABS(cp.amount - gl.credit) < 0.01 AND gl.credit > 0
             )""",
        (aid["id"], THROUGH),
    ).fetchone()
    print("\nGL orphans (no cash book match) count:", orphan_net[1], "net:", f"{float(orphan_net[0]):,.2f}")
    print("Top orphan GL rows:")
    for r in orphans[:15]:
        print(
            f"  {r['entry_date']} GL#{r['id']} {r['reference_type']} {r['reference_no']} "
            f"dr={float(r['debit'] or 0):,.2f} cr={float(r['credit'] or 0):,.2f} | {(r['description'] or '')[:50]}"
        )

    bo_sorted = sorted(bo, key=lambda x: abs(x["amount"]), reverse=True)
    print("\nTop 10 book-only (no GL amount match on same date):")
    for r in bo_sorted[:10]:
        print(f"  {r['date']} {r['document_no']} {r['amount']:,.2f} {r['description'][:50]}")
