import sqlite3
c=sqlite3.connect("ifs_erp.db"); c.row_factory=sqlite3.Row
print("GL now for 4721:")
for r in c.execute("SELECT id,account_id,debit,credit,description,reference_no FROM general_ledger WHERE reference_type='sales_invoice' AND reference_id=4721"):
    print(dict(r))

# audit
for t in ["erp_audit_log","audit_log","db_audit","activity_log"]:
    try:
        n=c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print("table", t, n)
    except: pass
for t in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%audit%'"):
    print("audit tbl", t[0], [x[1] for x in c.execute(f"PRAGMA table_info({t[0]})")])

# GP sequence
print("GP seq", dict(c.execute("SELECT * FROM document_sequences WHERE doc_type='GP'").fetchone() or {}))

# Does stock for 3107 look like it includes -1400 from today?
# Compare sum of movements vs warehouse
mov=c.execute("SELECT COALESCE(SUM(CASE WHEN movement_type='in' THEN quantity ELSE -quantity END),0) FROM inventory_movements WHERE product_id=3107 AND warehouse_id=1").fetchone()[0]
ws=c.execute("SELECT quantity FROM warehouse_stock WHERE product_id=3107 AND warehouse_id=1").fetchone()[0]
print("mov net", mov, "ws", ws, "diff", ws-mov)
