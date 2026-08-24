"""
Import FMYE SQL Anywhere dbunload export (reload.sql + *.dat) into IFS ERP.

Export folder: import/fmye/full/

Usage:
  python import_fmye_from_dat.py                 # preview counts
  python import_fmye_from_dat.py --apply         # import (backs up ifs_erp.db)
  python import_fmye_from_dat.py --apply --with-gl   # include voucher GL lines
  python import_fmye_from_dat.py --apply --years 2024,2025,2026
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import shutil
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
EXPORT_DIR = ROOT / "import" / "fmye" / "full"
BACKUP_DIR = ROOT / "import" / "fmye" / "backups"

def _db():
    """Lazy import — avoids circular import while database.py is still loading."""
    import database as db
    return db


GROUP_MAP = {"A": "asset", "L": "liability", "E": "expense", "R": "income", "C": "equity"}
ITEM_TYPE_MAP = {"F": "finished", "R": "raw", "P": "packaging"}


def ifs_status_from_fmye(flag) -> str:
    """FMYE Status/Approved: '1' = posted → approved; '0' / blank = under authorization."""
    return "approved" if str(flag or "").strip() == "1" else "pending_approval"


class FMYEExport:
    def __init__(self, export_dir: Path):
        self.export_dir = export_dir
        self.reload_sql = (export_dir / "reload.sql").read_text(encoding="utf-8", errors="replace")
        self._maps: dict[str, dict] = {}

    def table_map(self) -> dict[str, dict]:
        if self._maps:
            return self._maps
        # Old export: FROM './704.dat'
        # Live dbunload: FROM 'C:/MY ERPS/import/fmye/full_live/704.dat'
        pat = re.compile(
            r'LOAD TABLE "saller"\."([^"]+)" \(([^)]+)\)\s+FROM \'([^\']*?(\d+)\.dat)\'',
            re.MULTILINE,
        )
        for name, cols_raw, _full, num in pat.findall(self.reload_sql):
            self._maps[name] = {
                "columns": [c.strip('"') for c in cols_raw.split(",")],
                "dat": self.export_dir / f"{num}.dat",
            }
        return self._maps

    def rows(self, table: str) -> list[dict]:
        info = self.table_map().get(table)
        if not info:
            return []
        path = info["dat"]
        cols = info["columns"]
        if not path.exists() or path.stat().st_size == 0:
            return []
        out = []
        with path.open(encoding="windows-1252", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n\r")
                if not line:
                    continue
                reader = csv.reader(io.StringIO(line), delimiter=",", quotechar="'")
                out.append(dict(zip(cols, next(reader))))
        return out


def _f(val, default=0.0) -> float:
    if val is None or val == "":
        return default
    try:
        return float(str(val).replace(",", ""))
    except ValueError:
        return default


def _d(val) -> str:
    if not val:
        return date.today().isoformat()
    s = str(val).strip()
    return s[:10] if len(s) >= 10 else s


def _year(val) -> int | None:
    try:
        return int(str(val)[:4])
    except (TypeError, ValueError):
        return None


def _in_years(val, years: set[int] | None) -> bool:
    if not years:
        return True
    y = _year(val)
    return y in years if y else False


def _ensure_units(conn, items: list[dict], uid: int) -> dict[str, int]:
    cache: dict[str, int] = {}
    for row in conn.execute("SELECT id, symbol FROM units_of_measure").fetchall():
        cache[row["symbol"].upper()] = row["id"]
    for sym in sorted({(r.get("MeasuringUnit") or "PCS").strip().upper() for r in items}):
        if sym in cache:
            continue
        code = sym[:10]
        cur = conn.execute(
            "INSERT INTO units_of_measure(code, name, symbol, created_by) VALUES(?,?,?,?)",
            (code, sym, sym, uid),
        )
        cache[sym] = cur.lastrowid
    return cache


def _group_id(conn, group_type: str) -> int:
    row = conn.execute(
        "SELECT id FROM account_groups WHERE group_type=? ORDER BY id LIMIT 1", (group_type,)
    ).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO account_groups(code, name, group_type, created_by) VALUES(?,?,?,?)",
        (group_type.upper()[:3], group_type.title(), group_type, 1),
    )
    return cur.lastrowid


def _opening_map(rows: list[dict], years: set[int] | None = None, *, period_id: str | None = None) -> dict[str, float]:
    """FMYE OpeningBalances PeriodID = fiscal year opening (2024 = 2023 closing brought forward)."""
    period = period_id or (str(max(years)) if years else "2026")
    if not any(r.get("PeriodID") == period for r in rows):
        period = max((r.get("PeriodID") or "0") for r in rows)
    out: dict[str, float] = {}
    for r in rows:
        if r.get("PeriodID") != period:
            continue
        code = r.get("AccountCode", "")
        out[code] = _f(r.get("OpeningDr")) - _f(r.get("OpeningCr"))
    return out


def _resolve_party_for_voucher(code, vt, doc_name, cust_ids, sup_ids, chart_cats):
    """Route voucher lines to customer or supplier ledger (FMYE uses same code for both roles)."""
    doc = (doc_name or "").strip().upper()
    vt = (vt or "").strip().upper()
    if vt == "JVR" and doc in {"SL", "PU", "SR", "PR"}:
        return None

    in_c = code in cust_ids
    in_s = code in sup_ids
    if not in_c and not in_s:
        return None

    prefer_sup = doc in {"PU", "PR"} or vt in {"BPV", "CPV", "BP", "CP"}
    prefer_cust = doc in {"SL", "SR"} or vt in {"CRV", "BRV", "CR", "BR"}

    if prefer_sup and in_s:
        return "supplier", sup_ids[code]
    if prefer_cust and in_c:
        return "customer", cust_ids[code]
    if in_s and not in_c:
        return "supplier", sup_ids[code]
    if in_c and not in_s:
        return "customer", cust_ids[code]

    cat = chart_cats.get(code, "")
    if in_c and in_s:
        debit_side = vt in {"BPV", "CPV", "BP", "CP"} or cat == "V"
        if prefer_sup or debit_side:
            return "supplier", sup_ids[code]
        return "customer", cust_ids[code]
    return None


def preview(years: set[int] | None):
    exp = FMYEExport(EXPORT_DIR)
    if not EXPORT_DIR.exists():
        print(f"Missing export folder: {EXPORT_DIR}")
        return
    chart = exp.rows("Chart")
    items = exp.rows("ItemInformation")
    sales = [r for r in exp.rows("SaleInvoiceHeader") if _in_years(r.get("InvoiceDate"), years)]
    purch = [r for r in exp.rows("PurchaseHeader") if _in_years(r.get("PurchaseInvoiceDate"), years)]
    vlines = [r for r in exp.rows("Voucher") if _in_years(r.get("VoucherDate"), years)]
    yr_label = "all years" if not years else f"{min(years)}-{max(years)}"
    print(f"Export folder: {EXPORT_DIR}")
    print(f"  Chart accounts:        {len(chart)}")
    print(f"  Customers (S):         {sum(1 for r in chart if r.get('AccountCategory') == 'S')}")
    print(f"  Suppliers (V):       {sum(1 for r in chart if r.get('AccountCategory') == 'V')}")
    print(f"  Products:              {len(items)}")
    print(f"  Sales invoices ({yr_label}): {len(sales)}")
    print(f"  Purchase invoices:     {len(purch)}")
    print(f"  Voucher GL lines:      {len(vlines)}")
    if not years or min(years) > 2020:
        print("  Note: FMYE export sales data is only 2024-2026 in this backup.")


def _import_party_vouchers(conn, vouchers, cust_ids, sup_ids, years, uid, stats, chart_cats=None):
    """Import cash/bank/JV lines on customer & supplier accounts for ledger balances."""
    _db()._ensure_fmye_party_entries_table(conn)
    conn.execute("DELETE FROM fmye_party_entries")
    chart_cats = chart_cats or {}
    batch = []
    for v in vouchers:
        if not _in_years(v.get("VoucherDate"), years):
            continue
        code = (v.get("AccountCode") or "").strip()
        vt = (v.get("VoucherType") or "").strip().upper()
        doc_name = (v.get("DocumentName") or "").strip().upper()
        resolved = _resolve_party_for_voucher(code, vt, doc_name, cust_ids, sup_ids, chart_cats)
        if not resolved:
            if vt == "JVR" and doc_name in {"SL", "PU", "SR", "PR"}:
                stats["party_voucher_skipped"] += 1
            continue
        party_type, party_id = resolved
        debit = _f(v.get("Debit"))
        credit = _f(v.get("Credit"))
        if debit <= 0 and credit <= 0:
            continue
        ref = f"{vt}-{v.get('TransactionNO', '')}"
        narr = (v.get("Narration") or vt or "Voucher").strip()[:500]
        batch.append((
            party_type, party_id, _d(v.get("VoucherDate")), ref, narr,
            debit, credit, vt,
        ))
        if len(batch) >= 3000:
            conn.executemany(
                """INSERT INTO fmye_party_entries(party_type, party_id, entry_date, document_no,
                   description, debit, credit, voucher_type, created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                [(b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7], _db()._now()) for b in batch],
            )
            stats["party_voucher_lines"] += len(batch)
            batch.clear()
    if batch:
        conn.executemany(
            """INSERT INTO fmye_party_entries(party_type, party_id, entry_date, document_no,
               description, debit, credit, voucher_type, created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
            [(b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7], _db()._now()) for b in batch],
        )
        stats["party_voucher_lines"] += len(batch)


def apply_import(years: set[int] | None, uid: int, with_gl: bool = False, with_party_vouchers: bool = True):
    if not EXPORT_DIR.exists():
        raise SystemExit(f"Export folder not found: {EXPORT_DIR}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = date.today().strftime("%Y%m%d_%H%M")
    backup = BACKUP_DIR / f"ifs_erp_before_fmye_dat_{stamp}.db"
    if _db().DB_PATH.exists():
        shutil.copy2(_db().DB_PATH, backup)
        print(f"Backup: {backup}")

    _db().init_db()
    exp = FMYEExport(EXPORT_DIR)
    chart = exp.rows("Chart")
    items = exp.rows("ItemInformation")
    sales_h = exp.rows("SaleInvoiceHeader")
    sales_d = exp.rows("SaleInvoiceDetail")
    purch_h = exp.rows("PurchaseHeader")
    purch_d = exp.rows("PurchaseDetail")
    openings = exp.rows("OpeningBalances")
    vouchers = exp.rows("Voucher")

    open_bal = _opening_map(openings, years)
    sales_lines = defaultdict(list)
    for r in sales_d:
        sales_lines[r.get("SaleInvoiceCode", "")].append(r)
    purch_lines = defaultdict(list)
    for r in purch_d:
        purch_lines[r.get("PurchaseInvoiceCode", "")].append(r)

    stats = defaultdict(int)

    with _db().get_connection() as conn:
        wh = conn.execute("SELECT id FROM warehouses ORDER BY id LIMIT 1").fetchone()[0]
        cat_id = conn.execute("SELECT id FROM product_categories ORDER BY id LIMIT 1").fetchone()[0]
        unit_cache = _ensure_units(conn, items, uid)

        # --- Chart of accounts ---
        acct_ids: dict[str, int] = {}
        existing_accts = {r["code"]: r["id"] for r in conn.execute("SELECT id, code FROM chart_of_accounts")}
        for r in chart:
            code = (r.get("AccountCode") or "").strip()
            if not code:
                continue
            gtype = GROUP_MAP.get(r.get("AccountType", "A"), "asset")
            gid = _group_id(conn, gtype)
            ob = open_bal.get(code, _f(r.get("OpeningDr")) - _f(r.get("OpeningCr")))
            name = (r.get("AccountName") or code).strip()
            active = 1 if r.get("Active", "1") in ("1", 1, "Y") else 0
            if code in existing_accts:
                conn.execute(
                    """UPDATE chart_of_accounts SET name=?, opening_balance=?, current_balance=?,
                       is_active=?, modified_by=?, modified_at=? WHERE id=?""",
                    (name, ob, ob, active, uid, _db()._now(), existing_accts[code]),
                )
                acct_ids[code] = existing_accts[code]
                stats["accounts_updated"] += 1
            else:
                cur = conn.execute(
                    """INSERT INTO chart_of_accounts(code, name, account_group_id, opening_balance,
                       current_balance, is_active, created_by) VALUES(?,?,?,?,?,?,?)""",
                    (code, name, gid, ob, ob, active, uid),
                )
                acct_ids[code] = cur.lastrowid
                stats["accounts_added"] += 1

        # --- Customers (Chart category S) ---
        cust_ids: dict[str, int] = {}
        existing_cust = {r["code"]: r["id"] for r in conn.execute("SELECT id, code FROM customers")}
        for r in chart:
            if r.get("AccountCategory") != "S":
                continue
            code = (r.get("AccountCode") or "").strip()
            if not code:
                continue
            name = (r.get("AccountName") or code).strip()
            ob = open_bal.get(code, _f(r.get("OpeningDr")) - _f(r.get("OpeningCr")))
            phone = r.get("Phone") or r.get("MobileNo") or ""
            payload = (
                name, phone, r.get("Email") or "", r.get("Address") or "", r.get("City") or "",
                r.get("SaleTaxNo") or "", ob, ob,
            )
            if code in existing_cust:
                conn.execute(
                    """UPDATE customers SET name=?, phone=?, email=?, address=?, city=?, ntn=?,
                       opening_balance=?, current_balance=?, modified_by=?, modified_at=? WHERE id=?""",
                    (*payload, uid, _db()._now(), existing_cust[code]),
                )
                cust_ids[code] = existing_cust[code]
                stats["customers_updated"] += 1
            else:
                cur = conn.execute(
                    """INSERT INTO customers(code, name, phone, email, address, city, ntn,
                       opening_balance, current_balance, created_by) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (code, *payload, uid),
                )
                cust_ids[code] = cur.lastrowid
                stats["customers_added"] += 1

        # --- Suppliers (Chart category V) ---
        sup_ids: dict[str, int] = {}
        existing_sup = {r["code"]: r["id"] for r in conn.execute("SELECT id, code FROM suppliers")}
        for r in chart:
            if r.get("AccountCategory") != "V":
                continue
            code = (r.get("AccountCode") or "").strip()
            if not code:
                continue
            name = (r.get("AccountName") or code).strip()
            ob = open_bal.get(code, _f(r.get("OpeningDr")) - _f(r.get("OpeningCr")))
            phone = r.get("Phone") or r.get("MobileNo") or ""
            payload = (
                name, phone, r.get("Email") or "", r.get("Address") or "", r.get("City") or "",
                ob, ob,
            )
            if code in existing_sup:
                conn.execute(
                    """UPDATE suppliers SET name=?, phone=?, email=?, address=?, city=?,
                       opening_balance=?, current_balance=?, modified_by=?, modified_at=? WHERE id=?""",
                    (*payload, uid, _db()._now(), existing_sup[code]),
                )
                sup_ids[code] = existing_sup[code]
                stats["suppliers_updated"] += 1
            else:
                cur = conn.execute(
                    """INSERT INTO suppliers(code, name, phone, email, address, city,
                       opening_balance, current_balance, created_by) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (code, *payload, uid),
                )
                sup_ids[code] = cur.lastrowid
                stats["suppliers_added"] += 1

        # --- Products ---
        prod_ids: dict[str, int] = {}
        existing_prod = {r["code"]: r["id"] for r in conn.execute("SELECT id, code FROM products")}
        for r in items:
            code = (r.get("ItemCode") or "").strip()
            if not code:
                continue
            sym = (r.get("MeasuringUnit") or "PCS").strip().upper()
            unit_id = unit_cache.get(sym) or next(iter(unit_cache.values()))
            ptype = ITEM_TYPE_MAP.get(r.get("ItemType", "F"), "finished")
            sale_p = _f(r.get("SaleRate"))
            purch_p = _f(r.get("PurchaseRate"))
            stock = _f(r.get("OpeningStock"))
            active = 1 if r.get("Status", "1") in ("1", 1) else 0
            name = (r.get("ItemName") or code).strip()
            if code in existing_prod:
                conn.execute(
                    """UPDATE products SET name=?, unit_id=?, product_type=?, purchase_price=?,
                       sale_price=?, is_active=?, modified_by=?, modified_at=? WHERE id=?""",
                    (name, unit_id, ptype, purch_p, sale_p, active, uid, _db()._now(), existing_prod[code]),
                )
                pid = existing_prod[code]
                stats["products_updated"] += 1
            else:
                cur = conn.execute(
                    """INSERT INTO products(code, name, category_id, unit_id, product_type,
                       purchase_price, sale_price, created_by) VALUES(?,?,?,?,?,?,?,?)""",
                    (code, name, cat_id, unit_id, ptype, purch_p, sale_p, uid),
                )
                pid = cur.lastrowid
                stats["products_added"] += 1
            prod_ids[code] = pid
            conn.execute(
                """INSERT INTO warehouse_stock(warehouse_id, product_id, quantity, modified_at)
                   VALUES(?,?,?,?) ON CONFLICT(warehouse_id, product_id)
                   DO UPDATE SET quantity=excluded.quantity, modified_at=excluded.modified_at""",
                (wh, pid, stock, _db()._now()),
            )

        existing_sale_docs = {
            r[0] for r in conn.execute("SELECT document_no FROM sales_invoices").fetchall()
        }
        existing_purch_docs = {
            r[0] for r in conn.execute("SELECT document_no FROM purchase_invoices").fetchall()
        }

        # --- Sales invoices ---
        for h in sales_h:
            if not _in_years(h.get("InvoiceDate"), years):
                continue
            doc = (h.get("DocumentNo") or h.get("SaleInvoiceCode") or "").strip()
            if not doc or doc in existing_sale_docs:
                stats["sales_skipped"] += 1
                continue
            pc = (h.get("PartyCode") or "").strip()
            cid = cust_ids.get(pc)
            if not cid and pc:
                row = conn.execute("SELECT id FROM customers WHERE code=?", (pc,)).fetchone()
                if row:
                    cid = row[0]
                    cust_ids[pc] = cid
            if not cid:
                cname = (h.get("Name") or pc or "Unknown").strip()
                cc = pc or _db().next_code("CUS", "customers")
                cur = conn.execute(
                    """INSERT INTO customers(code, name, opening_balance, current_balance, created_by)
                       VALUES(?,?,0,0,?)""",
                    (cc, cname, uid),
                )
                cid = cur.lastrowid
                cust_ids[cc] = cid
                stats["customers_added"] += 1
            lines = sales_lines.get(h.get("SaleInvoiceCode", ""), [])
            subtotal = sum(_f(ln.get("TotalAmount") or ln.get("Amount")) for ln in lines) or _f(h.get("NetAmount"))
            total = _f(h.get("NetAmount")) or subtotal
            inv_date = _d(h.get("InvoiceDate"))
            notes = " | ".join(x for x in [h.get("Remarks"), h.get("Despatch")] if x)
            inv_status = ifs_status_from_fmye(h.get("Status"))
            cur = conn.execute(
                """INSERT INTO sales_invoices(document_no, invoice_date, customer_id, warehouse_id,
                   subtotal, discount, tax, total, paid_amount, payment_mode, notes, status,
                   weighbridge_required, created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    doc, inv_date, cid, wh, subtotal, _f(h.get("DiscountAmount")), 0, total, 0,
                    "credit", notes, inv_status, 0, uid,
                ),
            )
            inv_id = cur.lastrowid
            for ln in lines:
                ic = (ln.get("ItemCode") or "").strip()
                pid = prod_ids.get(ic)
                if not pid:
                    stats["sale_lines_skipped"] += 1
                    continue
                qty = _f(ln.get("Quantity"))
                rate = _f(ln.get("SaleRate"))
                amt = _f(ln.get("TotalAmount") or ln.get("Amount"))
                conn.execute(
                    """INSERT INTO sales_invoice_items(invoice_id, product_id, quantity, rate, amount)
                       VALUES(?,?,?,?,?)""",
                    (inv_id, pid, qty, rate, amt),
                )
            existing_sale_docs.add(doc)
            stats["sales_added"] += 1

        # --- Purchase invoices ---
        for h in purch_h:
            if not _in_years(h.get("PurchaseInvoiceDate"), years):
                continue
            doc = (h.get("PurchaseInvoiceCode") or h.get("DocumentNo") or "").strip()
            if doc and not str(doc).upper().startswith("PI"):
                doc = f"PI-{doc}"
            if not doc or doc in existing_purch_docs:
                stats["purchases_skipped"] += 1
                continue
            pc = (h.get("PartyCode") or "").strip()
            sid = sup_ids.get(pc)
            if not sid and pc:
                row = conn.execute("SELECT id FROM suppliers WHERE code=?", (pc,)).fetchone()
                if row:
                    sid = row[0]
                    sup_ids[pc] = sid
            if not sid:
                sname = (h.get("Name") or pc or "Unknown").strip()
                sc = pc or _db().next_code("SUP", "suppliers")
                cur = conn.execute(
                    """INSERT INTO suppliers(code, name, opening_balance, current_balance, created_by)
                       VALUES(?,?,0,0,?)""",
                    (sc, sname, uid),
                )
                sid = cur.lastrowid
                sup_ids[sc] = sid
                stats["suppliers_added"] += 1
            lines = purch_lines.get(h.get("PurchaseInvoiceCode", ""), [])
            subtotal = sum(_f(ln.get("Amount")) for ln in lines) or _f(h.get("NetAmount"))
            total = _f(h.get("NetAmount")) or subtotal
            inv_date = _d(h.get("PurchaseInvoiceDate"))
            notes = " | ".join(x for x in [h.get("Remarks"), h.get("Despatch")] if x)
            inv_status = ifs_status_from_fmye(h.get("Status"))
            cur = conn.execute(
                """INSERT INTO purchase_invoices(document_no, invoice_date, supplier_id, warehouse_id,
                   subtotal, discount, tax, total, paid_amount, payment_mode, notes, status,
                   weighbridge_required, created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    doc, inv_date, sid, wh, subtotal, _f(h.get("DiscountAmount")), 0, total, 0,
                    "credit", notes, inv_status, 0, uid,
                ),
            )
            inv_id = cur.lastrowid
            for ln in lines:
                ic = (ln.get("ItemCode") or "").strip()
                pid = prod_ids.get(ic)
                if not pid:
                    stats["purchase_lines_skipped"] += 1
                    continue
                qty = _f(ln.get("Quantity"))
                rate = _f(ln.get("PurchaseRate"))
                amt = _f(ln.get("Amount"))
                conn.execute(
                    """INSERT INTO purchase_invoice_items(invoice_id, product_id, quantity, rate, amount)
                       VALUES(?,?,?,?,?)""",
                    (inv_id, pid, qty, rate, amt),
                )
            existing_purch_docs.add(doc)
            stats["purchases_added"] += 1

        # --- General ledger from vouchers (optional) ---
        if with_gl:
            conn.execute("DELETE FROM general_ledger WHERE reference_type='fmye_voucher'")
            batch = []
            for v in vouchers:
                if not _in_years(v.get("VoucherDate"), years):
                    continue
                acode = (v.get("AccountCode") or "").strip()
                aid = acct_ids.get(acode)
                if not aid:
                    continue
                ref = f"{v.get('VoucherType','')}-{v.get('TransactionNO','')}"
                batch.append((
                    _d(v.get("VoucherDate")),
                    aid,
                    _f(v.get("Debit")),
                    _f(v.get("Credit")),
                    (v.get("Narration") or "")[:500],
                    "fmye_voucher",
                    0,
                    ref,
                    uid,
                ))
                if len(batch) >= 2000:
                    conn.executemany(
                        """INSERT INTO general_ledger(entry_date, account_id, debit, credit,
                           description, reference_type, reference_id, reference_no, created_by)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                        batch,
                    )
                    stats["gl_lines"] += len(batch)
                    batch.clear()
            if batch:
                conn.executemany(
                    """INSERT INTO general_ledger(entry_date, account_id, debit, credit,
                       description, reference_type, reference_id, reference_no, created_by)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    batch,
                )
                stats["gl_lines"] += len(batch)

        # --- Fiscal years ---
        for fy in sorted(years or {2020, 2021, 2022, 2023, 2024, 2025, 2026}):
            code = str(fy)
            if conn.execute("SELECT 1 FROM fiscal_years WHERE fy_code=?", (code,)).fetchone():
                continue
            _db().create_fiscal_year(code, f"{fy}-01-01", f"{fy}-12-31", uid, make_active=False)

        if with_party_vouchers:
            print("Importing party voucher entries (receipts/payments/JV)...")
            chart_cats = {
                (r.get("AccountCode") or "").strip(): r.get("AccountCategory", "")
                for r in chart
            }
            _import_party_vouchers(conn, vouchers, cust_ids, sup_ids, years, uid, stats, chart_cats)

    print("Recalculating customer/supplier balances from ledger...")
    bal = _db().recalculate_party_balances()
    stats["balances_customers"] = bal["customers"]
    stats["balances_suppliers"] = bal["suppliers"]

    _db().sync_document_sequences()
    print("\nImport complete:")
    for k in sorted(stats):
        print(f"  {k}: {stats[k]}")
    print("\nRestart Streamlit and verify Trial Balance / sample invoices.")


def main():
    ap = argparse.ArgumentParser(description="Import FMYE dbunload export into IFS ERP")
    ap.add_argument("--apply", action="store_true", help="Write to ifs_erp.db")
    ap.add_argument("--with-gl", action="store_true", help="Import voucher lines into general_ledger")
    ap.add_argument("--all-years", action="store_true", help="Import all years (no date filter)")
    ap.add_argument("--years", default="2023,2024,2025,2026", help="Years to import")
    ap.add_argument("--no-party-vouchers", action="store_true", help="Skip FMYE receipt/payment voucher import")
    args = ap.parse_args()
    years = None if args.all_years else {int(y.strip()) for y in args.years.split(",") if y.strip()}

    print("=" * 60)
    print("FMYE dat export -> IFS Chemicals ERP")
    print("=" * 60)

    if args.apply:
        user = _db().authenticate("admin", "admin123")
        if not user:
            raise SystemExit("Login failed — ensure admin user exists.")
        apply_import(years, user["id"], with_gl=args.with_gl, with_party_vouchers=not args.no_party_vouchers)
    else:
        preview(years)
        print("\nTo import all years: python import_fmye_from_dat.py --apply --all-years")
        print("With GL:             python import_fmye_from_dat.py --apply --all-years --with-gl")


if __name__ == "__main__":
    main()
