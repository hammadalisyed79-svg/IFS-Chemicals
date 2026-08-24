"""Audit deleted idle items vs FMYE 2026 activity; restore false positives.

User rule:
  - Keep items with 2026 activity even if opening/stock is NIL (e.g. CLY239).
  - True idle = OpeningStock NIL AND no 2026 transaction (both true).
"""
from __future__ import annotations

import csv
import shutil
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from import_fmye_from_dat import FMYEExport, EXPORT_DIR, _d, _f

ROOT = Path(r"c:\MY ERPS")
LIVE = ROOT / "ifs_erp.db"
BAK = ROOT / "ifs_erp_before_idle_item_delete_20260808_173900.db"
DELETED_CSV = ROOT / "reports" / "idle_items_deleted_2026.csv"
OUT_DIR = ROOT / "reports"
YEAR = "2026"


def _year(d) -> str:
    s = (_d(d) or "")[:10]
    return s[:4] if len(s) >= 4 else ""


def _index_headers(rows, key_col):
    return { (r.get(key_col) or "").strip(): r for r in rows if (r.get(key_col) or "").strip() }


def fmye_2026_activity(exp: FMYEExport) -> dict[str, set[str]]:
    act: dict[str, set[str]] = defaultdict(set)

    def link(detail, header, d_item, d_key, h_key, h_date, label):
        headers = _index_headers(exp.rows(header), h_key)
        for r in exp.rows(detail):
            code = (r.get(d_item) or "").strip().upper()
            if not code:
                continue
            h = headers.get((r.get(d_key) or "").strip())
            if not h:
                continue
            if _year(h.get(h_date)) == YEAR:
                act[code].add(label)

    link("SaleInvoiceDetail", "SaleInvoiceHeader", "ItemCode", "SaleInvoiceCode",
         "SaleInvoiceCode", "InvoiceDate", "sale")
    link("PurchaseDetail", "PurchaseHeader", "ItemCode", "PurchaseInvoiceCode",
         "PurchaseInvoiceCode", "PurchaseInvoiceDate", "purchase")
    link("SrDetail", "SrHeader", "ItemCode", "SrNo", "SrNo", "SrDate", "sale_return")
    link("PrDetail", "PrHeader", "ItemCode", "PrNo", "PrNo", "PrDate", "purchase_return")
    link("MaterIssueNoteDetail", "MaterialIssueNoteHeader", "ItemCode", "MINCode",
         "MINcode", "MINDate", "material_issue")
    link("ConsumptionNoteDetail", "ConsumptionNoteHeader", "ItemCode", "ConsNoteCode",
         "ConsNoteCode", "ConsNoteDate", "consumption")
    link("SADetail", "SAHeader", "ItemCode", "SaCode", "SaCode", "SaDate", "stock_adj")
    return act


def opening_map(exp: FMYEExport) -> dict[str, float]:
    out = {}
    for r in exp.rows("ItemInformation"):
        code = (r.get("ItemCode") or "").strip().upper()
        if code:
            out[code] = _f(r.get("OpeningStock"))
    return out


def restore_products(codes: list[str]) -> dict:
    stats = {"restored": 0, "already": 0, "missing_in_backup": 0, "errors": []}
    live = sqlite3.connect(str(LIVE))
    bak = sqlite3.connect(str(BAK))
    bak.row_factory = sqlite3.Row
    live.row_factory = sqlite3.Row
    cols = [r[1] for r in bak.execute("PRAGMA table_info(products)").fetchall()]
    col_list = ", ".join(cols)
    placeholders = ", ".join(["?"] * len(cols))
    ws_cols = [r[1] for r in bak.execute("PRAGMA table_info(warehouse_stock)").fetchall()]

    for code in codes:
        cu = code.upper()
        if live.execute("SELECT id FROM products WHERE UPPER(TRIM(code))=?", (cu,)).fetchone():
            stats["already"] += 1
            # ensure active
            live.execute("UPDATE products SET is_active=1 WHERE UPPER(TRIM(code))=?", (cu,))
            continue
        row = bak.execute("SELECT * FROM products WHERE UPPER(TRIM(code))=?", (cu,)).fetchone()
        if not row:
            stats["missing_in_backup"] += 1
            continue
        try:
            live.execute(
                f"INSERT INTO products ({col_list}) VALUES ({placeholders})",
                [row[c] for c in cols],
            )
            pid = row["id"]
            for ws in bak.execute("SELECT * FROM warehouse_stock WHERE product_id=?", (pid,)).fetchall():
                live.execute(
                    f"INSERT OR REPLACE INTO warehouse_stock ({', '.join(ws_cols)}) "
                    f"VALUES ({', '.join('?' for _ in ws_cols)})",
                    [ws[c] for c in ws_cols],
                )
            stats["restored"] += 1
        except Exception as e:
            stats["errors"].append(f"{code}: {e}")
    live.commit()
    live.close()
    bak.close()
    return stats


def main():
    print("Loading FMYE…")
    exp = FMYEExport(EXPORT_DIR)
    act = fmye_2026_activity(exp)
    openings = opening_map(exp)
    print(f"FMYE items with 2026 activity: {len(act)}")
    print(f"CLY239 opening={openings.get('CLY239')} activity={sorted(act.get('CLY239', []))}")

    deleted = list(csv.DictReader(DELETED_CSV.open(encoding="utf-8")))
    deleted_codes = [(r.get("code") or "").strip().upper() for r in deleted if (r.get("code") or "").strip()]

    restore_list = []
    for code in deleted_codes:
        if code in act:
            restore_list.append({
                "code": code,
                "opening_stock": openings.get(code, 0.0),
                "sources": "|".join(sorted(act[code])),
            })

    true_idle = []
    for r in exp.rows("ItemInformation"):
        code = (r.get("ItemCode") or "").strip().upper()
        if not code:
            continue
        if abs(openings.get(code, 0.0)) < 0.0001 and code not in act:
            true_idle.append({
                "code": code,
                "name": (r.get("ItemName") or "").strip(),
                "opening_stock": openings.get(code, 0.0),
                "item_type": r.get("ItemType"),
            })

    OUT_DIR.mkdir(exist_ok=True)
    restore_csv = OUT_DIR / "idle_items_restore_fmye_2026_activity.csv"
    with restore_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["code", "opening_stock", "sources"])
        w.writeheader()
        for row in sorted(restore_list, key=lambda x: x["code"]):
            w.writerow(row)

    idle_csv = OUT_DIR / "fmye_true_idle_nil_opening_no_txn_2026.csv"
    with idle_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["code", "name", "opening_stock", "item_type"])
        w.writeheader()
        for row in true_idle:
            w.writerow(row)

    # Sources breakdown for restore list
    src_counts = defaultdict(int)
    for r in restore_list:
        for s in r["sources"].split("|"):
            src_counts[s] += 1

    summary_lines = [
        f"fmye_with_2026_activity: {len(act)}",
        f"deleted_erp_items: {len(deleted_codes)}",
        f"restore_candidates (deleted but FMYE 2026 activity): {len(restore_list)}",
        f"fmye_true_idle (NIL opening AND no 2026 txn): {len(true_idle)}",
        f"CLY239 opening: {openings.get('CLY239')}",
        f"CLY239 activity: {sorted(act.get('CLY239', []))}",
        f"restore source hits: {dict(src_counts)}",
        f"restore_csv: {restore_csv}",
        f"true_idle_csv: {idle_csv}",
        "",
        "Restore sample:",
        *[f"  {r['code']} OB={r['opening_stock']} [{r['sources']}]" for r in sorted(restore_list, key=lambda x: x['code'])[:50]],
    ]
    (OUT_DIR / "idle_items_fmye_reaudit_summary.txt").write_text("\n".join(summary_lines), encoding="utf-8")
    print("\n".join(summary_lines[:20]))

    if restore_list:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safety = ROOT / f"ifs_erp_before_restore_fmye_active_items_{ts}.db"
        shutil.copy2(LIVE, safety)
        print(f"Safety backup: {safety.name}")
        stats = restore_products([r["code"] for r in restore_list])
        print("Restore stats:", stats)
        (OUT_DIR / "idle_items_restore_fmye_stats.txt").write_text(str(stats), encoding="utf-8")
    else:
        print("No restore needed.")

    live = sqlite3.connect(str(LIVE))
    row = live.execute(
        "SELECT id, code, name, is_active FROM products WHERE UPPER(TRIM(code))='CLY239'"
    ).fetchone()
    print("Live CLY239:", row)
    n = live.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    print("Product count:", n)
    live.close()


if __name__ == "__main__":
    main()
