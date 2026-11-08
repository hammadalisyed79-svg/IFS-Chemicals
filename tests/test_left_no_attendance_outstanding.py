"""Staff who left or have no attendance, with leftover advance/loan/salary."""
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


def _emp(conn, code, name, *, status="active", active=1, join="2026-01-01", leave=None):
    cur = conn.execute(
        """INSERT INTO employees(
               code, full_name, basic_salary, is_active, employment_status,
               joining_date, leaving_date
           ) VALUES(?,?,?,?,?,?,?)""",
        (code, name, 50000.0, active, status, join, leave),
    )
    return int(cur.lastrowid)


def _advance(conn, eid, amount, doc):
    conn.execute(
        """INSERT INTO employee_advances(
               document_no, employee_id, request_date, amount, outstanding_amount,
               recovered_amount, status, issued_at
           ) VALUES(?,?,?,?,?,?,?,?)""",
        (doc, eid, "2026-09-01", amount, amount, 0, "issued", "2026-09-01"),
    )


def _loan(conn, eid, amount, doc):
    conn.execute(
        """INSERT INTO employee_loans(
               document_no, employee_id, issue_date, amount, outstanding_amount,
               recovered_amount, status, issued_at
           ) VALUES(?,?,?,?,?,?,?,?)""",
        (doc, eid, "2026-09-01", amount, amount, 0, "issued", "2026-09-01"),
    )


def _att(conn, eid, day, status="present"):
    conn.execute(
        """INSERT INTO attendance(employee_id, att_date, status)
           VALUES(?,?,?)""",
        (eid, day, status),
    )


def _posted_salary(conn, eid, net, *, month=9, year=2026, doc="PAY-LNA", paid=False):
    cur = conn.execute(
        """INSERT INTO payroll_runs(
               document_no, payroll_month, payroll_year, run_date, status,
               total_gross, total_deductions, total_net
           ) VALUES(?,?,?,?,?,?,?,?)""",
        (doc, month, year, f"{year:04d}-{month:02d}-28", "posted", net, 0, net),
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
            pid, eid, net, 0, 0, 0, net, 0, 0, 0, 0, 0, 0, 0,
            0, net, 30, 0, 0, "paid" if paid else "unpaid", net if paid else 0,
        ),
    )


def _posted_unpaid_salary(conn, eid, net, doc="PAY-LNA"):
    _posted_salary(conn, eid, net, month=9, year=2026, doc=doc, paid=False)


def test_left_or_no_attendance_outstanding_filters():
    path = Path(tempfile.gettempdir()) / f"erp_lna_{uuid.uuid4().hex}.db"
    os.environ["IFS_DB_PATH"] = str(path)
    db.DB_PATH = path
    db.reset_runtime_state()
    db.init_db()
    try:
        with db.get_connection() as conn:
            hr.apply_hr(conn, db)
            left_adv = _emp(conn, "EMP-L01", "Left With Advance", status="left", active=0, leave="2026-09-30")
            _advance(conn, left_adv, 8000, "ADV-L01")

            left_clear = _emp(conn, "EMP-L02", "Left Cleared", status="resigned", active=0, leave="2026-09-15")

            no_att = _emp(conn, "EMP-A01", "Active No Attendance")
            _loan(conn, no_att, 12000, "LN-A01")

            present = _emp(conn, "EMP-P01", "Active Present")
            _advance(conn, present, 5000, "ADV-P01")
            _att(conn, present, "2026-10-05")

            future = _emp(conn, "EMP-F01", "Joins Later", join="2026-11-01")
            _advance(conn, future, 3000, "ADV-F01")

            unpaid = _emp(conn, "EMP-U01", "Left Unpaid Salary", status="terminated", active=0, leave="2026-10-02")
            _posted_unpaid_salary(conn, unpaid, 25000)
            conn.commit()

        rows = hr.report_left_or_no_attendance_outstanding("2026-10-01", "2026-10-31")
        by_code = {r["code"]: r for r in rows}

        assert "EMP-L01" in by_code
        assert by_code["EMP-L01"]["reason"] == "Left"
        assert by_code["EMP-L01"]["advance_outstanding"] == 8000
        assert by_code["EMP-L01"]["who_owes"] == "Employee owes"

        assert "EMP-L02" not in by_code

        assert "EMP-A01" in by_code
        assert by_code["EMP-A01"]["reason"] == "No attendance"
        assert by_code["EMP-A01"]["loan_outstanding"] == 12000
        assert by_code["EMP-A01"]["attendance_days"] == 0

        assert "EMP-P01" not in by_code
        assert "EMP-F01" not in by_code

        assert "EMP-U01" in by_code
        assert by_code["EMP-U01"]["unpaid_salary"] == 25000
        assert by_code["EMP-U01"]["who_owes"] == "Company owes"
        assert by_code["EMP-U01"]["ledger_balance"] == -25000

        left_only = hr.report_left_or_no_attendance_outstanding(
            "2026-10-01", "2026-10-31", include_left=True, include_no_attendance=False,
        )
        assert {r["code"] for r in left_only} == {"EMP-L01", "EMP-U01"}

        no_att_only = hr.report_left_or_no_attendance_outstanding(
            "2026-10-01", "2026-10-31", include_left=False, include_no_attendance=True,
        )
        assert "EMP-A01" in {r["code"] for r in no_att_only}
        assert "EMP-L01" not in {r["code"] for r in no_att_only}
    finally:
        _cleanup(path)


def test_left_or_unpaid_salary_outstanding_filters():
    path = Path(tempfile.gettempdir()) / f"erp_lus_{uuid.uuid4().hex}.db"
    os.environ["IFS_DB_PATH"] = str(path)
    db.DB_PATH = path
    db.reset_runtime_state()
    db.init_db()
    try:
        with db.get_connection() as conn:
            hr.apply_hr(conn, db)
            left_adv = _emp(conn, "EMP-L10", "Left With Loan", status="left", active=0, leave="2026-09-20")
            _loan(conn, left_adv, 9000, "LN-L10")

            uncredited = _emp(conn, "EMP-U10", "Active Uncredited")
            _posted_salary(conn, uncredited, 40000, month=10, year=2026, doc="PAY-OCT", paid=False)

            old_unpaid = _emp(conn, "EMP-U11", "Old Unpaid Only")
            _posted_salary(conn, old_unpaid, 18000, month=9, year=2026, doc="PAY-SEP", paid=False)

            paid_adv = _emp(conn, "EMP-P10", "Paid With Advance")
            _advance(conn, paid_adv, 7000, "ADV-P10")
            _posted_salary(conn, paid_adv, 35000, month=8, year=2026, doc="PAY-AUG", paid=True)
            conn.commit()

        rows = hr.report_left_or_unpaid_salary_outstanding("2026-10-01", "2026-10-31")
        by_code = {r["code"]: r for r in rows}

        assert "EMP-L10" in by_code
        assert by_code["EMP-L10"]["reason"] == "Left"
        assert by_code["EMP-L10"]["loan_outstanding"] == 9000

        assert "EMP-U10" in by_code
        assert by_code["EMP-U10"]["reason"] == "Salary not credited"
        assert by_code["EMP-U10"]["unpaid_in_period"] == 40000
        assert by_code["EMP-U10"]["who_owes"] == "Company owes"

        assert "EMP-U11" not in by_code
        assert "EMP-P10" not in by_code

        unpaid_only = hr.report_left_or_unpaid_salary_outstanding(
            "2026-10-01", "2026-10-31", include_left=False, include_unpaid_salary=True,
        )
        assert {r["code"] for r in unpaid_only} == {"EMP-U10"}
    finally:
        _cleanup(path)
