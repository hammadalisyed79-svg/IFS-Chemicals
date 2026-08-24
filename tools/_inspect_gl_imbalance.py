import database as db
import json

REFS = ("CR-126928", "CR-126932", "JVR-126885")

with db.get_connection() as c:
    tables = [
        x[0]
        for x in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND (name LIKE '%cash_rec%' OR name LIKE '%journal%' OR name LIKE '%general_led%' OR name LIKE '%fmye%')"
        ).fetchall()
    ]
    print("TABLES", tables)
    print("GL COLS", [x[1] for x in c.execute("PRAGMA table_info(general_ledger)").fetchall()])
    print("CR COLS", [x[1] for x in c.execute("PRAGMA table_info(cash_receipts)").fetchall()])

    cash = c.execute(
        "SELECT id, code, name FROM chart_of_accounts "
        "WHERE code IN ('000000','1000','100000') OR UPPER(name) LIKE '%CASH IN HAND%' "
        "ORDER BY code"
    ).fetchall()
    print("CASH", [dict(r) for r in cash])

    print(
        "NET",
        dict(
            c.execute(
                "SELECT ROUND(SUM(debit),2) dr, ROUND(SUM(credit),2) cr, "
                "ROUND(SUM(debit)-SUM(credit),2) net FROM general_ledger"
            ).fetchone()
        ),
    )

    for ref in REFS:
        print("\n====", ref)
        for r in c.execute(
            """SELECT gl.id, gl.entry_date, gl.account_id, a.code, a.name,
                      gl.debit, gl.credit, gl.description, gl.reference_type,
                      gl.reference_id, gl.reference_no, gl.created_by
               FROM general_ledger gl
               LEFT JOIN chart_of_accounts a ON a.id=gl.account_id
               WHERE gl.reference_no=? ORDER BY gl.id""",
            (ref,),
        ).fetchall():
            print(dict(r))
        cr = c.execute("SELECT * FROM cash_receipts WHERE document_no=?", (ref,)).fetchone()
        print("cash_receipt", dict(cr) if cr else None)
        if cr:
            cust = c.execute(
                "SELECT id, code, name FROM customers WHERE id=?", (cr["party_id"],)
            ).fetchone()
            print("customer", dict(cust) if cust else None)

    # Find invoice mentioned by JVR
    print("\nInvoice search 26080116")
    for r in c.execute(
        "SELECT id, document_no, customer_id, total, invoice_date, status "
        "FROM sales_invoices WHERE document_no LIKE '%26080116%'"
    ).fetchall():
        print(dict(r))
