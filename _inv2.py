import sqlite3
from pathlib import Path
c = sqlite3.connect("ifs_erp.db")
c.row_factory = sqlite3.Row

print("=== SAL invoices Aug 8 / SAL- prefix ===")
for r in c.execute("""
SELECT id, document_no, invoice_date, customer_id, total, status, gate_pass_id, total_net_weight,
       physical_weight_kg, weight_match_status, weighbridge_required, paid_amount, payment_mode
FROM sales_invoices
WHERE document_no LIKE 'SAL-%' OR invoice_date>='2026-08-06'
ORDER BY id
"""):
    print(dict(r))

print("\n=== all gate_passes ===")
for r in c.execute("SELECT * FROM gate_passes ORDER BY id"):
    print(dict(r))

print("\n=== items for SAL-26010201 ===")
for r in c.execute("""
SELECT i.*, p.code, p.name FROM sales_invoice_items i
LEFT JOIN products p ON p.id=i.product_id
WHERE i.invoice_id=4721
"""):
    print(dict(r))

print("\n=== GL for invoice 4721 ===")
for r in c.execute("""
SELECT id, entry_date, account_id, debit, credit, description, reference_type, reference_no
FROM general_ledger WHERE reference_id=4721 OR reference_no='SAL-26010201' OR reference_no='26010201'
ORDER BY id
"""):
    print(dict(r))

print("\n=== stock movements invoice 4721 ===")
# find stock tables
for t in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE '%stock%' OR name LIKE '%inventory%' OR name LIKE '%movement%')"):
    print("tbl", t[0])
