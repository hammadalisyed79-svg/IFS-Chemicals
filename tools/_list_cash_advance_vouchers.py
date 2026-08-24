"""List cash book rows linked to cash advances."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import database as db

with db.get_connection() as conn:
    try:
        conn.execute("SELECT 1 FROM cash_advances LIMIT 1")
    except Exception:
        print("cash_advances table missing")
        raise SystemExit(0)

    advances = conn.execute(
        """SELECT id, document_no, issue_date, person_name, amount, issue_doc_no,
                  issue_entry_id, issue_entry_source, status, outstanding_amount
           FROM cash_advances ORDER BY id"""
    ).fetchall()
    print(f"Cash advances: {len(advances)}")
    issue_docs = []
    for a in advances:
        a = dict(a)
        print(a)
        if a.get("issue_doc_no"):
            issue_docs.append(a["issue_doc_no"])

    settlements = conn.execute(
        """SELECT s.id, s.document_no, s.advance_id, s.settle_date, s.bills_total,
                  s.cash_returned, s.cash_doc_no, s.cash_entry_id, s.cash_entry_source,
                  a.document_no AS advance_no
           FROM cash_advance_settlements s
           JOIN cash_advances a ON a.id=s.advance_id
           ORDER BY s.id"""
    ).fetchall()
    print(f"\nSettlements: {len(settlements)}")
    settle_docs = []
    for s in settlements:
        s = dict(s)
        print(s)
        if s.get("cash_doc_no"):
            settle_docs.append(s["cash_doc_no"])

    all_docs = set(issue_docs + settle_docs)
    print(f"\nLinked cash vouchers ({len(all_docs)}):")
    for doc in sorted(all_docs):
        for tbl, dcol in (("cash_receipts", "receipt_date"), ("cash_payments", "payment_date")):
            rows = conn.execute(
                f"SELECT id, document_no, {dcol}, amount, description, reference_no FROM {tbl} WHERE document_no=?",
                (doc,),
            ).fetchall()
            for r in rows:
                print(f"  {tbl}: {dict(r)}")

    # GL rows for cash_advance
    gl = conn.execute(
        """SELECT id, entry_date, reference_type, reference_no, debit, credit, description
           FROM general_ledger WHERE reference_type IN ('cash_advance','cash_advance_settlement')
           ORDER BY entry_date, id LIMIT 50"""
    ).fetchall()
    print(f"\nGL cash_advance rows (sample {len(gl)}):")
    for r in gl[:20]:
        print(dict(r))
