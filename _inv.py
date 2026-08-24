import sqlite3
from pathlib import Path
c = sqlite3.connect(str(Path("ifs_erp.db")))
c.row_factory = sqlite3.Row

def show(sql, params=()):
    rows = c.execute(sql, params).fetchall()
    for r in rows:
        print(dict(r))
    return rows

print("=== SAL-26010201 ===")
inv = show("SELECT * FROM sales_invoices WHERE document_no=? OR document_no LIKE ?", ("SAL-26010201","%26010201%"))
print("=== GP-0001 ===")
# find tables with GP
for t in c.execute("SELECT name FROM sqlite_master WHERE type='table'"):
    name=t[0]
    cols=[x[1] for x in c.execute(f"PRAGMA table_info({name})")]
    if "document_no" in cols:
        rows=c.execute(f"SELECT * FROM {name} WHERE document_no=? OR document_no LIKE ?", ("GP-0001","GP-0001%")).fetchall()
        if rows:
            print("TABLE", name)
            for r in rows: print(dict(r))

print("=== nearby sales around 26010201 ===")
show("""SELECT id, document_no, invoice_date, customer_id, total, status, payment_mode, gate_pass_id, order_id
        FROM sales_invoices WHERE document_no LIKE 'SAL-2601%' OR document_no LIKE '2601%'
        ORDER BY document_no LIMIT 30""")
