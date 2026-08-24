import database as db
from db_v3 import gl_account_code, _acct_id

with db.get_connection() as c:
    cust = c.execute(
        "SELECT id, code, name FROM customers WHERE id=1121"
    ).fetchone()
    print("customer", dict(cust) if cust else None)
    if cust:
        coa = c.execute(
            "SELECT id, code, name FROM chart_of_accounts WHERE code=?",
            (cust["code"],),
        ).fetchone()
        print("customer coa", dict(coa) if coa else None)

    # GL for invoice 26080116
    print("\nGL for invoice 26080116 / SAL")
    for r in c.execute(
        """SELECT gl.id, gl.entry_date, a.code, a.name, gl.debit, gl.credit,
                  gl.reference_type, gl.reference_no, gl.description
           FROM general_ledger gl
           JOIN chart_of_accounts a ON a.id=gl.account_id
           WHERE gl.reference_no LIKE '%26080116%'
              OR gl.description LIKE '%26080116%'
           ORDER BY gl.id"""
    ).fetchall():
        print(dict(r))

    # journal voucher header/lines for JVR-126885
    print("\njournal_vouchers for JVR-126885")
    jv = c.execute(
        "SELECT * FROM journal_vouchers WHERE document_no=?", ("JVR-126885",)
    ).fetchone()
    print(dict(jv) if jv else None)
    if jv:
        for r in c.execute(
            """SELECT l.*, a.code, a.name FROM journal_voucher_lines l
               LEFT JOIN chart_of_accounts a ON a.id=l.account_id
               WHERE l.voucher_id=? ORDER BY l.id""",
            (jv["id"],),
        ).fetchall():
            print(dict(r))

    cash_code = gl_account_code("cash")
    print("cash role code", cash_code, "id", _acct_id(c, cash_code))

    # Similar balanced customer receipts for pattern
    print("\nSample balanced customer_receipt")
    for r in c.execute(
        """SELECT reference_no, COUNT(*) n,
                  ROUND(SUM(debit),2) dr, ROUND(SUM(credit),2) cr
           FROM general_ledger
           WHERE reference_type='customer_receipt'
           GROUP BY reference_no
           HAVING ABS(SUM(debit)-SUM(credit))<0.05 AND COUNT(*)>=2
           ORDER BY reference_no DESC LIMIT 3"""
    ).fetchall():
        print(dict(r))
        for g in c.execute(
            """SELECT a.code, a.name, gl.debit, gl.credit
               FROM general_ledger gl JOIN chart_of_accounts a ON a.id=gl.account_id
               WHERE gl.reference_no=?""",
            (r["reference_no"],),
        ).fetchall():
            print(" ", dict(g))
