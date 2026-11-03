"""Sync mid-month employee salary changes onto a draft payroll."""
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


def _seed_employee_payroll(conn, *, basic=50000.0, paid=False, code="EMP-S001", pay_no="PAY-S66"):
    cur = conn.execute(
        """INSERT INTO employees(code, full_name, basic_salary, is_active, employment_status)
           VALUES(?,'Salary Sync Test',?,1,'active')""",
        (code, basic),
    )
    eid = int(cur.lastrowid)
    cur = conn.execute(
        """INSERT INTO payroll_runs(
               document_no, payroll_month, payroll_year, run_date, status,
               total_gross, total_deductions, total_net
           ) VALUES(?,?,?,?,?,?,?,?)""",
        (pay_no, 9, 2026, "2026-09-30", "draft", basic, 0, basic),
    )
    pid = int(cur.lastrowid)
    conn.execute(
        """INSERT INTO payroll_lines(
               payroll_id, employee_id, basic_salary, allowances, overtime, bonus,
               gross_salary, tax_deduction, eobi, social_security,
               advance_recovery, loan_recovery, other_deductions, absent_deduction,
               total_deductions, net_salary, days_present, days_absent, overtime_hrs,
               paid_status, paid_amount
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            pid, eid, basic, 0, 0, 0, basic, 0, 0, 0, 0, 0, 0, 0,
            0, basic, 30, 0, 0, "paid" if paid else "unpaid", 0,
        ),
    )
    line_id = int(conn.execute(
        "SELECT id FROM payroll_lines WHERE payroll_id=? AND employee_id=?",
        (pid, eid),
    ).fetchone()[0])
    return eid, pid, line_id


def test_refresh_payroll_salaries_increase_and_decrease():
    path = Path(tempfile.gettempdir()) / f"erp_sal_sync_{uuid.uuid4().hex}.db"
    os.environ["IFS_DB_PATH"] = str(path)
    db.DB_PATH = path
    db.reset_runtime_state()
    db.init_db()
    try:
        with db.get_connection() as conn:
            hr.apply_hr(conn, db)
            eid, pid, line_id = _seed_employee_payroll(conn, basic=50000.0)
            conn.commit()

        assert hr.list_payroll_salary_drifts(pid)["drifts"] == []

        hr.update_employee_hr(
            eid,
            {
                "code": "EMP-S001",
                "full_name": "Salary Sync Test",
                "basic_salary": 60000,
                "employment_status": "active",
                "is_active": 1,
            },
            user_id=1,
        )
        drifts = hr.list_payroll_salary_drifts(pid)["drifts"]
        assert len(drifts) == 1, drifts
        assert abs(drifts[0]["old_basic"] - 50000) < 0.02
        assert abs(drifts[0]["new_basic"] - 60000) < 0.02

        res = hr.refresh_payroll_salaries(pid, user_id=1)
        assert res["updated"] == 1, res
        with db.get_connection() as conn:
            ln = dict(conn.execute(
                "SELECT basic_salary, overtime, net_salary, gross_salary FROM payroll_lines WHERE id=?",
                (line_id,),
            ).fetchone())
        assert abs(float(ln["basic_salary"]) - 60000) < 0.02, ln
        assert abs(float(ln["net_salary"]) - 60000) < 0.02, ln

        # Decrease
        hr.update_employee_hr(
            eid,
            {
                "code": "EMP-S001",
                "full_name": "Salary Sync Test",
                "basic_salary": 45000,
                "employment_status": "active",
                "is_active": 1,
            },
            user_id=1,
        )
        res = hr.refresh_payroll_salaries(pid, user_id=1)
        assert res["updated"] == 1, res
        with db.get_connection() as conn:
            ln = dict(conn.execute(
                "SELECT basic_salary, net_salary FROM payroll_lines WHERE id=?",
                (line_id,),
            ).fetchone())
        assert abs(float(ln["basic_salary"]) - 45000) < 0.02, ln
        assert abs(float(ln["net_salary"]) - 45000) < 0.02, ln
        assert hr.list_payroll_salary_drifts(pid)["drifts"] == []
    finally:
        _cleanup(path)


def test_refresh_payroll_salaries_skips_paid_and_recalcs_ot():
    path = Path(tempfile.gettempdir()) / f"erp_sal_sync_ot_{uuid.uuid4().hex}.db"
    os.environ["IFS_DB_PATH"] = str(path)
    db.DB_PATH = path
    db.reset_runtime_state()
    db.init_db()
    try:
        with db.get_connection() as conn:
            hr.apply_hr(conn, db)
            eid, pid, line_id = _seed_employee_payroll(conn, basic=30000.0)
            conn.execute(
                "UPDATE payroll_lines SET overtime_hrs=6, overtime=?, days_absent=2 WHERE id=?",
                (hr.calc_overtime_amount(30000, 2026, 9, 6), line_id),
            )
            conn.commit()

        hr.update_employee_hr(
            eid,
            {
                "code": "EMP-S001",
                "full_name": "Salary Sync Test",
                "basic_salary": 60000,
                "employment_status": "active",
                "is_active": 1,
            },
            user_id=1,
        )
        res = hr.refresh_payroll_salaries(pid, user_id=1)
        assert res["updated"] == 1, res
        with db.get_connection() as conn:
            ln = dict(conn.execute(
                """SELECT basic_salary, overtime, absent_deduction, gross_salary, net_salary
                   FROM payroll_lines WHERE id=?""",
                (line_id,),
            ).fetchone())
        # Sep 2026 = 30 days. OT = 60000/30/6 * 6 = 2000. Absent = 60000/30*2 = 4000.
        assert abs(float(ln["overtime"]) - 2000) < 0.02, ln
        assert abs(float(ln["absent_deduction"]) - 4000) < 0.02, ln
        assert abs(float(ln["gross_salary"]) - 62000) < 0.02, ln
        assert abs(float(ln["net_salary"]) - 58000) < 0.02, ln

        # Paid line on the same draft must not change
        with db.get_connection() as conn:
            cur = conn.execute(
                """INSERT INTO employees(code, full_name, basic_salary, is_active, employment_status)
                   VALUES('EMP-S002','Paid Skip Test',40000,1,'active')"""
            )
            eid2 = int(cur.lastrowid)
            conn.execute(
                """INSERT INTO payroll_lines(
                       payroll_id, employee_id, basic_salary, allowances, overtime, bonus,
                       gross_salary, tax_deduction, eobi, social_security,
                       advance_recovery, loan_recovery, other_deductions, absent_deduction,
                       total_deductions, net_salary, days_present, days_absent, overtime_hrs,
                       paid_status, paid_amount
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    pid, eid2, 40000, 0, 0, 0, 40000, 0, 0, 0, 0, 0, 0, 0,
                    0, 40000, 30, 0, 0, "paid", 0,
                ),
            )
            line2 = int(conn.execute(
                "SELECT id FROM payroll_lines WHERE payroll_id=? AND employee_id=?",
                (pid, eid2),
            ).fetchone()[0])
            conn.execute("UPDATE employees SET basic_salary=50000 WHERE id=?", (eid2,))
            conn.commit()
        paid_res = hr.refresh_payroll_salaries(pid, user_id=1)
        assert paid_res["updated"] == 0, paid_res
        assert paid_res["skipped_paid"] == 1, paid_res
        with db.get_connection() as conn:
            still = float(conn.execute(
                "SELECT basic_salary FROM payroll_lines WHERE id=?", (line2,),
            ).fetchone()[0])
        assert abs(still - 40000) < 0.02
    finally:
        _cleanup(path)
