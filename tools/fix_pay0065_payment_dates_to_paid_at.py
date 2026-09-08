"""Align PAY-0065 paid_date / cash / GL dates with actual paid_at day (7–8 Sep).

Safe, reversible-by-rerun logic:
- Only lines where paid_date (voucher date) differs from date(paid_at)
- Updates payroll_lines.paid_date, cash_payments.payment_date, general_ledger.entry_date
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database import get_connection


def main(apply: bool = True) -> int:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT pl.id AS line_id, pl.payment_document_no AS doc_no,
                      substr(pl.paid_date,1,10) AS old_date,
                      substr(pl.paid_at,1,10) AS new_date,
                      pl.paid_amount, e.code, e.full_name
               FROM payroll_lines pl
               JOIN payroll_runs pr ON pr.id=pl.payroll_id
               JOIN employees e ON e.id=pl.employee_id
               WHERE pr.document_no='PAY-0065'
                 AND pl.paid_status='paid'
                 AND pl.paid_at IS NOT NULL AND trim(pl.paid_at)<>''
                 AND substr(pl.paid_date,1,10) <> substr(pl.paid_at,1,10)
               ORDER BY pl.paid_at, pl.id"""
        ).fetchall()
        rows = [dict(r) for r in rows]
        print(f"Lines to adjust: {len(rows)}")
        by_new = {}
        for r in rows:
            by_new.setdefault(r["new_date"], []).append(r)
            print(
                f"  {r['code']} {r['full_name']}: {r['old_date']} -> {r['new_date']} "
                f"{r['doc_no']} Rs.{float(r['paid_amount'] or 0):,.2f}"
            )
        for d, items in sorted(by_new.items()):
            print(f"  => {d}: {len(items)} vouchers")

        if not rows:
            print("Nothing to do.")
            return 0
        if not apply:
            print("Dry run only.")
            return 0

        n_pl = n_cp = n_gl = 0
        for r in rows:
            lid = int(r["line_id"])
            doc = (r["doc_no"] or "").strip()
            new_d = r["new_date"]
            old_d = r["old_date"]

            cur = conn.execute(
                "UPDATE payroll_lines SET paid_date=? WHERE id=? AND substr(paid_date,1,10)=?",
                (new_d, lid, old_d),
            )
            n_pl += cur.rowcount

            if doc:
                cur = conn.execute(
                    """UPDATE cash_payments SET payment_date=?
                       WHERE document_no=? AND substr(payment_date,1,10)=?""",
                    (new_d, doc, old_d),
                )
                n_cp += cur.rowcount
                cur = conn.execute(
                    """UPDATE bank_payments SET payment_date=?
                       WHERE document_no=? AND substr(payment_date,1,10)=?""",
                    (new_d, doc, old_d),
                )
                n_cp += cur.rowcount

            # GL for this payroll line payment (+ accrual if same doc/date)
            cur = conn.execute(
                """UPDATE general_ledger SET entry_date=?
                   WHERE reference_type IN ('payroll_line_payment','payroll_line_accrual')
                     AND reference_id=?
                     AND substr(entry_date,1,10)=?""",
                (new_d, lid, old_d),
            )
            n_gl += cur.rowcount
            if doc:
                cur = conn.execute(
                    """UPDATE general_ledger SET entry_date=?
                       WHERE reference_no=?
                         AND substr(entry_date,1,10)=?
                         AND reference_type IN (
                             'payroll_line_payment','payroll_line_accrual','cash_payment','bank_payment'
                         )""",
                    (new_d, doc, old_d),
                )
                n_gl += cur.rowcount

        # verify
        left = conn.execute(
            """SELECT COUNT(*) FROM payroll_lines pl
               JOIN payroll_runs pr ON pr.id=pl.payroll_id
               WHERE pr.document_no='PAY-0065' AND pl.paid_status='paid'
                 AND pl.paid_at IS NOT NULL AND trim(pl.paid_at)<>''
                 AND substr(pl.paid_date,1,10) <> substr(pl.paid_at,1,10)"""
        ).fetchone()[0]
        print(
            f"Updated payroll_lines={n_pl}, cash/bank={n_cp}, gl_rows={n_gl}. "
            f"Remaining mismatches={left}"
        )
        for d in ("2026-09-06", "2026-09-07", "2026-09-08"):
            n, amt = conn.execute(
                """SELECT COUNT(*), COALESCE(SUM(paid_amount),0)
                   FROM payroll_lines pl
                   JOIN payroll_runs pr ON pr.id=pl.payroll_id
                   WHERE pr.document_no='PAY-0065' AND pl.paid_status='paid'
                     AND substr(pl.paid_date,1,10)=?""",
                (d,),
            ).fetchone()
            print(f"  PAY-0065 paid_date {d}: {n} lines, Rs.{float(amt):,.2f}")
    return 0


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    raise SystemExit(main(apply=apply))
