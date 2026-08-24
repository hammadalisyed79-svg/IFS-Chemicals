import sqlite3

c = sqlite3.connect("ifs_erp.db", timeout=120)
c.row_factory = sqlite3.Row
n = c.execute(
    "SELECT COUNT(*) AS n FROM inventory_movements WHERE reason LIKE 'FMYE stock align%'"
).fetchone()["n"]
print("align_movements", n)
print(
    "allow_neg",
    c.execute(
        "SELECT value FROM system_settings WHERE key='allow_negative_stock'"
    ).fetchone(),
)
r = c.execute(
    """SELECT p.code, COALESCE(SUM(ws.quantity),0) AS q
       FROM products p
       LEFT JOIN warehouse_stock ws ON ws.product_id=p.id
       WHERE UPPER(TRIM(p.code))='RM0007'
       GROUP BY p.id"""
).fetchone()
print("RM0007", dict(r) if r else None)
sf = c.execute(
    """SELECT p.code, COALESCE(SUM(ws.quantity),0) AS q
       FROM products p
       LEFT JOIN warehouse_stock ws ON ws.product_id=p.id
       WHERE UPPER(TRIM(p.code))='SF0005'
       GROUP BY p.id"""
).fetchone()
print("SF0005", dict(sf) if sf else None)
c.close()
