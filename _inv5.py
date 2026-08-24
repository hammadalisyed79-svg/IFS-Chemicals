import sqlite3
c=sqlite3.connect("ifs_erp.db"); c.row_factory=sqlite3.Row

def dump(iid, doc):
    print(f"\n==== {doc} id={iid} ====")
    inv=dict(c.execute("SELECT id,document_no,status,total,posted_at,approved_at,payment_mode,paid_amount,gate_pass_id FROM sales_invoices WHERE id=?",(iid,)).fetchone())
    print(inv)
    gl=c.execute("SELECT COUNT(*), SUM(debit), SUM(credit) FROM general_ledger WHERE reference_type='sales_invoice' AND reference_id=?",(iid,)).fetchone()
    print("GL", tuple(gl))
    for r in c.execute("SELECT account_id,debit,credit,description,reference_no FROM general_ledger WHERE reference_type='sales_invoice' AND reference_id=?",(iid,)):
        print(" ",dict(r))
    im=c.execute("SELECT COUNT(*), SUM(quantity) FROM inventory_movements WHERE reference_type='sales_invoice' AND reference_id=?",(iid,)).fetchone()
    print("INV_MOV", tuple(im))
    for r in c.execute("SELECT * FROM inventory_movements WHERE reference_type='sales_invoice' AND reference_id=?",(iid,)):
        print(" ",dict(r))
    gp=c.execute("SELECT id,document_no,remarks,sales_invoice_id,status,weight,quantity FROM gate_passes WHERE sales_invoice_id=? OR id=(SELECT gate_pass_id FROM sales_invoices WHERE id=?)",(iid,iid)).fetchall()
    for r in gp: print("GP",dict(r))

dump(4721,"SAL-26010201")
dump(4722,"SAL-26080140")
dump(4723,"SAL-26080141")

# how many approved sales missing GL?
print("\n=== approved SAL missing GL ===")
for r in c.execute("""
SELECT s.id, s.document_no, s.status, s.total,
 (SELECT COUNT(*) FROM general_ledger g WHERE g.reference_type='sales_invoice' AND g.reference_id=s.id) AS gl_n,
 (SELECT COUNT(*) FROM inventory_movements m WHERE m.reference_type='sales_invoice' AND m.reference_id=s.id) AS im_n
FROM sales_invoices s
WHERE s.document_no LIKE 'SAL-%' AND s.status='approved'
ORDER BY s.id
"""):
    print(dict(r))
