"""Mid-month joiners: salary starts on joining date, not the 1st of the month."""
from __future__ import annotations

import os
import sys
import tempfile
import uuid
from datetime import date, timedelta
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


def _oct_days():
    d = date(2026, 10, 1)
    while d.month == 10:
        yield d
        d += timedelta(days=1)


def test_mid_month_joiner_salary_starts_from_joining_date():
    path = Path(tempfile.gettempdir()) / f"erp_join_from_{uuid.uuid4().hex}.db"
    os.environ["IFS_DB_PATH"] = str(path)
    db.DB_PATH = path
    db.reset_runtime_state()
    db.init_db()
    try:
        with db.get_connection() as conn:
            hr.apply_hr(conn, db)
            cur = conn.execute(
                """INSERT INTO employees(
                       code, full_name, basic_salary, is_active, employment_status,
                       joining_date
                   ) VALUES('EMP565','Amir Joiner',25000,1,'active','2026-10-15')"""
            )
            eid = int(cur.lastrowid)
            for d in _oct_days():
                iso = d.isoformat()
                if iso < "2026-10-15":
                    status = "absent"  # leftover marks must be ignored
                elif d.weekday() == 4:
                    status = "weekly_holiday"
                else:
                    status = "present"
                conn.execute(
                    """INSERT INTO attendance(employee_id, att_date, status, overtime_hrs)
                       VALUES(?,?,?,0)""",
                    (eid, iso, status),
                )
            cur = conn.execute(
                """INSERT INTO payroll_runs(
                       document_no, payroll_month, payroll_year, run_date, status,
                       total_gross, total_deductions, total_net
                   ) VALUES('PAY-T67',10,2026,'2026-10-31','draft',0,0,0)"""
            )
            pid = int(cur.lastrowid)
            line = hr._calc_payroll_line(conn, eid, 10, 2026, pid)
            # 15–31 Oct = 17 payable days; 1–14 must not be absent
            assert abs(float(line["days_absent"]) - 0) < 0.05, line
            assert abs(float(line["days_present"]) - 17) < 0.05, line
            assert float(line["absent_deduction"] or 0) == 0, line
            assert line.get("partial_month") is True, line
            expect_net = hr.calc_earned_basic(25000, 2026, 10, 17)
            assert abs(float(line["net_salary"]) - expect_net) < 0.05, (line, expect_net)

            conn.execute(
                """INSERT INTO payroll_lines(
                       payroll_id, employee_id, basic_salary, allowances, overtime, bonus,
                       gross_salary, tax_deduction, eobi, social_security,
                       advance_recovery, loan_recovery, other_deductions, absent_deduction,
                       total_deductions, net_salary, days_present, days_absent, overtime_hrs,
                       paid_status
                   ) VALUES(?,?,25000,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,'unpaid')""",
                (pid, eid),
            )
            conn.commit()

        res = hr.refresh_payroll_attendance_days(pid, user_id=1)
        assert res["updated"] == 1, res
        with db.get_connection() as conn:
            ln = dict(conn.execute(
                """SELECT days_present, days_absent, absent_deduction, net_salary
                   FROM payroll_lines WHERE payroll_id=?""",
                (pid,),
            ).fetchone())
        assert abs(float(ln["days_absent"]) - 0) < 0.05, ln
        assert abs(float(ln["days_present"]) - 17) < 0.05, ln

        # Saving a pre-join date must drop it, not keep absent
        hr.save_attendance({
            "employee_id": eid, "att_date": "2026-10-10", "status": "absent",
        }, user_id=1)
        with db.get_connection() as conn:
            leftover = conn.execute(
                "SELECT COUNT(*) FROM attendance WHERE employee_id=? AND att_date='2026-10-10'",
                (eid,),
            ).fetchone()[0]
        assert leftover == 0
    finally:
        _cleanup(path)


def test_true_leaver_still_clips_after_leaving_date():
    path = Path(tempfile.gettempdir()) / f"erp_left_clip_{uuid.uuid4().hex}.db"
    os.environ["IFS_DB_PATH"] = str(path)
    db.DB_PATH = path
    db.reset_runtime_state()
    db.init_db()
    try:
        with db.get_connection() as conn:
            hr.apply_hr(conn, db)
            cur = conn.execute(
                """INSERT INTO employees(
                       code, full_name, basic_salary, is_active, employment_status,
                       joining_date, leaving_date
                   ) VALUES('EMP-L1','Left Mid',20000,0,'left','2026-01-01','2026-10-10')"""
            )
            eid = int(cur.lastrowid)
            es, ee, partial = hr._employment_bounds_in_period(
                conn, eid, "2026-10-01", "2026-10-31",
            )
            assert es == "2026-10-01"
            assert ee == "2026-10-10"
            assert partial is True
    finally:
        _cleanup(path)
