"""
Compare FMYE closing stock vs IFS ERP and optionally force-align.

FMYE stock formula (from r_itemwise_stock) — NO Status filter:
  OpeningStock
  + Purchases + DPR + SaleReturns + StockAdjustments
  - Sales - PurchaseReturns - Consumption - MaterialIssue

Usage:
  python sync_fmye_stock_position.py              # dry-run report
  python sync_fmye_stock_position.py --apply      # write ERP stock to match FMYE
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from import_fmye_from_dat import FMYEExport, EXPORT_DIR, _d, _f

OUT = ROOT / "reports"
TOL = 0.0005


def _code(v) -> str:
    return (v or "").strip().upper()


def _pick_export() -> Path:
    best = None
    best_key = ("", 0, -1)  # max_date, n2026, preference
    prefer = {"full": 3, "full_live": 2, "full_old_20260808_094509": 1, "_live_delta": 0}
    for name in prefer:
        p = ROOT / "import" / "fmye" / name
        if not (p / "reload.sql").exists():
            continue
        e = FMYEExport(p)
        dates = [_d(r.get("DPRDate")) or "" for r in e.rows("DPRHeader")]
        dates = [d[:10] for d in dates if d]
        mx = max(dates) if dates else ""
        n = sum(1 for d in dates if d >= "2026-01-01")
        key = (mx, n, prefer[name])
        if key >= best_key:
            best_key = key
            best = p
    return best or EXPORT_DIR


def fmye_closing_stock(exp: FMYEExport) -> dict[str, dict]:
    """ItemCode -> {name, opening, components..., closing} — all docs, ignore Status."""
    stock: dict[str, dict] = {}

    def row(code: str, name: str = "") -> dict:
        code = _code(code)
        if not code:
            return {}
        if code not in stock:
            stock[code] = {
                "code": code,
                "name": name or "",
                "opening": 0.0,
                "purchase": 0.0,
                "dpr": 0.0,
                "sale_return": 0.0,
                "sa": 0.0,
                "sale": 0.0,
                "purchase_return": 0.0,
                "consumption": 0.0,
                "mir": 0.0,
                "closing": 0.0,
            }
        elif name and not stock[code]["name"]:
            stock[code]["name"] = name
        return stock[code]

    for r in exp.rows("ItemInformation"):
        code = _code(r.get("ItemCode"))
        if not code:
            continue
        rec = row(code, (r.get("ItemName") or "").strip())
        rec["opening"] = _f(r.get("OpeningStock"))

    def add_detail(detail, header, d_item, d_key, h_key, h_date, field, sign=1):
        headers = {
            (r.get(h_key) or "").strip(): r
            for r in exp.rows(header)
            if (r.get(h_key) or "").strip()
        }
        for r in exp.rows(detail):
            code = _code(r.get(d_item))
            if not code:
                continue
            hk = (r.get(d_key) or "").strip()
            if hk not in headers:
                continue
            # Include ALL headers — pending or posted (no Status filter)
            qty = _f(r.get("Quantity"))
            if abs(qty) < TOL:
                continue
            rec = row(code, (r.get("ItemName") or "").strip())
            rec[field] += sign * qty

    add_detail(
        "PurchaseDetail", "PurchaseHeader", "ItemCode", "PurchaseInvoiceCode",
        "PurchaseInvoiceCode", "PurchaseInvoiceDate", "purchase", 1,
    )
    add_detail(
        "SaleInvoiceDetail", "SaleInvoiceHeader", "ItemCode", "SaleInvoiceCode",
        "SaleInvoiceCode", "InvoiceDate", "sale", 1,
    )
    add_detail(
        "DPRDetail", "DPRHeader", "ItemCode", "DPRCode",
        "DPRCode", "DPRDate", "dpr", 1,
    )
    add_detail(
        "SrDetail", "SrHeader", "ItemCode", "SrNo",
        "SrNo", "SrDate", "sale_return", 1,
    )
    add_detail(
        "PrDetail", "PrHeader", "ItemCode", "PrNo",
        "PrNo", "PrDate", "purchase_return", 1,
    )
    add_detail(
        "ConsumptionNoteDetail", "ConsumptionNoteHeader", "ItemCode", "ConsNoteCode",
        "ConsNoteCode", "ConsNoteDate", "consumption", 1,
    )
    add_detail(
        "SADetail", "SAHeader", "ItemCode", "SaCode",
        "SaCode", "SaDate", "sa", 1,
    )
    add_detail(
        "MaterIssueNoteDetail", "MaterialIssueNoteHeader", "ItemCode", "MINCode",
        "MINcode", "MINDate", "mir", 1,
    )

    for rec in stock.values():
        rec["closing"] = (
            rec["opening"]
            + rec["purchase"]
            + rec["dpr"]
            + rec["sale_return"]
            + rec["sa"]
            - rec["sale"]
            - rec["purchase_return"]
            - rec["consumption"]
            - rec["mir"]
        )
    return stock


def erp_stock_map(conn: sqlite3.Connection) -> dict[str, dict]:
    out = {}
    for r in conn.execute(
        """SELECT p.id, UPPER(TRIM(p.code)) AS code, p.name,
                  COALESCE(SUM(ws.quantity), 0) AS qty
           FROM products p
           LEFT JOIN warehouse_stock ws ON ws.product_id = p.id
           WHERE p.is_active = 1
           GROUP BY p.id, p.code, p.name"""
    ):
        out[r["code"]] = {"id": r["id"], "name": r["name"], "qty": float(r["qty"] or 0)}
    return out


def build_diff(fmye: dict[str, dict], erp: dict[str, dict]) -> list[dict]:
    codes = sorted(set(fmye) | set(erp))
    rows = []
    for code in codes:
        f = fmye.get(code)
        e = erp.get(code)
        fqty = float(f["closing"]) if f else 0.0
        eqty = float(e["qty"]) if e else 0.0
        delta = fqty - eqty  # positive => ERP needs more stock
        if abs(fqty) < TOL and abs(eqty) < TOL and not f and not e:
            continue
        if abs(delta) < TOL and f and e:
            match = "match"
        elif not e:
            match = "missing_in_erp"
        elif not f:
            match = "extra_in_erp"
        else:
            match = "diff"
        if match == "match":
            continue
        rows.append({
            "code": code,
            "name": (f or {}).get("name") or (e or {}).get("name") or "",
            "fmye_qty": round(fqty, 6),
            "erp_qty": round(eqty, 6),
            "delta_to_fmye": round(delta, 6),
            "product_id": (e or {}).get("id"),
            "status": match,
            "fmye_dpr": round((f or {}).get("dpr") or 0, 3),
            "fmye_sa": round((f or {}).get("sa") or 0, 3),
            "fmye_consumption": round((f or {}).get("consumption") or 0, 3),
        })
    rows.sort(key=lambda r: abs(r["delta_to_fmye"]), reverse=True)
    return rows


def apply_align(conn: sqlite3.Connection, diffs: list[dict], uid: int | None) -> dict:
    import database as db

    wh = db._default_warehouse_id(conn)
    as_of = datetime.now().strftime("%Y-%m-%d")
    stats = {"adjusted": 0, "skipped_no_product": 0, "movements": 0}
    for r in diffs:
        if r["status"] == "missing_in_erp":
            stats["skipped_no_product"] += 1
            continue
        pid = r.get("product_id")
        if not pid:
            stats["skipped_no_product"] += 1
            continue
        delta = float(r["delta_to_fmye"])
        if abs(delta) < TOL:
            continue
        db._adjust_warehouse_stock(conn, pid, wh, delta, user_id=uid)
        mov = "in" if delta > 0 else "out"
        qty = abs(delta)
        conn.execute(
            """INSERT INTO inventory_movements(
                   movement_date, product_id, warehouse_id, movement_type, quantity,
                   reference_type, reference_id, reason, created_by)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                as_of, pid, wh, mov, qty,
                "adjustment", None,
                f"FMYE stock align (all docs incl. pending) → {r['fmye_qty']}",
                uid,
            ),
        )
        stats["adjusted"] += 1
        stats["movements"] += 1
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Write ERP stock to match FMYE")
    args = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    export = _pick_export()
    print("FMYE export:", export)
    exp = FMYEExport(export)
    fmye = fmye_closing_stock(exp)
    print(f"FMYE items with stock calc: {len(fmye)}")

    import database as db

    conn = sqlite3.connect(str(ROOT / "ifs_erp.db"))
    conn.row_factory = sqlite3.Row
    erp = erp_stock_map(conn)
    print(f"ERP active products: {len(erp)}")

    diffs = build_diff(fmye, erp)
    match_n = len(set(fmye) & set(erp)) - sum(1 for d in diffs if d["status"] == "diff")
    # recount matches properly
    matched = 0
    for code in set(fmye) & set(erp):
        if abs(fmye[code]["closing"] - erp[code]["qty"]) < TOL:
            matched += 1

    summary = {
        "fmye_items": len(fmye),
        "erp_items": len(erp),
        "matched": matched,
        "diff_rows": len(diffs),
        "missing_in_erp": sum(1 for d in diffs if d["status"] == "missing_in_erp"),
        "extra_in_erp": sum(1 for d in diffs if d["status"] == "extra_in_erp"),
        "qty_diff": sum(1 for d in diffs if d["status"] == "diff"),
        "abs_delta_sum": round(sum(abs(d["delta_to_fmye"]) for d in diffs), 3),
    }
    print("Summary:", summary)

    csv_path = OUT / "fmye_vs_erp_stock_gap.csv"
    cols = [
        "code", "name", "fmye_qty", "erp_qty", "delta_to_fmye", "status",
        "fmye_dpr", "fmye_sa", "fmye_consumption", "product_id",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(diffs)
    print("Wrote", csv_path)

    top = diffs[:15]
    print("\nTop gaps (|delta|):")
    for r in top:
        print(
            f"  {r['code']:12} FMYE={r['fmye_qty']:>12.3f} ERP={r['erp_qty']:>12.3f} "
            f"delta={r['delta_to_fmye']:>12.3f} {r['status']}"
        )

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to set ERP stock = FMYE (backup first).")
        conn.close()
        return

    bak = ROOT / f"ifs_erp_before_fmye_stock_align_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(ROOT / "ifs_erp.db", bak)
    print("Backup:", bak)

    conn.close()

    # Single connection for settings + stock writes (avoid nested lock).
    with db.get_connection() as conn2:
        conn2.execute("PRAGMA busy_timeout=120000")
        erp2 = erp_stock_map(conn2)
        for d in diffs:
            e = erp2.get(d["code"])
            d["product_id"] = e["id"] if e else None
        uid = None
        try:
            row = conn2.execute("SELECT id FROM users WHERE username='admin'").fetchone()
            uid = row[0] if row else None
        except Exception:
            pass

        prev_row = conn2.execute(
            "SELECT value FROM system_settings WHERE key='allow_negative_stock'"
        ).fetchone()
        prev = (prev_row[0] if prev_row else None) or "0"
        conn2.execute(
            "INSERT INTO system_settings(key,value) VALUES('allow_negative_stock','1') "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
        )

        try:
            stats = apply_align(conn2, diffs, uid)
            print("Applied:", stats)
        finally:
            conn2.execute(
                "INSERT INTO system_settings(key,value) VALUES('allow_negative_stock',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (prev,),
            )

    # verify
    conn3 = sqlite3.connect(str(ROOT / "ifs_erp.db"), timeout=120)
    conn3.row_factory = sqlite3.Row
    erp3 = erp_stock_map(conn3)
    left = build_diff(fmye, erp3)
    still = [d for d in left if d["status"] == "diff"]
    missing = sum(1 for d in left if d["status"] == "missing_in_erp")
    print(f"After apply: remaining qty diffs={len(still)} missing_in_erp={missing}")
    conn3.close()
    try:
        db.invalidate_stock()
    except Exception:
        pass

if __name__ == "__main__":
    main()
