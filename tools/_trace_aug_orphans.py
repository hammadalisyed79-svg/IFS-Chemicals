import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import database as db

with db.get_connection() as conn:
    # similar amounts / customer around Aug 2026
    print("=== Bank receipts ~1.5M Aug 2026 ===")
    rows = conn.execute(
        """SELECT document_no, receipt_date, amount, description, party_id
           FROM bank_receipts WHERE receipt_date BETWEEN '2026-08-01' AND '2026-08-15'
           AND amount BETWEEN 1400000 AND 1600000 ORDER BY receipt_date"""
    ).fetchall()
    for r in rows:
        print(dict(r))

    print("\n=== Cash receipts ~1.5M Aug 2026 ===")
    rows = conn.execute(
        """SELECT document_no, receipt_date, amount, description, party_id
           FROM cash_receipts WHERE receipt_date BETWEEN '2026-08-01' AND '2026-08-15'
           AND amount BETWEEN 1400000 AND 1600000 ORDER BY receipt_date"""
    ).fetchall()
    for r in rows:
        print(dict(r))

    print("\n=== HAJI MUSHTAQ receipts Aug 2026 ===")
    rows = conn.execute(
        """SELECT 'cash' src, document_no, receipt_date dt, amount, description FROM cash_receipts
           WHERE party_id=679 AND party_type='customer' AND receipt_date BETWEEN '2026-08-01' AND '2026-08-31'
           UNION ALL
           SELECT 'bank', document_no, receipt_date, amount, description FROM bank_receipts
           WHERE party_id=679 AND party_type='customer' AND receipt_date BETWEEN '2026-08-01' AND '2026-08-31'
           ORDER BY dt"""
    ).fetchall()
    for r in rows:
        print(dict(r))

    print("\n=== CP-126909 expense - cash payments 5000 Aug 8 ===")
    rows = conn.execute(
        """SELECT document_no, payment_date, amount, description FROM cash_payments
           WHERE payment_date='2026-08-08' AND amount=5000"""
    ).fetchall()
    for r in rows:
        print(dict(r))
