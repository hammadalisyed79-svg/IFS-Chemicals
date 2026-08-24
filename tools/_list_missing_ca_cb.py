import sys
sys.path.insert(0, ".")
import database as db
from db_v3 import _ensure_cash_advances_schema

with db.get_connection() as conn:
    _ensure_cash_advances_schema(conn)
    rows = conn.execute(
        """SELECT s.id, s.document_no, s.settle_date, s.bills_total, s.cash_returned,
                  a.document_no AS advance_no, a.person_name, a.payment_mode
           FROM cash_advance_settlements s
           JOIN cash_advances a ON a.id=s.advance_id
           WHERE s.bills_total > 0
           ORDER BY s.id"""
    ).fetchall()
    missing = []
    for s in rows:
        lines = conn.execute(
            """SELECT id, line_no, amount, cash_entry_id, cash_doc_no
               FROM cash_advance_settlement_lines WHERE settlement_id=?""",
            (s["id"],),
        ).fetchall()
        no_cb = [l for l in lines if not l["cash_entry_id"] and float(l["amount"] or 0) > 0]
        if no_cb:
            missing.append((dict(s), [dict(l) for l in no_cb]))
    print("settlements missing cash book:", len(missing))
    for s, lines in missing:
        print(s["document_no"], s["advance_no"], s["person_name"], s["settle_date"], "bills", s["bills_total"], "lines", len(lines))
