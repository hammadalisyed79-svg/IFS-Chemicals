import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import database as db

THROUGH = "2026-08-19"

with db.get_connection() as conn:
    pending = db.get_provisional_cash_sale_invoices(None, THROUGH)
    print(f"Provisional (draft/pending) cash sales through {THROUGH}:")
    print(f"  count={len(pending)} total={sum(float(r['amount']) for r in pending):,.2f}")
    for r in pending[:25]:
        print(f"  {r.get('entry_date')} {r['document_no']} [{r['status']}] {float(r['amount']):,.2f}")

    # Approved cash but no cash_receipt linked by document_no
    rows = conn.execute(
        """SELECT s.invoice_date, s.document_no, s.status, s.total, s.paid_amount
           FROM sales_invoices s
           WHERE LOWER(COALESCE(s.payment_mode,'')) = 'cash'
             AND LOWER(COALESCE(s.status,'')) IN ('draft','pending_approval','approved')
             AND s.invoice_date <= ?
             AND NOT EXISTS (
               SELECT 1 FROM cash_receipts cr WHERE cr.reference_no = s.document_no
             )
           ORDER BY s.invoice_date, s.document_no""",
        (THROUGH,),
    ).fetchall()
    by_status = {}
    for r in rows:
        st = r["status"]
        by_status.setdefault(st, {"n": 0, "amt": 0.0})
        by_status[st]["n"] += 1
        by_status[st]["amt"] += float(r["total"] or 0)
    print(f"\nCash sales WITHOUT cash_receipt row through {THROUGH}:")
    for st, v in sorted(by_status.items()):
        print(f"  {st}: {v['n']} invoices, Rs {v['amt']:,.2f}")

    # On 19-08 specifically
    day = conn.execute(
        """SELECT s.document_no, s.status, s.total
           FROM sales_invoices s
           WHERE LOWER(COALESCE(s.payment_mode,'')) = 'cash'
             AND s.invoice_date = ?
             AND LOWER(COALESCE(s.status,'')) IN ('draft','pending_approval')
             AND NOT EXISTS (
               SELECT 1 FROM cash_receipts cr WHERE cr.reference_no = s.document_no
             )""",
        (THROUGH,),
    ).fetchall()
    print(f"\nDraft/pending on {THROUGH} (user scenario):")
    print(f"  count={len(day)} total={sum(float(r['total'] or 0) for r in day):,.2f}")
    for r in day:
        print(f"  {r['document_no']} [{r['status']}] {float(r['total']):,.2f}")
