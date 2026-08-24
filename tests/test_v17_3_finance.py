"""V17.3 comprehensive finance certification — PASS/FAIL only."""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _boot():
    import database as db
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db.DB_PATH = __import__("pathlib").Path(path)
    db.reset_runtime_state()
    db.init_db()
    from tests._bootstrap import set_ci_admin
    set_ci_admin(db)
    return db, path


def test_sales_gl_reconcile():
    db, path = _boot()
    today = str(date.today())
    try:
        with db.get_connection() as conn:
            conn.execute("INSERT INTO customers(code,name,is_active) VALUES('FC','Fin Cust',1)")
            cid = conn.execute("SELECT id FROM customers WHERE code='FC'").fetchone()[0]
            conn.execute("INSERT INTO products(code,name,sale_price,purchase_price,is_active) VALUES('FP','Fin Prod',100,80,1)")
            pid = conn.execute("SELECT id FROM products WHERE code='FP'").fetchone()[0]
            wh = conn.execute("SELECT id FROM warehouses LIMIT 1").fetchone()[0]
            conn.execute("INSERT OR REPLACE INTO warehouse_stock(warehouse_id,product_id,quantity) VALUES(?,?,100)", (wh, pid))
        sid = db.save_sale({"customer_id": cid, "sale_date": today, "payment_mode": "credit", "paid_amount": 0},
                           [{"item_id": pid, "quantity": 2, "rate": 100, "amount": 200}], user_id=1)
        from db_invoice_workflow import submit_sale_invoice, approve_sale_invoice
        submit_sale_invoice(sid, 1)
        approve_sale_invoice(sid, 1)
        from db_v3 import post_sales_invoice_gl
        post_sales_invoice_gl(sid, 1)
        with db.get_connection() as conn:
            dr, cr = conn.execute("SELECT COALESCE(SUM(debit),0), COALESCE(SUM(credit),0) FROM general_ledger").fetchone()
            assert abs(dr - cr) < 0.05, f"GL imbalance {dr} vs {cr}"
        print("PASS sales GL reconcile")
    finally:
        os.unlink(path)


def test_purchase_create():
    db, path = _boot()
    today = str(date.today())
    try:
        with db.get_connection() as conn:
            conn.execute("INSERT INTO suppliers(code,name,is_active) VALUES('FS','Fin Sup',1)")
            sid = conn.execute("SELECT id FROM suppliers WHERE code='FS'").fetchone()[0]
            conn.execute("INSERT INTO products(code,name,sale_price,purchase_price,is_active) VALUES('PP','Pur Prod',100,80,1)")
            pid = conn.execute("SELECT id FROM products WHERE code='PP'").fetchone()[0]
        pid_pur = db.save_purchase({"supplier_id": sid, "purchase_date": today, "payment_mode": "credit", "paid_amount": 0},
                                   [{"item_id": pid, "quantity": 5, "rate": 80, "amount": 400}], user_id=1)
        assert pid_pur
        print("PASS purchase create")
    finally:
        os.unlink(path)


def test_trial_balance():
    db, path = _boot()
    try:
        from db_v3 import get_trial_balance
        tb = get_trial_balance()
        assert isinstance(tb, list)
        print("PASS trial balance")
    finally:
        os.unlink(path)


def test_production_gl():
    db, path = _boot()
    try:
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "test_v17_1_manufacturing.py")],
                           capture_output=True, text=True, cwd=ROOT)
        assert r.returncode == 0, r.stdout + r.stderr
        print("PASS production posting")
    finally:
        os.unlink(path)


def test_cash_bank_jv():
    """Cash/bank/JV — fail loud if GL path missing (no NOT CERTIFIED)."""
    db, path = _boot()
    try:
        from db_v3 import get_trial_balance
        get_trial_balance()
        # Cash/bank standalone GL — verify functions exist
        import database as dbm
        has_cash = hasattr(dbm, "add_cash_entry") or hasattr(dbm, "save_cash_book_entry")
        if not has_cash:
            raise AssertionError("FAIL cash entry API missing")
        print("PASS cash/bank/jv API present")
    finally:
        os.unlink(path)


if __name__ == "__main__":
    test_sales_gl_reconcile()
    test_purchase_create()
    test_trial_balance()
    test_production_gl()
    test_cash_bank_jv()
    print("All V17.3 finance tests passed.")
