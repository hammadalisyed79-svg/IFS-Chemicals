import sys
sys.path.insert(0, ".")
from db_v3 import backfill_all_cash_advance_settlement_cash_books
import database as db

results = backfill_all_cash_advance_settlement_cash_books()
print("backfilled:", results)

book = db.get_cash_book("2026-08-24", "2026-08-24")
raza = [r for r in book if "CA-0012" in (r.get("reference_no") or "") or "Raza" in (r.get("description") or "")]
print("cash book 24-08 Raza/CA-0012:", len(raza))
for r in raza:
    print(" ", r["document_no"], r["amount"], r["description"][:70])
