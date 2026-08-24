import sqlite3
c=sqlite3.connect("ifs_erp.db"); c.row_factory=sqlite3.Row
print("=== SAL-* docs ordered ===")
for r in c.execute("""
SELECT id, document_no, invoice_date, status, gate_pass_id, created_at, posted_at
FROM sales_invoices WHERE document_no LIKE 'SAL-%' ORDER BY id
"""):
    print(dict(r))

print("\n=== doc number sequences ===")
for t in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE '%doc%' OR name LIKE '%seq%' OR name LIKE '%number%')"):
    print(t[0])
    try:
        for r in c.execute(f"SELECT * FROM {t[0]} LIMIT 30"):
            print(" ", dict(r))
    except Exception as e:
        print(" ", e)

print("\n=== GL for 4721 any ref ===")
for r in c.execute("""
SELECT id,entry_date,account_id,debit,credit,description,reference_type,reference_id,reference_no
FROM general_ledger
WHERE reference_id=4721 OR reference_no LIKE '%26010201%' OR description LIKE '%26010201%'
   OR description LIKE '%SAL-26010201%' OR description LIKE '%MERCEDEZ%' OR description LIKE '%MERCEDES CEILLING%'
ORDER BY id LIMIT 40
"""):
    print(dict(r))

print("\n=== inventory for invoice 4721 ===")
for r in c.execute("SELECT * FROM inventory_movements WHERE reference_id=4721 OR reference_no LIKE '%26010201%' LIMIT 20"):
    print(dict(r))

print("\n=== customer 78 ===")
print(dict(c.execute("SELECT id,code,name,current_balance FROM customers WHERE id=78").fetchone()))
