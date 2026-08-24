import sys
sys.path.insert(0, ".")
from db_v3 import detach_all_cash_advance_issues_from_cash_book
import database as db

results = detach_all_cash_advance_issues_from_cash_book()
print("detached", len(results))
for r in results:
    print(" ", r)

with db.get_connection() as conn:
    row = conn.execute(
        """SELECT id, document_no, amount FROM cash_payments
           WHERE reference_no='CA-0014' OR document_no='CP-127183'"""
    ).fetchall()
    print("CA-0014 payments left:", len(row))
    book = db.get_cash_book("2026-08-24", "2026-08-24")
    ca = [r for r in book if "CA-0014" in (r.get("reference_no") or "") or "CP-127183" in (r.get("document_no") or "")]
    print("in cash book 24-08:", ca)
