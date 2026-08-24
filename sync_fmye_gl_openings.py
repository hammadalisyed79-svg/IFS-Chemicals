"""Sync all GL opening balances from FMYE OpeningBalances (PeriodID=2026)
and refresh current_balance = opening + YTD general ledger.

Usage:
  python sync_fmye_gl_openings.py           # preview
  python sync_fmye_gl_openings.py --apply  # write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import database as db
from import_fmye_from_dat import EXPORT_DIR, FMYEExport, _f, _opening_map

OPENING_PERIOD = "2026"


def _uid() -> int:
    db.init_db()
    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE LOWER(username)='admin' AND is_active=1"
        ).fetchone()
    if not row:
        raise SystemExit("No admin user")
    return int(row[0])


def preview():
    exp = FMYEExport(EXPORT_DIR)
    ob = _opening_map(exp.rows("OpeningBalances"), period_id=OPENING_PERIOD)
    nonzero = sum(1 for v in ob.values() if abs(v) > 0.001)
    print(f"FMYE OpeningBalances[{OPENING_PERIOD}]: {len(ob)} accounts, {nonzero} nonzero")
    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT code, opening_balance, current_balance FROM chart_of_accounts"
        ).fetchall()
        same = diff = missing = 0
        for r in rows:
            code = (r["code"] or "").strip()
            if code not in ob:
                continue
            if abs(float(r["opening_balance"] or 0) - ob[code]) > 0.5:
                diff += 1
            else:
                same += 1
        for code in ob:
            if not conn.execute(
                "SELECT 1 FROM chart_of_accounts WHERE code=?", (code,)
            ).fetchone():
                missing += 1
        print(f"IFS match: same={same} diff={diff} missing_in_ifs={missing}")

        stale = conn.execute(
            """SELECT COUNT(*) FROM chart_of_accounts a
               WHERE ABS(
                 COALESCE(a.current_balance,0) - (
                   COALESCE(a.opening_balance,0)
                   + COALESCE((SELECT SUM(debit)-SUM(credit) FROM general_ledger g
                               WHERE g.account_id=a.id),0)
                 )
               ) > 0.5"""
        ).fetchone()[0]
        print(f"Accounts with stale current_balance: {stale}")


def apply(uid: int):
    exp = FMYEExport(EXPORT_DIR)
    ob = _opening_map(exp.rows("OpeningBalances"), period_id=OPENING_PERIOD)
    chart = exp.rows("Chart")
    s_codes = {(r.get("AccountCode") or "").strip() for r in chart if r.get("AccountCategory") == "S"}
    v_codes = {(r.get("AccountCode") or "").strip() for r in chart if r.get("AccountCategory") == "V"}

    stats = {
        "coa_updated": 0,
        "coa_zeroed": 0,
        "customers": 0,
        "suppliers": 0,
        "current_refreshed": 0,
    }

    with db.get_connection() as conn:
        # 1) Apply FMYE openings to all GL accounts
        for code, amount in ob.items():
            cur = conn.execute(
                """UPDATE chart_of_accounts
                   SET opening_balance=?, modified_by=?, modified_at=?
                   WHERE code=?""",
                (amount, uid, db._now(), code),
            )
            stats["coa_updated"] += cur.rowcount

        # Accounts in chart with no FMYE opening row -> opening 0
        for r in chart:
            code = (r.get("AccountCode") or "").strip()
            if code and code not in ob:
                cur = conn.execute(
                    """UPDATE chart_of_accounts
                       SET opening_balance=0, modified_by=?, modified_at=?
                       WHERE code=?""",
                    (uid, db._now(), code),
                )
                stats["coa_zeroed"] += cur.rowcount

        # 2) Party openings from same period
        for code in s_codes:
            amount = ob.get(code, 0.0)
            cur = conn.execute(
                """UPDATE customers SET opening_balance=?, modified_by=?, modified_at=?
                   WHERE code=?""",
                (amount, uid, db._now(), code),
            )
            stats["customers"] += cur.rowcount
        for code in v_codes:
            amount = ob.get(code, 0.0)
            cur = conn.execute(
                """UPDATE suppliers SET opening_balance=?, modified_by=?, modified_at=?
                   WHERE code=?""",
                (amount, uid, db._now(), code),
            )
            stats["suppliers"] += cur.rowcount

        # 3) Refresh COA current_balance = opening + all GL to date
        cur = conn.execute(
            """UPDATE chart_of_accounts
               SET current_balance = COALESCE(opening_balance,0) + COALESCE((
                   SELECT SUM(g.debit) - SUM(g.credit)
                   FROM general_ledger g
                   WHERE g.account_id = chart_of_accounts.id
               ), 0),
               modified_by=?, modified_at=?""",
            (uid, db._now()),
        )
        stats["current_refreshed"] = cur.rowcount

        # Spot checks
        for code in ("000000", "100068", "100314"):
            row = conn.execute(
                """SELECT code, name, opening_balance, current_balance,
                          COALESCE((SELECT SUM(debit)-SUM(credit) FROM general_ledger
                                    WHERE account_id=chart_of_accounts.id),0) AS ytd
                   FROM chart_of_accounts WHERE code=?""",
                (code,),
            ).fetchone()
            if row:
                print(
                    f"  {row['code']} {row['name'][:28]} | "
                    f"open={row['opening_balance']:,.2f} ytd={row['ytd']:,.2f} "
                    f"current={row['current_balance']:,.2f} "
                    f"FMYE={ob.get(code, 0):,.2f}"
                )

    # 4) Party current balances from full ledger
    bal = db.recalculate_party_balances()
    stats["party_customers"] = bal["customers"]
    stats["party_suppliers"] = bal["suppliers"]

    print("\nDone:")
    for k, v in stats.items():
        print(f"  {k}: {v}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    print("=" * 60)
    print(f"Sync GL openings from FMYE PeriodID={OPENING_PERIOD}")
    print("=" * 60)
    preview()
    if args.apply:
        apply(_uid())
    else:
        print("\nRun with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
