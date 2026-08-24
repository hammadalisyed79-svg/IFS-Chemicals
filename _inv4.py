import sqlite3
c=sqlite3.connect("ifs_erp.db"); c.row_factory=sqlite3.Row
print("26080139", [dict(r) for r in c.execute("SELECT id,document_no,invoice_date,status FROM sales_invoices WHERE document_no IN ('26080139','SAL-26080139','SAL-26080140')")])
print("max numeric among 2608*", c.execute("SELECT document_no FROM sales_invoices WHERE document_no LIKE '%2608%' ORDER BY length(document_no), document_no DESC LIMIT 5").fetchall())

# How was 26010201 generated?
print("\n=== ensure_document_no SI logic peek ===")

# inventory movements columns + any for product 3107 around date
cols=[x[1] for x in c.execute("PRAGMA table_info(inventory_movements)")]
print("inv cols", cols)
for r in c.execute("SELECT * FROM inventory_movements WHERE product_id=3107 ORDER BY id DESC LIMIT 10"):
    print(dict(r))

# warehouse stock
print("ws", dict(c.execute("SELECT * FROM warehouse_stock WHERE product_id=3107").fetchone() or {}))

# customer ledger entries for this sale?
import database as db
party, entries = db.get_customer_ledger(78, "2026-08-08", "2026-08-08")
for e in entries:
    if "26010201" in str(e) or "134400" in str(e.get("debit")) or "134400" in str(e.get("credit")) or "MERCEDES" in str(e.get("description","")).upper() or "SAL-" in str(e.get("ref","")):
        print("LEDGER", e)

# all refs containing 4721
for t in ["general_ledger","inventory_movements","cash_receipts","fmye_party_entries"]:
    try:
        cols=[x[1] for x in c.execute(f"PRAGMA table_info({t})")]
        idcols=[x for x in cols if "id" in x.lower() or "ref" in x.lower() or "no" in x.lower() or "desc" in x.lower()]
        print(t, "has", idcols[:12])
    except: pass

# approval audit
for t in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE '%audit%' OR name LIKE '%approval%' OR name LIKE '%log%')"):
    name=t[0]
    cols=[x[1] for x in c.execute(f"PRAGMA table_info({name})")]
    if any("document" in x.lower() or "ref" in x.lower() for x in cols):
        qcols=[x for x in cols if "document" in x.lower() or "ref" in x.lower() or "summary" in x.lower()]
        for qc in qcols[:2]:
            rows=c.execute(f"SELECT * FROM {name} WHERE CAST({qc} AS TEXT) LIKE '%26010201%' OR CAST({qc} AS TEXT) LIKE '%4721%' LIMIT 5").fetchall()
            if rows:
                print(name, [dict(r) for r in rows])
