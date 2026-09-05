"""
Set ERP stock so closing as of 2026-07-31 matches the Excel file.

Blank Closing Qty in Excel = 0.
Products not listed in Excel are left unchanged.
Missing Excel codes (no ERP product) are reported and skipped.

Target: opening stock as of 2026-08-01 (= July 31 closing) = Excel qty.
Post-July movements are preserved (current = Excel + net movements since Aug 1).

Usage:
  python tools/apply_closing_stock_20260731.py           # dry-run
  python tools/apply_closing_stock_20260731.py --apply   # write
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EXCEL = Path(r"c:\Users\Administrator\Desktop\Closing Stock 31.07.2026.xlsx")
AS_OF_NEXT = "2026-08-01"  # opening = July 31 closing
ADJ_DATE = "2026-07-31"
TOL = 0.0005
REASON = "Closing stock take 31.07.2026 (Excel)"


def load_excel(path: Path) -> dict[str, dict]:
    df = pd.read_excel(path, header=1)
    df.columns = ["code", "name", "qty"]
    df["code"] = df["code"].astype(str).str.strip()
    df = df[
        df["code"].notna()
        & (df["code"] != "nan")
        & (df["code"].str.upper() != "ITEM CODE")
    ]
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0.0)
    df = df.groupby("code", as_index=False).agg({"name": "first", "qty": "sum"})
    out = {}
    for _, row in df.iterrows():
        code = str(row["code"]).strip().upper()
        out[code] = {
            "code": code,
            "name": str(row["name"] or ""),
            "qty": float(row["qty"] or 0),
        }
    return out


def _opening_as_of(conn, product_id: int, as_of_next: str) -> tuple[float, float, float]:
    """Return (current, net_since, opening) for product."""
    cur = float(
        conn.execute(
            "SELECT COALESCE(SUM(quantity),0) FROM warehouse_stock WHERE product_id=?",
            (product_id,),
        ).fetchone()[0]
    )
    net = float(
        conn.execute(
            """
            SELECT COALESCE(SUM(
              CASE LOWER(COALESCE(movement_type,''))
                WHEN 'in' THEN quantity
                WHEN 'out' THEN -quantity
                ELSE 0 END
            ),0)
            FROM inventory_movements
            WHERE product_id=? AND movement_date >= ?
            """,
            (product_id, as_of_next),
        ).fetchone()[0]
    )
    return cur, net, round(cur - net, 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--excel", default=str(EXCEL))
    args = ap.parse_args()

    import database as db

    excel_path = Path(args.excel)
    if not excel_path.exists():
        raise SystemExit(f"Excel not found: {excel_path}")

    excel = load_excel(excel_path)
    print(
        f"Excel items: {len(excel)}  "
        f"nonzero: {sum(1 for v in excel.values() if abs(v['qty']) > TOL)}"
    )

    report_dir = ROOT / "reports"
    report_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rows_out = []

    with db.get_connection() as conn:
        wh = db._default_warehouse_id(conn)
        products = {
            str(r["code"]).strip().upper(): dict(r)
            for r in conn.execute("SELECT id, code, name FROM products").fetchall()
        }

        current_all = {
            int(r["product_id"]): float(r["qty"] or 0)
            for r in conn.execute(
                "SELECT product_id, COALESCE(SUM(quantity),0) AS qty "
                "FROM warehouse_stock GROUP BY product_id"
            )
        }
        net_since = {
            int(r["product_id"]): float(r["net"] or 0)
            for r in conn.execute(
                """
                SELECT product_id,
                       COALESCE(SUM(
                         CASE LOWER(COALESCE(movement_type,''))
                           WHEN 'in' THEN quantity
                           WHEN 'out' THEN -quantity
                           ELSE 0 END
                       ), 0) AS net
                FROM inventory_movements
                WHERE movement_date >= ?
                GROUP BY product_id
                """,
                (AS_OF_NEXT,),
            )
        }

        matched = missing = adjust_n = 0
        abs_delta = 0.0
        plan = []

        for code, info in sorted(excel.items()):
            target_opening = float(info["qty"])
            p = products.get(code)
            if not p:
                missing += 1
                rows_out.append({
                    "code": code,
                    "name": info["name"],
                    "excel_qty": target_opening,
                    "erp_code": "",
                    "product_id": "",
                    "current_qty": "",
                    "opening_now": "",
                    "target_opening": target_opening,
                    "target_current": "",
                    "delta": "",
                    "status": "missing_in_erp",
                })
                continue
            matched += 1
            pid = int(p["id"])
            cur = float(current_all.get(pid, 0.0))
            net = float(net_since.get(pid, 0.0))
            opening_now = round(cur - net, 4)
            target_current = round(target_opening + net, 4)
            delta = round(target_current - cur, 4)
            status = "ok" if abs(delta) < TOL else "adjust"
            if status == "adjust":
                adjust_n += 1
                abs_delta += abs(delta)
                plan.append(
                    (pid, p["code"], info["name"], target_opening, cur, opening_now, target_current, delta)
                )
            rows_out.append({
                "code": code,
                "name": info["name"],
                "excel_qty": target_opening,
                "erp_code": p["code"],
                "product_id": pid,
                "current_qty": cur,
                "opening_now": opening_now,
                "target_opening": target_opening,
                "target_current": target_current,
                "delta": delta,
                "status": status,
            })

        csv_path = report_dir / f"closing_stock_20260731_plan_{stamp}.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            cols = list(rows_out[0].keys()) if rows_out else []
            w = csv.DictWriter(f, fieldnames=cols)
            if cols:
                w.writeheader()
                w.writerows(rows_out)

        print(
            f"Matched {matched}  missing {missing}  "
            f"need adjust {adjust_n}  abs_delta {abs_delta:,.2f}"
        )
        print("Plan CSV:", csv_path)
        print("\nTop adjustments:")
        for r in sorted(plan, key=lambda x: abs(x[7]), reverse=True)[:20]:
            print(
                f"  {r[1]:12} excel={r[3]:>10.2f} open_now={r[5]:>10.2f} "
                f"cur={r[4]:>10.2f} -> {r[6]:>10.2f} delta={r[7]:>10.2f}"
            )
        miss_nz = [
            r for r in rows_out
            if r["status"] == "missing_in_erp" and abs(float(r["excel_qty"] or 0)) > TOL
        ]
        if miss_nz:
            print("\nMissing in ERP (nonzero Excel qty) — skipped:")
            for r in miss_nz:
                print(f"  {r['code']:12} {r['excel_qty']:>10.2f}  {r['name']}")

        if not args.apply:
            print("\nDry-run only. Re-run with --apply to write stock.")
            return

        bak = ROOT / "backups" / f"pre_closing_stock_20260731_{stamp}.db"
        bak.parent.mkdir(exist_ok=True)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        shutil.copy2(db.DB_PATH, bak)
        print("Backup:", bak)

        uid = None
        try:
            u = conn.execute(
                "SELECT id FROM users WHERE LOWER(username)='admin' AND is_active=1 LIMIT 1"
            ).fetchone()
            uid = int(u["id"]) if u else None
        except Exception:
            pass

        applied = 0
        for pid, code, name, target_opening, cur, opening_now, target_current, delta in plan:
            if abs(delta) < TOL:
                continue
            db._adjust_warehouse_stock(conn, pid, wh, delta, user_id=uid)
            mov = "in" if delta > 0 else "out"
            # Date as 31 Jul so Aug-onward net movements stay unchanged
            conn.execute(
                """INSERT INTO inventory_movements(
                       movement_date, product_id, warehouse_id, movement_type, quantity,
                       reference_type, reference_id, reason, created_by)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    ADJ_DATE, pid, wh, mov, abs(delta),
                    "adjustment", None,
                    f"{REASON} → closing={target_opening:g}",
                    uid,
                ),
            )
            applied += 1
        print(f"Applied {applied} stock adjustments dated {ADJ_DATE}.")

    # verify openings
    with db.get_connection() as conn:
        print("\nVerify opening as of Aug 1 (should match Excel):")
        products = {
            str(r["code"]).strip().upper(): dict(r)
            for r in conn.execute("SELECT id, code, name FROM products").fetchall()
        }
        bad = 0
        checked = 0
        for code, info in sorted(excel.items()):
            p = products.get(code)
            if not p:
                continue
            pid = int(p["id"])
            cur, net, opening = _opening_as_of(conn, pid, AS_OF_NEXT)
            checked += 1
            if abs(opening - float(info["qty"])) > 0.01:
                bad += 1
                if bad <= 10:
                    print(
                        f"  MISMATCH {p['code']}: excel={info['qty']} opening={opening} "
                        f"cur={cur} net_since={net}"
                    )
        print(f"Checked {checked} matched items; mismatches={bad}")


if __name__ == "__main__":
    main()
