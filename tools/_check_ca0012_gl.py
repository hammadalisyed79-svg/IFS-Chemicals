import sys
sys.path.insert(0, ".")
import database as db

with db.get_connection() as conn:
    gl = conn.execute(
        """SELECT g.*, a.code FROM general_ledger g
           JOIN chart_of_accounts a ON a.id=g.account_id
           WHERE reference_type='cash_advance' AND reference_no='CA-0012'"""
    ).fetchall()
    print("issue gl", len(gl))
    for g in gl:
        print(g["code"], "Dr", g["debit"], "Cr", g["credit"])
