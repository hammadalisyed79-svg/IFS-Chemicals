import sys
sys.path.insert(0, ".")
import database as db

with db.get_connection() as conn:
    gl = conn.execute(
        """SELECT * FROM general_ledger
           WHERE reference_type='cash_advance_settlement'
             AND reference_id=(SELECT id FROM cash_advance_settlements WHERE document_no='CAS-0022')
           ORDER BY id"""
    ).fetchall()
    for g in gl:
        acc = conn.execute("SELECT code, name FROM chart_of_accounts WHERE id=?", (g["account_id"],)).fetchone()
        print(g["entry_date"], acc["code"] if acc else "?", "Dr", g["debit"], "Cr", g["credit"], (g["description"] or "")[:50])
