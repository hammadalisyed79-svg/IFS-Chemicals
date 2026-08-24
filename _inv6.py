import sqlite3
c=sqlite3.connect("ifs_erp.db"); c.row_factory=sqlite3.Row
# taxable helpers path - try posting GL manually to see error
from db_v3 import post_sales_invoice_gl, _invoice_taxable, _invoice_tax_payable
from database import row_to_dict, get_connection
with get_connection() as conn:
    inv = row_to_dict(conn.execute("SELECT * FROM sales_invoices WHERE id=4721").fetchone())
    print("taxable", _invoice_taxable(inv), "tax_pay", _invoice_tax_payable(inv))
    print("total", inv["total"], "paid", inv["paid_amount"], "taxable_amount", inv["taxable_amount"])

# dry run balance
total=round(inv["total"],2); paid=round(inv.get("paid_amount") or 0,2)
taxable=_invoice_taxable(inv); tax_payable=_invoice_tax_payable(inv); wht=round(inv.get("wht_tax") or 0,2)
debits=round((total-paid)+paid+wht,2); credits=round(taxable+tax_payable,2)
print("debits",debits,"credits",credits)

# try post
try:
    post_sales_invoice_gl(4721, 5)
    print("GL POSTED OK")
except Exception as e:
    print("GL FAIL", type(e), e)

# check movements again - maybe post effects needed
from db_invoice_workflow import _post_sale_effects
# check if stock already adjusted - compare expected
ws=c.execute("SELECT quantity FROM warehouse_stock WHERE product_id=3107 AND warehouse_id=1").fetchone()
print("stock before effects retry", ws[0] if ws else None)
# would double customer balance if we call _post_sale_effects again!
cust=c.execute("SELECT current_balance FROM customers WHERE id=78").fetchone()[0]
print("cust bal", cust)
# sum of unpaid approved invoices
s=c.execute("SELECT SUM(total-paid_amount) FROM sales_invoices WHERE customer_id=78 AND status='approved'").fetchone()[0]
print("sum unpaid approved", s)
