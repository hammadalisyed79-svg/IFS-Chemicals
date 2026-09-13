"""Reclass HR cash GL from legacy 1000 → live CASH A/C 000000.

Payroll / advance / loan payments were posted with AC['cash']='1000' while
Cash Book uses 000000 — causing book vs GL gaps (e.g. Sep 7 payroll ~2.65M,
and the Rs 25,000 WAQAS RIAZ CP-127304 on Sep 6).
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database import DB_PATH, get_connection

REF_TYPES = ("payroll_line_payment", "employee_advance", "employee_loan", "expense_claim")


def main(apply: bool = True) -> int:
    with get_connection() as conn:
        cash0 = conn.execute(
            "SELECT id, current_balance FROM chart_of_accounts WHERE code='000000'"
        ).fetchone()
        cash1 = conn.execute(
            "SELECT id, current_balance FROM chart_of_accounts WHERE code='1000'"
        ).fetchone()
        if not cash0 or not cash1:
            print("Missing cash accounts")
            return 1
        id0, bal0 = int(cash0["id"]), float(cash0["current_balance"] or 0)
        id1, bal1 = int(cash1["id"]), float(cash1["current_balance"] or 0)

        rows = conn.execute(
            f"""
            SELECT id, entry_date, debit, credit, reference_type, reference_no, description
            FROM general_ledger
            WHERE account_id=?
              AND reference_type IN ({",".join("?" * len(REF_TYPES))})
            ORDER BY entry_date, id
            """,
            (id1, *REF_TYPES),
        ).fetchall()
        rows = [dict(r) for r in rows]
        cr = sum(float(r["credit"] or 0) for r in rows)
        dr = sum(float(r["debit"] or 0) for r in rows)
        print(f"Rows to move 1000->000000: {len(rows)}")
        print(f"  Credits: {cr:,.2f}  Debits: {dr:,.2f}")
        by_rt = {}
        for r in rows:
            by_rt.setdefault(r["reference_type"], {"n": 0, "cr": 0.0})
            by_rt[r["reference_type"]]["n"] += 1
            by_rt[r["reference_type"]]["cr"] += float(r["credit"] or 0)
        for k, v in by_rt.items():
            print(f"  {k}: n={v['n']} cr={v['cr']:,.2f}")

        # Highlight exact 25k
        for r in rows:
            if abs(float(r["credit"] or 0) - 25000) < 0.02:
                print(
                    f"  ** 25k: {r['entry_date']} {r['reference_no']} "
                    f"{(r['description'] or '')[:60]}"
                )

        if not rows:
            print("Nothing to do.")
            return 0
        if not apply:
            print("Dry run only.")
            return 0

        bak = Path(DB_PATH).with_name(
            f"{Path(DB_PATH).stem}_bak_reclass_cash1000_{datetime.now():%Y%m%d_%H%M%S}{Path(DB_PATH).suffix}"
        )
        shutil.copy2(DB_PATH, bak)
        print(f"Backup: {bak}")

        ids = [int(r["id"]) for r in rows]
        # chunk update
        for i in range(0, len(ids), 200):
            chunk = ids[i : i + 200]
            conn.execute(
                f"UPDATE general_ledger SET account_id=? WHERE id IN ({','.join('?'*len(chunk))})",
                (id0, *chunk),
            )

        # Asset balances: moving credit off 1000 increases 1000; onto 000000 decreases 000000
        net_cr = cr - dr
        conn.execute(
            "UPDATE chart_of_accounts SET current_balance=? WHERE id=?",
            (round(bal1 + net_cr, 2), id1),
        )
        conn.execute(
            "UPDATE chart_of_accounts SET current_balance=? WHERE id=?",
            (round(bal0 - net_cr, 2), id0),
        )
        print(f"Updated COA: 1000 {bal1:,.2f} -> {bal1+net_cr:,.2f}")
        print(f"Updated COA: 000000 {bal0:,.2f} -> {bal0-net_cr:,.2f}")
        print(f"Moved {len(ids)} GL rows.")
        return 0


if __name__ == "__main__":
    apply = "--dry-run" not in sys.argv
    raise SystemExit(main(apply=apply))
