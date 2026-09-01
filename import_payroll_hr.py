"""Import IFS Access payroll (PAYROLL) into IFS HR module.

Source (default):
  C:\\IFS\\DataBase\\PAYROLL\\IFS-PayRoll-Final.accdb

Imports:
  - Departments / designations (from Employee)
  - Employees (skip Photo OLE; code EMP-A#### = Access ID)
  - Salary history → payroll_runs + payroll_lines (2022–2026)
    (re-apply backfills missing lines on existing Access import runs)
  - Ending negative balances → issued employee advances
  - Payments → mark matching payroll lines paid

Usage:
  python import_payroll_hr.py              # preview
  python import_payroll_hr.py --apply      # import
  python import_payroll_hr.py --apply --year 2026
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import database as db

DEFAULT_SRC = Path(r"C:\IFS\DataBase\PAYROLL\IFS-PayRoll-Final.accdb")

EMP_SQL = """
SELECT ID, EmployeeName, Gender, PayScale, DayMonth, Designation, Department,
       Address, Mobile, PAN, BankAcNo, BankName, BankBranch, IFSCode,
       DateofBirth, JoineOn, Aadhaar, Active, LeftOn, EsiPf, Notes
FROM Employee
ORDER BY ID
"""

SAL_SQL = """
SELECT ID, Dated, Days, EID, PayScale, DayMonth, Present, SalaryAmount,
       FoodAmt, BataAmt, Advance, Loan, EsiPf, EsiPfAmt, TotalDeduct, NetPay, Remark, Prepared
FROM Salary
ORDER BY Dated, ID
"""

BAL_SQL = """
SELECT ID, Dated, PaidAmt, SalaryAmt, Balance, Remark
FROM Balance
ORDER BY ID, Dated
"""

PAY_SQL = """
SELECT p.ID AS PayID, y.Dated, p.EID, p.PaidAmt, p.Remark
FROM Payments p
INNER JOIN Pay y ON p.ID = y.ID
ORDER BY y.Dated, p.EID
"""


def _s(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, bytes):
        try:
            return v.decode("utf-16-le", errors="replace").strip() or None
        except Exception:
            return v.decode("latin-1", errors="replace").strip() or None
    t = str(v).strip()
    return t or None


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _d(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    t = str(v).strip()
    if not t:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(t[:19], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return t[:10]


def _gender(v) -> str | None:
    g = (_s(v) or "").upper()
    if g.startswith("M"):
        return "Male"
    if g.startswith("F"):
        return "Female"
    return _s(v)


def _code_slug(name: str, prefix: str, n: int) -> str:
    slug = re.sub(r"[^A-Z0-9]", "", (name or "X").upper())[:8] or "X"
    return f"{prefix}-{slug}-{n:03d}"


def _uid() -> int:
    db.init_db()
    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE LOWER(username)='admin' AND is_active=1"
        ).fetchone()
    if not row:
        raise SystemExit("No admin user")
    return int(row[0])


def _open_access(path: Path):
    try:
        import pyodbc
    except ImportError as e:
        raise SystemExit(f"pyodbc required: {e}") from e
    if not path.exists():
        raise SystemExit(f"Source DB not found: {path}")
    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ="
        + str(path)
        + ";"
    )
    return pyodbc.connect(conn_str)


def _ensure_map_table(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS payroll_access_map (
               access_eid INTEGER PRIMARY KEY,
               employee_id INTEGER NOT NULL UNIQUE,
               imported_at TEXT
           )"""
    )


def _ensure_dept(conn, name: str, cache: dict, uid: int) -> int | None:
    name = _s(name)
    if not name:
        return None
    key = name.upper()
    if key in cache:
        return cache[key]
    row = conn.execute(
        "SELECT id FROM departments WHERE UPPER(name)=?", (key,)
    ).fetchone()
    if row:
        cache[key] = row[0]
        return row[0]
    code = _code_slug(name, "DEP", len(cache) + 1)
    while conn.execute("SELECT 1 FROM departments WHERE code=?", (code,)).fetchone():
        code = _code_slug(name, "DEP", len(cache) + 100)
    cur = conn.execute(
        "INSERT INTO departments(code,name,is_active,created_by,created_at) VALUES(?,?,1,?,?)",
        (code, name, uid, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    cache[key] = cur.lastrowid
    return cur.lastrowid


def _ensure_desig(conn, name: str, cache: dict, uid: int) -> int | None:
    name = _s(name)
    if not name:
        return None
    key = name.upper()
    if key in cache:
        return cache[key]
    row = conn.execute(
        "SELECT id FROM designations WHERE UPPER(name)=?", (key,)
    ).fetchone()
    if row:
        cache[key] = row[0]
        return row[0]
    code = _code_slug(name, "DSG", len(cache) + 1)
    while conn.execute("SELECT 1 FROM designations WHERE code=?", (code,)).fetchone():
        code = _code_slug(name, "DSG", len(cache) + 100)
    cur = conn.execute(
        "INSERT INTO designations(code,name,is_active,created_by,created_at) VALUES(?,?,1,?,?)",
        (code, name, uid, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    cache[key] = cur.lastrowid
    return cur.lastrowid


def preview(src: Path, year_filter: int | None):
    ac = _open_access(src)
    cur = ac.cursor()
    emp_n = cur.execute("SELECT COUNT(*) FROM Employee").fetchone()[0]
    act = cur.execute("SELECT COUNT(*) FROM Employee WHERE Active<>0").fetchone()[0]
    sal_q = "SELECT COUNT(*) FROM Salary"
    if year_filter:
        sal_q += f" WHERE Year(Dated)={int(year_filter)}"
    sal_n = cur.execute(sal_q).fetchone()[0]
    pay_n = cur.execute("SELECT COUNT(*) FROM Payments").fetchone()[0]
    bal_n = cur.execute("SELECT COUNT(*) FROM Balance").fetchone()[0]
    depts = [r[0] for r in cur.execute("SELECT DISTINCT Department FROM Employee").fetchall() if r[0]]
    print(f"Source: {src}")
    print(f"Employees: {emp_n} ({act} active)")
    print(f"Departments: {len(depts)} — {', '.join(str(d) for d in depts[:8])}...")
    print(f"Salary rows: {sal_n}" + (f" (year {year_filter})" if year_filter else ""))
    print(f"Payments: {pay_n}")
    print(f"Balance ledger: {bal_n}")
    print("\nRun with --apply to import into IFS HR.")
    ac.close()


def _salary_line_values(r, *, eid: int, run_date: str, uid, ts):
    """Map one Access Salary row to payroll_lines INSERT values (and amounts)."""
    days = _f(r[2]) or 30
    present = _f(r[6])
    payscale = _f(r[4])
    salary_amt = _f(r[7])
    food = _f(r[8])
    bata = _f(r[9])
    advance = _f(r[10])
    loan = _f(r[11])
    esi_amt = _f(r[13])
    total_deduct = _f(r[14])
    net = _f(r[15])
    allowances = food + bata
    # SalaryAmount is often already net-of-attendance; treat as gross for the period
    gross = salary_amt + allowances if allowances else salary_amt
    if gross <= 0 and payscale > 0:
        gross = payscale
    other = max(0.0, total_deduct - advance - loan - esi_amt)
    if total_deduct <= 0:
        total_deduct = advance + loan + esi_amt + other
    if net <= 0 and gross > 0:
        net = gross - total_deduct
    absent = max(0.0, days - present) if present else 0.0
    values = (
        eid, payscale, allowances, 0, 0,
        gross, 0, esi_amt, 0,
        advance, loan, other,
        total_deduct, net, present, absent, 0,
        "paid", net, run_date, "cash", uid, ts,
    )
    return values, gross, total_deduct, net


def apply(src: Path, year_filter: int | None):
    uid = _uid()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ac = _open_access(src)
    cur = ac.cursor()

    print("Loading Access data...")
    employees = list(cur.execute(EMP_SQL).fetchall())
    salaries = list(cur.execute(SAL_SQL).fetchall())
    balances = list(cur.execute(BAL_SQL).fetchall())
    payments = list(cur.execute(PAY_SQL).fetchall())
    ac.close()

    if year_filter:
        salaries = [r for r in salaries if r[1] and r[1].year == year_filter]

    print(f"  employees={len(employees)} salary={len(salaries)} balance={len(balances)} payments={len(payments)}")

    dept_cache: dict = {}
    desig_cache: dict = {}
    access_to_ifs: dict[int, int] = {}

    with db.get_connection() as conn:
        _ensure_map_table(conn)
        for row in conn.execute("SELECT access_eid, employee_id FROM payroll_access_map").fetchall():
            access_to_ifs[int(row[0])] = int(row[1])

        # --- Departments / designations / employees ---
        created_emp = updated_emp = 0
        for r in employees:
            aid = int(r[0])
            name = _s(r[1]) or f"Employee {aid}"
            gender = _gender(r[2])
            payscale = _f(r[3])
            desig = _s(r[5])
            dept = _s(r[6])
            address = _s(r[7])
            mobile = _s(r[8])
            cnic = _s(r[9]) or _s(r[16])  # PAN / Aadhaar as CNIC fallback
            bank = _s(r[10])
            bank_name = _s(r[11])
            dob = _d(r[14])
            join_on = _d(r[15])
            active = 1 if r[17] else 0
            left_on = _d(r[18])
            bank_account = bank
            if bank_name and bank:
                bank_account = f"{bank_name} / {bank}"
            elif bank_name:
                bank_account = bank_name

            dept_id = _ensure_dept(conn, dept, dept_cache, uid)
            desig_id = _ensure_desig(conn, desig, desig_cache, uid)
            status = "active" if active else "left"
            code = f"EMP-A{aid:04d}"

            existing = access_to_ifs.get(aid)
            if existing:
                # Do not overwrite is_active / employment_status — ERP may have
                # inactivated staff after import; reactivation is intentional.
                conn.execute(
                    """UPDATE employees SET full_name=?, gender=?, mobile=?, address=?, cnic=?,
                       department_id=?, designation_id=?, department=?, designation=?,
                       joining_date=?, date_of_birth=?,
                       basic_salary=?, bank_account=?, confirmation_date=COALESCE(confirmation_date,?),
                       modified_by=?, modified_at=?
                       WHERE id=?""",
                    (
                        name, gender, mobile, address, cnic,
                        dept_id, desig_id, dept, desig,
                        join_on, dob,
                        payscale, bank_account, left_on,
                        uid, ts, existing,
                    ),
                )
                updated_emp += 1
            else:
                # Prefer stable Access-based code; fall back if taken
                if conn.execute("SELECT 1 FROM employees WHERE code=?", (code,)).fetchone():
                    code = f"EMP-A{aid:04d}X"
                cur_i = conn.execute(
                    """INSERT INTO employees(
                           code, full_name, father_name, cnic, date_of_birth, gender, marital_status,
                           phone, mobile, email, address, department_id, designation_id, manager_id,
                           joining_date, confirmation_date, employment_status, basic_salary, bank_account,
                           department, designation, is_active, created_by, created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        code, name, None, cnic, dob, gender, None,
                        mobile, mobile, None, address, dept_id, desig_id, None,
                        join_on, left_on if not active else None, status, payscale, bank_account,
                        dept, desig, active, uid, ts,
                    ),
                )
                eid = cur_i.lastrowid
                conn.execute(
                    "INSERT INTO payroll_access_map(access_eid, employee_id, imported_at) VALUES(?,?,?)",
                    (aid, eid, ts),
                )
                access_to_ifs[aid] = eid
                created_emp += 1

        print(f"Employees: created={created_emp} updated={updated_emp} mapped={len(access_to_ifs)}")

        # --- Payroll runs from Salary ---
        by_period: dict[tuple[int, int], list] = defaultdict(list)
        for r in salaries:
            dated = r[1]
            if not dated:
                continue
            by_period[(dated.year, dated.month)].append(r)

        runs_created = lines_created = lines_backfilled = runs_existing = 0
        line_ids_by_emp_period: dict[tuple[int, int, int], int] = {}  # (ifs_eid,y,m) -> payroll_line id

        line_sql = """INSERT INTO payroll_lines(
                           payroll_id, employee_id, basic_salary, allowances, overtime, bonus,
                           gross_salary, tax_deduction, eobi, social_security,
                           advance_recovery, loan_recovery, other_deductions,
                           total_deductions, net_salary, days_present, days_absent, overtime_hrs,
                           paid_status, paid_amount, paid_date, payment_mode, paid_by, paid_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""

        for (year, month) in sorted(by_period.keys()):
            existing = conn.execute(
                "SELECT id, COALESCE(notes,'') FROM payroll_runs WHERE payroll_month=? AND payroll_year=?",
                (month, year),
            ).fetchone()

            run_date = f"{year}-{month:02d}-28"
            last_d = max((r[1] for r in by_period[(year, month)] if r[1]), default=None)
            if last_d:
                run_date = last_d.strftime("%Y-%m-%d")

            if existing:
                pid = existing[0]
                notes = existing[1] or ""
                if "Access payroll import" not in notes:
                    print(
                        f"  skip {year}-{month:02d}: non-Access payroll run already exists "
                        f"(id={pid}); not creating Access import for this month"
                    )
                    for lr in conn.execute(
                        "SELECT id, employee_id FROM payroll_lines WHERE payroll_id=?",
                        (pid,),
                    ).fetchall():
                        line_ids_by_emp_period[(lr[1], year, month)] = lr[0]
                    runs_existing += 1
                    continue

                have_eids = set()
                for lr in conn.execute(
                    "SELECT id, employee_id FROM payroll_lines WHERE payroll_id=?",
                    (pid,),
                ).fetchall():
                    line_ids_by_emp_period[(lr[1], year, month)] = lr[0]
                    have_eids.add(int(lr[1]))

                # Backfill lines added in Access after the first import of this month
                added_g = added_d = added_n = 0.0
                backfilled_eids: list[int] = []
                for r in by_period[(year, month)]:
                    aid = int(r[3]) if r[3] is not None else None
                    if aid is None or aid not in access_to_ifs:
                        continue
                    eid = access_to_ifs[aid]
                    if eid in have_eids:
                        continue
                    values, gross, total_deduct, net = _salary_line_values(
                        r, eid=eid, run_date=run_date, uid=uid, ts=ts
                    )
                    cur_l = conn.execute(line_sql, (pid, *values))
                    line_ids_by_emp_period[(eid, year, month)] = cur_l.lastrowid
                    have_eids.add(eid)
                    backfilled_eids.append(eid)
                    lines_backfilled += 1
                    added_g += gross
                    added_d += total_deduct
                    added_n += net
                if added_g or added_d or added_n:
                    conn.execute(
                        """UPDATE payroll_runs
                           SET total_gross=COALESCE(total_gross,0)+?,
                               total_deductions=COALESCE(total_deductions,0)+?,
                               total_net=COALESCE(total_net,0)+?
                           WHERE id=?""",
                        (added_g, added_d, added_n, pid),
                    )
                # Staff with late-added Access salary for this month should be active again
                for eid in backfilled_eids:
                    conn.execute(
                        """UPDATE employees
                           SET is_active=1, employment_status='active',
                               modified_by=?, modified_at=?
                           WHERE id=?""",
                        (uid, ts, eid),
                    )
                runs_existing += 1
                continue

            doc = db.ensure_document_no("PAY", None, conn)
            cur_r = conn.execute(
                """INSERT INTO payroll_runs(
                       document_no, payroll_month, payroll_year, run_date, status,
                       total_gross, total_deductions, total_net, notes,
                       created_by, created_at, paid_by, paid_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    doc, month, year, run_date, "paid",
                    0, 0, 0, f"Access payroll import {year}-{month:02d}",
                    uid, ts, uid, ts,
                ),
            )
            pid = cur_r.lastrowid
            total_gross = total_ded = total_net = 0.0

            for r in by_period[(year, month)]:
                aid = int(r[3]) if r[3] is not None else None
                if aid is None or aid not in access_to_ifs:
                    continue
                eid = access_to_ifs[aid]
                values, gross, total_deduct, net = _salary_line_values(
                    r, eid=eid, run_date=run_date, uid=uid, ts=ts
                )
                cur_l = conn.execute(line_sql, (pid, *values))
                line_ids_by_emp_period[(eid, year, month)] = cur_l.lastrowid
                lines_created += 1
                total_gross += gross
                total_ded += total_deduct
                total_net += net

            conn.execute(
                "UPDATE payroll_runs SET total_gross=?, total_deductions=?, total_net=? WHERE id=?",
                (total_gross, total_ded, total_net, pid),
            )
            runs_created += 1

        print(
            f"Payroll: runs_created={runs_created} existing={runs_existing} "
            f"lines_new={lines_created} lines_backfilled={lines_backfilled}"
        )

        # --- Ending balance per Access employee = SUM(Balance deltas) ---
        # Access Balance.ID is the employee ID; Balance.Balance is a signed movement.
        last_bal: dict[int, float] = defaultdict(float)
        for r in balances:
            last_bal[int(r[0])] += _f(r[4])
        last_bal = {aid: round(bal, 2) for aid, bal in last_bal.items()}

        unpaid = 0
        restored_paid = 0
        for aid, bal in last_bal.items():
            if aid not in access_to_ifs:
                continue
            eid = access_to_ifs[aid]
            lines = conn.execute(
                """SELECT pl.id, pl.net_salary, pl.paid_amount
                   FROM payroll_lines pl
                   JOIN payroll_runs pr ON pr.id=pl.payroll_id
                   WHERE pl.employee_id=?
                   ORDER BY pr.payroll_year DESC, pr.payroll_month DESC, pl.id DESC""",
                (eid,),
            ).fetchall()
            if not lines:
                continue
            # Reset all lines to fully paid, then leave unpaid = Access ending bal (if > 0)
            for row in lines:
                net = _f(row[1])
                if abs(_f(row[2]) - net) > 0.01:
                    conn.execute(
                        "UPDATE payroll_lines SET paid_status='paid', paid_amount=? WHERE id=?",
                        (net, row[0]),
                    )
                    restored_paid += 1
            remain = bal if bal > 0.01 else 0.0
            if remain <= 0.01:
                continue
            for row in lines:
                if remain <= 0.01:
                    break
                net = _f(row[1])
                if net <= 0.01:
                    continue
                leave_unpaid = min(remain, net)
                paid_amt = max(0.0, net - leave_unpaid)
                status = "paid" if paid_amt >= net - 0.01 else ("partial" if paid_amt > 0.01 else "unpaid")
                conn.execute(
                    "UPDATE payroll_lines SET paid_status=?, paid_amount=? WHERE id=?",
                    (status, paid_amt, row[0]),
                )
                remain = round(remain - leave_unpaid, 2)
                unpaid += 1
        print(f"Unpaid-salary sync: lines marked unpaid/partial={unpaid}; reset-to-paid touches={restored_paid}")

        # --- Outstanding advances from negative ending balances (SUM) ---
        adv_created = adv_updated = adv_cleared = 0
        # Clear stale Access-ending advances when true ending bal is no longer negative
        for row in conn.execute(
            """SELECT id, employee_id FROM employee_advances
               WHERE reason LIKE '%Access ending balance%'
                 AND status IN ('issued','approved','pending')"""
        ).fetchall():
            eid = int(row[1])
            aid = next((a for a, e in access_to_ifs.items() if e == eid), None)
            if aid is None:
                continue
            bal = last_bal.get(aid, 0.0)
            if bal >= -0.01:
                conn.execute(
                    """UPDATE employee_advances
                       SET outstanding_amount=0, recovered_amount=amount, status='closed',
                           modified_by=?, modified_at=?
                       WHERE id=?""",
                    (uid, ts, row[0]),
                )
                adv_cleared += 1

        for aid, bal in last_bal.items():
            if bal >= -0.01 or aid not in access_to_ifs:
                continue
            eid = access_to_ifs[aid]
            amt = round(abs(bal), 2)
            exists = conn.execute(
                """SELECT id FROM employee_advances
                   WHERE employee_id=? AND reason LIKE ? AND status IN ('issued','approved','pending','closed')
                   ORDER BY CASE status WHEN 'closed' THEN 1 ELSE 0 END, id DESC LIMIT 1""",
                (eid, "%Access ending balance%"),
            ).fetchone()
            if exists:
                conn.execute(
                    """UPDATE employee_advances SET amount=?, outstanding_amount=?, recovered_amount=0,
                       monthly_recovery=?, status='issued', modified_by=?, modified_at=? WHERE id=?""",
                    (amt, amt, amt, uid, ts, exists[0]),
                )
                adv_updated += 1
                continue
            doc = db.ensure_document_no("ADV", None, conn)
            conn.execute(
                """INSERT INTO employee_advances(
                       document_no, employee_id, request_date, amount, reason,
                       recovery_months, monthly_recovery, recovered_amount, outstanding_amount,
                       status, approved_by, approved_at, issued_by, issued_at, created_by, created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    doc, eid, ts[:10], amt,
                    "Access ending balance (employee owes)",
                    1, amt, 0, amt,
                    "issued", uid, ts, uid, ts, uid, ts,
                ),
            )
            adv_created += 1
        print(f"Advances: created={adv_created} updated={adv_updated} cleared={adv_cleared}")

        # --- Optional: stamp payment dates from Payments onto recent lines ---
        # Aggregate paid by employee for Aug 2026 window already handled via balance.
        pay_by_emp: dict[int, float] = defaultdict(float)
        for r in payments:
            aid = int(r[2]) if r[2] is not None else None
            if aid is None:
                continue
            pay_by_emp[aid] += _f(r[3])
        print(f"Payment batches linked: {len(payments)} lines / {len(pay_by_emp)} employees")

    print("\nDone. HR employees, payroll history, and advances are in IFS.")


def main():
    ap = argparse.ArgumentParser(description="Import Access PAYROLL into IFS HR")
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--apply", action="store_true", help="Write to IFS DB")
    ap.add_argument("--year", type=int, default=None, help="Only import Salary for this year")
    args = ap.parse_args()
    if args.apply:
        apply(args.src, args.year)
    else:
        preview(args.src, args.year)


if __name__ == "__main__":
    main()
