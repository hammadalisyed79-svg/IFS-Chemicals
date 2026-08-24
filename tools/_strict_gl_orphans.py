"""Find GL cash lines without any cash book match (broader search)."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import database as db
from db_v3 import gl_account_code

THROUGH = "2026-08-19"

with db.get_connection() as conn:
    code = gl_account_code("cash")
    aid = conn.execute("SELECT id FROM chart_of_accounts WHERE code=?", (code,)).fetchone()["id"]
    rows = conn.execute(
        """SELECT gl.id, gl.entry_date, gl.debit, gl.credit, gl.reference_type, gl.reference_no, gl.description
           FROM general_ledger gl
           WHERE gl.account_id=? AND gl.entry_date<=?
           ORDER BY gl.entry_date, gl.id""",
        (aid, THROUGH),
    ).fetchall()

    orphans = []
    for r in rows:
        ref = (r["reference_no"] or "").strip()
        dt = r["entry_date"]
        dr = float(r["debit"] or 0)
        cr = float(r["credit"] or 0)
        amt = dr if dr > 0 else cr
        found = False
        if ref:
            if dr > 0:
                q = """SELECT 1 FROM cash_receipts WHERE receipt_date=? AND amount BETWEEN ? AND ?
                         AND (document_no=? OR reference_no=?)"""
                if conn.execute(q, (dt, amt - 0.01, amt + 0.01, ref, ref)).fetchone():
                    found = True
            if cr > 0:
                q = """SELECT 1 FROM cash_payments WHERE payment_date=? AND amount BETWEEN ? AND ?
                         AND (document_no=? OR reference_no=?)"""
                if conn.execute(q, (dt, amt - 0.01, amt + 0.01, ref, ref)).fetchone():
                    found = True
        # SAL invoice cash: ref may be SAL-xxx in cash book
        if not found and ref.startswith("SAL-"):
            if conn.execute(
                "SELECT 1 FROM cash_receipts WHERE reference_no=? AND receipt_date=?",
                (ref, dt),
            ).fetchone():
                found = True
        if not found and dr > 0 and ref.startswith("CR-"):
            # any cash receipt same date+amount
            if conn.execute(
                "SELECT 1 FROM cash_receipts WHERE receipt_date=? AND amount BETWEEN ? AND ?",
                (dt, amt - 0.01, amt + 0.01),
            ).fetchone():
                found = True  # loose match - skip for orphan list
                found = False  # keep strict for CR
        if not found:
            orphans.append(dict(r))

    net = sum(float(o["debit"] or 0) - float(o["credit"] or 0) for o in orphans)
    print(f"Strict orphans: {len(orphans)} net GL cash effect: {net:,.2f}")
    for o in orphans:
        print(
            f"  {o['entry_date']} {o['reference_no']} {o['reference_type']} "
            f"dr={float(o['debit'] or 0):,.2f} cr={float(o['credit'] or 0):,.2f} | {(o['description'] or '')[:55]}"
        )
