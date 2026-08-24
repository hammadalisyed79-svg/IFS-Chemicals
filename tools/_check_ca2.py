import sys
sys.path.insert(0, ".")
import database as db

with db.get_connection() as conn:
    rows = conn.execute(
        """SELECT document_no, issue_date, person_name, amount, outstanding_amount,
                  issue_doc_no, issue_entry_id, status
           FROM cash_advances WHERE status IN ('open','partial') ORDER BY issue_date"""
    ).fetchall()
    for r in rows:
        doc = r["issue_doc_no"]
        cp = None
        if doc:
            cp = conn.execute(
                "SELECT payment_date, amount FROM cash_payments WHERE document_no=?",
                (doc,),
            ).fetchone()
        print(
            r["document_no"], r["issue_date"], r["person_name"][:20],
            "issued", r["amount"], "out", r["outstanding_amount"],
            "voucher", doc, "in_cb", "yes" if cp else "NO",
            cp["payment_date"] if cp else "",
        )
