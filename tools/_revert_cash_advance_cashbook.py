"""Revert all cash book entries posted for cash advances."""
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db_v3 import revert_all_cash_advance_cash_book
import database as db

report = revert_all_cash_advance_cash_book(user_id=1)
print(json.dumps(report, indent=2))

with db.get_connection() as conn:
    n_adv = conn.execute("SELECT COUNT(*) FROM cash_advances").fetchone()[0]
    n_set = conn.execute("SELECT COUNT(*) FROM cash_advance_settlements").fetchone()[0]
    n_cp = conn.execute(
        "SELECT COUNT(*) FROM cash_payments WHERE reference_no LIKE 'CA-%'"
    ).fetchone()[0]
    n_cr = conn.execute(
        "SELECT COUNT(*) FROM cash_receipts WHERE reference_no LIKE 'CAS-%'"
    ).fetchone()[0]
    gl = conn.execute(
        """SELECT COUNT(*) FROM general_ledger
           WHERE reference_type IN ('cash_advance','cash_advance_settlement')"""
    ).fetchone()[0]
    open_adv = conn.execute(
        "SELECT document_no, person_name, amount, outstanding_amount, status FROM cash_advances ORDER BY id"
    ).fetchall()

print("\nAfter cleanup:")
print(f"  settlements left: {n_set}")
print(f"  CA cash payments left: {n_cp}")
print(f"  CAS cash receipts left: {n_cr}")
print(f"  GL cash_advance rows left: {gl}")
print(f"  advances ({n_adv}):")
for r in open_adv:
    print(f"    {r['document_no']} {r['person_name'][:30]} issued={r['amount']} out={r['outstanding_amount']} {r['status']}")
