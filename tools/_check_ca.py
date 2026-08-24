import sys
sys.path.insert(0, ".")
import database as db

with db.get_connection() as conn:
    r = db.search_cash_advances(open_only=True, page_size=500)
    items = r.get("items") or []
    tot = sum(float(x.get("outstanding_amount") or 0) for x in items)
    print("open advances", len(items), "outstanding", tot)
    pays = conn.execute(
        """SELECT document_no, amount, description, reference_no
           FROM cash_payments WHERE payment_date='2026-08-23'
           AND (reference_no GLOB 'CA-*' OR description LIKE 'Advance to%')
           ORDER BY id"""
    ).fetchall()
    print("CA payments on 23-08:", len(pays))
    for p in pays:
        print(" ", p["document_no"], p["amount"], p["reference_no"] or "", (p["description"] or "")[:40])
