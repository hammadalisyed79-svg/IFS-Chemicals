"""
Import 2020-2023 sales from FMYE Voucher SL entries.

FMYE only has SaleInvoiceHeader from 2024+. Older sales are posted as
Voucher rows with DocumentName = 'SL' (cash and credit sales).

Usage:
  python import_fmye_sl_sales.py              # preview
  python import_fmye_sl_sales.py --apply
"""

from __future__ import annotations

import argparse
import re
import shutil
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
EXPORT_DIR = ROOT / "import" / "fmye" / "full"
BACKUP_DIR = ROOT / "import" / "fmye" / "backups"
CASH_CUSTOMER_CODE = "100013"  # SALE IN CASH in FMYE

import database as db
from import_fmye_from_dat import FMYEExport, _d, _f


def _sl_groups(vouchers):
    groups = defaultdict(list)
    for v in vouchers:
        if (v.get("DocumentName") or "").upper() == "SL":
            groups[v["TransactionNO"]].append(v)
    return groups


def _parse_doc_no(lines):
    narr = (lines[0].get("Narration") or "") + " " + (lines[1].get("Narration") if len(lines) > 1 else "")
    m = re.search(r"Invoice No\s*(\d+)", narr, re.I)
    if m:
        return m.group(1)
    doc = (lines[0].get("Documentno") or "").strip()
    if doc:
        return doc
    return f"SL-{lines[0].get('TransactionNO', '')}"


def _resolve_party_and_total(lines, chart, cust_codes):
    lines = sorted(lines, key=lambda x: int(x.get("SeqNo") or 0))
    for ln in lines:
        ac = (ln.get("AccountCode") or "").strip()
        dr = _f(ln.get("Debit"))
        if dr <= 0:
            continue
        if ac in cust_codes:
            return ac, dr, "credit"
        if ac == "000000":
            return CASH_CUSTOMER_CODE, dr, "cash"
    for ln in lines:
        ac = (ln.get("AccountCode") or "").strip()
        dr = _f(ln.get("Debit"))
        if dr > 0 and ac in chart:
            return ac, dr, "other"
    sales_cr = sum(_f(ln.get("Credit")) for ln in lines if (ln.get("AccountCode") or "").startswith("500"))
    if sales_cr > 0:
        return CASH_CUSTOMER_CODE, sales_cr, "cash"
    # Zero-amount SL voucher — party on customer line, total 0
    for ln in lines:
        ac = (ln.get("AccountCode") or "").strip()
        if ac in cust_codes:
            return ac, 0, "credit"
    return None, 0, ""


def preview():
    exp = FMYEExport(EXPORT_DIR)
    chart_rows = exp.rows("Chart")
    chart = {r["AccountCode"]: r for r in chart_rows}
    cust_codes = {c for c, r in chart.items() if r.get("AccountCategory") == "S"}
    groups = _sl_groups(exp.rows("Voucher"))

    by_year = defaultdict(int)
    for txn, lines in groups.items():
        yr = (lines[0].get("VoucherDate") or "")[:4]
        if yr in ("2020", "2021", "2022", "2023"):
            by_year[yr] += 1

    print("FMYE SL sales vouchers (2020-2023):", dict(sorted(by_year.items())), "total", sum(by_year.values()))
    print("SaleInvoiceHeader in export starts 2024 only — these SL vouchers are the missing sales.")


def apply(uid: int, stats=None, recalc_balances: bool = False):
    """Import 2020-2023 SL voucher sales. Optional shared stats dict."""
    if stats is None:
        stats = defaultdict(int)

    exp = FMYEExport(EXPORT_DIR)
    chart_rows = exp.rows("Chart")
    chart = {r["AccountCode"]: r for r in chart_rows}
    cust_codes = {c for c, r in chart.items() if r.get("AccountCategory") == "S"}
    groups = _sl_groups(exp.rows("Voucher"))

    with db.get_connection() as conn:
        wh = conn.execute("SELECT id FROM warehouses ORDER BY id LIMIT 1").fetchone()[0]
        cust_ids = {r["code"]: r["id"] for r in conn.execute("SELECT id, code FROM customers").fetchall()}
        existing = {r[0] for r in conn.execute("SELECT document_no FROM sales_invoices").fetchall()}

        for txn, lines in groups.items():
            yr = (lines[0].get("VoucherDate") or "")[:4]
            if yr not in ("2020", "2021", "2022", "2023"):
                continue

            doc = _parse_doc_no(lines)
            if doc in existing:
                stats["skipped"] += 1
                continue

            party_code, total, kind = _resolve_party_and_total(lines, chart, cust_codes)
            if not party_code or total < 0:
                stats["failed"] += 1
                continue

            cid = cust_ids.get(party_code)
            if not cid:
                ch = chart.get(party_code, {})
                name = (ch.get("AccountName") or party_code).strip()
                cur = conn.execute(
                    """INSERT INTO customers(code, name, opening_balance, current_balance, created_by)
                       VALUES(?,?,0,0,?)""",
                    (party_code, name, uid),
                )
                cid = cur.lastrowid
                cust_ids[party_code] = cid
                stats["customers_added"] += 1

            inv_date = _d(lines[0].get("VoucherDate"))
            narr = (lines[0].get("Narration") or "").strip()
            payment_mode = "cash" if kind == "cash" else "credit"
            paid = total if kind == "cash" else 0

            conn.execute(
                """INSERT INTO sales_invoices(document_no, invoice_date, customer_id, warehouse_id,
                   subtotal, discount, tax, total, paid_amount, payment_mode, notes, status,
                   weighbridge_required, created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    doc, inv_date, cid, wh, total, 0, 0, total, paid, payment_mode,
                    f"FMYE SL voucher {txn} | {narr}"[:500], "approved", 0, uid,
                ),
            )
            existing.add(doc)
            stats["added"] += 1
            stats[f"year_{yr}"] += 1
            stats[kind] += 1

    if recalc_balances:
        stats["balances"] = db.recalculate_party_balances()
    return stats


def apply_import(uid: int):
    if not EXPORT_DIR.exists():
        raise SystemExit(f"Missing {EXPORT_DIR}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = date.today().strftime("%Y%m%d_%H%M")
    backup = BACKUP_DIR / f"ifs_erp_before_sl_sales_{stamp}.db"
    if db.DB_PATH.exists():
        shutil.copy2(db.DB_PATH, backup)
        print(f"Backup: {backup}")

    stats = defaultdict(int)
    apply(uid, stats, recalc_balances=True)
    print("\nImport complete:")
    for k in sorted(stats):
        print(f"  {k}: {stats[k]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    print("=" * 60)
    print("FMYE SL sales import (2020-2023)")
    print("=" * 60)
    if args.apply:
        user = db.authenticate("admin", "admin123")
        if not user:
            raise SystemExit("Admin login failed.")
        apply_import(user["id"])
    else:
        preview()
        print("\nRun: python import_fmye_sl_sales.py --apply")


if __name__ == "__main__":
    main()
