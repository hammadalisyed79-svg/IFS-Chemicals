"""
FMYE → ERP step-by-step migration (clean database).

Start fresh, then import one phase at a time and verify before continuing.

Usage:
  python migrate_fmye.py --reset              # empty ERP (schema + admin only)
  python migrate_fmye.py --list               # show all steps
  python migrate_fmye.py --step masters       # run one step
  python migrate_fmye.py --through purchases  # run steps 1..N in order
  python migrate_fmye.py --all                # run every step (after reset)

Login after reset: admin / admin123
"""

from __future__ import annotations

import argparse
import shutil
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
EXPORT_DIR = ROOT / "import" / "fmye" / "full"
BACKUP_DIR = ROOT / "import" / "fmye" / "backups"

import database as db
from import_fmye_from_dat import (
    EXPORT_DIR as _EXP,
    FMYEExport,
    GROUP_MAP,
    ITEM_TYPE_MAP,
    _d,
    _ensure_units,
    _f,
    _group_id,
    _import_party_vouchers,
    _in_years,
    _opening_map,
    _resolve_party_for_voucher,
    ifs_status_from_fmye,
)

# OpeningBalances PeriodID "2026" = balances as of 1 Jan 2026 (2025 year-end closing)
OPENING_PERIOD = "2026"
IMPORT_YEARS = {2026}

STEPS = [
    ("masters", "Chart, customers, suppliers, products, stock (no opening balances yet)"),
    ("openings", f"Opening balances from FMYE {OPENING_PERIOD} (= 1 Jan 2026 opening)"),
    ("stock", "Product opening stock from FMYE opening_stock table (2026 opening)"),
    ("inventory", "Post stock movements from 2026 sales/purchases/returns"),
    ("sales", f"Sales invoices {min(IMPORT_YEARS)}–{max(IMPORT_YEARS)} + line items"),
    ("sales2020", "Sales 2020–2023 from SL vouchers (optional — skip for 2026 cutover)"),
    ("purchases", f"Purchase invoices {min(IMPORT_YEARS)}–{max(IMPORT_YEARS)} + lines"),
    ("returns", f"Sales & purchase returns {min(IMPORT_YEARS)}–{max(IMPORT_YEARS)}"),
    ("vouchers", f"Receipts/payments/JV {min(IMPORT_YEARS)}–{max(IMPORT_YEARS)} only"),
    ("bom", "BOM / composition formulas"),
    ("balances", "Recalculate party balances + audit"),
]

PHASE_2026_STEPS = ["openings", "stock", "sales", "purchases", "returns", "vouchers", "inventory", "bom", "balances"]
# Keep old name as alias for scripts that still pass --phase 2024
PHASE_2024_STEPS = PHASE_2026_STEPS

STEP_NAMES = [s[0] for s in STEPS]


def _prod_map(conn):
    m = {}
    for r in conn.execute("SELECT id, code FROM products"):
        k = (r["code"] or "").strip().upper()
        if k:
            m[k] = r["id"]
    return m


def _backup(label: str) -> Path | None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if not db.DB_PATH.exists():
        return None
    stamp = date.today().strftime("%Y%m%d_%H%M")
    dest = BACKUP_DIR / f"ifs_erp_{label}_{stamp}.db"
    shutil.copy2(db.DB_PATH, dest)
    return dest


def reset_erp() -> Path | None:
    """Delete live DB and create empty schema (no demo data)."""
    backup = _backup("before_clean_reset")
    path = Path(db.DB_PATH)
    if path.exists():
        path.unlink()
        print(f"Removed: {path}")
    db.init_db()
    print("Empty ERP ready. Use reset_admin_password.bat for login.")
    return backup


def _require_export():
    if not EXPORT_DIR.exists():
        raise SystemExit(f"FMYE export missing: {EXPORT_DIR}")


def _uid():
    """Use admin user id without password (import runs on trusted server)."""
    db.init_db()
    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE LOWER(username)='admin' AND is_active=1"
        ).fetchone()
    if not row:
        raise SystemExit("No active admin user. Run: python migrate_fmye.py --reset")
    return row[0]


def _print_counts():
    with db.get_connection() as conn:
        checks = [
            ("customers", "SELECT COUNT(*) FROM customers"),
            ("suppliers", "SELECT COUNT(*) FROM suppliers"),
            ("products", "SELECT COUNT(*) FROM products"),
            ("chart_of_accounts", "SELECT COUNT(*) FROM chart_of_accounts"),
            ("sales_invoices", "SELECT COUNT(*) FROM sales_invoices"),
            ("purchase_invoices", "SELECT COUNT(*) FROM purchase_invoices"),
            ("sales_returns", "SELECT COUNT(*) FROM sales_returns"),
            ("purchase_returns", "SELECT COUNT(*) FROM purchase_returns"),
            ("fmye_party_entries", "SELECT COUNT(*) FROM fmye_party_entries"),
            ("bom_formulas", "SELECT COUNT(*) FROM bom_formulas"),
        ]
        print("\n  ERP counts after step:")
        for label, q in checks:
            try:
                n = conn.execute(q).fetchone()[0]
                print(f"    {label:22} {n:>8,}")
            except Exception:
                print(f"    {label:22}   (n/a)")
        print(f"\n  Sales by year ({min(IMPORT_YEARS)}–{max(IMPORT_YEARS)}):")
        for row in conn.execute(
            """SELECT substr(invoice_date,1,4) y, COUNT(*) n FROM sales_invoices
               WHERE substr(invoice_date,1,4) BETWEEN ? AND ? GROUP BY 1 ORDER BY 1""",
            (str(min(IMPORT_YEARS)), str(max(IMPORT_YEARS))),
        ):
            print(f"    {row[0]}: {row[1]:,}")
        print(f"  Purchases by year:")
        for row in conn.execute(
            """SELECT substr(invoice_date,1,4) y, COUNT(*) n FROM purchase_invoices
               WHERE substr(invoice_date,1,4) BETWEEN ? AND ? GROUP BY 1 ORDER BY 1""",
            (str(min(IMPORT_YEARS)), str(max(IMPORT_YEARS))),
        ):
            print(f"    {row[0]}: {row[1]:,}")


def step_openings(uid: int, stats: dict):
    """Set opening balances = FMYE 2023 closing (OpeningBalances period 2024)."""
    exp = FMYEExport(EXPORT_DIR)
    open_bal = _opening_map(exp.rows("OpeningBalances"), period_id=OPENING_PERIOD)
    chart = exp.rows("Chart")
    s_codes = {r["AccountCode"] for r in chart if r.get("AccountCategory") == "S"}
    v_codes = {r["AccountCode"] for r in chart if r.get("AccountCategory") == "V"}

    with db.get_connection() as conn:
        # Every Chart S customer: opening = 2024 period row or 0 (new accounts in 2025+)
        for code in s_codes:
            ob = open_bal.get(code, 0.0)
            conn.execute(
                """UPDATE customers SET opening_balance=?, current_balance=?,
                   modified_by=?, modified_at=? WHERE code=?""",
                (ob, ob, uid, db._now(), code),
            )
            stats["customers"] += 1
        for code in v_codes:
            ob = open_bal.get(code, 0.0)
            conn.execute(
                """UPDATE suppliers SET opening_balance=?, current_balance=?,
                   modified_by=?, modified_at=? WHERE code=?""",
                (ob, ob, uid, db._now(), code),
            )
            stats["suppliers"] += 1
        for code, ob in open_bal.items():
            conn.execute(
                """UPDATE chart_of_accounts SET opening_balance=?, current_balance=?,
                   modified_by=?, modified_at=? WHERE code=?""",
                (ob, ob, uid, db._now(), code),
            )
            stats["accounts"] += 1
        # GL accounts in chart but no 2024 opening row -> zero
        for r in chart:
            code = (r.get("AccountCode") or "").strip()
            if code and code not in open_bal:
                conn.execute(
                    """UPDATE chart_of_accounts SET opening_balance=0, current_balance=0,
                       modified_by=?, modified_at=? WHERE code=?""",
                    (uid, db._now(), code),
                )
    stats["period"] = OPENING_PERIOD
    print(f"  Opening balances: FMYE OpeningBalances[{OPENING_PERIOD}] (2023 year-end closing)")


def step_stock(uid: int, stats: dict):
    """Product opening stock = FMYE opening_stock table (2023 closing / 2024 opening)."""
    exp = FMYEExport(EXPORT_DIR)
    qty_by_item = defaultdict(float)
    for r in exp.rows("opening_stock"):
        ic = (r.get("itemcode") or "").strip().upper()
        if ic:
            qty_by_item[ic] += _f(r.get("open_qty"))

    with db.get_connection() as conn:
        wh = conn.execute("SELECT id FROM warehouses ORDER BY id LIMIT 1").fetchone()[0]
        prod_map = _prod_map(conn)
        for ic, qty in qty_by_item.items():
            pid = prod_map.get(ic)
            if not pid:
                stats["stock_skipped"] += 1
                continue
            conn.execute(
                """INSERT INTO warehouse_stock(warehouse_id, product_id, quantity, modified_at)
                   VALUES(?,?,?,?) ON CONFLICT(warehouse_id, product_id)
                   DO UPDATE SET quantity=excluded.quantity, modified_at=excluded.modified_at""",
                (wh, pid, qty, db._now()),
            )
            stats["stock_items"] += 1
        # Items not in opening_stock table -> zero opening (2024 start)
        for row in conn.execute("SELECT id, code FROM products"):
            ic = (row["code"] or "").strip().upper()
            if ic not in qty_by_item:
                conn.execute(
                    """INSERT INTO warehouse_stock(warehouse_id, product_id, quantity, modified_at)
                       VALUES(?,?,0,?) ON CONFLICT(warehouse_id, product_id)
                       DO UPDATE SET quantity=0, modified_at=excluded.modified_at""",
                    (wh, row["id"], db._now()),
                )
                stats["stock_zeroed"] += 1
    print(f"  Stock from FMYE opening_stock table ({stats['stock_items']} items with qty)")


def step_masters(uid: int, stats: dict):
    exp = FMYEExport(EXPORT_DIR)
    chart = exp.rows("Chart")
    items = exp.rows("ItemInformation")

    with db.get_connection() as conn:
        wh = conn.execute("SELECT id FROM warehouses ORDER BY id LIMIT 1").fetchone()[0]
        cat_id = conn.execute("SELECT id FROM product_categories ORDER BY id LIMIT 1").fetchone()[0]
        unit_cache = _ensure_units(conn, items, uid)

        for r in chart:
            code = (r.get("AccountCode") or "").strip()
            if not code:
                continue
            gtype = GROUP_MAP.get(r.get("AccountType", "A"), "asset")
            gid = _group_id(conn, gtype)
            name = (r.get("AccountName") or code).strip()
            active = 1 if r.get("Active", "1") in ("1", 1, "Y") else 0
            row = conn.execute("SELECT id FROM chart_of_accounts WHERE code=?", (code,)).fetchone()
            if row:
                conn.execute(
                    """UPDATE chart_of_accounts SET name=?, is_active=?, modified_by=?, modified_at=? WHERE id=?""",
                    (name, active, uid, db._now(), row[0]),
                )
            else:
                conn.execute(
                    """INSERT INTO chart_of_accounts(code, name, account_group_id, opening_balance,
                       current_balance, is_active, created_by) VALUES(?,?,?,?,?,?,?)""",
                    (code, name, gid, 0, 0, active, uid),
                )
            stats["accounts"] += 1

        for r in chart:
            if r.get("AccountCategory") != "S":
                continue
            code = (r.get("AccountCode") or "").strip()
            if not code:
                continue
            name = (r.get("AccountName") or code).strip()
            phone = r.get("Phone") or r.get("MobileNo") or ""
            row = conn.execute("SELECT id FROM customers WHERE code=?", (code,)).fetchone()
            if row:
                conn.execute(
                    """UPDATE customers SET name=?, phone=?, email=?, address=?, city=?, ntn=?,
                       modified_by=?, modified_at=? WHERE id=?""",
                    (name, phone, r.get("Email") or "", r.get("Address") or "", r.get("City") or "",
                     r.get("SaleTaxNo") or "", uid, db._now(), row[0]),
                )
            else:
                conn.execute(
                    """INSERT INTO customers(code, name, phone, email, address, city, ntn,
                       opening_balance, current_balance, created_by) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (code, name, phone, r.get("Email") or "", r.get("Address") or "", r.get("City") or "",
                     r.get("SaleTaxNo") or "", 0, 0, uid),
                )
            stats["customers"] += 1

        for r in chart:
            if r.get("AccountCategory") != "V":
                continue
            code = (r.get("AccountCode") or "").strip()
            if not code:
                continue
            name = (r.get("AccountName") or code).strip()
            phone = r.get("Phone") or r.get("MobileNo") or ""
            row = conn.execute("SELECT id FROM suppliers WHERE code=?", (code,)).fetchone()
            if row:
                conn.execute(
                    """UPDATE suppliers SET name=?, phone=?, email=?, address=?, city=?,
                       modified_by=?, modified_at=? WHERE id=?""",
                    (name, phone, r.get("Email") or "", r.get("Address") or "", r.get("City") or "",
                     uid, db._now(), row[0]),
                )
            else:
                conn.execute(
                    """INSERT INTO suppliers(code, name, phone, email, address, city,
                       opening_balance, current_balance, created_by) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (code, name, phone, r.get("Email") or "", r.get("Address") or "", r.get("City") or "",
                     0, 0, uid),
                )
            stats["suppliers"] += 1

        prod_map = _prod_map(conn)
        for r in items:
            code = (r.get("ItemCode") or "").strip()
            if not code:
                continue
            sym = (r.get("MeasuringUnit") or "PCS").strip().upper()
            unit_id = unit_cache.get(sym) or next(iter(unit_cache.values()))
            ptype = ITEM_TYPE_MAP.get(r.get("ItemType", "F"), "finished")
            name = (r.get("ItemName") or code).strip()
            pid = prod_map.get(code.upper())
            if pid:
                conn.execute(
                    """UPDATE products SET name=?, unit_id=?, product_type=?, purchase_price=?,
                       sale_price=?, modified_by=?, modified_at=? WHERE id=?""",
                    (name, unit_id, ptype, _f(r.get("PurchaseRate")), _f(r.get("SaleRate")), uid, db._now(), pid),
                )
            else:
                cur = conn.execute(
                    """INSERT INTO products(code, name, category_id, unit_id, product_type,
                       purchase_price, sale_price, created_by) VALUES(?,?,?,?,?,?,?,?)""",
                    (code, name, cat_id, unit_id, ptype, _f(r.get("PurchaseRate")), _f(r.get("SaleRate")), uid),
                )
                pid = cur.lastrowid
                prod_map[code.upper()] = pid
            conn.execute(
                """INSERT INTO warehouse_stock(warehouse_id, product_id, quantity, modified_at)
                   VALUES(?,?,0,?) ON CONFLICT(warehouse_id, product_id) DO NOTHING""",
                (wh, pid, db._now()),
            )
            stats["products"] += 1

        for fy in range(2020, 2027):
            code = str(fy)
            if conn.execute("SELECT 1 FROM fiscal_years WHERE fy_code=?", (code,)).fetchone():
                continue
            conn.execute(
                """INSERT INTO fiscal_years(fy_code, start_date, end_date, is_active, created_by)
                   VALUES(?,?,?,?,?)""",
                (code, f"{fy}-01-01", f"{fy}-12-31", 1 if fy == 2026 else 0, uid),
            )
            if fy == 2026:
                conn.execute("UPDATE fiscal_years SET is_active=0 WHERE fy_code!=?", (code,))


def step_sales(uid: int, stats: dict):
    exp = FMYEExport(EXPORT_DIR)
    sales_h = exp.rows("SaleInvoiceHeader")
    sales_d = exp.rows("SaleInvoiceDetail")
    open_bal = _opening_map(exp.rows("OpeningBalances"), period_id=OPENING_PERIOD)
    lines_by = defaultdict(list)
    for ln in sales_d:
        lines_by[ln.get("SaleInvoiceCode", "")].append(ln)

    with db.get_connection() as conn:
        wh = conn.execute("SELECT id FROM warehouses ORDER BY id LIMIT 1").fetchone()[0]
        cust_ids = {r["code"]: r["id"] for r in conn.execute("SELECT id, code FROM customers")}
        prod_map = _prod_map(conn)
        existing = {r[0] for r in conn.execute("SELECT document_no FROM sales_invoices")}

        for h in sales_h:
            if not _in_years(h.get("InvoiceDate"), IMPORT_YEARS):
                stats["skipped_year"] += 1
                continue
            doc = (h.get("DocumentNo") or "").strip()
            if not doc or doc in existing:
                continue
            pc = (h.get("PartyCode") or "").strip()
            cid = cust_ids.get(pc)
            if not cid and pc:
                ob = open_bal.get(pc, 0)
                cur = conn.execute(
                    """INSERT INTO customers(code, name, opening_balance, current_balance, created_by)
                       VALUES(?,?,?,?,?)""",
                    (pc, (h.get("Name") or pc).strip(), ob, ob, uid),
                )
                cid = cur.lastrowid
                cust_ids[pc] = cid
                stats["customers_added"] += 1
            if not cid:
                continue
            yr = _d(h.get("InvoiceDate"))[:4]
            stats[f"sales_{yr}"] += 1
            lines = lines_by.get(h.get("SaleInvoiceCode", ""), [])
            subtotal = sum(_f(ln.get("TotalAmount") or ln.get("Amount")) for ln in lines) or _f(h.get("NetAmount"))
            total = _f(h.get("NetAmount")) or subtotal
            inv_status = ifs_status_from_fmye(h.get("Status"))
            cur = conn.execute(
                """INSERT INTO sales_invoices(document_no, invoice_date, customer_id, warehouse_id,
                   subtotal, discount, tax, total, paid_amount, payment_mode, notes, status,
                   weighbridge_required, created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (doc, _d(h.get("InvoiceDate")), cid, wh, subtotal, _f(h.get("DiscountAmount")), 0, total, 0,
                 "credit", (h.get("Remarks") or "")[:500], inv_status, 0, uid),
            )
            inv_id = cur.lastrowid
            for ln in lines:
                ic = (ln.get("ItemCode") or "").strip().upper()
                pid = prod_map.get(ic)
                if not pid:
                    continue
                conn.execute(
                    """INSERT INTO sales_invoice_items(invoice_id, product_id, quantity, rate, amount)
                       VALUES(?,?,?,?,?)""",
                    (inv_id, pid, _f(ln.get("Quantity")), _f(ln.get("SaleRate")),
                     _f(ln.get("TotalAmount") or ln.get("Amount"))),
                )
            existing.add(doc)
            stats["sales"] += 1


def step_sales2020(uid: int, stats: dict):
    from import_fmye_sl_sales import apply as apply_sl

    apply_sl(uid, stats, recalc_balances=False)
    stats["sales2020"] = stats.get("added", 0)


def step_purchases(uid: int, stats: dict):
    exp = FMYEExport(EXPORT_DIR)
    purch_h = exp.rows("PurchaseHeader")
    purch_d = exp.rows("PurchaseDetail")
    open_bal = _opening_map(exp.rows("OpeningBalances"), period_id=OPENING_PERIOD)
    lines_by = defaultdict(list)
    for ln in purch_d:
        lines_by[ln.get("PurchaseInvoiceCode", "")].append(ln)

    with db.get_connection() as conn:
        wh = conn.execute("SELECT id FROM warehouses ORDER BY id LIMIT 1").fetchone()[0]
        sup_ids = {r["code"]: r["id"] for r in conn.execute("SELECT id, code FROM suppliers")}
        prod_map = _prod_map(conn)
        existing = {r[0] for r in conn.execute("SELECT document_no FROM purchase_invoices")}

        for h in purch_h:
            if not _in_years(h.get("PurchaseInvoiceDate"), IMPORT_YEARS):
                stats["skipped_year"] += 1
                continue
            code = h.get("PurchaseInvoiceCode")
            doc = f"PI-{code}" if code else ""
            if not doc or doc in existing:
                continue
            pc = (h.get("PartyCode") or "").strip()
            sid = sup_ids.get(pc)
            if not sid and pc:
                ob = open_bal.get(pc, 0)
                cur = conn.execute(
                    """INSERT INTO suppliers(code, name, opening_balance, current_balance, created_by)
                       VALUES(?,?,?,?,?)""",
                    (pc, (h.get("Name") or pc).strip(), ob, ob, uid),
                )
                sid = cur.lastrowid
                sup_ids[pc] = sid
                stats["suppliers_added"] += 1
            if not sid:
                continue
            yr = _d(h.get("PurchaseInvoiceDate"))[:4]
            stats[f"purchases_{yr}"] += 1
            lines = lines_by.get(code, [])
            subtotal = sum(_f(ln.get("Amount")) for ln in lines) or _f(h.get("NetAmount"))
            total = _f(h.get("NetAmount")) or subtotal
            inv_status = ifs_status_from_fmye(h.get("Status"))
            cur = conn.execute(
                """INSERT INTO purchase_invoices(document_no, invoice_date, supplier_id, warehouse_id,
                   subtotal, discount, tax, total, paid_amount, payment_mode, notes, status,
                   weighbridge_required, created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (doc, _d(h.get("PurchaseInvoiceDate")), sid, wh, subtotal, _f(h.get("DiscountAmount")), 0, total, 0,
                 "credit", (h.get("Remarks") or "")[:500], inv_status, 0, uid),
            )
            inv_id = cur.lastrowid
            for ln in lines:
                ic = (ln.get("ItemCode") or "").strip().upper()
                pid = prod_map.get(ic)
                if not pid:
                    continue
                conn.execute(
                    """INSERT INTO purchase_invoice_items(invoice_id, product_id, quantity, rate, amount)
                       VALUES(?,?,?,?,?)""",
                    (inv_id, pid, _f(ln.get("Quantity")), _f(ln.get("PurchaseRate")), _f(ln.get("Amount"))),
                )
            existing.add(doc)
            stats["purchases"] += 1


def step_returns(uid: int, stats: dict):
    exp = FMYEExport(EXPORT_DIR)
    with db.get_connection() as conn:
        wh = conn.execute("SELECT id FROM warehouses ORDER BY id LIMIT 1").fetchone()[0]
        cust_ids = {r["code"]: r["id"] for r in conn.execute("SELECT id, code FROM customers")}
        sup_ids = {r["code"]: r["id"] for r in conn.execute("SELECT id, code FROM suppliers")}
        prod_map = _prod_map(conn)

        sr_lines = defaultdict(list)
        for r in exp.rows("SrDetail"):
            sr_lines[r.get("SrNo", "")].append(r)
        existing_sr = {r[0] for r in conn.execute("SELECT document_no FROM sales_returns")}

        for h in exp.rows("SrHeader"):
            if not _in_years(h.get("SrDate"), IMPORT_YEARS):
                continue
            doc = f"SR-{h.get('SrNo', '').strip()}"
            if doc in existing_sr:
                continue
            pc = (h.get("PartyCode") or "").strip()
            cid = cust_ids.get(pc)
            if not cid and pc:
                cur = conn.execute(
                    "INSERT INTO customers(code, name, opening_balance, current_balance, created_by) VALUES(?,?,0,0,?)",
                    (pc, (h.get("Name") or pc).strip(), uid),
                )
                cid = cur.lastrowid
                cust_ids[pc] = cid
            if not cid:
                continue
            total = _f(h.get("NetAmount"))
            cur = conn.execute(
                """INSERT INTO sales_returns(document_no, customer_id, return_date, warehouse_id,
                   subtotal, total, notes, created_by) VALUES(?,?,?,?,?,?,?,?)""",
                (doc, cid, _d(h.get("SrDate")), wh, total, total, (h.get("Remarks") or "")[:500], uid),
            )
            rid = cur.lastrowid
            for ln in sr_lines.get(h.get("SrNo", ""), []):
                ic = (ln.get("ItemCode") or "").strip().upper()
                pid = prod_map.get(ic)
                if pid:
                    conn.execute(
                        """INSERT INTO sales_return_items(return_id, product_id, quantity, rate, amount)
                           VALUES(?,?,?,?,?)""",
                        (rid, pid, _f(ln.get("Quantity")), _f(ln.get("SaleRate")),
                         _f(ln.get("NetAmount") or ln.get("Amount"))),
                    )
            stats["sales_returns"] += 1

        pr_lines = defaultdict(list)
        for r in exp.rows("PrDetail"):
            pr_lines[r.get("PrNo", "")].append(r)
        existing_pr = {r[0] for r in conn.execute("SELECT document_no FROM purchase_returns")}

        for h in exp.rows("PrHeader"):
            if not _in_years(h.get("PrDate"), IMPORT_YEARS):
                continue
            doc = f"PR-{h.get('PrNo', '').strip()}"
            if doc in existing_pr:
                continue
            pc = (h.get("PartyCode") or "").strip()
            sid = sup_ids.get(pc)
            if not sid and pc:
                cur = conn.execute(
                    "INSERT INTO suppliers(code, name, opening_balance, current_balance, created_by) VALUES(?,?,0,0,?)",
                    (pc, (h.get("Name") or pc).strip(), uid),
                )
                sid = cur.lastrowid
                sup_ids[pc] = sid
            if not sid:
                continue
            total = _f(h.get("NetAmount"))
            cur = conn.execute(
                """INSERT INTO purchase_returns(document_no, supplier_id, return_date, warehouse_id,
                   subtotal, total, notes, created_by) VALUES(?,?,?,?,?,?,?,?)""",
                (doc, sid, _d(h.get("PrDate")), wh, total, total, (h.get("Remarks") or "")[:500], uid),
            )
            rid = cur.lastrowid
            for ln in pr_lines.get(h.get("PrNo", ""), []):
                ic = (ln.get("ItemCode") or "").strip().upper()
                pid = prod_map.get(ic)
                if pid:
                    conn.execute(
                        """INSERT INTO purchase_return_items(return_id, product_id, quantity, rate, amount)
                           VALUES(?,?,?,?,?)""",
                        (rid, pid, _f(ln.get("Quantity")), _f(ln.get("PurchaseRate")),
                         _f(ln.get("NetAmount") or ln.get("Amount"))),
                    )
            stats["purchase_returns"] += 1


def step_vouchers(uid: int, stats: dict):
    exp = FMYEExport(EXPORT_DIR)
    chart_cats = {
        (r.get("AccountCode") or "").strip(): r.get("AccountCategory", "")
        for r in exp.rows("Chart")
    }
    with db.get_connection() as conn:
        cust_ids = {r["code"]: r["id"] for r in conn.execute("SELECT id, code FROM customers")}
        sup_ids = {r["code"]: r["id"] for r in conn.execute("SELECT id, code FROM suppliers")}
        _import_party_vouchers(
            conn, exp.rows("Voucher"), cust_ids, sup_ids, IMPORT_YEARS, uid, stats, chart_cats,
        )
    print(f"  Party vouchers limited to years {sorted(IMPORT_YEARS)}")


def step_inventory(uid: int, stats: dict):
    from sync_fmye_inventory import sync_inventory

    result = sync_inventory(uid, dry_run=False)
    stats.update(result)
    print(f"  Stock movements posted for {IMPORT_YEARS} transactions")


def step_bom(uid: int, stats: dict):
    from database import ensure_document_no

    exp = FMYEExport(EXPORT_DIR)
    comp_lines = defaultdict(list)
    for ln in exp.rows("CompositionDetail"):
        comp_lines[ln.get("CompCode", "")].append(ln)

    with db.get_connection() as conn:
        unit_id = conn.execute("SELECT id FROM units_of_measure ORDER BY id LIMIT 1").fetchone()[0]
        prod_map = _prod_map(conn)
        existing = {
            (r[0], r[1]) for r in conn.execute(
                "SELECT finished_product_id, version_no FROM bom_formulas"
            ).fetchall()
        }
        for h in exp.rows("CompositionHeader"):
            fg_code = (h.get("ItemCode") or "").strip().upper()
            fg_id = prod_map.get(fg_code)
            if not fg_id or (fg_id, "1.0") in existing:
                continue
            lines = []
            for ln in comp_lines.get(h.get("CompCode", ""), []):
                rc = (ln.get("ItemCode") or "").strip().upper()
                rid = prod_map.get(rc)
                if rid:
                    lines.append((rid, _f(ln.get("Quantity")), _f(ln.get("WastageRate"))))
            if not lines:
                continue
            doc_no = ensure_document_no("BOM", f"BOM-{h.get('CompCode', '')}", conn)
            cur = conn.execute(
                """INSERT INTO bom_formulas(document_no, finished_product_id, version_no,
                   standard_output_qty, output_unit_id, standard_cost, status, notes,
                   composition_type, composition_date, description, created_by, approved_by, approved_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (doc_no, fg_id, "1.0", 1, unit_id, 0, "approved",
                 f"FMYE {h.get('CompCode')}"[:500], "other", _d(h.get("CompDate")),
                 (h.get("CompDesc") or "")[:500], uid, uid, db._now()),
            )
            bom_id = cur.lastrowid
            for rid, qty, wastage in lines:
                conn.execute(
                    """INSERT INTO bom_formula_lines(bom_id, raw_product_id, quantity, unit_id,
                       weight_required, wastage_pct, standard_cost, line_cost)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (bom_id, rid, qty, unit_id, 0, wastage, 0, 0),
                )
            existing.add((fg_id, "1.0"))
            stats["bom"] += 1


def step_balances(uid: int, stats: dict):
    bal = db.recalculate_party_balances()
    stats["balances"] = bal
    with db.get_connection() as conn:
        n = conn.execute(
            """SELECT COUNT(*) FROM customers c
               JOIN (SELECT customer_id, SUM(total-paid_amount) s FROM sales_invoices
                     WHERE status='approved' GROUP BY customer_id) x ON x.customer_id=c.id
               WHERE ABS(c.current_balance) < 0.01 AND x.s > 1000"""
        ).fetchone()[0]
        stats["zero_balance_with_sales"] = n


STEP_FUNCS = {
    "masters": step_masters,
    "openings": step_openings,
    "stock": step_stock,
    "sales": step_sales,
    "sales2020": step_sales2020,
    "purchases": step_purchases,
    "returns": step_returns,
    "vouchers": step_vouchers,
    "inventory": step_inventory,
    "bom": step_bom,
    "balances": step_balances,
}


def run_step(name: str):
    if name not in STEP_FUNCS:
        raise SystemExit(f"Unknown step: {name}. Use --list")
    _require_export()
    uid = _uid()
    backup = _backup(f"before_step_{name}")
    if backup:
        print(f"Backup: {backup}")
    print(f"\n{'='*60}\nSTEP: {name}\n{'='*60}")
    desc = next(d for n, d in STEPS if n == name)
    print(f"  {desc}\n")
    stats = defaultdict(int)
    STEP_FUNCS[name](uid, stats)
    db.sync_document_sequences()
    print("  Result:", dict(stats))
    _print_counts()


def run_through(last_step: str):
    if last_step not in STEP_NAMES:
        raise SystemExit(f"Unknown step: {last_step}")
    idx = STEP_NAMES.index(last_step)
    for name in STEP_NAMES[: idx + 1]:
        run_step(name)


def run_phase_2026():
    """1 Jan 2026 opening + all 2026 transactions (Saturday go-live cutover)."""
    print("=" * 60)
    print("PHASE: 2026 cutover migration")
    print(f"  Opening balances: FMYE OpeningBalances[{OPENING_PERIOD}] (1 Jan 2026)")
    print(f"  Transactions:     year {sorted(IMPORT_YEARS)} only (from export)")
    print("=" * 60)
    for name in PHASE_2026_STEPS:
        run_step(name)
    print("\n2026 cutover migration complete.")


def run_phase_2024():
    """Alias for --phase 2024 (same as 2026 cutover)."""
    run_phase_2026()


def main():
    ap = argparse.ArgumentParser(description="FMYE step-by-step migration")
    ap.add_argument("--reset", action="store_true", help="Clear ERP to empty schema")
    ap.add_argument("--list", action="store_true", help="List migration steps")
    ap.add_argument("--step", metavar="NAME", help="Run one step")
    ap.add_argument("--through", metavar="NAME", help="Run steps from masters through NAME")
    ap.add_argument("--all", action="store_true", help="Run all steps (masters → balances)")
    ap.add_argument(
        "--phase",
        choices=["2024", "2026"],
        help="Run openings + 2026 transactions (Saturday cutover)",
    )
    args = ap.parse_args()

    if args.list:
        print("FMYE migration steps:\n")
        for i, (name, desc) in enumerate(STEPS, 1):
            print(f"  {i}. {name:12} — {desc}")
        print(f"\nSaturday go-live (2026 cutover):")
        print(f"  1. Fresh FMYE export into import\\fmye\\full\\")
        print(f"  2. python migrate_fmye.py --reset")
        print(f"  3. python migrate_fmye.py --step masters")
        print(f"  4. python migrate_fmye.py --phase 2026")
        print(f"  Or: run_cutover_import.bat")
        return 0

    if args.reset:
        b = reset_erp()
        if b:
            print(f"Backup: {b}")
        _print_counts()
        print("\nNext: python migrate_fmye.py --step masters")
        return 0

    if args.step:
        run_step(args.step)
        n = STEP_NAMES.index(args.step)
        if n + 1 < len(STEP_NAMES):
            print(f"\nNext: python migrate_fmye.py --step {STEP_NAMES[n + 1]}")
        else:
            print("\nMigration complete. Run: python -m streamlit run app.py")
        return 0

    if args.through:
        run_through(args.through)
        return 0

    if args.phase in ("2024", "2026"):
        run_phase_2026()
        return 0

    if args.all:
        run_through(STEP_NAMES[-1])
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
