"""Restore deleted items that have FMYE Material Issue in 2025/2026.

CLY239's MIR 11184 is dated 2025-05-31 in export but shows as 5/31/2026
in Finance Manager year-2026 books. Restore the same class of items.
"""
from __future__ import annotations

import csv
import shutil
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from import_fmye_from_dat import FMYEExport, EXPORT_DIR, _d

ROOT = Path(r"c:\MY ERPS")
LIVE = ROOT / "ifs_erp.db"
BAK = ROOT / "ifs_erp_before_idle_item_delete_20260808_173900.db"
DELETED_CSV = ROOT / "reports" / "idle_items_deleted_2026.csv"
OUT = ROOT / "reports" / "idle_items_restore_fmye_mir_like_cly239.csv"


def main():
    exp = FMYEExport(EXPORT_DIR)
    hdrs = {(r.get("MINcode") or "").strip(): r for r in exp.rows("MaterialIssueNoteHeader")}
    mir_codes: dict[str, set[str]] = defaultdict(set)
    for r in exp.rows("MaterIssueNoteDetail"):
        code = (r.get("ItemCode") or "").strip().upper()
        if not code:
            continue
        h = hdrs.get((r.get("MINCode") or "").strip())
        if not h:
            continue
        y = (_d(h.get("MINDate")) or "")[:4]
        if y in ("2025", "2026"):
            mir_codes[code].add(y)

    deleted = {
        (r.get("code") or "").strip().upper()
        for r in csv.DictReader(DELETED_CSV.open(encoding="utf-8"))
        if (r.get("code") or "").strip()
    }

    live = sqlite3.connect(str(LIVE))
    have = {
        (r[0] or "").strip().upper()
        for r in live.execute("SELECT code FROM products").fetchall()
        if r[0]
    }

    restore = sorted(c for c in mir_codes if c in deleted and c not in have)
    print(f"MIR 2025/26 codes: {len(mir_codes)}")
    print(f"To restore (deleted, missing, have MIR): {len(restore)}")
    print(f"CLY239 present: {'CLY239' in have}; MIR years: {mir_codes.get('CLY239')}")

    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["code", "mir_years"])
        w.writeheader()
        for c in restore:
            w.writerow({"code": c, "mir_years": "|".join(sorted(mir_codes[c]))})

    if not restore:
        print("Nothing to restore.")
        live.close()
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safety = ROOT / f"ifs_erp_before_restore_mir_items_{ts}.db"
    shutil.copy2(LIVE, safety)
    print(f"Safety backup: {safety.name}")

    bak = sqlite3.connect(str(BAK))
    bak.row_factory = sqlite3.Row
    live.row_factory = sqlite3.Row
    cols = [r[1] for r in bak.execute("PRAGMA table_info(products)").fetchall()]
    ws_cols = [r[1] for r in bak.execute("PRAGMA table_info(warehouse_stock)").fetchall()]
    col_list = ", ".join(cols)
    ph = ", ".join(["?"] * len(cols))

    restored = 0
    errors = []
    for code in restore:
        row = bak.execute(
            "SELECT * FROM products WHERE UPPER(TRIM(code))=?", (code,)
        ).fetchone()
        if not row:
            errors.append(f"{code}: missing in backup")
            continue
        try:
            live.execute(
                f"INSERT INTO products ({col_list}) VALUES ({ph})",
                [row[c] for c in cols],
            )
            pid = row["id"]
            for ws in bak.execute(
                "SELECT * FROM warehouse_stock WHERE product_id=?", (pid,)
            ).fetchall():
                live.execute(
                    f"INSERT OR REPLACE INTO warehouse_stock ({', '.join(ws_cols)}) "
                    f"VALUES ({', '.join('?' for _ in ws_cols)})",
                    [ws[c] for c in ws_cols],
                )
            restored += 1
        except Exception as e:
            errors.append(f"{code}: {e}")

    live.commit()
    n = live.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    live.close()
    bak.close()
    print(f"Restored: {restored}; errors: {len(errors)}; products now: {n}")
    if errors[:5]:
        print("error sample:", errors[:5])
    (ROOT / "reports" / "idle_items_restore_mir_stats.txt").write_text(
        f"restored={restored}\nerrors={errors}\nproducts={n}\ncsv={OUT}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
