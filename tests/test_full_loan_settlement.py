"""Full loan settlement anytime — reclaim other draft payroll recoveries."""
from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import database as db  # noqa: E402
import db_hr as hr  # noqa: E402


def _cleanup(path: Path) -> None:
    db.reset_runtime_state()
    for suffix in ("", "-wal", "-shm"):
        p = Path(f"{path}{suffix}") if suffix else path
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass


def test_full_loan_settlement_reclaims_other_draft_month():
    path = Path(tempfile.gettempdir()) / f"erp_loan_full_{uuid.uuid4().hex}.db"
    os.environ["IFS_DB_PATH"] = str(path)
    db.DB_PATH = path
    db.reset_runtime_state()
    db.init_db()
    try:
        with db.get_connection() as conn:
            hr.apply_hr(conn, db)
            # Minimal employee + salary structure
            cur = conn.execute(
                """INSERT INTO employees(code, full_name, basic_salary, is_active, employment_status)
                   VALUES('EMP-T001','Test Loan Full',30000,1,'active')"""
            )
            eid = int(cur.lastrowid)
            conn.execute(
                """INSERT INTO employee_loans(
                       document_no, employee_id, issue_date, amount, installments,
                       monthly_installment, recovered_amount, outstanding_amount,
                       reason, status
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                ("LON-T1", eid, "2026-08-01", 6000.0, 3, 2000.0, 0.0, 6000.0, "test", "issued"),
            )
            loan_id = int(conn.execute("SELECT id FROM employee_loans WHERE document_no='LON-T1'").fetchone()[0])
            for i, due in enumerate(("2026-08-31", "2026-09-30", "2026-10-31"), start=1):
                conn.execute(
                    """INSERT INTO loan_installments(loan_id, installment_no, due_date, amount, recovered)
                       VALUES(?,?,?,?,0)""",
                    (loan_id, i, due, 2000.0),
                )
            # Two draft payrolls Aug + Sep
            cur = conn.execute(
                """INSERT INTO payroll_runs(
                       document_no, payroll_month, payroll_year, run_date, status,
                       total_gross, total_deductions, total_net
                   ) VALUES(?,?,?,?,?,?,?,?)""",
                ("PAY-T65", 8, 2026, "2026-08-31", "draft", 0, 0, 0),
            )
            pay65 = int(cur.lastrowid)
            cur = conn.execute(
                """INSERT INTO payroll_runs(
                       document_no, payroll_month, payroll_year, run_date, status,
                       total_gross, total_deductions, total_net
                   ) VALUES(?,?,?,?,?,?,?,?)""",
                ("PAY-T66", 9, 2026, "2026-09-30", "draft", 0, 0, 0),
            )
            pay66 = int(cur.lastrowid)
            for pid, loan_rec, net in ((pay65, 2000.0, 28000.0), (pay66, 2000.0, 28000.0)):
                conn.execute(
                    """INSERT INTO payroll_lines(
                           payroll_id, employee_id, basic_salary, allowances, overtime, bonus,
                           gross_salary, tax_deduction, eobi, social_security,
                           advance_recovery, loan_recovery, other_deductions, absent_deduction,
                           total_deductions, net_salary, days_present, days_absent, overtime_hrs,
                           paid_status, paid_amount
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        pid, eid, 30000, 0, 0, 0, 30000, 0, 0, 0, 0, loan_rec, 0, 0,
                        loan_rec, net, 30, 0, 0, "unpaid", 0,
                    ),
                )
            # Mark first two installments recovered on each draft payroll
            conn.execute(
                """UPDATE loan_installments SET recovered=1, recovered_date='2026-08-31', payroll_id=?
                   WHERE loan_id=? AND installment_no=1""",
                (pay65, loan_id),
            )
            conn.execute(
                """UPDATE loan_installments SET recovered=1, recovered_date='2026-09-30', payroll_id=?
                   WHERE loan_id=? AND installment_no=2""",
                (pay66, loan_id),
            )
            conn.execute(
                """UPDATE employee_loans SET recovered_amount=4000, outstanding_amount=2000 WHERE id=?""",
                (loan_id,),
            )
            conn.commit()

        # Capacity must allow full 6000 on Aug payroll
        with db.get_connection() as conn:
            cap = hr._loan_recovery_capacity(conn, eid, pay65)
            assert abs(cap - 6000.0) < 0.02, cap

        line65 = None
        with db.get_connection() as conn:
            line65 = int(conn.execute(
                "SELECT id FROM payroll_lines WHERE payroll_id=? AND employee_id=?",
                (pay65, eid),
            ).fetchone()[0])

        # Settle full loan on August
        calc = hr.update_payroll_line(
            line65,
            {
                "basic_salary": 30000,
                "allowances": 0,
                "overtime": 0,
                "bonus": 0,
                "tax_deduction": 0,
                "eobi": 0,
                "social_security": 0,
                "advance_recovery": 0,
                "loan_recovery": 6000,
                "other_deductions": 0,
                "days_present": 30,
                "days_absent": 0,
                "overtime_hrs": 0,
            },
            user_id=1,
        )
        assert abs(float(calc["loan_recovery"]) - 6000.0) < 0.02, calc

        with db.get_connection() as conn:
            ln = dict(conn.execute(
                "SELECT recovered_amount, outstanding_amount, status FROM employee_loans WHERE id=?",
                (loan_id,),
            ).fetchone())
            assert abs(float(ln["outstanding_amount"]) - 0.0) < 0.02, ln
            assert abs(float(ln["recovered_amount"]) - 6000.0) < 0.02, ln

            aug = dict(conn.execute(
                "SELECT loan_recovery, net_salary FROM payroll_lines WHERE id=?",
                (line65,),
            ).fetchone())
            assert abs(float(aug["loan_recovery"]) - 6000.0) < 0.02, aug

            sep = dict(conn.execute(
                "SELECT loan_recovery FROM payroll_lines WHERE payroll_id=? AND employee_id=?",
                (pay66, eid),
            ).fetchone())
            # Sep draft must have released its installment
            assert abs(float(sep["loan_recovery"]) - 0.0) < 0.02, sep

            on_aug = conn.execute(
                """SELECT COALESCE(SUM(amount),0) FROM loan_installments
                   WHERE loan_id=? AND payroll_id=? AND recovered=1""",
                (loan_id, pay65),
            ).fetchone()[0]
            assert abs(float(on_aug) - 6000.0) < 0.02, on_aug
    finally:
        _cleanup(path)
