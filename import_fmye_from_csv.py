"""
Import legacy FMYE / SQL Anywhere exports into IFS Chemicals ERP (SQLite).

FMYE11.db is SAP SQL Anywhere format — NOT readable by this ERP directly.
Export from the OLD PC / old ERP first, then run this script.

Required folder: import/fmye/csv/

Place these CSV files (UTF-8, header row):
  customers.csv       — code, name, phone, city, address, opening_balance, ntn
  suppliers.csv       — code, name, phone, city, address, opening_balance
  products.csv        — code, name, unit, purchase_price, sale_price, stock_qty, reorder_level
  sales_invoices.csv  — document_no, invoice_date, customer_code, subtotal, tax, total, paid_amount, status
  sales_lines.csv     — document_no, product_code, quantity, rate, amount
  purchase_invoices.csv — document_no, invoice_date, supplier_code, subtotal, tax, total, paid_amount, status
  purchase_lines.csv  — document_no, product_code, quantity, rate, amount

Optional (2023–2026 only — filter in export query):
  cash_book.csv, bank_book.csv, journal_vouchers.csv

Usage:
  python import_fmye_from_csv.py              # dry-run (preview counts)
  python import_fmye_from_csv.py --apply       # import into ifs_erp.db
  python import_fmye_from_csv.py --apply --years 2023,2024,2025,2026

Before --apply: backup ifs_erp.db (Administration → Backup or copy file).
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
CSV_DIR = ROOT / "import" / "fmye" / "csv"
BACKUP_DIR = ROOT / "import" / "fmye" / "backups"

import database as db


def _read_csv(name):
    path = CSV_DIR / name
    if not path.exists():
        return None
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _norm_row(row):
    return {k.strip().lower().replace(" ", "_"): (v or "").strip() for k, v in row.items() if k}


def _in_years(dt_str, years):
    if not years or not dt_str:
        return True
    try:
        y = int(str(dt_str)[:4])
        return y in years
    except ValueError:
        return True


def _ensure_fiscal_years(years, uid):
    for y in years:
        code = str(y)
        fd, td = f"{y}-01-01", f"{y}-12-31"
        existing = [f for f in db.get_fiscal_years() if f.get("fy_code") == code]
        if not existing:
            db.create_fiscal_year(code, fd, td, uid, make_active=False)
            print(f"  Fiscal year {code} created")
    active = str(max(years))
    for f in db.get_fiscal_years():
        if f.get("fy_code") == active:
            db.set_active_fiscal_year(f["id"], uid)
            print(f"  Active fiscal year: {active}")


def preview(years):
    print(f"CSV folder: {CSV_DIR}")
    if not CSV_DIR.exists():
        print("  (folder missing — create it and add export CSVs)")
        return
    for name in sorted(CSV_DIR.glob("*.csv")):
        rows = _read_csv(name.name) or []
        if years and "date" in name.name or "invoice" in name.name:
            rows = [r for r in rows if _in_years(_norm_row(r).get("invoice_date") or _norm_row(r).get("date"), years)]
        print(f"  {name.name}: {len(rows)} rows")


def apply_import(years, uid):
    if not CSV_DIR.exists():
        raise SystemExit(f"Create {CSV_DIR} and add CSV exports from FMYE first.")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = date.today().strftime("%Y%m%d")
    backup = BACKUP_DIR / f"ifs_erp_before_fmye_{stamp}.db"
    if db.DB_PATH.exists():
        shutil.copy2(db.DB_PATH, backup)
        print(f"Backup: {backup}")

    db.init_db()
    _ensure_fiscal_years(years or [2023, 2024, 2025, 2026], uid)

    cust_map, sup_map, prod_map = {}, {}, {}

    rows = _read_csv("customers.csv")
    if rows:
        for raw in rows:
            r = _norm_row(raw)
            code = r.get("code") or db.next_code("CUS", "customers")
            cid = db.add_customer({
                "code": code, "name": r.get("name", code),
                "phone": r.get("phone"), "city": r.get("city"), "address": r.get("address"),
                "ntn": r.get("ntn"), "opening_balance": float(r.get("opening_balance") or 0),
            }, uid)
            cust_map[code] = cid
        print(f"Customers: {len(cust_map)}")

    rows = _read_csv("suppliers.csv")
    if rows:
        for raw in rows:
            r = _norm_row(raw)
            code = r.get("code") or db.next_code("SUP", "suppliers")
            sid = db.add_supplier({
                "code": code, "name": r.get("name", code),
                "phone": r.get("phone"), "city": r.get("city"), "address": r.get("address"),
                "opening_balance": float(r.get("opening_balance") or 0),
            })
            sup_map[code] = sid
        print(f"Suppliers: {len(sup_map)}")

    rows = _read_csv("products.csv")
    if rows:
        cats = db.get_product_categories()
        units = db.get_units_of_measure()
        cat_id = cats[0]["id"] if cats else None
        unit_id = units[0]["id"] if units else None
        tax_rows = db.get_tax_rates()
        tax_id = tax_rows[0]["id"] if tax_rows else None
        for raw in rows:
            r = _norm_row(raw)
            code = r.get("code") or db.next_code("PRD", "products")
            pid = db.add_item({
                "code": code, "name": r.get("name", code),
                "category_id": cat_id, "unit_id": unit_id, "tax_rate_id": tax_id,
                "purchase_price": float(r.get("purchase_price") or 0),
                "sale_price": float(r.get("sale_price") or 0),
                "reorder_level": float(r.get("reorder_level") or 0),
                "stock_qty": float(r.get("stock_qty") or 0),
            }, uid)
            prod_map[code] = pid
        print(f"Products: {len(prod_map)}")

    si_rows = _read_csv("sales_invoices.csv") or []
    sl_rows = _read_csv("sales_lines.csv") or []
    lines_by_doc = {}
    for raw in sl_rows:
        r = _norm_row(raw)
        lines_by_doc.setdefault(r.get("document_no", ""), []).append(r)

    imported_sales = 0
    for raw in si_rows:
        r = _norm_row(raw)
        if not _in_years(r.get("invoice_date"), years):
            continue
        cc = r.get("customer_code")
        if cc not in cust_map:
            print(f"  Skip sale {r.get('document_no')}: unknown customer {cc}")
            continue
        doc = r.get("document_no")
        line_items = []
        for ln in lines_by_doc.get(doc, []):
            pc = ln.get("product_code")
            if pc not in prod_map:
                continue
            line_items.append({
                "product_id": prod_map[pc],
                "quantity": float(ln.get("quantity") or 0),
                "rate": float(ln.get("rate") or 0),
                "amount": float(ln.get("amount") or 0),
            })
        if not line_items:
            continue
        db.save_sale({
            "document_no": doc,
            "customer_id": cust_map[cc],
            "invoice_date": r.get("invoice_date"),
            "subtotal": float(r.get("subtotal") or 0),
            "tax": float(r.get("tax") or 0),
            "total": float(r.get("total") or 0),
            "paid_amount": float(r.get("paid_amount") or 0),
            "status": r.get("status") or "approved",
        }, line_items, user_id=uid)
        imported_sales += 1
    print(f"Sales invoices: {imported_sales}")

    pi_rows = _read_csv("purchase_invoices.csv") or []
    pl_rows = _read_csv("purchase_lines.csv") or []
    pl_by_doc = {}
    for raw in pl_rows:
        r = _norm_row(raw)
        pl_by_doc.setdefault(r.get("document_no", ""), []).append(r)

    imported_purch = 0
    for raw in pi_rows:
        r = _norm_row(raw)
        if not _in_years(r.get("invoice_date"), years):
            continue
        sc = r.get("supplier_code")
        if sc not in sup_map:
            print(f"  Skip purchase {r.get('document_no')}: unknown supplier {sc}")
            continue
        doc = r.get("document_no")
        line_items = []
        for ln in pl_by_doc.get(doc, []):
            pc = ln.get("product_code")
            if pc not in prod_map:
                continue
            line_items.append({
                "product_id": prod_map[pc],
                "quantity": float(ln.get("quantity") or 0),
                "rate": float(ln.get("rate") or 0),
                "amount": float(ln.get("amount") or 0),
            })
        if not line_items:
            continue
        db.save_purchase({
            "document_no": doc,
            "supplier_id": sup_map[sc],
            "invoice_date": r.get("invoice_date"),
            "subtotal": float(r.get("subtotal") or 0),
            "tax": float(r.get("tax") or 0),
            "total": float(r.get("total") or 0),
            "paid_amount": float(r.get("paid_amount") or 0),
            "status": r.get("status") or "approved",
        }, line_items, user_id=uid)
        imported_purch += 1
    print(f"Purchase invoices: {imported_purch}")

    db.sync_document_sequences()
    print("Done. Restart Streamlit and verify Trial Balance / party ledgers.")


def main():
    ap = argparse.ArgumentParser(description="Import FMYE CSV exports into IFS ERP")
    ap.add_argument("--apply", action="store_true", help="Write to ifs_erp.db (default: preview only)")
    ap.add_argument("--years", default="2023,2024,2025,2026", help="Comma-separated years to import")
    args = ap.parse_args()
    years = [int(y.strip()) for y in args.years.split(",") if y.strip()]

    print("=" * 60)
    print("FMYE -> IFS Chemicals ERP import")
    print("=" * 60)
    legacy = ROOT / "import" / "fmye" / "FMYE11.db"
    if legacy.exists():
        print(f"Legacy DB on file: {legacy} ({legacy.stat().st_size // (1024*1024)} MB)")
        print("  Format: SQL Anywhere — export CSV from old ERP, then run this script.")
    else:
        print("Legacy FMYE11.db not found in import/fmye/")

    if args.apply:
        user = db.authenticate("admin", "admin123")
        if not user:
            raise SystemExit("Login failed — ensure admin user exists.")
        apply_import(years, user["id"])
    else:
        print("\nPreview (dry run):")
        preview(years)
        print("\nTo import: python import_fmye_from_csv.py --apply")


if __name__ == "__main__":
    main()
