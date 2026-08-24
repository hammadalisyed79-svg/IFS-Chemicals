import database
database.init_db()
with database.get_connection() as conn:
    print("GL reference_type counts:", [tuple(r) for r in conn.execute("SELECT reference_type, COUNT(*) FROM general_ledger GROUP BY 1 ORDER BY 2 DESC LIMIT 30").fetchall()])
    n = conn.execute("""
        SELECT COUNT(*) FROM sales_invoices si
        WHERE EXISTS (SELECT 1 FROM general_ledger g WHERE g.reference_no=si.document_no)
    """).fetchone()[0]
    print("SI with GL by reference_no:", n)
    n = conn.execute("""
        SELECT COUNT(*) FROM purchase_invoices pi
        WHERE EXISTS (SELECT 1 FROM general_ledger g WHERE g.reference_no=pi.document_no)
    """).fetchone()[0]
    print("PI with GL by reference_no:", n)
    n = conn.execute("""
        SELECT COUNT(*) FROM sales_returns sr
        WHERE EXISTS (SELECT 1 FROM general_ledger g WHERE g.reference_no=sr.document_no)
    """).fetchone()[0]
    print("SR with GL by reference_no:", n)
    n = conn.execute("""
        SELECT COUNT(*) FROM purchase_returns pr
        WHERE EXISTS (SELECT 1 FROM general_ledger g WHERE g.reference_no=pr.document_no)
    """).fetchone()[0]
    print("PR with GL by reference_no:", n)

    print("\nweight_slips first_weigh:")
    cols = [r[1] for r in conn.execute("PRAGMA table_info(weight_slips)").fetchall()]
    print("cols", cols)
    for r in conn.execute("SELECT * FROM weight_slips WHERE status='first_weigh'").fetchall():
        print({k: r[k] for k in r.keys()})

    print("\nALL SR docs:", [r[0] for r in conn.execute("SELECT document_no FROM sales_returns ORDER BY id").fetchall()])
    print("ALL PR docs:", [r[0] for r in conn.execute("SELECT document_no FROM purchase_returns ORDER BY id").fetchall()])
