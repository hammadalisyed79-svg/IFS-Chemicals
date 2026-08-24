import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import database as db

with db.get_connection() as conn:
    invs = conn.execute(
        """SELECT document_no, total FROM sales_invoices
           WHERE LOWER(payment_mode)='cash' AND status='approved' AND invoice_date='2026-08-19'
           LIMIT 5"""
    ).fetchall()
    print("Approved cash invoices 19-08:")
    for inv in invs:
        doc = inv["document_no"]
        cr = conn.execute(
            "SELECT document_no, reference_no, amount FROM cash_receipts WHERE reference_no=?",
            (doc,),
        ).fetchall()
        print(f"  {doc} total={inv['total']} cr_match={len(cr)}")

    crs = conn.execute(
        "SELECT document_no, reference_no, amount FROM cash_receipts WHERE receipt_date='2026-08-19' LIMIT 8"
    ).fetchall()
    print("\nCash receipts 19-08 sample refs:")
    for cr in crs:
        print(f"  doc={cr['document_no']} ref={cr['reference_no']} amt={cr['amount']}")

    # SAL- prefix pattern
    linked = conn.execute(
        """SELECT COUNT(*) FROM sales_invoices s
           JOIN cash_receipts cr ON cr.reference_no = s.document_no
           WHERE s.invoice_date='2026-08-19' AND LOWER(s.payment_mode)='cash'"""
    ).fetchone()[0]
    total = conn.execute(
        """SELECT COUNT(*) FROM sales_invoices s
           WHERE s.invoice_date='2026-08-19' AND LOWER(s.payment_mode)='cash' AND status='approved'"""
    ).fetchone()[0]
    print(f"\n19-08 approved cash invoices: {total}, linked to cash_receipt: {linked}")
