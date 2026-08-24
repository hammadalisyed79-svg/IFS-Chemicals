"""V15 distributor portal security and isolation tests."""

from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _temp_db():
    import database as db
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db.DB_PATH = __import__("pathlib").Path(path)
    db.reset_runtime_state()
    db.init_db()
    return db, path


def _cust(db, code, name):
    return db.add_customer({"code": code, "name": name}, created_by=1)


def _dist_user(db, username, customer_id):
    with db.get_connection() as conn:
        rid = conn.execute("SELECT id FROM roles WHERE code='DISTRIBUTOR'").fetchone()[0]
    db.add_user(
        username, "Pass1234", username, role="user", created_by=1,
        user_type="distributor", linked_customer_id=customer_id, role_id=rid,
    )
    with db.get_connection() as conn:
        return db.get_user_by_id(conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()[0])


def test_distributor_cannot_view_internal_nav():
    db, path = _temp_db()
    try:
        from erp_ui.nav import can_view_screen, filtered_nav_groups
        cid = _cust(db, "D001", "Dist A")
        with db.get_connection() as conn:
            conn.execute("UPDATE customers SET is_distributor=1, portal_enabled=1 WHERE id=?", (cid,))
        user = _dist_user(db, "dist1", cid)
        assert not can_view_screen(user, "Finance")
        assert not can_view_screen(user, "User Management")
        assert filtered_nav_groups(user) == {}
        print("PASS distributor cannot view internal nav")
    finally:
        os.unlink(path)


def test_distributor_isolation_orders():
    db, path = _temp_db()
    try:
        from erp_core import portal_service as ps
        c1 = _cust(db, "D1", "One")
        c2 = _cust(db, "D2", "Two")
        u1 = _dist_user(db, "d1", c1)
        u2 = _dist_user(db, "d2", c2)
        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO products(code,name,unit_id,sale_price,is_active,created_by) VALUES('P1','Prod',1,100,1,1)"
            )
            pid = conn.execute("SELECT id FROM products WHERE code='P1'").fetchone()[0]
        from erp_core import distributor_catalog as dcat
        dcat.upsert_catalog_item(c1, pid, rate=100, discount_pct=0, created_by=1, notify=False)
        cart = [{"product_id": pid, "quantity": 2, "rate": 100}]
        oid = ps.create_portal_order(u1, cart, submit=False)
        try:
            ps.get_portal_order(u2, oid)
            raise AssertionError("D2 should not read D1 order")
        except PermissionError:
            pass
        print("PASS distributor order isolation")
    finally:
        os.unlink(path)


def test_failed_login_lockout():
    db, path = _temp_db()
    try:
        from erp_core.v15_security import max_failed_logins
        from tests._bootstrap import set_ci_admin, CI_ADMIN_PASSWORD
        set_ci_admin(db)
        for _ in range(max_failed_logins()):
            db.authenticate("admin", "wrong")
        r = db.authenticate("admin", CI_ADMIN_PASSWORD)
        assert r and r.get("_error"), "Locked account should return error"
        print("PASS failed login lockout")
    finally:
        os.unlink(path)


def test_portal_tables_exist():
    db, path = _temp_db()
    try:
        with db.get_connection() as conn:
            for t in ("portal_orders", "erp_notifications", "price_lists", "role_permission_matrix", "login_attempts"):
                assert conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone(), t
        print("PASS portal tables exist")
    finally:
        os.unlink(path)


def test_price_list_applied():
    db, path = _temp_db()
    try:
        from erp_core import portal_service as ps
        with db.get_connection() as conn:
            pl = conn.execute("SELECT id FROM price_lists WHERE code='DIST'").fetchone()[0]
            conn.execute(
                "INSERT INTO products(code,name,unit_id,sale_price,is_active,created_by) VALUES('PX','X',1,50,1,1)"
            )
            pid = conn.execute("SELECT id FROM products WHERE code='PX'").fetchone()[0]
            conn.execute(
                "INSERT INTO price_list_items(price_list_id,product_id,rate,discount_pct,min_qty) VALUES(?,?,?,?,?)",
                (pl, pid, 77.5, 0, 1),
            )
        cid = _cust(db, "DC", "Dist C")
        with db.get_connection() as conn:
            conn.execute("UPDATE customers SET assigned_price_list_id=? WHERE id=?", (pl, cid))
        u = _dist_user(db, "dx", cid)
        pr = ps.get_product_price(pid, ps.resolve_price_list_id(u), 50)
        assert pr["rate"] == 77.5
        print("PASS price list rate")
    finally:
        os.unlink(path)


def test_portal_order_creates_sales_order():
    db, path = _temp_db()
    try:
        from erp_core import portal_service as ps
        from erp_core import distributor_catalog as dcat
        cid = _cust(db, "D3", "Three")
        u = _dist_user(db, "d3", cid)
        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO products(code,name,unit_id,sale_price,is_active,created_by) VALUES('P2','P2',1,10,1,1)"
            )
            pid = conn.execute("SELECT id FROM products WHERE code='P2'").fetchone()[0]
        dcat.upsert_catalog_item(cid, pid, rate=10, discount_pct=0, created_by=1, notify=False)
        oid = ps.create_portal_order(u, [{"product_id": pid, "quantity": 1, "rate": 10}], submit=True)
        order = ps.get_portal_order(u, oid)
        assert order.get("sales_order_id"), "sales_order_id missing on portal order"
        with db.get_connection() as conn:
            so = conn.execute(
                "SELECT id, status, source_channel, portal_order_id, customer_id FROM sales_orders WHERE id=?",
                (order["sales_order_id"],),
            ).fetchone()
        assert so, "sales_orders row missing"
        assert so["customer_id"] == cid
        assert (so["source_channel"] or "") == "portal"
        assert so["portal_order_id"] == oid
        print("PASS portal order creates sales order draft for staff")
    finally:
        os.unlink(path)


def test_distributor_catalog_rebuild_and_admin_override():
    db, path = _temp_db()
    try:
        from erp_core import distributor_catalog as dcat
        from erp_core import portal_service as ps
        cid = _cust(db, "DCAT", "Cat Co")
        with db.get_connection() as conn:
            conn.execute("UPDATE customers SET is_distributor=1, portal_enabled=1 WHERE id=?", (cid,))
            conn.execute(
                "INSERT INTO products(code,name,unit_id,sale_price,is_active,created_by) VALUES('PX','CatProd',1,50,1,1)"
            )
            pid = conn.execute("SELECT id FROM products WHERE code='PX'").fetchone()[0]
            wh = conn.execute("SELECT id FROM warehouses LIMIT 1").fetchone()[0]
            conn.execute(
                """INSERT INTO sales_invoices(
                    document_no, invoice_date, customer_id, warehouse_id, subtotal, total,
                    status, created_by)
                   VALUES('T-INV-1','2026-06-15',?,?,100,100,'approved',1)""",
                (cid, wh),
            )
            iid = conn.execute("SELECT id FROM sales_invoices WHERE document_no='T-INV-1'").fetchone()[0]
            conn.execute(
                """INSERT INTO sales_invoice_items(invoice_id,product_id,quantity,rate,amount,line_discount)
                   VALUES(?,?,2,50,90,10)""",
                (iid, pid),
            )
        res = dcat.rebuild_catalog_from_invoices(cid, cutoff="2026-05-01", created_by=1)
        assert res["inserted"] == 1
        rows = dcat.list_catalog(cid)
        assert len(rows) == 1
        assert float(rows[0]["rate"]) == 50
        assert abs(float(rows[0]["discount_pct"]) - 10.0) < 0.01  # 10/(2*50)*100

        # Newer invoice with implied discount (amount < qty*rate, line_discount=0)
        with db.get_connection() as conn:
            conn.execute(
                """INSERT INTO sales_invoices(
                    document_no, invoice_date, customer_id, warehouse_id, subtotal, total,
                    status, created_by)
                   VALUES('T-INV-2','2026-07-01',?,?,100,93,'approved',1)""",
                (cid, wh),
            )
            iid2 = conn.execute("SELECT id FROM sales_invoices WHERE document_no='T-INV-2'").fetchone()[0]
            conn.execute(
                """INSERT INTO sales_invoice_items(invoice_id,product_id,quantity,rate,amount,line_discount)
                   VALUES(?,?,1,100,93,0)""",
                (iid2, pid),
            )
        dcat.rebuild_catalog_from_invoices(cid, cutoff="2026-05-01", created_by=1)
        rows_imp = dcat.list_catalog(cid)
        assert float(rows_imp[0]["rate"]) == 100
        assert abs(float(rows_imp[0]["discount_pct"]) - 7.0) < 0.05

        dcat.upsert_catalog_item(cid, pid, rate=55, discount_pct=5, created_by=1, notify=False)
        res2 = dcat.rebuild_catalog_from_invoices(cid, cutoff="2026-05-01", created_by=1)
        assert res2["skipped_admin"] == 1
        rows2 = dcat.list_catalog(cid)
        assert float(rows2[0]["rate"]) == 55
        assert int(rows2[0]["admin_changed"]) == 1
        u = _dist_user(db, "dcatu", cid)
        cat = ps.get_catalog(u)
        assert len(cat) == 1 and cat[0]["admin_changed"] is True
        print("PASS distributor catalog rebuild + admin override")
    finally:
        os.unlink(path)


def test_my_ledger_scoped_to_linked_customer():
    db, path = _temp_db()
    try:
        from erp_core import portal_service as ps
        c1 = _cust(db, "L1", "Ledger One")
        c2 = _cust(db, "L2", "Ledger Two")
        u1 = _dist_user(db, "led1", c1)
        cust, entries = ps.get_my_ledger(u1)
        assert cust and cust["id"] == c1
        # Isolation: cannot assert access to other customer
        try:
            ps.assert_distributor_access(u1, c2)
            raise AssertionError("should not access other customer")
        except PermissionError:
            pass
        print("PASS my ledger scoped to linked customer")
    finally:
        os.unlink(path)


def test_enable_distributor_portal():
    db, path = _temp_db()
    try:
        from erp_core import portal_service as ps
        cid = _cust(db, "EP1", "Enable Portal Co")
        with db.get_connection() as conn:
            pl = conn.execute("SELECT id FROM price_lists WHERE is_active=1 ORDER BY id LIMIT 1").fetchone()
            assert pl, "need a price list"
            pl_id = pl[0]
        creds = ps.enable_distributor_portal(
            cid,
            username="ep_portal",
            password="TempPass9",
            full_name="Enable Portal Co",
            price_list_id=pl_id,
            credit_limit=50000,
            created_by=1,
        )
        assert creds["username"] == "ep_portal"
        with db.get_connection() as conn:
            c = conn.execute(
                "SELECT is_distributor, portal_enabled, assigned_price_list_id FROM customers WHERE id=?",
                (cid,),
            ).fetchone()
            u = conn.execute(
                "SELECT user_type, linked_customer_id, must_change_password FROM users WHERE id=?",
                (creds["user_id"],),
            ).fetchone()
        assert c["is_distributor"] == 1 and c["portal_enabled"] == 1
        assert c["assigned_price_list_id"] == pl_id
        assert (u["user_type"] or "").startswith("distributor")
        assert u["linked_customer_id"] == cid
        assert u["must_change_password"] == 1
        print("PASS enable distributor portal")
    finally:
        os.unlink(path)


if __name__ == "__main__":
    test_portal_tables_exist()
    test_distributor_cannot_view_internal_nav()
    test_distributor_isolation_orders()
    test_price_list_applied()
    test_portal_order_creates_sales_order()
    test_distributor_catalog_rebuild_and_admin_override()
    test_my_ledger_scoped_to_linked_customer()
    test_enable_distributor_portal()
    test_failed_login_lockout()
    print("All V15 portal security tests passed.")
