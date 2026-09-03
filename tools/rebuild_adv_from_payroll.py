"""Rebuild advance/loan recovered+outstanding from actual payroll links."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import database as db

ROOT = Path(r"C:\MY ERPS")
DB = ROOT / "ifs_erp.db"


def main():
    bak = ROOT / "backups" / f"pre_adv_rebuild_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    bak.parent.mkdir(exist_ok=True)
    shutil.copy2(DB, bak)
    print("Backup:", bak)

    with db.get_connection() as conn:
        # Orphan schedule rows (recovered but payroll gone)
        orphan_s = conn.execute(
            """SELECT COUNT(*) FROM advance_recovery_schedule s
               WHERE s.recovered=1 AND (
                 s.payroll_id IS NULL
                 OR NOT EXISTS (SELECT 1 FROM payroll_runs pr WHERE pr.id=s.payroll_id)
               )"""
        ).fetchone()[0]
        print("Orphan recovered schedule rows:", orphan_s)
        conn.execute(
            """UPDATE advance_recovery_schedule
               SET recovered=0, recovered_date=NULL, payroll_id=NULL
               WHERE recovered=1 AND (
                 payroll_id IS NULL
                 OR NOT EXISTS (SELECT 1 FROM payroll_runs pr WHERE pr.id=payroll_id)
               )"""
        )

        orphan_l = conn.execute(
            """SELECT COUNT(*) FROM loan_installments s
               WHERE s.recovered=1 AND (
                 s.payroll_id IS NULL
                 OR NOT EXISTS (SELECT 1 FROM payroll_runs pr WHERE pr.id=s.payroll_id)
               )"""
        ).fetchone()[0]
        print("Orphan recovered loan installments:", orphan_l)
        conn.execute(
            """UPDATE loan_installments
               SET recovered=0, recovered_date=NULL, payroll_id=NULL
               WHERE recovered=1 AND (
                 payroll_id IS NULL
                 OR NOT EXISTS (SELECT 1 FROM payroll_runs pr WHERE pr.id=payroll_id)
               )"""
        )

        adv_rows = conn.execute(
            """SELECT id, document_no, amount, recovered_amount, outstanding_amount, status, reason
               FROM employee_advances
               WHERE status IN ('issued', 'closed')"""
        ).fetchall()

        adv_fixed = adv_reset = adv_keep_closed = 0
        for row in adv_rows:
            a = dict(row)
            aid = a["id"]
            amount = float(a["amount"] or 0)
            old_rec = float(a["recovered_amount"] or 0)
            old_out = float(a["outstanding_amount"] or 0)
            status = a["status"]
            reason = a.get("reason") or ""

            sched = conn.execute(
                """SELECT COALESCE(SUM(s.amount), 0)
                   FROM advance_recovery_schedule s
                   JOIN payroll_runs pr ON pr.id=s.payroll_id
                   WHERE s.advance_id=? AND s.recovered=1""",
                (aid,),
            ).fetchone()[0]
            sched_rec = float(sched or 0)

            if sched_rec > 0.01:
                new_rec = min(amount, round(sched_rec, 2))
                new_out = round(max(0.0, amount - new_rec), 2)
                new_status = "closed" if new_out <= 0.01 else "issued"
            elif status == "closed" and "Access ending balance" in reason:
                # Cleared by Access sync when ending bal no longer negative — keep
                adv_keep_closed += 1
                continue
            else:
                # No payroll-backed recovery → fully outstanding again
                new_rec = 0.0
                new_out = amount
                new_status = "issued" if amount > 0.01 else status

            if abs(new_rec - old_rec) < 0.01 and abs(new_out - old_out) < 0.01 and new_status == status:
                continue

            conn.execute(
                """UPDATE employee_advances
                   SET recovered_amount=?, outstanding_amount=?, status=?,
                       modified_by=1, modified_at=?
                   WHERE id=?""",
                (new_rec, new_out, new_status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), aid),
            )
            adv_fixed += 1
            if new_rec < old_rec - 0.01:
                adv_reset += 1
            print(
                f"  {a['document_no']}: rec {old_rec:,.2f}->{new_rec:,.2f} "
                f"out {old_out:,.2f}->{new_out:,.2f} {status}->{new_status}"
            )

        loan_rows = conn.execute(
            """SELECT id, document_no, amount, recovered_amount, outstanding_amount, status
               FROM employee_loans
               WHERE status IN ('issued', 'closed')"""
        ).fetchall()
        loan_fixed = 0
        for row in loan_rows:
            a = dict(row)
            lid = a["id"]
            amount = float(a["amount"] or 0)
            old_rec = float(a["recovered_amount"] or 0)
            old_out = float(a["outstanding_amount"] or 0)
            status = a["status"]
            sched = conn.execute(
                """SELECT COALESCE(SUM(s.amount), 0)
                   FROM loan_installments s
                   JOIN payroll_runs pr ON pr.id=s.payroll_id
                   WHERE s.loan_id=? AND s.recovered=1""",
                (lid,),
            ).fetchone()[0]
            sched_rec = float(sched or 0)
            if sched_rec > 0.01:
                new_rec = min(amount, round(sched_rec, 2))
                new_out = round(max(0.0, amount - new_rec), 2)
                new_status = "closed" if new_out <= 0.01 else "issued"
            else:
                new_rec = 0.0
                new_out = amount
                new_status = "issued" if amount > 0.01 else status
            if abs(new_rec - old_rec) < 0.01 and abs(new_out - old_out) < 0.01 and new_status == status:
                continue
            conn.execute(
                """UPDATE employee_loans
                   SET recovered_amount=?, outstanding_amount=?, status=?,
                       modified_by=1, modified_at=?
                   WHERE id=?""",
                (new_rec, new_out, new_status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), lid),
            )
            loan_fixed += 1
            print(
                f"  LOAN {a['document_no']}: rec {old_rec:,.2f}->{new_rec:,.2f} "
                f"out {old_out:,.2f}->{new_out:,.2f} {status}->{new_status}"
            )

        conn.commit()
        print("---")
        print(f"Advances updated={adv_fixed} (reset downward={adv_reset}), Access closed kept={adv_keep_closed}")
        print(f"Loans updated={loan_fixed}")

        # Verify ADV-0035 and KPIs
        a35 = dict(conn.execute("SELECT * FROM employee_advances WHERE document_no='ADV-0035'").fetchone())
        print(
            "ADV-0035 now:",
            a35["status"],
            "rec",
            a35["recovered_amount"],
            "out",
            a35["outstanding_amount"],
        )
        print(
            "Outstanding advances sum:",
            conn.execute(
                "SELECT COALESCE(SUM(outstanding_amount),0) FROM employee_advances WHERE status='issued'"
            ).fetchone()[0],
        )
        print(
            "Payroll-linked recovered schedule sum:",
            conn.execute(
                """SELECT COALESCE(SUM(s.amount),0) FROM advance_recovery_schedule s
                   JOIN payroll_runs pr ON pr.id=s.payroll_id WHERE s.recovered=1"""
            ).fetchone()[0],
        )


if __name__ == "__main__":
    main()
