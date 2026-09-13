"""IFS Chemicals ERP - HR & Payroll module."""

import calendar
from datetime import date, datetime
from pathlib import Path

SCHEMA_HR_PATH = Path(__file__).parent / "schema_hr.sql"


def days_in_month(year, month):
    """Calendar days in month (28/29/30/31)."""
    return calendar.monthrange(int(year), int(month))[1]


def overtime_hourly_rate(basic_salary, year, month):
    """OT rate = Basic ÷ days_in_month ÷ 6 (IFS payroll rule)."""
    basic = float(basic_salary or 0)
    days = days_in_month(year, month)
    if basic <= 0 or days <= 0:
        return 0.0
    return basic / days / 6.0


def calc_overtime_amount(basic_salary, year, month, hours):
    """Overtime pay = (Basic / month_days / 6) × hours."""
    return round(float(hours or 0) * overtime_hourly_rate(basic_salary, year, month), 2)


def calc_overtime_hours(basic_salary, year, month, ot_amount):
    """Reverse: hours from a paid overtime amount (for prior months)."""
    rate = overtime_hourly_rate(basic_salary, year, month)
    if rate <= 0:
        return 0.0
    return round(float(ot_amount or 0) / rate, 2)


def calc_absent_deduction(basic_salary, year, month, days_absent):
    """Unpaid absent (LWP) = Basic ÷ calendar days × absent days.

    Attendance status ``leave`` is paid and must not be passed here.
    """
    basic = float(basic_salary or 0)
    abs_d = float(days_absent or 0)
    days = days_in_month(year, month) if year and month else 0
    if basic <= 0 or days <= 0 or abs_d <= 0:
        return 0.0
    return round(basic / days * abs_d, 2)

HR_AC = {
    "salary_expense": "6200",
    "salary_payable": "2150",
    # 100180 ADVANCE PAYMENTS — employees only (cash/rider floats use 100193)
    "employee_advance": "100180",
    "eobi_payable": "2160",
    "ss_payable": "2165",
    "tax_payable_payroll": "2170",
}


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _hr_ver(conn):
    r = conn.execute("SELECT value FROM schema_meta WHERE key='hr_version'").fetchone()
    return int(r[0]) if r else 0


def apply_hr(conn, db_module):
    ver = _hr_ver(conn)
    if ver < 1:
        if SCHEMA_HR_PATH.exists():
            conn.executescript(SCHEMA_HR_PATH.read_text(encoding="utf-8"))
        _extend_employees(conn)
        _seed_hr(conn, db_module)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('hr_version','1') "
            "ON CONFLICT(key) DO UPDATE SET value='1'"
        )
        ver = 1
    if ver < 2:
        _apply_hr_v2(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('hr_version','2') "
            "ON CONFLICT(key) DO UPDATE SET value='2'"
        )
        ver = 2
    if ver < 3:
        _apply_hr_v3(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('hr_version','3') "
            "ON CONFLICT(key) DO UPDATE SET value='3'"
        )
        ver = 3
    if ver < 4:
        _apply_hr_v4(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('hr_version','4') "
            "ON CONFLICT(key) DO UPDATE SET value='4'"
        )
        ver = 4
    if ver < 5:
        _apply_hr_v5(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('hr_version','5') "
            "ON CONFLICT(key) DO UPDATE SET value='5'"
        )
        ver = 5
    if ver < 6:
        _apply_hr_v6(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('hr_version','6') "
            "ON CONFLICT(key) DO UPDATE SET value='6'"
        )
        ver = 6
    if ver < 7:
        _apply_hr_v7(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('hr_version','7') "
            "ON CONFLICT(key) DO UPDATE SET value='7'"
        )
        ver = 7
    if ver < 8:
        _apply_hr_v8(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('hr_version','8') "
            "ON CONFLICT(key) DO UPDATE SET value='8'"
        )
        ver = 8
    if ver < 9:
        _apply_hr_v9(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('hr_version','9') "
            "ON CONFLICT(key) DO UPDATE SET value='9'"
        )
        ver = 9
    # Idempotent: ensure Cash & HR role exists (do not re-assign users)
    try:
        aid = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
        ensure_cash_hr_role(conn, aid[0] if aid else None)
    except Exception:
        pass


def _apply_hr_v2(conn):
    """Leave balances start at zero; HR allocates explicitly."""
    pass


def _apply_hr_v3(conn):
    """Per-employee salary payment tracking on payroll lines."""
    for col, ddl in (
        ("paid_status", "TEXT DEFAULT 'unpaid'"),
        ("paid_amount", "REAL DEFAULT 0"),
        ("paid_date", "TEXT"),
        ("payment_mode", "TEXT"),
        ("payment_document_no", "TEXT"),
        ("paid_by", "INTEGER REFERENCES users(id)"),
        ("paid_at", "TEXT"),
    ):
        _add_col(conn, "payroll_lines", col, ddl)


def _apply_hr_v4(conn):
    """Month closure lock on payroll runs."""
    for col, ddl in (
        ("closed_by", "INTEGER REFERENCES users(id)"),
        ("closed_at", "TEXT"),
    ):
        _add_col(conn, "payroll_runs", col, ddl)


def _apply_hr_v5(conn):
    """Salary month on advances — posting date and recovery payroll month can differ."""
    _add_col(conn, "employee_advances", "salary_month", "TEXT")


def _apply_hr_v6(conn):
    """Cash/bank voucher link when salary advance / loan is issued."""
    for table in ("employee_advances", "employee_loans"):
        _add_col(conn, table, "payment_mode", "TEXT")
        _add_col(conn, table, "payment_document_no", "TEXT")


def _apply_hr_v7(conn):
    """Absent (LWP) deduction on payroll lines — leave remains paid."""
    _add_col(conn, "payroll_lines", "absent_deduction", "REAL DEFAULT 0")


def _apply_hr_v8(conn):
    """Last working day for mid-month resign / final salary pro-rata."""
    _add_col(conn, "employees", "leaving_date", "TEXT")


def _apply_hr_v9(conn):
    """Cash return settlement for issued salary advances (returned next day)."""
    _add_col(conn, "employee_advances", "settlement_document_no", "TEXT")
    _add_col(conn, "employee_advances", "settled_at", "TEXT")
    _add_col(conn, "employee_advances", "settled_by", "INTEGER")
    _add_col(conn, "employee_advances", "settlement_notes", "TEXT")

def _col_exists(conn, table, col):
    return col in [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _add_col(conn, table, col, ddl):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
        if not _col_exists(conn, table, col):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


def _extend_employees(conn):
    cols = [
        ("father_name", "TEXT"), ("cnic", "TEXT"), ("date_of_birth", "TEXT"),
        ("gender", "TEXT"), ("marital_status", "TEXT"), ("mobile", "TEXT"),
        ("address", "TEXT"), ("department_id", "INTEGER REFERENCES departments(id)"),
        ("designation_id", "INTEGER REFERENCES designations(id)"),
        ("manager_id", "INTEGER REFERENCES employees(id)"),
        ("joining_date", "TEXT"), ("confirmation_date", "TEXT"),
        ("employment_status", "TEXT DEFAULT 'active'"),
        ("basic_salary", "REAL DEFAULT 0"), ("bank_account", "TEXT"),
        ("modified_by", "INTEGER"), ("modified_at", "TEXT"),
    ]
    for col, ddl in cols:
        _add_col(conn, "employees", col, ddl)


def _seed_hr(conn, db_module):
    from db_v3 import log_audit
    aid = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    aid = aid[0] if aid else None

    dept_names = [
        ("DEP-ADM", "Administration"),
        ("DEP-ACC", "Accounts & Finance"),
        ("DEP-PUR", "Purchase"),
        ("DEP-SAL", "Sales"),
        ("DEP-INV", "Inventory"),
        ("DEP-PRO", "Production"),
        ("DEP-QC", "Quality Control"),
        ("DEP-HR", "Human Resources"),
        ("DEP-MGT", "Management"),
    ]
    for code, name in dept_names:
        if not conn.execute("SELECT 1 FROM departments WHERE code=?", (code,)).fetchone():
            conn.execute("INSERT INTO departments(code,name,created_by) VALUES(?,?,?)", (code, name, aid))

    desig_names = [
        ("DSG-CEO", "CEO"),
        ("DSG-GM", "General Manager"),
        ("DSG-PM", "Production Manager"),
        ("DSG-AM", "Accounts Manager"),
        ("DSG-SM", "Sales Manager"),
        ("DSG-PO", "Purchase Officer"),
        ("DSG-SK", "Store Keeper"),
        ("DSG-OP", "Production Operator"),
        ("DSG-QC", "QC Officer"),
        ("DSG-HR", "HR Officer"),
    ]
    for code, name in desig_names:
        if not conn.execute("SELECT 1 FROM designations WHERE code=?", (code,)).fetchone():
            conn.execute("INSERT INTO designations(code,name,created_by) VALUES(?,?,?)", (code, name, aid))

    leave_types = [
        ("CL", "Casual Leave", 10, 1),
        ("SL", "Sick Leave", 10, 1),
        ("AL", "Annual Leave", 14, 1),
        ("UL", "Unpaid Leave", 0, 0),
    ]
    for code, name, days, paid in leave_types:
        if not conn.execute("SELECT 1 FROM leave_types WHERE code=?", (code,)).fetchone():
            conn.execute(
                "INSERT INTO leave_types(code,name,days_per_year,is_paid,created_by) VALUES(?,?,?,?,?)",
                (code, name, days, paid, aid),
            )
    # days_per_year = standard policy template when HR applies allocation (not auto-assigned)

    seq = [
        ("LVR", "LVR", 4), ("PAY", "PAY", 4), ("ADV", "ADV", 4),
        ("LON", "LON", 4), ("EXP", "EXP", 4),
    ]
    for dt, px, pad in seq:
        conn.execute("INSERT OR IGNORE INTO document_sequences(doc_type,prefix,padding) VALUES(?,?,?)", (dt, px, pad))

    groups = {r["group_type"]: r["id"] for r in conn.execute("SELECT id, group_type FROM account_groups").fetchall()}
    hr_accounts = [
        ("6200", "Salary Expense", "expense"),
        ("2150", "Salary Payable", "liability"),
        ("1360", "Employee Advances", "asset"),
        ("2160", "EOBI Payable", "liability"),
        ("2165", "Social Security Payable", "liability"),
        ("2170", "Payroll Tax Payable", "liability"),
    ]
    for code, name, gtype in hr_accounts:
        if not conn.execute("SELECT 1 FROM chart_of_accounts WHERE code=?", (code,)).fetchone():
            conn.execute(
                "INSERT INTO chart_of_accounts(code,name,account_group_id,created_by) VALUES(?,?,?,?)",
                (code, name, groups.get(gtype, list(groups.values())[0]), aid),
            )

    admin_role = conn.execute("SELECT id FROM roles WHERE code='ADMIN'").fetchone()
    if admin_role:
        rid = admin_role[0]
        if not conn.execute("SELECT 1 FROM role_permissions WHERE role_id=? AND module_name='HR'", (rid,)).fetchone():
            conn.execute(
                "INSERT INTO role_permissions(role_id,module_name,can_view,can_add,can_edit,can_delete,can_post,can_approve) "
                "VALUES(?,?,1,1,1,1,1,1)", (rid, "HR"))
        hr_role = conn.execute("SELECT id FROM roles WHERE code='HR'").fetchone()
        if not hr_role:
            conn.execute(
                "INSERT INTO roles(code,name,description,created_by) VALUES('HR','HR Officer','Human Resources access',?)",
                (aid,),
            )
            hr_rid = conn.execute("SELECT id FROM roles WHERE code='HR'").fetchone()[0]
            for m, perms in [
                ("Dashboard", (1, 0, 0, 0, 0, 0)),
                ("Masters", (1, 0, 0, 0, 0, 0)),
                ("HR", (1, 1, 1, 0, 1, 1)),
                ("Reports", (1, 0, 0, 0, 0, 0)),
            ]:
                conn.execute(
                    "INSERT INTO role_permissions(role_id,module_name,can_view,can_add,can_edit,can_delete,can_post,can_approve) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (hr_rid, m, *perms),
                )
    ensure_cash_hr_role(conn, aid)


def ensure_cash_hr_role(conn, created_by=None):
    """Cash desk + HR officer role (e.g. user shabab) — Finance cash ops and HR only."""
    row = conn.execute("SELECT id FROM roles WHERE upper(code)='CASH_HR'").fetchone()
    if not row:
        conn.execute(
            """INSERT INTO roles(code,name,description,created_by)
               VALUES('CASH_HR','Cash & HR Officer',
                      'Cash book / receipts / payments and HR & payroll only',?)""",
            (created_by,),
        )
        row = conn.execute("SELECT id FROM roles WHERE upper(code)='CASH_HR'").fetchone()
    rid = int(row[0])
    wanted = {
        "Dashboard": (1, 0, 0, 0, 0, 0),
        "Finance": (1, 1, 1, 0, 1, 1),
        "HR": (1, 1, 1, 0, 1, 1),
    }
    for module, perms in wanted.items():
        exists = conn.execute(
            "SELECT 1 FROM role_permissions WHERE role_id=? AND module_name=?",
            (rid, module),
        ).fetchone()
        if not exists:
            conn.execute(
                """INSERT INTO role_permissions(
                       role_id,module_name,can_view,can_add,can_edit,can_delete,can_post,can_approve)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (rid, module, *perms),
            )
    # Do not force any username onto CASH_HR — assign via Users admin screen.
    return rid


def user_can_hr(user, action="view"):
    from db_v3 import user_can
    return user_can(user, "HR", action)


def user_is_admin(user) -> bool:
    return bool(user) and str(user.get("role") or "").strip().lower() == "admin"


def _require_admin_user_id(conn, user_id, *, action="perform this action"):
    """Raise unless users.role is admin."""
    if not user_id:
        raise ValueError(f"Admin login required to {action}.")
    row = conn.execute("SELECT role FROM users WHERE id=?", (int(user_id),)).fetchone()
    if not row or str(row[0] or "").strip().lower() != "admin":
        raise ValueError(
            f"Paid salary vouchers are locked. Only an admin can {action}."
        )


# ---------- Designations ----------
def get_designations(active_only=True, search=None):
    from database import get_connection, rows_to_list
    q = "SELECT * FROM designations WHERE 1=1"
    p = []
    if active_only:
        q += " AND is_active=1"
    if search:
        q += " AND (code LIKE ? OR name LIKE ?)"
        p.extend([f"%{search}%", f"%{search}%"])
    q += " ORDER BY name"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


def get_designation(did):
    from database import get_connection, row_to_dict
    with get_connection() as conn:
        return row_to_dict(conn.execute("SELECT * FROM designations WHERE id=?", (did,)).fetchone())


def add_designation(data, user_id=None):
    from database import get_connection, next_code
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO designations(code,name,created_by) VALUES(?,?,?)",
            (data.get("code") or next_code("DSG", "designations"), data["name"], user_id),
        )


def update_designation(did, data, user_id=None):
    from database import get_connection
    with get_connection() as conn:
        conn.execute(
            "UPDATE designations SET code=?,name=?,is_active=?,modified_by=?,modified_at=? WHERE id=?",
            (data["code"], data["name"], data.get("is_active", 1), user_id, now(), did),
        )


def delete_designation(did, user_id=None):
    from database import get_connection
    from db_v3 import log_audit
    with get_connection() as conn:
        conn.execute("UPDATE designations SET is_active=0 WHERE id=?", (did,))
        log_audit("designations", did, "delete", "", user_id)


# ---------- Employees (enhanced) ----------
def get_employees_hr(active_only=True, search=None):
    from database import get_connection, rows_to_list
    q = """SELECT e.*, d.name AS department_name, g.name AS designation_name,
                  m.full_name AS manager_name
           FROM employees e
           LEFT JOIN departments d ON e.department_id=d.id
           LEFT JOIN designations g ON e.designation_id=g.id
           LEFT JOIN employees m ON e.manager_id=m.id
           WHERE 1=1"""
    p = []
    if active_only:
        q += " AND e.is_active=1"
    if search:
        q += " AND (e.code LIKE ? OR e.full_name LIKE ? OR e.cnic LIKE ? OR e.mobile LIKE ?)"
        p.extend([f"%{search}%"] * 4)
    # Department-wise everywhere — each dept keeps its own attendance / HR register
    q += """ ORDER BY COALESCE(d.name, e.department, 'Unassigned'),
                     e.full_name, e.code"""
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


def get_employee_hr(eid):
    from database import get_connection, row_to_dict
    with get_connection() as conn:
        return row_to_dict(conn.execute(
            """SELECT e.*, d.name AS department_name, g.name AS designation_name
               FROM employees e
               LEFT JOIN departments d ON e.department_id=d.id
               LEFT JOIN designations g ON e.designation_id=g.id
               WHERE e.id=?""", (eid,)).fetchone())


def add_employee_hr(data, user_id=None):
    from database import get_connection, next_code
    ts = now()
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO employees(
                   code, full_name, father_name, cnic, date_of_birth, gender, marital_status,
                   phone, mobile, email, address, department_id, designation_id, manager_id,
                   joining_date, confirmation_date, leaving_date, employment_status, basic_salary, bank_account,
                   department, designation, is_active, created_by, created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                data.get("code") or next_code("EMP", "employees"),
                data["full_name"], data.get("father_name"), data.get("cnic"),
                data.get("date_of_birth"), data.get("gender"), data.get("marital_status"),
                data.get("phone"), data.get("mobile"), data.get("email"), data.get("address"),
                data.get("department_id"), data.get("designation_id"), data.get("manager_id"),
                data.get("joining_date"), data.get("confirmation_date"), data.get("leaving_date"),
                data.get("employment_status", "active"), data.get("basic_salary", 0),
                data.get("bank_account"),
                data.get("department_name"), data.get("designation_name"),
                data.get("is_active", 1), user_id, ts,
            ),
        )
        eid = cur.lastrowid
        _ensure_leave_balances(conn, eid)
        return eid


def update_employee_hr(eid, data, user_id=None):
    from database import get_connection

    prev_emp = get_employee_hr(eid) or {}
    prev_status_l = str(prev_emp.get("employment_status") or "").strip().lower()
    prev_active = int(prev_emp.get("is_active") or 0)
    new_status_l = str(
        data.get("employment_status", prev_emp.get("employment_status") or "active") or ""
    ).strip().lower()
    new_active = int(data["is_active"]) if "is_active" in data else prev_active
    leave_d_check = data["leaving_date"] if "leaving_date" in data else prev_emp.get("leaving_date")
    becoming_exit = (
        (new_status_l in _FINAL_EXIT_STATUSES and prev_status_l not in _FINAL_EXIT_STATUSES)
        or (
            new_active == 0
            and prev_active == 1
            and (
                new_status_l in _FINAL_EXIT_STATUSES
                or bool(str(leave_d_check or "").strip())
            )
        )
    )
    if becoming_exit:
        assert_final_settlement_clear(eid)

    with get_connection() as conn:
        prev = conn.execute(
            "SELECT joining_date, confirmation_date, leaving_date FROM employees WHERE id=?",
            (eid,),
        ).fetchone()
        join_d = data["joining_date"] if "joining_date" in data else (prev["joining_date"] if prev else None)
        conf_d = data["confirmation_date"] if "confirmation_date" in data else (prev["confirmation_date"] if prev else None)
        leave_d = data["leaving_date"] if "leaving_date" in data else (prev["leaving_date"] if prev else None)
        conn.execute(
            """UPDATE employees SET code=?,full_name=?,father_name=?,cnic=?,date_of_birth=?,
               gender=?,marital_status=?,phone=?,mobile=?,email=?,address=?,
               department_id=?,designation_id=?,manager_id=?,joining_date=?,confirmation_date=?,
               leaving_date=?,employment_status=?,basic_salary=?,bank_account=?,department=?,designation=?,
               is_active=?,modified_by=?,modified_at=? WHERE id=?""",
            (
                data["code"], data["full_name"], data.get("father_name"), data.get("cnic"),
                data.get("date_of_birth"), data.get("gender"), data.get("marital_status"),
                data.get("phone"), data.get("mobile"), data.get("email"), data.get("address"),
                data.get("department_id"), data.get("designation_id"), data.get("manager_id"),
                join_d, conf_d, leave_d,
                data.get("employment_status", "active"), data.get("basic_salary", 0),
                data.get("bank_account"), data.get("department_name"), data.get("designation_name"),
                data.get("is_active", 1), user_id, now(), eid,
            ),
        )


def delete_employee_hr(eid, user_id=None):
    from database import get_connection
    from db_v3 import log_audit
    with get_connection() as conn:
        conn.execute("UPDATE employees SET is_active=0, modified_by=?, modified_at=? WHERE id=?", (user_id, now(), eid))
        log_audit("employees", eid, "deactivate", "", user_id)


def _ensure_leave_balances(conn, employee_id, year=None):
    year = year or datetime.now().year
    for lt in conn.execute("SELECT id FROM leave_types WHERE is_active=1").fetchall():
        conn.execute(
            """INSERT OR IGNORE INTO leave_balances(employee_id,leave_type_id,year,allocated,used,balance)
               VALUES(?,?,?,?,?,?)""",
            (employee_id, lt[0], year, 0, 0, 0),
        )


def _validate_leave_balance(conn, employee_id, leave_type_id, days, from_date):
    """Paid leave requires HR allocation; unpaid leave is always allowed."""
    year = int(str(from_date)[:4])
    _ensure_leave_balances(conn, employee_id, year)
    lt = conn.execute(
        "SELECT is_paid, name FROM leave_types WHERE id=?", (leave_type_id,),
    ).fetchone()
    if not lt or not lt[0]:
        return
    bal = conn.execute(
        """SELECT allocated, balance FROM leave_balances
           WHERE employee_id=? AND leave_type_id=? AND year=?""",
        (employee_id, leave_type_id, year),
    ).fetchone()
    allocated = float(bal[0] if bal else 0)
    available = float(bal[1] if bal else 0)
    if allocated <= 0:
        raise ValueError(
            f"No {lt[1]} allocated for this employee in {year}. "
            "HR must allocate leave before request/approval."
        )
    if available < float(days):
        raise ValueError(
            f"Insufficient leave balance: {available:g} day(s) available, {days:g} requested."
        )


def allocate_leave(employee_id, leave_type_id, allocated_days, year=None, user_id=None, mode="set"):
    """Set or add allocated leave days. Balance = allocated - used."""
    from database import get_connection
    year = year or datetime.now().year
    allocated_days = float(allocated_days or 0)
    if allocated_days < 0:
        raise ValueError("Allocated days cannot be negative.")
    with get_connection() as conn:
        _ensure_leave_balances(conn, employee_id, year)
        row = conn.execute(
            """SELECT id, used, allocated FROM leave_balances
               WHERE employee_id=? AND leave_type_id=? AND year=?""",
            (employee_id, leave_type_id, year),
        ).fetchone()
        if not row:
            raise ValueError("Leave balance record not found.")
        used = float(row[1])
        if mode == "add":
            new_alloc = float(row[2]) + allocated_days
        else:
            new_alloc = allocated_days
        if new_alloc < used:
            raise ValueError(
                f"Cannot set allocation to {new_alloc:g} — {used:g} day(s) already used."
            )
        balance = new_alloc - used
        conn.execute(
            "UPDATE leave_balances SET allocated=?, balance=? WHERE id=?",
            (new_alloc, balance, row[0]),
        )
        return {"employee_id": employee_id, "leave_type_id": leave_type_id, "year": year,
                "allocated": new_alloc, "used": used, "balance": balance}


def apply_standard_leave_allocation(employee_id, year=None, user_id=None):
    """Apply leave_types.days_per_year policy to one employee (paid types only)."""
    from database import get_connection
    year = year or datetime.now().year
    results = []
    with get_connection() as conn:
        for lt in conn.execute(
            "SELECT id, days_per_year FROM leave_types WHERE is_active=1 AND is_paid=1"
        ).fetchall():
            days = float(lt[1] or 0)
            if days > 0:
                results.append(
                    allocate_leave(employee_id, lt[0], days, year, user_id, mode="set")
                )
    return results


def apply_standard_leave_allocation_all(year=None, user_id=None, employee_ids=None):
    """Apply standard leave policy to selected or all active employees."""
    from database import get_connection, rows_to_list
    year = year or datetime.now().year
    with get_connection() as conn:
        if employee_ids:
            emps = employee_ids
        else:
            emps = [r[0] for r in conn.execute(
                "SELECT id FROM employees WHERE is_active=1 ORDER BY full_name"
            ).fetchall()]
    for eid in emps:
        apply_standard_leave_allocation(eid, year, user_id)
    return len(emps)


def get_leave_allocation_register(year=None, employee_id=None):
    """All employees' leave balances for allocation review."""
    from database import get_connection, rows_to_list
    year = year or datetime.now().year
    q = """SELECT lb.*, e.code AS emp_code, e.full_name AS employee_name,
                  lt.name AS leave_type_name, lt.code AS leave_type_code, lt.days_per_year
           FROM leave_balances lb
           JOIN employees e ON lb.employee_id=e.id
           JOIN leave_types lt ON lb.leave_type_id=lt.id
           WHERE lb.year=?"""
    p = [year]
    if employee_id:
        q += " AND lb.employee_id=?"; p.append(employee_id)
    q += " ORDER BY e.full_name, lt.name"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


# ---------- Attendance ----------
ATTENDANCE_STATUSES = [
    "present", "absent", "leave", "late", "overtime", "half_day",
    "weekly_holiday", "public_holiday",
]


def save_attendance(data, user_id=None):
    from database import get_connection
    ts = now()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM attendance WHERE employee_id=? AND att_date=?",
            (data["employee_id"], data["att_date"]),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE attendance SET status=?,check_in=?,check_out=?,late_mins=?,overtime_hrs=?,
                   notes=?,modified_by=?,modified_at=? WHERE id=?""",
                (data["status"], data.get("check_in"), data.get("check_out"),
                 data.get("late_mins", 0), data.get("overtime_hrs", 0), data.get("notes"),
                 user_id, ts, existing[0]),
            )
            return existing[0]
        cur = conn.execute(
            """INSERT INTO attendance(employee_id,att_date,status,check_in,check_out,late_mins,overtime_hrs,notes,created_by)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (data["employee_id"], data["att_date"], data["status"],
             data.get("check_in"), data.get("check_out"), data.get("late_mins", 0),
             data.get("overtime_hrs", 0), data.get("notes"), user_id),
        )
        return cur.lastrowid


def get_attendance(from_date=None, to_date=None, employee_id=None):
    from database import get_connection, rows_to_list
    q = """SELECT a.*, e.code AS emp_code, e.full_name AS employee_name,
                  COALESCE(d.name, e.department, 'Unassigned') AS department_name
           FROM attendance a
           JOIN employees e ON a.employee_id=e.id
           LEFT JOIN departments d ON e.department_id=d.id
           WHERE 1=1"""
    p = []
    if employee_id:
        q += " AND a.employee_id=?"; p.append(employee_id)
    if from_date:
        q += " AND a.att_date>=?"; p.append(from_date)
    if to_date:
        q += " AND a.att_date<=?"; p.append(to_date)
    q += """ ORDER BY a.att_date DESC,
                     COALESCE(d.name, e.department, 'Unassigned'),
                     e.full_name"""
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


def report_attendance_monthly_coverage(year, month, department=None, active_only=True):
    """Active employees vs saved attendance for a calendar month.

    Returns list of dicts with saved_days, missing_days, coverage_pct, status bucket
    (none / partial / complete), and present/absent/leave/holiday counts from saved rows.
    For the current month, expected days stop at today (future days are not missing).
    """
    from database import get_connection, rows_to_list
    from datetime import date as _date

    year, month = int(year), int(month)
    period_start, period_end = _period_bounds(month, year)
    days_total = days_in_month(year, month)
    today = _date.today()
    if year == today.year and month == today.month:
        expected_days = today.day
        period_end_eff = today.isoformat()
    else:
        expected_days = days_total
        period_end_eff = period_end

    with get_connection() as conn:
        q = """SELECT e.id AS employee_id, e.code, e.full_name,
                      COALESCE(d.name, e.department, 'Unassigned') AS department_name,
                      COALESCE(att.saved_days, 0) AS saved_days,
                      COALESCE(att.present_days, 0) AS present_days,
                      COALESCE(att.absent_days, 0) AS absent_days,
                      COALESCE(att.leave_days, 0) AS leave_days,
                      COALESCE(att.holiday_days, 0) AS holiday_days,
                      COALESCE(att.other_days, 0) AS other_days,
                      att.first_date, att.last_date
               FROM employees e
               LEFT JOIN departments d ON e.department_id=d.id
               LEFT JOIN (
                   SELECT employee_id,
                          COUNT(*) AS saved_days,
                          SUM(CASE WHEN LOWER(COALESCE(status,'')) IN ('present','late','overtime') THEN 1 ELSE 0 END) AS present_days,
                          SUM(CASE WHEN LOWER(COALESCE(status,''))='absent' THEN 1 ELSE 0 END) AS absent_days,
                          SUM(CASE WHEN LOWER(COALESCE(status,''))='leave' THEN 1 ELSE 0 END) AS leave_days,
                          SUM(CASE WHEN LOWER(COALESCE(status,'')) IN ('weekly_holiday','public_holiday') THEN 1 ELSE 0 END) AS holiday_days,
                          SUM(CASE WHEN LOWER(COALESCE(status,'')) NOT IN (
                                'present','late','overtime','absent','leave','weekly_holiday','public_holiday'
                              ) THEN 1 ELSE 0 END) AS other_days,
                          MIN(att_date) AS first_date,
                          MAX(att_date) AS last_date
                   FROM attendance
                   WHERE att_date>=? AND att_date<=?
                   GROUP BY employee_id
               ) att ON att.employee_id=e.id
               WHERE 1=1"""
        p = [period_start, period_end_eff]
        if active_only:
            q += " AND e.is_active=1 AND COALESCE(e.employment_status,'active')='active'"
        # Contractor department is billed separately — not in attendance coverage
        q += """ AND LOWER(TRIM(COALESCE(d.name, e.department, ''))) NOT LIKE '%contractor%'"""
        if department and department != "All departments":
            q += " AND COALESCE(d.name, e.department, 'Unassigned')=?"
            p.append(department)
        q += """ ORDER BY COALESCE(d.name, e.department, 'Unassigned'),
                         e.full_name, e.code"""
        rows = rows_to_list(conn.execute(q, p).fetchall())

    out = []
    for r in rows:
        saved = int(r.get("saved_days") or 0)
        missing = max(0, expected_days - saved)
        if saved <= 0:
            bucket = "none"
        elif saved >= expected_days:
            bucket = "complete"
        else:
            bucket = "partial"
        pct = round(100.0 * saved / expected_days, 1) if expected_days else 0.0
        out.append({
            **r,
            "year": year,
            "month": month,
            "period_start": period_start,
            "period_end": period_end_eff,
            "days_in_month": days_total,
            "expected_days": expected_days,
            "saved_days": saved,
            "missing_days": missing,
            "coverage_pct": pct,
            "coverage_status": bucket,
        })
    return out


def bulk_save_attendance(att_date, records, user_id=None):
    """Save attendance for many employees in one transaction."""
    from database import get_connection
    ts = now()
    saved = 0
    with get_connection() as conn:
        for rec in records:
            eid = rec.get("employee_id")
            if not eid:
                continue
            status = rec.get("status") or "present"
            existing = conn.execute(
                "SELECT id FROM attendance WHERE employee_id=? AND att_date=?",
                (eid, att_date),
            ).fetchone()
            fields = (
                status, rec.get("check_in"), rec.get("check_out"),
                rec.get("late_mins", 0) or 0, rec.get("overtime_hrs", 0) or 0,
                rec.get("notes"), user_id, ts,
            )
            if existing:
                conn.execute(
                    """UPDATE attendance SET status=?,check_in=?,check_out=?,late_mins=?,overtime_hrs=?,
                       notes=?,modified_by=?,modified_at=? WHERE id=?""",
                    (*fields, existing[0]),
                )
            else:
                conn.execute(
                    """INSERT INTO attendance(employee_id,att_date,status,check_in,check_out,late_mins,overtime_hrs,notes,created_by)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (eid, att_date, status, rec.get("check_in"), rec.get("check_out"),
                     rec.get("late_mins", 0) or 0, rec.get("overtime_hrs", 0) or 0,
                     rec.get("notes"), user_id),
                )
            saved += 1
    return saved


def get_attendance_map_for_date(att_date):
    """Return {employee_id: attendance_row} for a single date."""
    return {r["employee_id"]: r for r in get_attendance(att_date, att_date)}


# ---------- Leave ----------
def get_leave_types():
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        return rows_to_list(conn.execute("SELECT * FROM leave_types WHERE is_active=1 ORDER BY name").fetchall())


def get_leave_balances(employee_id, year=None):
    from database import get_connection, rows_to_list
    year = year or datetime.now().year
    with get_connection() as conn:
        _ensure_leave_balances(conn, employee_id, year)
        return rows_to_list(conn.execute(
            """SELECT lb.*, lt.name AS leave_type_name, lt.code AS leave_type_code
               FROM leave_balances lb JOIN leave_types lt ON lb.leave_type_id=lt.id
               WHERE lb.employee_id=? AND lb.year=?""",
            (employee_id, year),
        ).fetchall())


def save_leave_request(data, user_id=None):
    from database import get_connection, ensure_document_no
    with get_connection() as conn:
        _validate_leave_balance(
            conn, data["employee_id"], data["leave_type_id"], data["days"], data["from_date"],
        )
        cur = conn.execute(
            """INSERT INTO leave_requests(document_no,employee_id,leave_type_id,from_date,to_date,days,reason,status,created_by)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (ensure_document_no("LVR", data.get("document_no"), conn), data["employee_id"], data["leave_type_id"],
             data["from_date"], data["to_date"], data["days"], data.get("reason"), "pending", user_id),
        )
        return cur.lastrowid


def get_leave_requests(status=None, employee_id=None):
    from database import get_connection, rows_to_list
    q = """SELECT lr.*, e.full_name AS employee_name, lt.name AS leave_type_name
           FROM leave_requests lr
           JOIN employees e ON lr.employee_id=e.id
           JOIN leave_types lt ON lr.leave_type_id=lt.id WHERE 1=1"""
    p = []
    if status:
        q += " AND lr.status=?"; p.append(status)
    if employee_id:
        q += " AND lr.employee_id=?"; p.append(employee_id)
    q += " ORDER BY lr.created_at DESC"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


def approve_leave_request(req_id, user_id, approve=True):
    from database import get_connection
    ts = now()
    with get_connection() as conn:
        req = conn.execute("SELECT * FROM leave_requests WHERE id=?", (req_id,)).fetchone()
        if not req or req["status"] != "pending":
            raise ValueError("Invalid leave request")
        req = dict(req)
        if approve:
            _validate_leave_balance(
                conn, req["employee_id"], req["leave_type_id"], req["days"], req["from_date"],
            )
            conn.execute(
                "UPDATE leave_requests SET status='approved',approved_by=?,approved_at=?,modified_by=?,modified_at=? WHERE id=?",
                (user_id, ts, user_id, ts, req_id),
            )
            year = int(req["from_date"][:4])
            bal = conn.execute(
                "SELECT id, balance FROM leave_balances WHERE employee_id=? AND leave_type_id=? AND year=?",
                (req["employee_id"], req["leave_type_id"], year),
            ).fetchone()
            if bal:
                new_used = conn.execute(
                    "SELECT used FROM leave_balances WHERE id=?", (bal[0],)
                ).fetchone()[0] + req["days"]
                conn.execute(
                    "UPDATE leave_balances SET used=?, balance=allocated-? WHERE id=?",
                    (new_used, new_used, bal[0]),
                )
            for d in _date_range(req["from_date"], req["to_date"]):
                save_attendance({"employee_id": req["employee_id"], "att_date": d, "status": "leave"}, user_id)
        else:
            conn.execute(
                "UPDATE leave_requests SET status='rejected',rejected_by=?,rejected_at=?,modified_by=?,modified_at=? WHERE id=?",
                (user_id, ts, user_id, ts, req_id),
            )


def _date_range(start, end):
    from datetime import timedelta
    s = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end, "%Y-%m-%d")
    out = []
    while s <= e:
        out.append(s.strftime("%Y-%m-%d"))
        s += timedelta(days=1)
    return out


# ---------- Salary structure ----------
def get_salary_structure(employee_id):
    from database import get_connection, row_to_dict
    with get_connection() as conn:
        return row_to_dict(conn.execute(
            "SELECT * FROM salary_structures WHERE employee_id=? AND is_active=1 ORDER BY effective_from DESC LIMIT 1",
            (employee_id,),
        ).fetchone())


def save_salary_structure(data, user_id=None):
    from database import get_connection
    ts = now()
    with get_connection() as conn:
        conn.execute("UPDATE salary_structures SET is_active=0 WHERE employee_id=?", (data["employee_id"],))
        conn.execute(
            """INSERT INTO salary_structures(employee_id,basic_salary,housing_allowance,transport_allowance,
               medical_allowance,other_allowance,effective_from,is_active,created_by)
               VALUES(?,?,?,?,?,?,?,1,?)""",
            (data["employee_id"], data.get("basic_salary", 0), data.get("housing_allowance", 0),
             data.get("transport_allowance", 0), data.get("medical_allowance", 0),
             data.get("other_allowance", 0), data.get("effective_from", ts[:10]), user_id),
        )
        conn.execute(
            "UPDATE employees SET basic_salary=?, modified_by=?, modified_at=? WHERE id=?",
            (data.get("basic_salary", 0), user_id, ts, data["employee_id"]),
        )


# ---------- Payroll ----------
def get_payroll_runs():
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            "SELECT * FROM payroll_runs ORDER BY payroll_year DESC, payroll_month DESC"
        ).fetchall())


def get_payroll_run(pid):
    from database import get_connection, row_to_dict, rows_to_list
    with get_connection() as conn:
        h = row_to_dict(conn.execute("SELECT * FROM payroll_runs WHERE id=?", (pid,)).fetchone())
        if h:
            h["lines"] = rows_to_list(conn.execute(
                """SELECT pl.id, pl.payroll_id, pl.employee_id,
                          e.code AS emp_code,
                          COALESCE(e.full_name, e.code, 'Employee #' || pl.employee_id) AS employee_name,
                          COALESCE(d.name, e.department, 'Unassigned') AS department_name,
                          pl.basic_salary, pl.allowances, pl.overtime, pl.bonus, pl.gross_salary,
                          pl.tax_deduction, pl.eobi, pl.social_security, pl.advance_recovery,
                          pl.loan_recovery, pl.other_deductions,
                          COALESCE(pl.absent_deduction, 0) AS absent_deduction,
                          pl.total_deductions, pl.net_salary,
                          pl.days_present, pl.days_absent, pl.overtime_hrs, e.bank_account,
                          e.joining_date, e.leaving_date, e.employment_status,
                          COALESCE(pl.paid_status, 'unpaid') AS paid_status,
                          pl.paid_amount, pl.paid_date, pl.payment_mode, pl.payment_document_no
                   FROM payroll_lines pl
                   LEFT JOIN employees e ON pl.employee_id=e.id
                   LEFT JOIN departments d ON e.department_id=d.id
                   WHERE pl.payroll_id=?
                   ORDER BY COALESCE(d.name, e.department, 'Unassigned'), e.full_name, e.code""",
                (pid,),
            ).fetchall())
        return h


def generate_payroll(month, year, user_id=None):
    from database import get_connection, ensure_document_no
    ts = now()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM payroll_runs WHERE payroll_month=? AND payroll_year=?", (month, year)
        ).fetchone()
        if existing:
            raise ValueError("Payroll already exists for this period")
        cur = conn.execute(
            """INSERT INTO payroll_runs(document_no,payroll_month,payroll_year,run_date,status,created_by)
               VALUES(?,?,?,?,?,?)""",
            (ensure_document_no("PAY", None, conn), month, year, ts[:10], "draft", user_id),
        )
        pid = cur.lastrowid
        employees = conn.execute("SELECT id FROM employees WHERE is_active=1 AND employment_status='active'").fetchall()
        total_gross = total_ded = total_net = 0
        for emp in employees:
            eid = emp[0]
            line = _calc_payroll_line(conn, eid, month, year, pid)
            conn.execute(
                """INSERT INTO payroll_lines(payroll_id,employee_id,basic_salary,allowances,overtime,bonus,
                   gross_salary,tax_deduction,eobi,social_security,advance_recovery,loan_recovery,other_deductions,
                   absent_deduction,total_deductions,net_salary,days_present,days_absent,overtime_hrs)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pid, eid, line["basic_salary"], line["allowances"], line["overtime"], line["bonus"],
                 line["gross_salary"], line["tax_deduction"], line["eobi"], line["social_security"],
                 line["advance_recovery"], line["loan_recovery"], line["other_deductions"],
                 line.get("absent_deduction", 0),
                 line["total_deductions"], line["net_salary"], line["days_present"],
                 line["days_absent"], line["overtime_hrs"]),
            )
            total_gross += line["gross_salary"]
            total_ded += line["total_deductions"]
            total_net += line["net_salary"]
        conn.execute(
            "UPDATE payroll_runs SET total_gross=?,total_deductions=?,total_net=? WHERE id=?",
            (total_gross, total_ded, total_net, pid),
        )
        return pid


def list_missing_active_employees_for_payroll(payroll_id):
    """Active employees not yet on this payroll run (joiners after generate)."""
    from database import get_connection, rows_to_list

    with get_connection() as conn:
        run = conn.execute(
            "SELECT id, status, payroll_month, payroll_year, document_no FROM payroll_runs WHERE id=?",
            (payroll_id,),
        ).fetchone()
        if not run:
            raise ValueError("Payroll run not found")
        rows = conn.execute(
            """
            SELECT e.id, e.code, e.full_name, e.department
            FROM employees e
            WHERE e.is_active=1
              AND LOWER(COALESCE(e.employment_status,'active'))='active'
              AND e.id NOT IN (
                    SELECT employee_id FROM payroll_lines WHERE payroll_id=?
              )
            ORDER BY e.full_name
            """,
            (payroll_id,),
        ).fetchall()
        return {
            "payroll_id": int(run["id"]),
            "document_no": run["document_no"],
            "status": (run["status"] or "").lower(),
            "payroll_month": int(run["payroll_month"] or 0),
            "payroll_year": int(run["payroll_year"] or 0),
            "missing": rows_to_list(rows),
        }


def add_missing_employees_to_payroll(payroll_id, user_id=None):
    """Append active employees missing from a draft payroll (new joiners).

    Calculates each line from salary structure + attendance like generate.
    Does not change existing lines or paid employees.
    """
    from database import get_connection

    with get_connection() as conn:
        run = conn.execute(
            "SELECT id, status, payroll_month, payroll_year, document_no FROM payroll_runs WHERE id=?",
            (payroll_id,),
        ).fetchone()
        if not run:
            raise ValueError("Payroll run not found")
        status = (run["status"] or "").lower()
        if status != "draft":
            raise ValueError(
                f"Can only add employees to a draft payroll "
                f"(current status: {(run['status'] or '').upper()}). "
                "Unapprove on Process / Pay first if needed."
            )
        month = int(run["payroll_month"])
        year = int(run["payroll_year"])
        missing = conn.execute(
            """
            SELECT e.id, e.code, e.full_name
            FROM employees e
            WHERE e.is_active=1
              AND LOWER(COALESCE(e.employment_status,'active'))='active'
              AND e.id NOT IN (
                    SELECT employee_id FROM payroll_lines WHERE payroll_id=?
              )
            ORDER BY e.full_name
            """,
            (payroll_id,),
        ).fetchall()
        if not missing:
            return {
                "added": 0,
                "employees": [],
                "document_no": run["document_no"],
                "payroll_id": int(payroll_id),
            }

        added = []
        for emp in missing:
            eid = int(emp["id"])
            line = _calc_payroll_line(conn, eid, month, year, payroll_id)
            conn.execute(
                """INSERT INTO payroll_lines(payroll_id,employee_id,basic_salary,allowances,overtime,bonus,
                   gross_salary,tax_deduction,eobi,social_security,advance_recovery,loan_recovery,other_deductions,
                   absent_deduction,total_deductions,net_salary,days_present,days_absent,overtime_hrs)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (payroll_id, eid, line["basic_salary"], line["allowances"], line["overtime"], line["bonus"],
                 line["gross_salary"], line["tax_deduction"], line["eobi"], line["social_security"],
                 line["advance_recovery"], line["loan_recovery"], line["other_deductions"],
                 line.get("absent_deduction", 0),
                 line["total_deductions"], line["net_salary"], line["days_present"],
                 line["days_absent"], line["overtime_hrs"]),
            )
            added.append({
                "employee_id": eid,
                "code": emp["code"],
                "name": emp["full_name"],
                "net_salary": line["net_salary"],
                "days_present": line["days_present"],
                "days_absent": line["days_absent"],
            })
        _refresh_payroll_run_totals(conn, payroll_id)
        return {
            "added": len(added),
            "employees": added,
            "document_no": run["document_no"],
            "payroll_id": int(payroll_id),
        }


def _period_bounds(month, year):
    period_start = f"{year}-{month:02d}-01"
    if month == 12:
        period_end = f"{year}-12-31"
    else:
        from datetime import timedelta
        end_dt = datetime.strptime(f"{year}-{month+1:02d}-01", "%Y-%m-%d") - timedelta(days=1)
        period_end = end_dt.strftime("%Y-%m-%d")
    return period_start, period_end


def _iso_day(raw):
    s = str(raw or "").strip()[:10]
    return s if len(s) >= 10 else None


def _employment_bounds_in_period(conn, employee_id, period_start, period_end):
    """Clip payroll period to joining_date … leaving_date (when set)."""
    emp = conn.execute(
        "SELECT joining_date, leaving_date, employment_status FROM employees WHERE id=?",
        (employee_id,),
    ).fetchone()
    start = _iso_day(period_start)
    end = _iso_day(period_end)
    if not emp:
        return start, end, False
    join_d = _iso_day(emp["joining_date"])
    leave_d = _iso_day(emp["leaving_date"])
    if join_d and join_d > start:
        start = join_d
    if leave_d and leave_d < end:
        end = leave_d
    if start > end:
        # Not employed in this month
        return start, end, True
    partial = start > _iso_day(period_start) or end < _iso_day(period_end)
    return start, end, partial


def calc_earned_basic(basic_salary, year, month, paid_days):
    """Basic earned for partial month = Basic ÷ calendar days × paid days."""
    basic = float(basic_salary or 0)
    paid = float(paid_days or 0)
    days = days_in_month(year, month) if year and month else 0
    if basic <= 0 or days <= 0 or paid <= 0:
        return 0.0
    return round(basic / days * paid, 2)


def _attendance_days_for_period(conn, employee_id, period_start, period_end):
    """Present / absent / OT hours for payroll.

    Present includes present/late/overtime, plus public & weekly holidays
    when the employee actually worked at least one day in the period.
    Holidays alone never create Present for someone with zero work marks.

    Calendar holidays are only auto-filled between the employee's first and
    last marked attendance day in the period (never future offs after they
    stopped marking — e.g. mid-month resign).

    Sandwich rule (always applied): a public or weekly holiday that sits
    between the employee's own leaves counts as leave (not present); between
    own absents counts as absent. Consecutive holidays between the same
    flank type are all converted.
    """
    from datetime import timedelta

    rows = conn.execute(
        """SELECT att_date, LOWER(COALESCE(status,'')) AS status,
                  COALESCE(overtime_hrs,0) AS ot
           FROM attendance
           WHERE employee_id=? AND att_date>=? AND att_date<=?""",
        (employee_id, period_start, period_end),
    ).fetchall()
    att_by_date = {}
    overtime_hrs = 0.0
    for row in rows:
        r = dict(row)
        d = str(r["att_date"] or "")[:10]
        if not d:
            continue
        att_by_date[d] = (r["status"] or "").strip().lower()
        overtime_hrs += float(r["ot"] or 0)

    try:
        from db_holidays import holidays_in_range
        hol_map = holidays_in_range(period_start, period_end) or {}
    except Exception:
        hol_map = {}

    holiday_statuses = {"public_holiday", "weekly_holiday"}
    present_work = {"present", "late", "overtime"}
    flank_statuses = {"leave", "absent", "present", "late", "overtime", "half_day"}
    # Holidays count as Present only if the employee showed up at least once
    has_work = any(st in present_work or st == "half_day" for st in att_by_date.values())

    # Do not invent Present on calendar offs after the last marked day
    marked_dates = sorted(att_by_date.keys())
    mark_lo = marked_dates[0] if marked_dates else None
    mark_hi = marked_dates[-1] if marked_dates else None

    # Effective status per calendar day in the period
    try:
        start_dt = datetime.strptime(str(period_start)[:10], "%Y-%m-%d")
        end_dt = datetime.strptime(str(period_end)[:10], "%Y-%m-%d")
    except ValueError:
        return {
            "days_present": 0.0,
            "days_absent": 0.0,
            "days_leave": 0.0,
            "overtime_hrs": round(overtime_hrs, 2),
        }

    effective = {}
    cur = start_dt
    while cur <= end_dt:
        iso = cur.strftime("%Y-%m-%d")
        marked = att_by_date.get(iso)
        if marked:
            effective[iso] = marked
        elif iso in hol_map and mark_lo and mark_hi and mark_lo <= iso <= mark_hi:
            info = hol_map[iso] or {}
            effective[iso] = (info.get("status") or "public_holiday").strip().lower()
        # else: no record — not a holiday fill outside marked span
        cur += timedelta(days=1)

    dates = sorted(effective.keys())

    def _flank(idx: int, direction: int):
        """Nearest non-holiday decisive status left (−1) or right (+1)."""
        j = idx + direction
        while 0 <= j < len(dates):
            st = effective.get(dates[j]) or ""
            if st in holiday_statuses:
                j += direction
                continue
            if st in flank_statuses:
                # present-like flanks
                if st in ("present", "late", "overtime", "half_day"):
                    return "present"
                return st  # leave or absent
            j += direction
        return None

    # Iterate until sandwich conversions settle (holiday chains)
    for _ in range(len(dates) + 2):
        changed = False
        for i, d in enumerate(dates):
            st = effective.get(d) or ""
            if st not in holiday_statuses:
                continue
            left = _flank(i, -1)
            right = _flank(i, 1)
            if left == "leave" and right == "leave":
                effective[d] = "leave"
                changed = True
            elif left == "absent" and right == "absent":
                effective[d] = "absent"
                changed = True
        if not changed:
            break

    days_present = 0.0
    days_absent = 0.0
    days_leave = 0.0
    for d, st in effective.items():
        if st in present_work:
            days_present += 1
        elif st in holiday_statuses:
            # Paid holiday only for people who worked in the month
            if has_work:
                days_present += 1
        elif st == "absent":
            days_absent += 1
        elif st == "leave":
            days_leave += 1
        # half_day: not counted as full present (unchanged policy)

    return {
        "days_present": round(days_present, 1),
        "days_absent": round(days_absent, 1),
        "days_leave": round(days_leave, 1),
        "overtime_hrs": round(overtime_hrs, 2),
    }


def _calc_payroll_line(conn, employee_id, month, year, payroll_id):
    period_start, period_end = _period_bounds(month, year)
    emp_start, emp_end, partial = _employment_bounds_in_period(
        conn, employee_id, period_start, period_end,
    )

    struct = conn.execute(
        "SELECT * FROM salary_structures WHERE employee_id=? AND is_active=1 ORDER BY effective_from DESC LIMIT 1",
        (employee_id,),
    ).fetchone()
    emp = conn.execute("SELECT basic_salary FROM employees WHERE id=?", (employee_id,)).fetchone()
    basic = (dict(struct)["basic_salary"] if struct else 0) or (emp[0] if emp else 0)
    allowances = 0
    if struct:
        s = dict(struct)
        allowances = (s.get("housing_allowance") or 0) + (s.get("transport_allowance") or 0) + \
                     (s.get("medical_allowance") or 0) + (s.get("other_allowance") or 0)

    if emp_start > emp_end:
        att = {"days_present": 0.0, "days_absent": 0.0, "days_leave": 0.0, "overtime_hrs": 0.0}
    else:
        att = _attendance_days_for_period(conn, employee_id, emp_start, emp_end)
    days_present = att["days_present"]
    days_absent = att["days_absent"]
    days_leave = float(att.get("days_leave") or 0)
    overtime_hrs = att["overtime_hrs"]

    # OT = Basic / calendar days in month / 6 × hours (from attendance)
    overtime = calc_overtime_amount(basic, year, month, overtime_hrs)
    bonus = 0

    # Tax / EOBI / SS default nil — enter manually on Edit Lines if required
    tax = eobi = ss = 0.0

    if partial:
        # Mid-month join / resign: pay only earned days (present + paid leave).
        # Absent already excluded from paid_days — do not deduct again.
        paid_days = days_present + days_leave
        basic_earned = calc_earned_basic(basic, year, month, paid_days)
        gross = basic_earned + allowances + overtime + bonus
        absent_deduction = 0.0
        # Store full scale basic on the line for reference; gross reflects earned
        line_basic = basic
    else:
        # Full month: full basic, deduct unpaid absents only (leave stays paid)
        line_basic = basic
        gross = basic + allowances + overtime + bonus
        absent_deduction = calc_absent_deduction(basic, year, month, days_absent)

    advance_recovery = _recover_advances(conn, employee_id, payroll_id, period_end)
    loan_recovery = _recover_loans(conn, employee_id, payroll_id, period_end)

    total_ded = tax + eobi + ss + advance_recovery + loan_recovery + absent_deduction
    net = gross - total_ded
    return {
        "basic_salary": line_basic,
        "allowances": allowances,
        "overtime": overtime,
        "bonus": bonus,
        "gross_salary": round(gross, 2),
        "tax_deduction": tax,
        "eobi": eobi,
        "social_security": ss,
        "advance_recovery": advance_recovery,
        "loan_recovery": loan_recovery,
        "other_deductions": 0,
        "absent_deduction": absent_deduction,
        "total_deductions": round(total_ded, 2),
        "net_salary": round(net, 2),
        "days_present": days_present,
        "days_absent": days_absent,
        "overtime_hrs": overtime_hrs,
        "partial_month": partial,
        "paid_days": days_present + days_leave if partial else None,
    }


def _recover_advances(conn, employee_id, payroll_id, due_date):
    return _recover_advances_capped(
        conn, employee_id, payroll_id, due_date, target_amount=None,
    )


def _undo_payroll_recoveries(conn, payroll_id):
    """Reverse advance/loan installments marked recovered during payroll generation."""
    for row in conn.execute(
        "SELECT id, advance_id, amount FROM advance_recovery_schedule WHERE payroll_id=?",
        (payroll_id,),
    ).fetchall():
        sched_id, adv_id, amt = row[0], row[1], float(row[2] or 0)
        adv = conn.execute(
            "SELECT recovered_amount, outstanding_amount, amount FROM employee_advances WHERE id=?",
            (adv_id,),
        ).fetchone()
        if adv and amt > 0:
            new_rec = max(0.0, float(adv[0] or 0) - amt)
            new_out = min(float(adv[2] or 0), float(adv[1] or 0) + amt)
            new_status = "closed" if new_out <= 0.01 else "issued"
            conn.execute(
                "UPDATE employee_advances SET recovered_amount=?, outstanding_amount=?, status=? WHERE id=?",
                (new_rec, new_out, new_status, adv_id),
            )
        conn.execute(
            "UPDATE advance_recovery_schedule SET recovered=0, recovered_date=NULL, payroll_id=NULL WHERE id=?",
            (sched_id,),
        )
    for row in conn.execute(
        "SELECT id, loan_id, amount FROM loan_installments WHERE payroll_id=?",
        (payroll_id,),
    ).fetchall():
        inst_id, loan_id, amt = row[0], row[1], float(row[2] or 0)
        ln = conn.execute(
            "SELECT recovered_amount, outstanding_amount, amount FROM employee_loans WHERE id=?",
            (loan_id,),
        ).fetchone()
        if ln and amt > 0:
            new_rec = max(0.0, float(ln[0] or 0) - amt)
            new_out = min(float(ln[2] or 0), float(ln[1] or 0) + amt)
            new_status = "closed" if new_out <= 0.01 else "issued"
            conn.execute(
                "UPDATE employee_loans SET recovered_amount=?, outstanding_amount=?, status=? WHERE id=?",
                (new_rec, new_out, new_status, loan_id),
            )
        conn.execute(
            "UPDATE loan_installments SET recovered=0, recovered_date=NULL, payroll_id=NULL WHERE id=?",
            (inst_id,),
        )


def _recover_loans(conn, employee_id, payroll_id, due_date):
    return _recover_loans_capped(
        conn, employee_id, payroll_id, due_date, target_amount=None,
    )


def _loan_recovery_capacity(conn, employee_id, payroll_id) -> float:
    """Max loan recovery this draft line may hold — full remaining balance anytime.

    = amount already on this payroll
      + loan outstanding still open
      + recoveries sitting on other draft/unpaid payrolls (reclaimed on save)
    """
    on_pay = float(conn.execute(
        """SELECT COALESCE(SUM(li.amount),0)
           FROM loan_installments li
           JOIN employee_loans l ON l.id=li.loan_id
           WHERE li.payroll_id=? AND l.employee_id=? AND COALESCE(li.recovered,0)=1""",
        (payroll_id, employee_id),
    ).fetchone()[0] or 0)
    outstanding = float(conn.execute(
        """SELECT COALESCE(SUM(outstanding_amount),0) FROM employee_loans
           WHERE employee_id=? AND status IN ('issued','closed') AND outstanding_amount>0""",
        (employee_id,),
    ).fetchone()[0] or 0)
    other_draft = float(conn.execute(
        """SELECT COALESCE(SUM(li.amount),0)
           FROM loan_installments li
           JOIN employee_loans l ON l.id=li.loan_id
           JOIN payroll_runs pr ON pr.id=li.payroll_id
           WHERE l.employee_id=?
             AND li.payroll_id<>?
             AND COALESCE(li.recovered,0)=1
             AND LOWER(COALESCE(pr.status,'')) NOT IN ('posted','paid','closed')
             AND NOT EXISTS (
                 SELECT 1 FROM payroll_lines pl
                 WHERE pl.payroll_id=li.payroll_id
                   AND pl.employee_id=l.employee_id
                   AND COALESCE(pl.paid_status,'')='paid'
             )""",
        (employee_id, payroll_id),
    ).fetchone()[0] or 0)
    return round(on_pay + outstanding + other_draft, 2)


def _advance_recovery_capacity(conn, employee_id, payroll_id) -> float:
    """Max advance recovery — full effective outstanding due by this payroll month."""
    pr = conn.execute(
        "SELECT payroll_month, payroll_year FROM payroll_runs WHERE id=?",
        (payroll_id,),
    ).fetchone()
    payroll_ym = "9999-12"
    if pr:
        try:
            payroll_ym = f"{int(pr['payroll_year']):04d}-{int(pr['payroll_month']):02d}"
        except (TypeError, ValueError, KeyError):
            pass
    # Stored outstanding due by this month + provisional recoveries on draft payrolls
    # for those same advances (so full settle can reclaim other draft months).
    stored = float(conn.execute(
        """SELECT COALESCE(SUM(outstanding_amount),0) FROM employee_advances
           WHERE employee_id=? AND status IN ('issued','closed') AND outstanding_amount>0
             AND (
               salary_month IS NULL OR TRIM(COALESCE(salary_month,''))=''
               OR substr(salary_month,1,7) <= ?
             )""",
        (employee_id, payroll_ym),
    ).fetchone()[0] or 0)
    prov = _provisional_advance_recovery_map(conn, employee_id)
    if not prov:
        return round(stored, 2)
    bump = 0.0
    for aid, amt in prov.items():
        row = conn.execute(
            """SELECT salary_month, outstanding_amount FROM employee_advances WHERE id=?""",
            (int(aid),),
        ).fetchone()
        if not row:
            continue
        sm = (row["salary_month"] if hasattr(row, "keys") else row[0]) or ""
        sm7 = str(sm).strip()[:7]
        if sm7 and sm7 > payroll_ym:
            continue
        bump += float(amt or 0)
    return round(stored + bump, 2)


def _undo_loan_recoveries_for_employee(conn, payroll_id, employee_id) -> list[int]:
    """Reverse loan installments on this payroll for one employee. Returns affected loan ids."""
    rows = conn.execute(
        """SELECT li.id, li.loan_id, li.amount
           FROM loan_installments li
           JOIN employee_loans l ON l.id=li.loan_id
           WHERE li.payroll_id=? AND l.employee_id=? AND li.recovered=1""",
        (payroll_id, employee_id),
    ).fetchall()
    affected = []
    for row in rows:
        inst_id, loan_id, amt = row[0], row[1], float(row[2] or 0)
        affected.append(int(loan_id))
        ln = conn.execute(
            "SELECT recovered_amount, outstanding_amount, amount FROM employee_loans WHERE id=?",
            (loan_id,),
        ).fetchone()
        if ln and amt > 0:
            new_rec = max(0.0, float(ln[0] or 0) - amt)
            new_out = min(float(ln[2] or 0), float(ln[1] or 0) + amt)
            conn.execute(
                "UPDATE employee_loans SET recovered_amount=?, outstanding_amount=?, status=? WHERE id=?",
                (new_rec, new_out, "closed" if new_out <= 0.01 else "issued", loan_id),
            )
        conn.execute(
            "UPDATE loan_installments SET recovered=0, recovered_date=NULL, payroll_id=NULL WHERE id=?",
            (inst_id,),
        )
    return sorted(set(affected))


def _rebuild_unpaid_loan_installments(conn, loan_id):
    """Recreate unpaid installments from current outstanding (keeps recovered history)."""
    ln = conn.execute(
        "SELECT outstanding_amount, monthly_installment, amount FROM employee_loans WHERE id=?",
        (loan_id,),
    ).fetchone()
    if not ln:
        return
    outstanding = round(float(ln[0] or 0), 2)
    monthly = float(ln[1] or 0) or outstanding
    conn.execute(
        "DELETE FROM loan_installments WHERE loan_id=? AND COALESCE(recovered,0)=0",
        (loan_id,),
    )
    if outstanding <= 0.01:
        return
    max_no = conn.execute(
        "SELECT COALESCE(MAX(installment_no),0) FROM loan_installments WHERE loan_id=?",
        (loan_id,),
    ).fetchone()[0]
    n = int(max_no or 0)
    left = outstanding
    # due dates: 30 days from today-ish; use last recovered due or issue cadence
    last_due = conn.execute(
        """SELECT due_date FROM loan_installments WHERE loan_id=? AND recovered=1
           ORDER BY installment_no DESC LIMIT 1""",
        (loan_id,),
    ).fetchone()
    from datetime import timedelta
    if last_due and last_due[0]:
        try:
            base = datetime.strptime(str(last_due[0])[:10], "%Y-%m-%d")
        except ValueError:
            base = datetime.now()
    else:
        base = datetime.now()
    while left > 0.01:
        n += 1
        amt = round(min(monthly, left), 2)
        if amt <= 0:
            break
        due = (base + timedelta(days=30 * (n - int(max_no or 0)))).strftime("%Y-%m-%d")
        conn.execute(
            "INSERT INTO loan_installments(loan_id,installment_no,due_date,amount) VALUES(?,?,?,?)",
            (loan_id, n, due, amt),
        )
        left = round(left - amt, 2)


def _recover_loans_capped(conn, employee_id, payroll_id, due_date, target_amount=None):
    """Recover loan installments; if target_amount set, stop at that total (partial OK).

    Auto mode (target_amount=None): at most **one** installment per loan for this
    payroll — never the full outstanding balance in one run.
    """
    total = 0.0
    cap = None if target_amount is None else round(float(target_amount), 2)
    loans = conn.execute(
        """SELECT id, monthly_installment, outstanding_amount FROM employee_loans
           WHERE employee_id=? AND status='issued' AND outstanding_amount>0
           ORDER BY id""",
        (employee_id,),
    ).fetchall()
    for ln in loans:
        if cap is not None and total >= cap - 0.009:
            break
        l = dict(ln)
        auto_one_installment = cap is None
        took = 0
        while float(l["outstanding_amount"] or 0) > 0.01:
            if cap is not None and total >= cap - 0.009:
                break
            if auto_one_installment and took >= 1:
                break
            inst = conn.execute(
                """SELECT id, amount FROM loan_installments
                   WHERE loan_id=? AND COALESCE(recovered,0)=0
                   ORDER BY installment_no LIMIT 1""",
                (l["id"],),
            ).fetchone()
            if inst:
                inst_id, inst_amt = inst[0], float(inst[1] or 0)
            else:
                inst_id, inst_amt = None, 0.0
            full = inst_amt or float(l["monthly_installment"] or 0)
            if full <= 0.009:
                # Do not fall back to full outstanding in auto mode
                if cap is None:
                    break
                full = float(l["outstanding_amount"] or 0)
            amt = min(full, float(l["outstanding_amount"] or 0))
            if cap is not None:
                amt = min(amt, round(cap - total, 2))
            amt = round(amt, 2)
            if amt <= 0:
                break
            new_out = round(float(l["outstanding_amount"]) - amt, 2)
            new_rec = float(conn.execute(
                "SELECT recovered_amount FROM employee_loans WHERE id=?", (l["id"],)
            ).fetchone()[0] or 0) + amt
            conn.execute(
                "UPDATE employee_loans SET recovered_amount=?, outstanding_amount=?, status=? WHERE id=?",
                (new_rec, new_out, "closed" if new_out <= 0.01 else "issued", l["id"]),
            )
            l["outstanding_amount"] = new_out
            if inst_id:
                leftover = round(full - amt, 2)
                conn.execute(
                    """UPDATE loan_installments
                       SET amount=?, recovered=1, recovered_date=?, payroll_id=? WHERE id=?""",
                    (amt, due_date, payroll_id, inst_id),
                )
                if leftover > 0.01:
                    nxt = conn.execute(
                        """SELECT id, amount FROM loan_installments
                           WHERE loan_id=? AND COALESCE(recovered,0)=0
                           ORDER BY installment_no LIMIT 1""",
                        (l["id"],),
                    ).fetchone()
                    if nxt:
                        conn.execute(
                            "UPDATE loan_installments SET amount=? WHERE id=?",
                            (round(float(nxt[1] or 0) + leftover, 2), nxt[0]),
                        )
                    else:
                        max_no = conn.execute(
                            "SELECT COALESCE(MAX(installment_no),0) FROM loan_installments WHERE loan_id=?",
                            (l["id"],),
                        ).fetchone()[0]
                        conn.execute(
                            """INSERT INTO loan_installments(
                                   loan_id, installment_no, due_date, amount
                               ) VALUES(?,?,?,?)""",
                            (l["id"], int(max_no) + 1, due_date, leftover),
                        )
            else:
                max_no = conn.execute(
                    "SELECT COALESCE(MAX(installment_no),0) FROM loan_installments WHERE loan_id=?",
                    (l["id"],),
                ).fetchone()[0]
                conn.execute(
                    """INSERT INTO loan_installments(
                           loan_id, installment_no, due_date, amount,
                           recovered, recovered_date, payroll_id
                       ) VALUES(?,?,?,?,1,?,?)""",
                    (l["id"], int(max_no) + 1, due_date, amt, due_date, payroll_id),
                )
            total = round(total + amt, 2)
            took += 1
            if auto_one_installment:
                break
    return total


def _undo_advance_recoveries_for_employee(conn, payroll_id, employee_id) -> list[int]:
    rows = conn.execute(
        """SELECT s.id, s.advance_id, s.amount
           FROM advance_recovery_schedule s
           JOIN employee_advances a ON a.id=s.advance_id
           WHERE s.payroll_id=? AND a.employee_id=? AND s.recovered=1""",
        (payroll_id, employee_id),
    ).fetchall()
    affected = []
    for row in rows:
        sched_id, adv_id, amt = row[0], row[1], float(row[2] or 0)
        affected.append(int(adv_id))
        adv = conn.execute(
            "SELECT recovered_amount, outstanding_amount, amount FROM employee_advances WHERE id=?",
            (adv_id,),
        ).fetchone()
        if adv and amt > 0:
            new_rec = max(0.0, float(adv[0] or 0) - amt)
            new_out = min(float(adv[2] or 0), float(adv[1] or 0) + amt)
            conn.execute(
                "UPDATE employee_advances SET recovered_amount=?, outstanding_amount=?, status=? WHERE id=?",
                (new_rec, new_out, "closed" if new_out <= 0.01 else "issued", adv_id),
            )
        conn.execute(
            "UPDATE advance_recovery_schedule SET recovered=0, recovered_date=NULL, payroll_id=NULL WHERE id=?",
            (sched_id,),
        )
    return sorted(set(affected))


def _rebuild_unpaid_advance_schedule(conn, advance_id):
    adv = conn.execute(
        "SELECT outstanding_amount, monthly_recovery, amount FROM employee_advances WHERE id=?",
        (advance_id,),
    ).fetchone()
    if not adv:
        return
    outstanding = round(float(adv[0] or 0), 2)
    monthly = float(adv[1] or 0) or outstanding
    conn.execute(
        "DELETE FROM advance_recovery_schedule WHERE advance_id=? AND COALESCE(recovered,0)=0",
        (advance_id,),
    )
    if outstanding <= 0.01:
        return
    max_no = conn.execute(
        "SELECT COALESCE(MAX(installment_no),0) FROM advance_recovery_schedule WHERE advance_id=?",
        (advance_id,),
    ).fetchone()[0]
    n = int(max_no or 0)
    left = outstanding
    from datetime import timedelta
    base = datetime.now()
    while left > 0.01:
        n += 1
        amt = round(min(monthly, left), 2)
        if amt <= 0:
            break
        due = (base + timedelta(days=30 * (n - int(max_no or 0)))).strftime("%Y-%m-%d")
        conn.execute(
            """INSERT INTO advance_recovery_schedule(advance_id,installment_no,due_date,amount)
               VALUES(?,?,?,?)""",
            (advance_id, n, due, amt),
        )
        left = round(left - amt, 2)


def _recover_advances_capped(conn, employee_id, payroll_id, due_date, target_amount=None):
    """Recover advance schedule; auto mode = one installment per advance this payroll.

    Advances with ``salary_month`` only recover on that payroll month or later
    (posting date can be later — e.g. cash on 6 Sep for August salary).
    """
    total = 0.0
    cap = None if target_amount is None else round(float(target_amount), 2)
    pr = conn.execute(
        "SELECT payroll_month, payroll_year FROM payroll_runs WHERE id=?",
        (payroll_id,),
    ).fetchone()
    payroll_ym = None
    if pr:
        try:
            payroll_ym = f"{int(pr['payroll_year']):04d}-{int(pr['payroll_month']):02d}"
        except (TypeError, ValueError, KeyError):
            payroll_ym = None
    advances = conn.execute(
        """SELECT id, monthly_recovery, outstanding_amount, salary_month FROM employee_advances
           WHERE employee_id=? AND status='issued' AND outstanding_amount>0
           ORDER BY id""",
        (employee_id,),
    ).fetchall()
    for adv in advances:
        if cap is not None and total >= cap - 0.009:
            break
        a = dict(adv)
        sm = (a.get("salary_month") or "").strip()[:7]
        if sm and payroll_ym and sm > payroll_ym:
            # Scheduled for a later salary month — skip this payroll
            continue
        auto_one = cap is None
        took = 0
        while float(a["outstanding_amount"] or 0) > 0.01:
            if cap is not None and total >= cap - 0.009:
                break
            if auto_one and took >= 1:
                break
            sched = conn.execute(
                """SELECT id, amount FROM advance_recovery_schedule
                   WHERE advance_id=? AND COALESCE(recovered,0)=0
                   ORDER BY installment_no LIMIT 1""",
                (a["id"],),
            ).fetchone()
            full = float((sched[1] if sched else 0) or a["monthly_recovery"] or 0)
            if full <= 0.009:
                if cap is None:
                    break
                full = float(a["outstanding_amount"] or 0)
            amt = min(full, float(a["outstanding_amount"] or 0))
            if cap is not None:
                amt = min(amt, round(cap - total, 2))
            amt = round(amt, 2)
            if amt <= 0:
                break
            new_out = round(float(a["outstanding_amount"]) - amt, 2)
            new_rec = float(conn.execute(
                "SELECT recovered_amount FROM employee_advances WHERE id=?", (a["id"],)
            ).fetchone()[0] or 0) + amt
            conn.execute(
                "UPDATE employee_advances SET recovered_amount=?, outstanding_amount=?, status=? WHERE id=?",
                (new_rec, new_out, "closed" if new_out <= 0.01 else "issued", a["id"]),
            )
            a["outstanding_amount"] = new_out
            if sched:
                leftover = round(full - amt, 2)
                conn.execute(
                    """UPDATE advance_recovery_schedule
                       SET amount=?, recovered=1, recovered_date=?, payroll_id=? WHERE id=?""",
                    (amt, due_date, payroll_id, sched[0]),
                )
                if leftover > 0.01:
                    nxt = conn.execute(
                        """SELECT id, amount FROM advance_recovery_schedule
                           WHERE advance_id=? AND COALESCE(recovered,0)=0
                           ORDER BY installment_no LIMIT 1""",
                        (a["id"],),
                    ).fetchone()
                    if nxt:
                        conn.execute(
                            "UPDATE advance_recovery_schedule SET amount=? WHERE id=?",
                            (round(float(nxt[1] or 0) + leftover, 2), nxt[0]),
                        )
                    else:
                        max_no = conn.execute(
                            "SELECT COALESCE(MAX(installment_no),0) FROM advance_recovery_schedule WHERE advance_id=?",
                            (a["id"],),
                        ).fetchone()[0]
                        conn.execute(
                            """INSERT INTO advance_recovery_schedule(
                                   advance_id, installment_no, due_date, amount
                               ) VALUES(?,?,?,?)""",
                            (a["id"], int(max_no) + 1, due_date, leftover),
                        )
            else:
                max_no = conn.execute(
                    "SELECT COALESCE(MAX(installment_no),0) FROM advance_recovery_schedule WHERE advance_id=?",
                    (a["id"],),
                ).fetchone()[0]
                conn.execute(
                    """INSERT INTO advance_recovery_schedule(
                           advance_id, installment_no, due_date, amount,
                           recovered, recovered_date, payroll_id
                       ) VALUES(?,?,?,?,1,?,?)""",
                    (a["id"], int(max_no) + 1, due_date, amt, due_date, payroll_id),
                )
            total = round(total + amt, 2)
            took += 1
            if auto_one:
                break
    return total


def _adjust_payroll_line_recovery_fields(conn, line_id, *, loan_delta=0.0, advance_delta=0.0):
    """Apply delta to loan/advance recovery on a draft line and refresh net + run totals."""
    row = conn.execute(
        """SELECT id, payroll_id, advance_recovery, loan_recovery, tax_deduction, eobi,
                  social_security, other_deductions, absent_deduction, gross_salary
           FROM payroll_lines WHERE id=?""",
        (int(line_id),),
    ).fetchone()
    if not row:
        return
    row = dict(row)
    new_loan = max(0.0, round(float(row.get("loan_recovery") or 0) + float(loan_delta or 0), 2))
    new_adv = max(0.0, round(float(row.get("advance_recovery") or 0) + float(advance_delta or 0), 2))
    total_ded = round(
        float(row.get("tax_deduction") or 0)
        + float(row.get("eobi") or 0)
        + float(row.get("social_security") or 0)
        + new_adv + new_loan
        + float(row.get("other_deductions") or 0)
        + float(row.get("absent_deduction") or 0),
        2,
    )
    net = round(float(row.get("gross_salary") or 0) - total_ded, 2)
    conn.execute(
        """UPDATE payroll_lines SET advance_recovery=?, loan_recovery=?,
           total_deductions=?, net_salary=? WHERE id=?""",
        (new_adv, new_loan, total_ded, net, int(line_id)),
    )
    _refresh_payroll_run_totals(conn, int(row["payroll_id"]))


def _reclaim_other_draft_loan_recoveries(conn, employee_id, keep_payroll_id, need_amount) -> float:
    """Free loan outstanding by undoing recoveries on other draft/unpaid payrolls.

    Used when settling the full loan on one month while later draft months already
    hold installments. Returns amount freed.
    """
    need = round(max(0.0, float(need_amount or 0)), 2)
    if need <= 0.01:
        return 0.0
    rows = conn.execute(
        """SELECT li.id AS inst_id, li.loan_id, li.amount, li.payroll_id, pl.id AS line_id
           FROM loan_installments li
           JOIN employee_loans l ON l.id=li.loan_id
           JOIN payroll_runs pr ON pr.id=li.payroll_id
           JOIN payroll_lines pl
             ON pl.payroll_id=li.payroll_id AND pl.employee_id=l.employee_id
           WHERE l.employee_id=?
             AND li.payroll_id<>?
             AND COALESCE(li.recovered,0)=1
             AND LOWER(COALESCE(pr.status,'')) NOT IN ('posted','paid','closed')
             AND COALESCE(pl.paid_status,'')<>'paid'
           ORDER BY pr.payroll_year DESC, pr.payroll_month DESC, li.installment_no DESC""",
        (int(employee_id), int(keep_payroll_id)),
    ).fetchall()
    freed = 0.0
    affected_loans = set()
    for row in rows:
        if freed >= need - 0.009:
            break
        r = dict(row)
        amt = round(float(r.get("amount") or 0), 2)
        if amt <= 0:
            continue
        loan_id = int(r["loan_id"])
        affected_loans.add(loan_id)
        ln = conn.execute(
            "SELECT recovered_amount, outstanding_amount, amount FROM employee_loans WHERE id=?",
            (loan_id,),
        ).fetchone()
        if ln:
            new_rec = max(0.0, float(ln[0] or 0) - amt)
            new_out = min(float(ln[2] or 0), float(ln[1] or 0) + amt)
            conn.execute(
                "UPDATE employee_loans SET recovered_amount=?, outstanding_amount=?, status=? WHERE id=?",
                (new_rec, new_out, "closed" if new_out <= 0.01 else "issued", loan_id),
            )
        conn.execute(
            "UPDATE loan_installments SET recovered=0, recovered_date=NULL, payroll_id=NULL WHERE id=?",
            (int(r["inst_id"]),),
        )
        _adjust_payroll_line_recovery_fields(conn, int(r["line_id"]), loan_delta=-amt)
        freed = round(freed + amt, 2)
    for lid in affected_loans:
        _rebuild_unpaid_loan_installments(conn, lid)
    return freed


def _reclaim_other_draft_advance_recoveries(conn, employee_id, keep_payroll_id, need_amount) -> float:
    """Free advance outstanding by undoing recoveries on other draft/unpaid payrolls."""
    need = round(max(0.0, float(need_amount or 0)), 2)
    if need <= 0.01:
        return 0.0
    rows = conn.execute(
        """SELECT s.id AS sched_id, s.advance_id, s.amount, s.payroll_id, pl.id AS line_id
           FROM advance_recovery_schedule s
           JOIN employee_advances a ON a.id=s.advance_id
           JOIN payroll_runs pr ON pr.id=s.payroll_id
           JOIN payroll_lines pl
             ON pl.payroll_id=s.payroll_id AND pl.employee_id=a.employee_id
           WHERE a.employee_id=?
             AND s.payroll_id<>?
             AND COALESCE(s.recovered,0)=1
             AND LOWER(COALESCE(pr.status,'')) NOT IN ('posted','paid','closed')
             AND COALESCE(pl.paid_status,'')<>'paid'
           ORDER BY pr.payroll_year DESC, pr.payroll_month DESC, s.installment_no DESC""",
        (int(employee_id), int(keep_payroll_id)),
    ).fetchall()
    freed = 0.0
    affected = set()
    for row in rows:
        if freed >= need - 0.009:
            break
        r = dict(row)
        amt = round(float(r.get("amount") or 0), 2)
        if amt <= 0:
            continue
        adv_id = int(r["advance_id"])
        affected.add(adv_id)
        adv = conn.execute(
            "SELECT recovered_amount, outstanding_amount, amount FROM employee_advances WHERE id=?",
            (adv_id,),
        ).fetchone()
        if adv:
            new_rec = max(0.0, float(adv[0] or 0) - amt)
            new_out = min(float(adv[2] or 0), float(adv[1] or 0) + amt)
            conn.execute(
                "UPDATE employee_advances SET recovered_amount=?, outstanding_amount=?, status=? WHERE id=?",
                (new_rec, new_out, "closed" if new_out <= 0.01 else "issued", adv_id),
            )
        conn.execute(
            "UPDATE advance_recovery_schedule SET recovered=0, recovered_date=NULL, payroll_id=NULL WHERE id=?",
            (int(r["sched_id"]),),
        )
        _adjust_payroll_line_recovery_fields(conn, int(r["line_id"]), advance_delta=-amt)
        freed = round(freed + amt, 2)
    for aid in affected:
        _rebuild_unpaid_advance_schedule(conn, aid)
    return freed


def _resync_payroll_line_recoveries(
    conn, payroll_id, employee_id, *, advance_amount, loan_amount, due_date,
):
    """Align advance/loan ledgers to edited payroll line amounts (draft only).

    Partial recovery (e.g. loan 5,000 instead of full installment):
      - This month recovers only the edited amount
      - Outstanding increases by the shortfall
      - Shortfall is added to the next unpaid installment (due next month)
    Full settlement anytime: capacity is the full remaining loan/advance; recoveries
    sitting on other draft months are reclaimed onto this payroll when needed.
    GL is not posted until payroll is posted; then credits 100180 for the
    amounts on the lines (same account as advances).
    """
    adv_target = round(max(0.0, float(advance_amount or 0)), 2)
    loan_target = round(max(0.0, float(loan_amount or 0)), 2)

    max_adv = _advance_recovery_capacity(conn, employee_id, payroll_id)
    max_loan = _loan_recovery_capacity(conn, employee_id, payroll_id)
    if adv_target > max_adv + 0.05:
        raise ValueError(
            f"Advance recovery Rs. {adv_target:,.2f} exceeds available "
            f"Rs. {max_adv:,.2f} (full outstanding / draft recoveries)."
        )
    if loan_target > max_loan + 0.05:
        raise ValueError(
            f"Loan recovery Rs. {loan_target:,.2f} exceeds available "
            f"Rs. {max_loan:,.2f} (full outstanding / draft recoveries)."
        )

    adv_ids = _undo_advance_recoveries_for_employee(conn, payroll_id, employee_id)
    for aid in adv_ids:
        _rebuild_unpaid_advance_schedule(conn, aid)
    # Also rebuild issued advances with outstanding that may have empty schedule
    for r in conn.execute(
        """SELECT id FROM employee_advances
           WHERE employee_id=? AND status='issued' AND outstanding_amount>0.01""",
        (employee_id,),
    ).fetchall():
        if int(r[0]) not in adv_ids:
            has_unpaid = conn.execute(
                """SELECT 1 FROM advance_recovery_schedule
                   WHERE advance_id=? AND COALESCE(recovered,0)=0 LIMIT 1""",
                (r[0],),
            ).fetchone()
            if not has_unpaid:
                _rebuild_unpaid_advance_schedule(conn, int(r[0]))
    # Free advance held on other draft months if settling more than unpaid now
    open_adv = float(conn.execute(
        """SELECT COALESCE(SUM(outstanding_amount),0) FROM employee_advances
           WHERE employee_id=? AND status='issued' AND outstanding_amount>0""",
        (employee_id,),
    ).fetchone()[0] or 0)
    if adv_target > open_adv + 0.05:
        _reclaim_other_draft_advance_recoveries(
            conn, employee_id, payroll_id, round(adv_target - open_adv, 2),
        )
    actual_adv = _recover_advances_capped(
        conn, employee_id, payroll_id, due_date, target_amount=adv_target,
    )

    loan_ids = _undo_loan_recoveries_for_employee(conn, payroll_id, employee_id)
    for lid in loan_ids:
        _rebuild_unpaid_loan_installments(conn, lid)
    for r in conn.execute(
        """SELECT id FROM employee_loans
           WHERE employee_id=? AND status='issued' AND outstanding_amount>0.01""",
        (employee_id,),
    ).fetchall():
        if int(r[0]) not in loan_ids:
            has_unpaid = conn.execute(
                """SELECT 1 FROM loan_installments
                   WHERE loan_id=? AND COALESCE(recovered,0)=0 LIMIT 1""",
                (r[0],),
            ).fetchone()
            if not has_unpaid:
                _rebuild_unpaid_loan_installments(conn, int(r[0]))
    open_loan = float(conn.execute(
        """SELECT COALESCE(SUM(outstanding_amount),0) FROM employee_loans
           WHERE employee_id=? AND status='issued' AND outstanding_amount>0""",
        (employee_id,),
    ).fetchone()[0] or 0)
    if loan_target > open_loan + 0.05:
        _reclaim_other_draft_loan_recoveries(
            conn, employee_id, payroll_id, round(loan_target - open_loan, 2),
        )
    actual_loan = _recover_loans_capped(
        conn, employee_id, payroll_id, due_date, target_amount=loan_target,
    )
    return actual_adv, actual_loan


def _recalc_payroll_line_fields(data, year=None, month=None, sync_ot=None, partial_month=False, days_leave=0.0):
    """Recompute gross, total deductions, and net from editable components.

    sync_ot:
      - "from_hours": Overtime = (Basic / days / 6) × OT hrs (default when hrs > 0)
      - "from_amount": OT hrs derived from Overtime amount (prior months)
      - None: keep both values as provided (legacy / manual)

    Full month: Absent deduction = Basic × absent ÷ month days (leave is paid).
    Partial month (mid join/leave): gross Basic = Basic ÷ days × (present + leave);
    absent is already excluded from paid days so LWP deduction is zero.
    """
    basic = float(data.get("basic_salary") or 0)
    allowances = float(data.get("allowances") or 0)
    overtime = float(data.get("overtime") or 0)
    ot_hrs = float(data.get("overtime_hrs") or 0)
    bonus = float(data.get("bonus") or 0)
    days_absent = float(data.get("days_absent") or 0)
    days_present = float(data.get("days_present") or 0)
    leave_days = float(days_leave or data.get("days_leave") or 0)

    if year and month:
        if sync_ot == "from_amount":
            ot_hrs = calc_overtime_hours(basic, year, month, overtime)
        elif sync_ot == "from_hours" or (sync_ot is None and ot_hrs > 0):
            # Hours drive pay whenever OT hours are entered
            overtime = calc_overtime_amount(basic, year, month, ot_hrs)

    if partial_month and year and month:
        paid_days = days_present + leave_days
        basic_earned = calc_earned_basic(basic, year, month, paid_days)
        gross = round(basic_earned + allowances + overtime + bonus, 2)
        absent_ded = 0.0
    else:
        gross = round(basic + allowances + overtime + bonus, 2)
        if year and month:
            absent_ded = calc_absent_deduction(basic, year, month, days_absent)
        else:
            absent_ded = round(float(data.get("absent_deduction") or 0), 2)

    tax = float(data.get("tax_deduction") or 0)
    eobi = float(data.get("eobi") or 0)
    ss = float(data.get("social_security") or 0)
    adv = float(data.get("advance_recovery") or 0)
    loan = float(data.get("loan_recovery") or 0)
    other = float(data.get("other_deductions") or 0)
    total_ded = round(tax + eobi + ss + adv + loan + other + absent_ded, 2)
    net = round(gross - total_ded, 2)
    return {
        "basic_salary": basic,
        "allowances": allowances,
        "overtime": overtime,
        "bonus": bonus,
        "gross_salary": gross,
        "tax_deduction": tax,
        "eobi": eobi,
        "social_security": ss,
        "advance_recovery": adv,
        "loan_recovery": loan,
        "other_deductions": other,
        "absent_deduction": absent_ded,
        "total_deductions": total_ded,
        "net_salary": net,
        "overtime_hrs": ot_hrs,
        "days_absent": days_absent,
        "partial_month": bool(partial_month),
    }


def _refresh_payroll_run_totals(conn, payroll_id):
    rows = conn.execute(
        "SELECT gross_salary, total_deductions, net_salary FROM payroll_lines WHERE payroll_id=?",
        (payroll_id,),
    ).fetchall()
    total_gross = sum(float(r[0] or 0) for r in rows)
    total_ded = sum(float(r[1] or 0) for r in rows)
    total_net = sum(float(r[2] or 0) for r in rows)
    conn.execute(
        "UPDATE payroll_runs SET total_gross=?, total_deductions=?, total_net=? WHERE id=?",
        (total_gross, total_ded, total_net, payroll_id),
    )


def update_payroll_line(line_id, data, user_id=None, sync_ot=None):
    """Edit one payroll line (draft payroll only). Recalculates gross/net and run totals.

    When OT hours > 0, overtime pay is calculated as Basic / month_days / 6 × hours
    unless sync_ot="from_amount" (derive hours from overtime amount).
    """
    from database import get_connection
    editable = (
        "basic_salary", "allowances", "overtime", "bonus",
        "tax_deduction", "eobi", "social_security",
        "advance_recovery", "loan_recovery", "other_deductions",
        "days_present", "days_absent", "overtime_hrs",
    )
    with get_connection() as conn:
        row = conn.execute(
            """SELECT pl.*, pr.status AS payroll_status,
                      pr.payroll_year, pr.payroll_month
               FROM payroll_lines pl
               JOIN payroll_runs pr ON pl.payroll_id=pr.id
               WHERE pl.id=?""",
            (line_id,),
        ).fetchone()
        if not row:
            raise ValueError("Payroll line not found.")
        row = dict(row)
        if row["payroll_status"] != "draft":
            raise ValueError("Only draft payroll can be edited.")
        if (row.get("paid_status") or "") == "paid":
            raise ValueError(
                "This employee is already paid — voucher is locked. "
                "Only an admin can undo payment before editing."
            )
        merged = dict(row)
        for k in editable:
            if k in data:
                merged[k] = data[k]
        year_i, month_i = int(row["payroll_year"]), int(row["payroll_month"])
        period_start, period_end = _period_bounds(month_i, year_i)
        _es, _ee, partial = _employment_bounds_in_period(
            conn, int(row["employee_id"]), period_start, period_end,
        )
        calc = _recalc_payroll_line_fields(
            merged,
            year=year_i,
            month=month_i,
            sync_ot=sync_ot,
            partial_month=partial,
        )
        due = _period_bounds(int(row["payroll_month"]), int(row["payroll_year"]))[1]
        old_adv = float(row.get("advance_recovery") or 0)
        old_loan = float(row.get("loan_recovery") or 0)
        new_adv = float(calc.get("advance_recovery") or 0)
        new_loan = float(calc.get("loan_recovery") or 0)
        if abs(new_adv - old_adv) > 0.009 or abs(new_loan - old_loan) > 0.009:
            actual_adv, actual_loan = _resync_payroll_line_recoveries(
                conn,
                int(row["payroll_id"]),
                int(row["employee_id"]),
                advance_amount=new_adv,
                loan_amount=new_loan,
                due_date=due,
            )
            calc["advance_recovery"] = actual_adv
            calc["loan_recovery"] = actual_loan
            calc["total_deductions"] = round(
                float(calc.get("tax_deduction") or 0)
                + float(calc.get("eobi") or 0)
                + float(calc.get("social_security") or 0)
                + actual_adv + actual_loan
                + float(calc.get("other_deductions") or 0)
                + float(calc.get("absent_deduction") or 0),
                2,
            )
            calc["net_salary"] = round(
                float(calc.get("gross_salary") or 0) - calc["total_deductions"], 2,
            )
        conn.execute(
            """UPDATE payroll_lines SET
               basic_salary=?, allowances=?, overtime=?, bonus=?, gross_salary=?,
               tax_deduction=?, eobi=?, social_security=?, advance_recovery=?,
               loan_recovery=?, other_deductions=?, absent_deduction=?,
               total_deductions=?, net_salary=?,
               days_present=?, days_absent=?, overtime_hrs=?
               WHERE id=?""",
            (
                calc["basic_salary"], calc["allowances"], calc["overtime"], calc["bonus"],
                calc["gross_salary"], calc["tax_deduction"], calc["eobi"], calc["social_security"],
                calc["advance_recovery"], calc["loan_recovery"], calc["other_deductions"],
                calc.get("absent_deduction", 0),
                calc["total_deductions"], calc["net_salary"],
                float(merged.get("days_present") or 0),
                float(merged.get("days_absent") or 0),
                float(calc.get("overtime_hrs") if calc.get("overtime_hrs") is not None
                      else merged.get("overtime_hrs") or 0),
                line_id,
            ),
        )
        _refresh_payroll_run_totals(conn, row["payroll_id"])
        return calc


def adjust_unpaid_payroll_line(line_id, data, user_id=None):
    """Counter adjust for one unpaid employee after payroll is posted to GL.

    Allows Advance / Loan / Other deduction changes at the pay window.
    Syncs advance/loan ledgers, recalculates net, posts a balancing GL
    adjustment (salary payable ↔ employee advance / other), then the cashier
    can Pay & voucher for the new net.
    """
    from database import get_connection
    from db_v3 import post_gl

    editable = ("advance_recovery", "loan_recovery", "other_deductions")
    with get_connection() as conn:
        apply_hr(conn, __import__("database"))
        row = conn.execute(
            """SELECT pl.*, pr.status AS payroll_status, pr.document_no AS payroll_no,
                      pr.payroll_year, pr.payroll_month, pr.run_date,
                      e.full_name AS employee_name, e.code AS emp_code
               FROM payroll_lines pl
               JOIN payroll_runs pr ON pl.payroll_id=pr.id
               JOIN employees e ON pl.employee_id=e.id
               WHERE pl.id=?""",
            (line_id,),
        ).fetchone()
        if not row:
            raise ValueError("Payroll line not found.")
        row = dict(row)
        status = (row.get("payroll_status") or "").strip().lower()
        if status == "closed":
            raise ValueError("Payroll month is closed — reopen before adjusting.")
        if status not in ("posted", "paid"):
            raise ValueError(
                "Post payroll to GL first, then adjust unpaid staff at Pay Desk."
            )
        if (row.get("paid_status") or "") == "paid":
            raise ValueError("Already paid — undo payment before adjusting this line.")

        old_adv = round(float(row.get("advance_recovery") or 0), 2)
        old_loan = round(float(row.get("loan_recovery") or 0), 2)
        old_other = round(float(row.get("other_deductions") or 0), 2)
        old_net = round(float(row.get("net_salary") or 0), 2)

        merged = dict(row)
        for k in editable:
            if k in data and data[k] is not None:
                merged[k] = float(data[k] or 0)
        calc = _recalc_payroll_line_fields(
            merged,
            year=int(row["payroll_year"]),
            month=int(row["payroll_month"]),
            sync_ot=None,
        )
        due = _period_bounds(int(row["payroll_month"]), int(row["payroll_year"]))[1]
        new_adv = round(float(calc.get("advance_recovery") or 0), 2)
        new_loan = round(float(calc.get("loan_recovery") or 0), 2)
        new_other = round(float(calc.get("other_deductions") or 0), 2)

        if (
            abs(new_adv - old_adv) > 0.009
            or abs(new_loan - old_loan) > 0.009
        ):
            actual_adv, actual_loan = _resync_payroll_line_recoveries(
                conn,
                int(row["payroll_id"]),
                int(row["employee_id"]),
                advance_amount=new_adv,
                loan_amount=new_loan,
                due_date=due,
            )
            calc["advance_recovery"] = actual_adv
            calc["loan_recovery"] = actual_loan
            calc["total_deductions"] = round(
                float(calc.get("tax_deduction") or 0)
                + float(calc.get("eobi") or 0)
                + float(calc.get("social_security") or 0)
                + actual_adv + actual_loan
                + float(calc.get("other_deductions") or 0)
                + float(calc.get("absent_deduction") or 0),
                2,
            )
            calc["net_salary"] = round(
                float(calc.get("gross_salary") or 0) - calc["total_deductions"], 2,
            )
            new_adv = round(float(calc["advance_recovery"]), 2)
            new_loan = round(float(calc["loan_recovery"]), 2)

        new_net = round(float(calc.get("net_salary") or 0), 2)
        new_other = round(float(calc.get("other_deductions") or 0), 2)
        d_adv = round(new_adv - old_adv, 2)
        d_loan = round(new_loan - old_loan, 2)
        d_other = round(new_other - old_other, 2)
        d_net = round(new_net - old_net, 2)

        if abs(d_adv) < 0.01 and abs(d_loan) < 0.01 and abs(d_other) < 0.01:
            return {
                "changed": False,
                "net_salary": new_net,
                "advance_recovery": new_adv,
                "loan_recovery": new_loan,
                "other_deductions": new_other,
                "employee": row["employee_name"],
            }

        # Expected: less deduction → higher net (d_net ≈ -(d_adv+d_loan+d_other))
        expected_net = round(-(d_adv + d_loan + d_other), 2)
        if abs(d_net - expected_net) > 0.05:
            raise ValueError(
                f"Net change {d_net} does not match deduction change {expected_net}."
            )

        conn.execute(
            """UPDATE payroll_lines SET
               advance_recovery=?, loan_recovery=?, other_deductions=?,
               total_deductions=?, net_salary=?
               WHERE id=?""",
            (
                new_adv, new_loan, new_other,
                calc["total_deductions"], new_net, line_id,
            ),
        )
        _refresh_payroll_run_totals(conn, row["payroll_id"])

        # Balancing GL vs original month accrual (ref: payroll_line_adjust)
        entry_date = str(row.get("run_date") or now()[:10])
        ref_no = f"{row['payroll_no']}/{row['emp_code']}/ADJ"
        label = (
            f"Counter adjust {row['payroll_no']} — "
            f"{row['employee_name']} ({row['emp_code']})"
        )
        # Less recovery (d_* < 0): reverse credit on 100180, increase payable
        # More recovery (d_* > 0): extra credit on 100180, reduce payable
        if abs(d_adv) >= 0.01:
            if d_adv < 0:
                post_gl(
                    conn, entry_date, HR_AC["employee_advance"], -d_adv, 0,
                    f"{label} — less advance", "payroll_line_adjust", line_id, ref_no, user_id,
                )
                post_gl(
                    conn, entry_date, HR_AC["salary_payable"], 0, -d_adv,
                    f"{label} — less advance", "payroll_line_adjust", line_id, ref_no, user_id,
                )
            else:
                post_gl(
                    conn, entry_date, HR_AC["salary_payable"], d_adv, 0,
                    f"{label} — more advance", "payroll_line_adjust", line_id, ref_no, user_id,
                )
                post_gl(
                    conn, entry_date, HR_AC["employee_advance"], 0, d_adv,
                    f"{label} — more advance", "payroll_line_adjust", line_id, ref_no, user_id,
                )
        if abs(d_loan) >= 0.01:
            if d_loan < 0:
                post_gl(
                    conn, entry_date, HR_AC["employee_advance"], -d_loan, 0,
                    f"{label} — less loan", "payroll_line_adjust", line_id, ref_no, user_id,
                )
                post_gl(
                    conn, entry_date, HR_AC["salary_payable"], 0, -d_loan,
                    f"{label} — less loan", "payroll_line_adjust", line_id, ref_no, user_id,
                )
            else:
                post_gl(
                    conn, entry_date, HR_AC["salary_payable"], d_loan, 0,
                    f"{label} — more loan", "payroll_line_adjust", line_id, ref_no, user_id,
                )
                post_gl(
                    conn, entry_date, HR_AC["employee_advance"], 0, d_loan,
                    f"{label} — more loan", "payroll_line_adjust", line_id, ref_no, user_id,
                )
        if abs(d_other) >= 0.01:
            # Other was not a separate credit on month post; balance via payable ↔ expense
            if d_other < 0:
                post_gl(
                    conn, entry_date, HR_AC["salary_expense"], -d_other, 0,
                    f"{label} — less other ded.", "payroll_line_adjust", line_id, ref_no, user_id,
                )
                post_gl(
                    conn, entry_date, HR_AC["salary_payable"], 0, -d_other,
                    f"{label} — less other ded.", "payroll_line_adjust", line_id, ref_no, user_id,
                )
            else:
                post_gl(
                    conn, entry_date, HR_AC["salary_payable"], d_other, 0,
                    f"{label} — more other ded.", "payroll_line_adjust", line_id, ref_no, user_id,
                )
                post_gl(
                    conn, entry_date, HR_AC["salary_expense"], 0, d_other,
                    f"{label} — more other ded.", "payroll_line_adjust", line_id, ref_no, user_id,
                )

        return {
            "changed": True,
            "net_salary": new_net,
            "advance_recovery": new_adv,
            "loan_recovery": new_loan,
            "other_deductions": new_other,
            "old_net": old_net,
            "delta_net": d_net,
            "employee": row["employee_name"],
            "document_no": ref_no,
        }


def update_payroll_lines_bulk(updates, user_id=None, sync_ot=None):
    """Update many draft payroll lines in one transaction.

    updates: [{line_id, basic_salary, ...}, ...]
    When OT hours > 0, overtime amount is auto-calculated from the IFS formula.
    """
    from database import get_connection

    if not updates:
        return 0
    editable = (
        "basic_salary", "allowances", "overtime", "bonus",
        "tax_deduction", "eobi", "social_security",
        "advance_recovery", "loan_recovery", "other_deductions",
        "days_present", "days_absent", "overtime_hrs",
    )
    payroll_ids = set()
    saved = 0
    with get_connection() as conn:
        for data in updates:
            line_id = data.get("line_id") or data.get("id")
            if not line_id:
                continue
            row = conn.execute(
                """SELECT pl.*, pr.status AS payroll_status,
                          pr.payroll_year, pr.payroll_month
                   FROM payroll_lines pl
                   JOIN payroll_runs pr ON pl.payroll_id=pr.id
                   WHERE pl.id=?""",
                (int(line_id),),
            ).fetchone()
            if not row:
                raise ValueError(f"Payroll line #{line_id} not found.")
            row = dict(row)
            if row["payroll_status"] != "draft":
                raise ValueError("Only draft payroll can be edited.")
            if (row.get("paid_status") or "") == "paid":
                raise ValueError(
                    f"Line #{line_id} is already paid — voucher is locked. "
                    "Only an admin can undo payment before editing."
                )
            if _payroll_line_accrual_exists(conn, int(line_id)):
                raise ValueError(
                    f"Line #{line_id} already has a posted voucher — "
                    "undo the payment first, then edit."
                )
            merged = dict(row)
            for k in editable:
                if k in data:
                    merged[k] = data[k]
            calc = _recalc_payroll_line_fields(
                merged,
                year=int(row["payroll_year"]),
                month=int(row["payroll_month"]),
                sync_ot=sync_ot,
            )
            due = _period_bounds(int(row["payroll_month"]), int(row["payroll_year"]))[1]
            old_adv = float(row.get("advance_recovery") or 0)
            old_loan = float(row.get("loan_recovery") or 0)
            new_adv = float(calc.get("advance_recovery") or 0)
            new_loan = float(calc.get("loan_recovery") or 0)
            if abs(new_adv - old_adv) > 0.009 or abs(new_loan - old_loan) > 0.009:
                actual_adv, actual_loan = _resync_payroll_line_recoveries(
                    conn,
                    int(row["payroll_id"]),
                    int(row["employee_id"]),
                    advance_amount=new_adv,
                    loan_amount=new_loan,
                    due_date=due,
                )
                calc["advance_recovery"] = actual_adv
                calc["loan_recovery"] = actual_loan
                calc["total_deductions"] = round(
                    float(calc.get("tax_deduction") or 0)
                    + float(calc.get("eobi") or 0)
                    + float(calc.get("social_security") or 0)
                    + actual_adv + actual_loan
                    + float(calc.get("other_deductions") or 0)
                    + float(calc.get("absent_deduction") or 0),
                    2,
                )
                calc["net_salary"] = round(
                    float(calc.get("gross_salary") or 0) - calc["total_deductions"], 2,
                )
            conn.execute(
                """UPDATE payroll_lines SET
                   basic_salary=?, allowances=?, overtime=?, bonus=?, gross_salary=?,
                   tax_deduction=?, eobi=?, social_security=?, advance_recovery=?,
                   loan_recovery=?, other_deductions=?, absent_deduction=?,
                   total_deductions=?, net_salary=?,
                   days_present=?, days_absent=?, overtime_hrs=?
                   WHERE id=?""",
                (
                    calc["basic_salary"], calc["allowances"], calc["overtime"], calc["bonus"],
                    calc["gross_salary"], calc["tax_deduction"], calc["eobi"], calc["social_security"],
                    calc["advance_recovery"], calc["loan_recovery"], calc["other_deductions"],
                    calc.get("absent_deduction", 0),
                    calc["total_deductions"], calc["net_salary"],
                    float(merged.get("days_present") or 0),
                    float(merged.get("days_absent") or 0),
                    float(calc.get("overtime_hrs") if calc.get("overtime_hrs") is not None
                          else merged.get("overtime_hrs") or 0),
                    int(line_id),
                ),
            )
            payroll_ids.add(row["payroll_id"])
            saved += 1
        for pid in payroll_ids:
            _refresh_payroll_run_totals(conn, pid)
    return saved


def sync_payroll_overtime(payroll_id, mode="from_hours", user_id=None):
    """Apply OT formula across a draft payroll run.

    mode="from_hours": Overtime pay = Basic / days / 6 × OT hrs (for upcoming payroll).
    mode="from_amount": Fill OT hrs from existing Overtime amount (prior months already paid).
    """
    if mode not in ("from_hours", "from_amount"):
        raise ValueError("mode must be 'from_hours' or 'from_amount'")
    from database import get_connection
    with get_connection() as conn:
        pr = conn.execute(
            "SELECT id, status, payroll_year, payroll_month FROM payroll_runs WHERE id=?",
            (payroll_id,),
        ).fetchone()
        if not pr:
            raise ValueError("Payroll run not found.")
        pr = dict(pr)
        if pr["status"] != "draft":
            raise ValueError("Only draft payroll can be synced.")
        year, month = int(pr["payroll_year"]), int(pr["payroll_month"])
        lines = conn.execute(
            "SELECT * FROM payroll_lines WHERE payroll_id=?", (payroll_id,)
        ).fetchall()
        n = 0
        for row in lines:
            merged = dict(row)
            calc = _recalc_payroll_line_fields(merged, year=year, month=month, sync_ot=mode)
            conn.execute(
                """UPDATE payroll_lines SET
                   overtime=?, absent_deduction=?, gross_salary=?, total_deductions=?,
                   net_salary=?, overtime_hrs=?
                   WHERE id=?""",
                (
                    calc["overtime"], calc.get("absent_deduction", 0),
                    calc["gross_salary"], calc["total_deductions"],
                    calc["net_salary"], calc["overtime_hrs"], merged["id"],
                ),
            )
            n += 1
        _refresh_payroll_run_totals(conn, payroll_id)
        return n


def refresh_payroll_attendance_days(payroll_id, user_id=None):
    """Re-pull Present / Absent / OT hrs from attendance for a draft payroll.

    Public holidays and weekly offs count toward Present only when the
    employee has at least one work day; sandwich converts holidays between
    leave→leave or absent→absent. Blank attendance does not earn holiday Present.

    Returns dict: updated, no_attendance, no_attendance_names (sample).
    """
    from database import get_connection
    with get_connection() as conn:
        pr = conn.execute(
            "SELECT id, status, payroll_year, payroll_month FROM payroll_runs WHERE id=?",
            (payroll_id,),
        ).fetchone()
        if not pr:
            raise ValueError("Payroll run not found.")
        pr = dict(pr)
        if pr["status"] != "draft":
            raise ValueError("Only draft payroll can refresh attendance.")
        year, month = int(pr["payroll_year"]), int(pr["payroll_month"])
        period_start, period_end = _period_bounds(month, year)
        lines = conn.execute(
            "SELECT id, employee_id, basic_salary, allowances, bonus, tax_deduction, eobi, "
            "social_security, advance_recovery, loan_recovery, other_deductions "
            "FROM payroll_lines WHERE payroll_id=?",
            (payroll_id,),
        ).fetchall()
        n = 0
        no_att = []
        date_skipped_with_att = []
        for row in lines:
            ln = dict(row)
            eid = int(ln["employee_id"])
            emp_start, emp_end, partial = _employment_bounds_in_period(
                conn, eid, period_start, period_end,
            )
            att_lo, att_hi = emp_start, emp_end
            # Master joining/leaving may exclude the month, but attendance was saved —
            # still pull those marks so "Refresh Present from attendance" works.
            if emp_start > emp_end:
                att_n_full = conn.execute(
                    "SELECT COUNT(*) FROM attendance WHERE employee_id=? AND att_date>=? AND att_date<=?",
                    (eid, period_start, period_end),
                ).fetchone()[0]
                if att_n_full:
                    att_lo, att_hi = period_start, period_end
                    partial = True
                    emp = conn.execute(
                        "SELECT code, full_name, joining_date FROM employees WHERE id=?",
                        (eid,),
                    ).fetchone()
                    if emp:
                        date_skipped_with_att.append(
                            f"{emp[0]} {emp[1]} (join {emp[2] or '—'})"
                        )
                else:
                    att = {
                        "days_present": 0.0,
                        "days_absent": 0.0,
                        "days_leave": 0.0,
                        "overtime_hrs": 0.0,
                    }
                    att_n = 0
                    emp = conn.execute(
                        "SELECT code, full_name FROM employees WHERE id=?", (eid,)
                    ).fetchone()
                    if emp:
                        no_att.append(f"{emp[0]} {emp[1]}")
                    basic = float(ln.get("basic_salary") or 0)
                    overtime = calc_overtime_amount(basic, year, month, 0)
                    merged = {
                        **ln,
                        "days_present": 0.0,
                        "days_absent": 0.0,
                        "days_leave": 0.0,
                        "overtime_hrs": 0.0,
                        "overtime": overtime,
                    }
                    calc = _recalc_payroll_line_fields(
                        merged, year=year, month=month, sync_ot=None, partial_month=True,
                        days_leave=0.0,
                    )
                    conn.execute(
                        """UPDATE payroll_lines SET
                           days_present=?, days_absent=?, overtime_hrs=?, overtime=?,
                           absent_deduction=?, gross_salary=?, total_deductions=?, net_salary=?
                           WHERE id=?""",
                        (
                            0.0, 0.0, 0.0, overtime,
                            calc.get("absent_deduction", 0),
                            calc["gross_salary"], calc["total_deductions"], calc["net_salary"],
                            ln["id"],
                        ),
                    )
                    n += 1
                    continue

            att_n = conn.execute(
                "SELECT COUNT(*) FROM attendance WHERE employee_id=? AND att_date>=? AND att_date<=?",
                (eid, att_lo, att_hi),
            ).fetchone()[0]
            att = _attendance_days_for_period(conn, eid, att_lo, att_hi)
            if not att_n:
                emp = conn.execute(
                    "SELECT code, full_name FROM employees WHERE id=?", (eid,)
                ).fetchone()
                if emp:
                    no_att.append(f"{emp[0]} {emp[1]}")
            basic = float(ln.get("basic_salary") or 0)
            overtime = calc_overtime_amount(basic, year, month, att["overtime_hrs"])
            merged = {
                **ln,
                "days_present": att["days_present"],
                "days_absent": att["days_absent"],
                "days_leave": att.get("days_leave") or 0,
                "overtime_hrs": att["overtime_hrs"],
                "overtime": overtime,
            }
            calc = _recalc_payroll_line_fields(
                merged, year=year, month=month, sync_ot=None, partial_month=partial,
                days_leave=float(att.get("days_leave") or 0),
            )
            conn.execute(
                """UPDATE payroll_lines SET
                   days_present=?, days_absent=?, overtime_hrs=?, overtime=?,
                   absent_deduction=?, gross_salary=?, total_deductions=?, net_salary=?
                   WHERE id=?""",
                (
                    att["days_present"], att["days_absent"], att["overtime_hrs"], overtime,
                    calc.get("absent_deduction", 0),
                    calc["gross_salary"], calc["total_deductions"], calc["net_salary"],
                    ln["id"],
                ),
            )
            n += 1
        _refresh_payroll_run_totals(conn, payroll_id)
        return {
            "updated": n,
            "no_attendance": len(no_att),
            "no_attendance_names": no_att[:15],
            "date_skipped_with_att": len(date_skipped_with_att),
            "date_skipped_with_att_names": date_skipped_with_att[:10],
            "period_start": period_start,
            "period_end": period_end,
        }


def refresh_payroll_loan_advance_recoveries(payroll_id, user_id=None):
    """Draft only: undo this run's loan/advance recoveries and re-apply one installment each.

    Fixes payrolls that incorrectly deducted the full outstanding balance.
    """
    from database import get_connection

    with get_connection() as conn:
        pr = conn.execute(
            "SELECT id, status, payroll_year, payroll_month FROM payroll_runs WHERE id=?",
            (payroll_id,),
        ).fetchone()
        if not pr:
            raise ValueError("Payroll run not found.")
        pr = dict(pr)
        if pr["status"] != "draft":
            raise ValueError("Only draft payroll can refresh loan/advance recoveries.")
        year, month = int(pr["payroll_year"]), int(pr["payroll_month"])
        period_end = _period_bounds(month, year)[1]

        loan_ids = [
            int(r[0]) for r in conn.execute(
                "SELECT DISTINCT loan_id FROM loan_installments WHERE payroll_id=?",
                (payroll_id,),
            ).fetchall()
        ]
        adv_ids = [
            int(r[0]) for r in conn.execute(
                "SELECT DISTINCT advance_id FROM advance_recovery_schedule WHERE payroll_id=?",
                (payroll_id,),
            ).fetchall()
        ]

        _undo_payroll_recoveries(conn, payroll_id)
        for lid in loan_ids:
            _rebuild_unpaid_loan_installments(conn, lid)
        for aid in adv_ids:
            _rebuild_unpaid_advance_schedule(conn, aid)

        lines = conn.execute(
            """SELECT id, employee_id, basic_salary, allowances, overtime, bonus,
                      tax_deduction, eobi, social_security, other_deductions,
                      days_present, days_absent, overtime_hrs
               FROM payroll_lines WHERE payroll_id=?""",
            (payroll_id,),
        ).fetchall()
        n = 0
        for row in lines:
            ln = dict(row)
            eid = int(ln["employee_id"])
            adv = _recover_advances(conn, eid, payroll_id, period_end)
            loan = _recover_loans(conn, eid, payroll_id, period_end)
            merged = {
                **ln,
                "advance_recovery": adv,
                "loan_recovery": loan,
            }
            calc = _recalc_payroll_line_fields(merged, year=year, month=month, sync_ot=None)
            conn.execute(
                """UPDATE payroll_lines SET
                   advance_recovery=?, loan_recovery=?, absent_deduction=?,
                   total_deductions=?, net_salary=?, gross_salary=?
                   WHERE id=?""",
                (
                    calc["advance_recovery"], calc["loan_recovery"],
                    calc.get("absent_deduction", 0),
                    calc["total_deductions"], calc["net_salary"], calc["gross_salary"],
                    ln["id"],
                ),
            )
            n += 1
        _refresh_payroll_run_totals(conn, payroll_id)
        return n


def _sync_employee_recoveries_on_draft_payroll(conn, employee_id, salary_month):
    """Pull newly issued advances/loans onto matching draft payroll (one employee).

    Used when cash is issued after the draft salary sheet already exists.
    """
    sm = _normalize_salary_month(salary_month)
    if not sm:
        return None
    try:
        year, month = int(sm[:4]), int(sm[5:7])
    except (TypeError, ValueError):
        return None
    pr = conn.execute(
        """SELECT id, status, payroll_year, payroll_month FROM payroll_runs
           WHERE payroll_year=? AND payroll_month=? AND status='draft'
           ORDER BY id DESC LIMIT 1""",
        (year, month),
    ).fetchone()
    if not pr:
        return None
    payroll_id = int(pr["id"])
    line = conn.execute(
        """SELECT id, employee_id, basic_salary, allowances, overtime, bonus,
                  tax_deduction, eobi, social_security, other_deductions,
                  days_present, days_absent, overtime_hrs, paid_status
           FROM payroll_lines WHERE payroll_id=? AND employee_id=?""",
        (payroll_id, int(employee_id)),
    ).fetchone()
    if not line:
        return None
    ln = dict(line)
    if (ln.get("paid_status") or "") == "paid":
        return {
            "payroll_id": payroll_id,
            "synced": False,
            "reason": "line already paid",
        }

    period_end = _period_bounds(month, year)[1]
    adv_ids = _undo_advance_recoveries_for_employee(conn, payroll_id, int(employee_id))
    loan_ids = _undo_loan_recoveries_for_employee(conn, payroll_id, int(employee_id))
    for aid in adv_ids:
        _rebuild_unpaid_advance_schedule(conn, aid)
    for lid in loan_ids:
        _rebuild_unpaid_loan_installments(conn, lid)

    adv = _recover_advances(conn, int(employee_id), payroll_id, period_end)
    loan = _recover_loans(conn, int(employee_id), payroll_id, period_end)
    merged = {**ln, "advance_recovery": adv, "loan_recovery": loan}
    calc = _recalc_payroll_line_fields(merged, year=year, month=month, sync_ot=None)
    conn.execute(
        """UPDATE payroll_lines SET
           advance_recovery=?, loan_recovery=?, absent_deduction=?,
           total_deductions=?, net_salary=?, gross_salary=?
           WHERE id=?""",
        (
            calc["advance_recovery"], calc["loan_recovery"],
            calc.get("absent_deduction", 0),
            calc["total_deductions"], calc["net_salary"], calc["gross_salary"],
            ln["id"],
        ),
    )
    _refresh_payroll_run_totals(conn, payroll_id)
    return {
        "payroll_id": payroll_id,
        "payroll_no": conn.execute(
            "SELECT document_no FROM payroll_runs WHERE id=?", (payroll_id,),
        ).fetchone()[0],
        "synced": True,
        "advance_recovery": calc["advance_recovery"],
        "loan_recovery": calc["loan_recovery"],
        "net_salary": calc["net_salary"],
    }


def approve_payroll(payroll_id, user_id):
    from database import get_connection
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE payroll_runs SET status='approved',approved_by=?,approved_at=? WHERE id=? AND status='draft'",
            (user_id, now(), payroll_id),
        )
        if cur.rowcount == 0:
            raise ValueError("Payroll not found or not in draft status.")


def unapprove_payroll(payroll_id, user_id):
    """Return approved payroll to draft so lines can be edited (not posted/paid)."""
    from database import get_connection
    with get_connection() as conn:
        pr = conn.execute("SELECT status FROM payroll_runs WHERE id=?", (payroll_id,)).fetchone()
        if not pr:
            raise ValueError("Payroll not found.")
        if pr[0] != "approved":
            raise ValueError(
                "Only approved (not yet posted) payroll can be unapproved. "
                "Posted payroll must be reversed in accounts first."
            )
        if conn.execute(
            "SELECT 1 FROM general_ledger WHERE reference_type='payroll' AND reference_id=? LIMIT 1",
            (payroll_id,),
        ).fetchone():
            raise ValueError("Payroll already has GL entries. Cannot unapprove.")
        cur = conn.execute(
            """UPDATE payroll_runs SET status='draft', approved_by=NULL, approved_at=NULL,
               modified_by=?, modified_at=? WHERE id=? AND status='approved'""",
            (user_id, now(), payroll_id),
        )
        if cur.rowcount == 0:
            raise ValueError("Could not unapprove payroll.")


def _delete_gl_reference(conn, ref_type, ref_id):
    """Remove GL rows for a reference and reverse chart_of_accounts balances."""
    rows = conn.execute(
        """SELECT account_id, debit, credit FROM general_ledger
           WHERE reference_type=? AND reference_id=?""",
        (ref_type, ref_id),
    ).fetchall()
    for row in rows:
        aid, dr, cr = row[0], float(row[1] or 0), float(row[2] or 0)
        if dr:
            conn.execute(
                "UPDATE chart_of_accounts SET current_balance=current_balance-? WHERE id=?",
                (dr, aid),
            )
        if cr:
            conn.execute(
                "UPDATE chart_of_accounts SET current_balance=current_balance+? WHERE id=?",
                (cr, aid),
            )
    conn.execute(
        "DELETE FROM general_ledger WHERE reference_type=? AND reference_id=?",
        (ref_type, ref_id),
    )
    return len(rows)


def payroll_gl_posted(payroll_id):
    from database import get_connection
    with get_connection() as conn:
        return bool(
            conn.execute(
                "SELECT 1 FROM general_ledger WHERE reference_type='payroll' AND reference_id=? LIMIT 1",
                (payroll_id,),
            ).fetchone()
        )


def rollback_payroll_gl(payroll_id, user_id, reason=""):
    """Reverse payroll salary accrual voucher (posted → approved). If paid, reverses payment GL first.

    Also clears per-employee Post & voucher accruals when the run is still draft.
    """
    from database import get_connection

    reason = (reason or "").strip()
    if not reason:
        raise ValueError("Reason is required to rollback payroll GL posting.")

    with get_connection() as conn:
        pr = conn.execute("SELECT * FROM payroll_runs WHERE id=?", (payroll_id,)).fetchone()
        if not pr:
            raise ValueError("Payroll not found.")
        pr = dict(pr)
        status = pr["status"]

        all_line_ids = [
            r[0] for r in conn.execute(
                "SELECT id FROM payroll_lines WHERE payroll_id=?", (payroll_id,),
            ).fetchall()
        ]
        paid_line_ids = [
            r[0] for r in conn.execute(
                "SELECT id FROM payroll_lines WHERE payroll_id=? AND paid_status='paid'",
                (payroll_id,),
            ).fetchall()
        ]
        has_line_accrual = any(_payroll_line_accrual_exists(conn, lid) for lid in all_line_ids)

        if status == "draft":
            if not paid_line_ids and not has_line_accrual:
                raise ValueError("Payroll is not posted to GL.")
            for lid in paid_line_ids:
                _undo_payroll_line_payment(conn, lid)
            for lid in all_line_ids:
                _undo_payroll_line_accrual(conn, lid)
            note = f"\nLine voucher rollback ({now()}): {reason}"
            conn.execute(
                """UPDATE payroll_runs SET notes=COALESCE(notes,'') || ?,
                   modified_by=?, modified_at=? WHERE id=?""",
                (note, user_id, now(), payroll_id),
            )
            return

        has_accrual = conn.execute(
            "SELECT 1 FROM general_ledger WHERE reference_type='payroll' AND reference_id=? LIMIT 1",
            (payroll_id,),
        ).fetchone()
        has_payment = conn.execute(
            "SELECT 1 FROM general_ledger WHERE reference_type='payroll_payment' AND reference_id=? LIMIT 1",
            (payroll_id,),
        ).fetchone()
        if status == "approved" and not has_accrual and not has_payment and not paid_line_ids:
            raise ValueError("Payroll has no GL voucher to rollback.")

        for lid in paid_line_ids:
            _undo_payroll_line_payment(conn, lid)
        for lid in all_line_ids:
            _undo_payroll_line_accrual(conn, lid)

        removed_payment = 0
        if status == "paid" or has_payment:
            removed_payment = _delete_gl_reference(conn, "payroll_payment", payroll_id)
            conn.execute(
                """UPDATE payroll_runs SET status='posted', paid_by=NULL, paid_at=NULL,
                   modified_by=?, modified_at=? WHERE id=?""",
                (user_id, now(), payroll_id),
            )
            status = "posted"

        if status == "posted" or has_accrual:
            removed = _delete_gl_reference(conn, "payroll", payroll_id)
            if removed == 0 and removed_payment == 0 and not paid_line_ids and not has_line_accrual:
                raise ValueError("No payroll GL entries found to rollback.")
            note = f"\nGL rollback ({now()}): {reason}"
            conn.execute(
                """UPDATE payroll_runs SET status='approved', posted_by=NULL, posted_at=NULL,
                   notes=COALESCE(notes,'') || ?, modified_by=?, modified_at=? WHERE id=?""",
                (note, user_id, now(), payroll_id),
            )
            return

        raise ValueError(f"Cannot rollback payroll in status '{status}'.")


def rollback_generated_payroll(payroll_id, user_id, reason=""):
    """Delete a generated payroll run: reverse GL (if any), undo advance/loan recoveries, remove lines."""
    from database import get_connection

    reason = (reason or "").strip()
    if not reason:
        raise ValueError("Reason is required to rollback generated payroll.")

    with get_connection() as conn:
        pr = conn.execute(
            "SELECT id, document_no, payroll_month, payroll_year, status FROM payroll_runs WHERE id=?",
            (payroll_id,),
        ).fetchone()
        if not pr:
            raise ValueError("Payroll not found.")
        pr = dict(pr)

        has_payment = conn.execute(
            "SELECT 1 FROM general_ledger WHERE reference_type='payroll_payment' AND reference_id=? LIMIT 1",
            (payroll_id,),
        ).fetchone()
        has_accrual = conn.execute(
            "SELECT 1 FROM general_ledger WHERE reference_type='payroll' AND reference_id=? LIMIT 1",
            (payroll_id,),
        ).fetchone()
        line_ids = [
            r[0] for r in conn.execute(
                "SELECT id FROM payroll_lines WHERE payroll_id=? AND paid_status='paid'",
                (payroll_id,),
            ).fetchall()
        ]
        for lid in line_ids:
            _undo_payroll_line_payment(conn, lid)
        # Clear any leftover one-employee accruals (paid undo already clears theirs)
        for lid in (
            r[0] for r in conn.execute(
                "SELECT id FROM payroll_lines WHERE payroll_id=?", (payroll_id,),
            ).fetchall()
        ):
            _undo_payroll_line_accrual(conn, lid)
        if has_payment:
            _delete_gl_reference(conn, "payroll_payment", payroll_id)
        if has_accrual:
            _delete_gl_reference(conn, "payroll", payroll_id)

        _undo_payroll_recoveries(conn, payroll_id)
        conn.execute("DELETE FROM payroll_lines WHERE payroll_id=?", (payroll_id,))
        conn.execute("DELETE FROM payroll_runs WHERE id=?", (payroll_id,))


def get_payroll_for_period(month, year):
    from database import get_connection, row_to_dict
    with get_connection() as conn:
        return row_to_dict(conn.execute(
            "SELECT * FROM payroll_runs WHERE payroll_month=? AND payroll_year=?",
            (month, year),
        ).fetchone())


def post_payroll_gl(payroll_id, user_id):
    from database import get_connection
    from db_v3 import post_gl
    with get_connection() as conn:
        pr = conn.execute("SELECT * FROM payroll_runs WHERE id=?", (payroll_id,)).fetchone()
        if not pr:
            return
        pr = dict(pr)
        if pr["status"] not in ("approved", "draft"):
            raise ValueError("Payroll cannot be posted")
        existing = conn.execute(
            "SELECT 1 FROM general_ledger WHERE reference_type='payroll' AND reference_id=? LIMIT 1",
            (payroll_id,),
        ).fetchone()
        if existing:
            return
        # Skip lines already paid / accrued one-by-one at the counter
        lines = conn.execute(
            """SELECT pl.* FROM payroll_lines pl
               WHERE pl.payroll_id=?
                 AND COALESCE(pl.paid_status,'unpaid')!='paid'
                 AND NOT EXISTS (
                     SELECT 1 FROM general_ledger g
                     WHERE g.reference_type='payroll_line_accrual' AND g.reference_id=pl.id
                 )""",
            (payroll_id,),
        ).fetchall()
        if not lines:
            conn.execute(
                "UPDATE payroll_runs SET status='posted',posted_by=?,posted_at=? WHERE id=?",
                (user_id, now(), payroll_id),
            )
            return
        gross = sum(float(dict(l)["gross_salary"] or 0) for l in lines)
        net = sum(float(dict(l)["net_salary"] or 0) for l in lines)
        adv_rec = sum(float(dict(l)["advance_recovery"] or 0) for l in lines)
        eobi = sum(float(dict(l)["eobi"] or 0) for l in lines)
        ss = sum(float(dict(l)["social_security"] or 0) for l in lines)
        tax = sum(float(dict(l)["tax_deduction"] or 0) for l in lines)
        loan_rec = sum(float(dict(l)["loan_recovery"] or 0) for l in lines)
        other_ded = sum(float(dict(l).get("other_deductions") or 0) for l in lines)
        absent_ded = sum(float(dict(l).get("absent_deduction") or 0) for l in lines)
        entry_date = pr["run_date"]
        ref_no = pr["document_no"]

        post_gl(conn, entry_date, HR_AC["salary_expense"], gross, 0, "Payroll", "payroll", payroll_id, ref_no, user_id)
        if adv_rec:
            post_gl(conn, entry_date, HR_AC["employee_advance"], 0, adv_rec, "Advance recovery", "payroll", payroll_id, ref_no, user_id)
        if eobi:
            post_gl(conn, entry_date, HR_AC["eobi_payable"], 0, eobi, "EOBI", "payroll", payroll_id, ref_no, user_id)
        if ss:
            post_gl(conn, entry_date, HR_AC["ss_payable"], 0, ss, "Social Security", "payroll", payroll_id, ref_no, user_id)
        if tax:
            post_gl(conn, entry_date, HR_AC["tax_payable_payroll"], 0, tax, "Payroll tax", "payroll", payroll_id, ref_no, user_id)
        if loan_rec:
            post_gl(conn, entry_date, HR_AC["employee_advance"], 0, loan_rec, "Loan recovery", "payroll", payroll_id, ref_no, user_id)
        if absent_ded:
            post_gl(
                conn, entry_date, HR_AC["salary_expense"], 0, absent_ded,
                "Absent (LWP)", "payroll", payroll_id, ref_no, user_id,
            )
        if other_ded:
            post_gl(
                conn, entry_date, HR_AC["salary_expense"], 0, other_ded,
                "Other salary deductions", "payroll", payroll_id, ref_no, user_id,
            )
        post_gl(conn, entry_date, HR_AC["salary_payable"], 0, net, "Net salary payable", "payroll", payroll_id, ref_no, user_id)

        conn.execute(
            "UPDATE payroll_runs SET status='posted',posted_by=?,posted_at=? WHERE id=?",
            (user_id, now(), payroll_id),
        )


def _payroll_line_accrual_exists(conn, line_id) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM general_ledger WHERE reference_type='payroll_line_accrual' AND reference_id=? LIMIT 1",
        (int(line_id),),
    ).fetchone())


def _post_payroll_line_accrual(conn, row, user_id):
    """Post salary accrual GL for one employee (counter / Edit Lines Post & voucher)."""
    from db_v3 import post_gl

    line_id = int(row["id"])
    if _payroll_line_accrual_exists(conn, line_id):
        return False
    # Whole-run accrual already covers this line
    if conn.execute(
        "SELECT 1 FROM general_ledger WHERE reference_type='payroll' AND reference_id=? LIMIT 1",
        (int(row["payroll_id"]),),
    ).fetchone():
        return False

    entry_date = str(row.get("run_date") or now()[:10])
    ref_no = f"{row['payroll_no']}/{row['emp_code']}"
    label = f"Salary accrual {row['payroll_no']} — {row['employee_name']} ({row['emp_code']})"
    gross = round(float(row.get("gross_salary") or 0), 2)
    net = round(float(row.get("net_salary") or 0), 2)
    adv = round(float(row.get("advance_recovery") or 0), 2)
    loan = round(float(row.get("loan_recovery") or 0), 2)
    eobi = round(float(row.get("eobi") or 0), 2)
    ss = round(float(row.get("social_security") or 0), 2)
    tax = round(float(row.get("tax_deduction") or 0), 2)
    other = round(float(row.get("other_deductions") or 0), 2)
    absent = round(float(row.get("absent_deduction") or 0), 2)
    # Balance: expense = credits (other/absent reduce expense; recoveries → liability)
    if gross > 0.009:
        post_gl(conn, entry_date, HR_AC["salary_expense"], gross, 0, label, "payroll_line_accrual", line_id, ref_no, user_id)
    if adv > 0.009:
        post_gl(conn, entry_date, HR_AC["employee_advance"], 0, adv, f"{label} — advance", "payroll_line_accrual", line_id, ref_no, user_id)
    if loan > 0.009:
        post_gl(conn, entry_date, HR_AC["employee_advance"], 0, loan, f"{label} — loan", "payroll_line_accrual", line_id, ref_no, user_id)
    if eobi > 0.009:
        post_gl(conn, entry_date, HR_AC["eobi_payable"], 0, eobi, f"{label} — EOBI", "payroll_line_accrual", line_id, ref_no, user_id)
    if ss > 0.009:
        post_gl(conn, entry_date, HR_AC["ss_payable"], 0, ss, f"{label} — SS", "payroll_line_accrual", line_id, ref_no, user_id)
    if tax > 0.009:
        post_gl(conn, entry_date, HR_AC["tax_payable_payroll"], 0, tax, f"{label} — tax", "payroll_line_accrual", line_id, ref_no, user_id)
    if absent > 0.009:
        post_gl(
            conn, entry_date, HR_AC["salary_expense"], 0, absent,
            f"{label} — absent LWP", "payroll_line_accrual", line_id, ref_no, user_id,
        )
    if other > 0.009:
        post_gl(
            conn, entry_date, HR_AC["salary_expense"], 0, other,
            f"{label} — other ded.", "payroll_line_accrual", line_id, ref_no, user_id,
        )
    # Net payable = gross - all deductions
    payable = round(gross - adv - loan - eobi - ss - tax - other - absent, 2)
    if abs(payable - net) > 0.05:
        payable = net
    if payable > 0.009:
        post_gl(conn, entry_date, HR_AC["salary_payable"], 0, payable, f"{label} — net", "payroll_line_accrual", line_id, ref_no, user_id)
    elif payable < -0.009:
        # Negative net: reduce expense / no cash pay later
        post_gl(conn, entry_date, HR_AC["salary_payable"], -payable, 0, f"{label} — net adj", "payroll_line_accrual", line_id, ref_no, user_id)
    return True


def _refresh_payroll_paid_status(conn, payroll_id, user_id=None):
    """Mark payroll run paid when every line is paid. Never overwrites closed.

    Partial pays from draft stay on draft so Edit Lines remains open for others.
    """
    st = conn.execute(
        "SELECT status FROM payroll_runs WHERE id=?", (payroll_id,),
    ).fetchone()
    cur = (st[0] or "").strip().lower() if st else ""
    if cur == "closed":
        return
    total = conn.execute(
        "SELECT COUNT(*) FROM payroll_lines WHERE payroll_id=?", (payroll_id,)
    ).fetchone()[0]
    unpaid_due = conn.execute(
        """SELECT COUNT(*) FROM payroll_lines
           WHERE payroll_id=? AND COALESCE(paid_status,'unpaid')!='paid'
             AND COALESCE(net_salary,0)>0.009""",
        (payroll_id,),
    ).fetchone()[0]
    if total and unpaid_due == 0:
        conn.execute(
            "UPDATE payroll_runs SET status='paid', paid_by=?, paid_at=? WHERE id=?",
            (user_id, now(), payroll_id),
        )
    elif cur == "draft":
        # Keep draft while some staff still unpaid — Edit Lines stays available
        conn.execute(
            "UPDATE payroll_runs SET modified_by=?, modified_at=? WHERE id=?",
            (user_id, now(), payroll_id),
        )
    else:
        conn.execute(
            """UPDATE payroll_runs SET status='posted', paid_by=NULL, paid_at=NULL,
               modified_by=?, modified_at=? WHERE id=?""",
            (user_id, now(), payroll_id),
        )


def payroll_unpaid_due_count(payroll_id) -> int:
    """Employees still owing a cash/bank net payment."""
    from database import get_connection
    with get_connection() as conn:
        return int(conn.execute(
            """SELECT COUNT(*) FROM payroll_lines
               WHERE payroll_id=? AND COALESCE(paid_status,'unpaid')!='paid'
                 AND COALESCE(net_salary,0)>0.009""",
            (int(payroll_id),),
        ).fetchone()[0] or 0)


def close_payroll_month(payroll_id, user_id, notes=""):
    """Final month lock — all due salaries must be paid first."""
    from database import get_connection

    with get_connection() as conn:
        apply_hr(conn, __import__("database"))
        pr = conn.execute(
            "SELECT * FROM payroll_runs WHERE id=?", (int(payroll_id),),
        ).fetchone()
        if not pr:
            raise ValueError("Payroll not found.")
        pr = dict(pr)
        status = (pr.get("status") or "").strip().lower()
        if status == "closed":
            raise ValueError("Payroll month is already closed.")
        if status not in ("draft", "posted", "paid"):
            raise ValueError("Pay all staff (or Post remaining to GL) before closing the month.")
        unpaid = conn.execute(
            """SELECT COUNT(*) FROM payroll_lines
               WHERE payroll_id=? AND COALESCE(paid_status,'unpaid')!='paid'
                 AND COALESCE(net_salary,0)>0.009""",
            (payroll_id,),
        ).fetchone()[0]
        if unpaid:
            raise ValueError(
                f"{unpaid} employee(s) still unpaid. Pay each salary (or settle nil-net) before Close month."
            )
        note = (notes or "").strip()
        extra = f"\nClosed: {now()}" + (f" — {note}" if note else "")
        conn.execute(
            """UPDATE payroll_runs SET status='closed', closed_by=?, closed_at=?,
               paid_by=COALESCE(paid_by,?), paid_at=COALESCE(paid_at,?),
               notes=TRIM(COALESCE(notes,'') || ?),
               modified_by=?, modified_at=?
               WHERE id=?""",
            (user_id, now(), user_id, now(), extra, user_id, now(), payroll_id),
        )
        return int(payroll_id)


def reopen_payroll_month(payroll_id, user_id, reason=""):
    """Unlock a closed payroll month (admin correction). Returns to paid."""
    from database import get_connection

    reason = (reason or "").strip()
    if not reason:
        raise ValueError("Reason is required to reopen a closed payroll month.")
    with get_connection() as conn:
        apply_hr(conn, __import__("database"))
        pr = conn.execute(
            "SELECT status FROM payroll_runs WHERE id=?", (int(payroll_id),),
        ).fetchone()
        if not pr:
            raise ValueError("Payroll not found.")
        if (pr[0] or "") != "closed":
            raise ValueError("Only a closed payroll month can be reopened.")
        conn.execute(
            """UPDATE payroll_runs SET status='paid', closed_by=NULL, closed_at=NULL,
               notes=TRIM(COALESCE(notes,'') || ?),
               modified_by=?, modified_at=?
               WHERE id=?""",
            (f"\nReopened: {now()} — {reason}", user_id, now(), payroll_id),
        )
        return int(payroll_id)


def get_payroll_line_voucher_data(line_id):
    """Details for printable salary payment voucher."""
    from database import get_connection, row_to_dict

    with get_connection() as conn:
        apply_hr(conn, __import__("database"))
        row = conn.execute(
            """SELECT pl.*,
                      pr.document_no AS payroll_no, pr.payroll_month, pr.payroll_year,
                      pr.run_date, pr.status AS payroll_status,
                      e.full_name AS employee_name, e.code AS emp_code,
                      d.name AS department_name
               FROM payroll_lines pl
               JOIN payroll_runs pr ON pl.payroll_id=pr.id
               JOIN employees e ON pl.employee_id=e.id
               LEFT JOIN departments d ON e.department_id=d.id
               WHERE pl.id=?""",
            (int(line_id),),
        ).fetchone()
        data = row_to_dict(row) if row else None
    if not data:
        return None
    eid = int(data.get("employee_id") or 0)
    if eid:
        ctx = get_employee_advance_context(eid) or {}
        data["advance_outstanding"] = float(ctx.get("advance_outstanding") or 0)
        data["loan_outstanding"] = float(ctx.get("loan_outstanding") or 0)
        data["ledger_balance"] = float(ctx.get("ledger_balance") or 0)
    else:
        data["advance_outstanding"] = 0.0
        data["loan_outstanding"] = 0.0
        data["ledger_balance"] = 0.0
    return data


def _undo_gl_by_reference(conn, ref_type, ref_id):
    """Reverse CoA balances and delete GL rows for one reference."""
    for gl_row in conn.execute(
        "SELECT account_id, debit, credit FROM general_ledger WHERE reference_type=? AND reference_id=?",
        (ref_type, ref_id),
    ).fetchall():
        aid, dr, cr = gl_row[0], float(gl_row[1] or 0), float(gl_row[2] or 0)
        if dr:
            conn.execute(
                "UPDATE chart_of_accounts SET current_balance=current_balance-? WHERE id=?",
                (dr, aid),
            )
        if cr:
            conn.execute(
                "UPDATE chart_of_accounts SET current_balance=current_balance+? WHERE id=?",
                (cr, aid),
            )
    conn.execute(
        "DELETE FROM general_ledger WHERE reference_type=? AND reference_id=?",
        (ref_type, ref_id),
    )


def _undo_payroll_line_accrual(conn, line_id):
    """Reverse per-employee salary accrual (only when no whole-run payroll GL)."""
    row = conn.execute(
        "SELECT payroll_id FROM payroll_lines WHERE id=?", (line_id,),
    ).fetchone()
    if not row:
        return
    whole = conn.execute(
        "SELECT 1 FROM general_ledger WHERE reference_type='payroll' AND reference_id=? LIMIT 1",
        (int(row[0]),),
    ).fetchone()
    if whole:
        return  # month-level accrual remains
    _undo_gl_by_reference(conn, "payroll_line_accrual", int(line_id))
    _undo_gl_by_reference(conn, "payroll_line_adjust", int(line_id))


def _undo_payroll_line_payment(conn, line_id, reverse_accrual=True):
    """Reverse one employee salary payment (GL + cash/bank book row)."""
    import database as db

    row = conn.execute(
        """SELECT pl.*, pr.document_no AS payroll_no
           FROM payroll_lines pl
           JOIN payroll_runs pr ON pl.payroll_id=pr.id
           WHERE pl.id=?""",
        (line_id,),
    ).fetchone()
    if not row or dict(row).get("paid_status") != "paid":
        return
    row = dict(row)
    doc = row.get("payment_document_no") or ""
    _undo_gl_by_reference(conn, "payroll_line_payment", line_id)
    if doc and not str(doc).startswith("ADJ/"):
        cp = conn.execute(
            "SELECT payment_date FROM cash_payments WHERE document_no=?", (doc,),
        ).fetchone()
        if cp:
            from db_cash_day import assert_cash_day_open
            assert_cash_day_open(cp[0], "undo salary payment")
        conn.execute("DELETE FROM cash_payments WHERE document_no=?", (doc,))
        conn.execute("DELETE FROM bank_payments WHERE document_no=?", (doc,))
    conn.execute(
        """UPDATE payroll_lines SET paid_status='unpaid', paid_amount=0, paid_date=NULL,
           payment_mode=NULL, payment_document_no=NULL, paid_by=NULL, paid_at=NULL WHERE id=?""",
        (line_id,),
    )
    if reverse_accrual:
        _undo_payroll_line_accrual(conn, line_id)


def pay_payroll_line(line_id, user_id, payment_mode="cash", payment_date=None, bank_account_id=None):
    """Pay one employee — from draft (accrue + cash) or after month Post to GL.

    Draft / approved: posts this employee's salary accrual then cash/bank voucher.
    Posted / paid month: pays against the existing salary payable (no re-accrual).
    """
    import database as db
    from db_v3 import post_gl, post_gl_account_id, resolve_cash_account_id

    mode = (payment_mode or "cash").lower()
    if mode not in ("cash", "bank"):
        raise ValueError("Payment mode must be cash or bank.")
    if mode == "bank" and not bank_account_id:
        raise ValueError("Select a bank account for bank payment.")

    with db.get_connection() as conn:
        apply_hr(conn, db)
        row = conn.execute(
            """SELECT pl.*, pr.document_no AS payroll_no, pr.status AS payroll_status, pr.run_date,
                      e.full_name AS employee_name, e.code AS emp_code
               FROM payroll_lines pl
               JOIN payroll_runs pr ON pl.payroll_id=pr.id
               JOIN employees e ON pl.employee_id=e.id
               WHERE pl.id=?""",
            (line_id,),
        ).fetchone()
        if not row:
            raise ValueError("Payroll line not found.")
        row = dict(row)
        status = (row.get("payroll_status") or "").strip().lower()
        if status == "closed":
            raise ValueError("Payroll month is closed — reopen before paying or changing payments.")
        if status not in ("draft", "approved", "posted", "paid"):
            raise ValueError(f"Cannot pay from payroll status '{status}'.")
        if row.get("paid_status") == "paid":
            raise ValueError(f"Already paid ({row.get('payment_document_no') or '—'}).")
        amt = round(float(row.get("net_salary") or 0), 2)
        if amt <= 0:
            raise ValueError(
                "Net salary is zero or negative — nothing to pay. "
                "Save the sheet (or lower Advance/Loan) so Net is positive, then post again."
            )

        whole_posted = bool(conn.execute(
            "SELECT 1 FROM general_ledger WHERE reference_type='payroll' AND reference_id=? LIMIT 1",
            (int(row["payroll_id"]),),
        ).fetchone())
        if not whole_posted:
            # One-employee Post & voucher from Edit Lines / Pay Desk (draft)
            _post_payroll_line_accrual(conn, row, user_id)

        pay_date = str(payment_date or row.get("run_date") or now()[:10])
        label = f"Salary {row['payroll_no']} — {row['employee_name']} ({row['emp_code']})"
        ref = f"{row['payroll_no']}/{row['emp_code']}"

        if mode == "cash":
            entry_id, doc_no = db._add_cash_payment(
                conn, pay_date, label, ref, amt, user_id,
                party_type="employee", party_id=row["employee_id"],
            )
            asset_id = resolve_cash_account_id(conn)
        else:
            entry_id, doc_no = db._add_bank_payment(
                conn, pay_date, label, ref, amt, bank_account_id, user_id,
                party_type="employee", party_id=row["employee_id"],
            )
            asset_id = bank_account_id

        if not asset_id:
            raise ValueError("Cash/bank account not found for salary payment.")

        post_gl(conn, pay_date, HR_AC["salary_payable"], amt, 0, label, "payroll_line_payment", line_id, doc_no, user_id)
        # Both legs must use payroll line_id so undo reverses cash+payable together
        post_gl_account_id(conn, pay_date, asset_id, 0, amt, label, "payroll_line_payment", line_id, doc_no, user_id)

        conn.execute(
            """UPDATE payroll_lines SET paid_status='paid', paid_amount=?, paid_date=?,
               payment_mode=?, payment_document_no=?, paid_by=?, paid_at=? WHERE id=?""",
            (amt, pay_date, mode, doc_no, user_id, now(), line_id),
        )
        _refresh_payroll_paid_status(conn, row["payroll_id"], user_id)
        return {
            "document_no": doc_no,
            "amount": amt,
            "payment_mode": mode,
            "employee": row["employee_name"],
            "line_id": int(line_id),
            "payroll_id": int(row["payroll_id"]),
            "entry_id": int(entry_id) if entry_id else None,
        }


def post_and_pay_payroll_line(line_id, user_id, payment_mode="cash", payment_date=None, bank_account_id=None):
    """Alias for counter / Edit Lines: accrue this employee (if needed) + cash voucher."""
    return pay_payroll_line(line_id, user_id, payment_mode, payment_date, bank_account_id)


def settle_payroll_line_adjustment(line_id, user_id, note="", payment_date=None):
    """Mark a payroll line paid without cash/bank voucher.

    Use when net salary was already settled outside payroll cash (e.g. folded into
    a contractor/employee ledger such as Hafiz Zaman). Does not post GL or Cash Book.
    """
    from database import get_connection

    note = (note or "").strip() or "Ledger adjustment (no cash)"
    with get_connection() as conn:
        row = conn.execute(
            """SELECT pl.*, pr.document_no AS payroll_no, pr.status AS payroll_status, pr.run_date,
                      e.full_name AS employee_name, e.code AS emp_code
               FROM payroll_lines pl
               JOIN payroll_runs pr ON pl.payroll_id=pr.id
               JOIN employees e ON pl.employee_id=e.id
               WHERE pl.id=?""",
            (line_id,),
        ).fetchone()
        if not row:
            raise ValueError("Payroll line not found.")
        row = dict(row)
        if row["payroll_status"] == "closed":
            raise ValueError("Payroll month is closed — reopen before settling lines.")
        if row["payroll_status"] not in ("draft", "approved", "posted", "paid"):
            raise ValueError("Payroll must be draft, posted, or paid before settling lines.")
        if row.get("paid_status") == "paid":
            raise ValueError(f"Already paid ({row.get('payment_document_no') or '—'}).")
        amt = round(float(row.get("net_salary") or 0), 2)
        if amt <= 0:
            raise ValueError("Net salary is zero — nothing to settle.")
        pay_date = str(payment_date or row.get("paid_date") or row.get("run_date") or now()[:10])
        doc = f"ADJ/{row['payroll_no']}/{row['emp_code']}"
        # Truncate note into payment_document_no-friendly ref; keep full note via mode label
        conn.execute(
            """UPDATE payroll_lines SET paid_status='paid', paid_amount=?, paid_date=?,
               payment_mode=?, payment_document_no=?, paid_by=?, paid_at=? WHERE id=?""",
            (amt, pay_date, "adjustment", doc[:80], user_id, now(), line_id),
        )
        _refresh_payroll_paid_status(conn, row["payroll_id"], user_id)
        return {
            "document_no": doc,
            "amount": amt,
            "payment_mode": "adjustment",
            "employee": row["employee_name"],
            "note": note,
        }


def pay_payroll(payroll_id, user_id, payment_mode="cash", payment_date=None, bank_account_id=None):
    """Pay all unpaid employees on this payroll (one cash/bank entry per employee)."""
    from database import get_connection
    with get_connection() as conn:
        pr = conn.execute("SELECT status FROM payroll_runs WHERE id=?", (payroll_id,)).fetchone()
        if not pr:
            raise ValueError("Payroll not found.")
        if (pr[0] or "") == "closed":
            raise ValueError("Payroll month is closed — reopen before paying.")
        if pr[0] not in ("draft", "approved", "posted", "paid"):
            raise ValueError("Payroll must be draft, approved, or posted before payment")
        line_ids = [
            r[0] for r in conn.execute(
                """SELECT id FROM payroll_lines
                   WHERE payroll_id=? AND COALESCE(paid_status,'unpaid')!='paid'
                     AND COALESCE(net_salary,0)>0.009""",
                (payroll_id,),
            ).fetchall()
        ]
    if not line_ids:
        raise ValueError("All employees on this payroll are already paid.")
    paid = []
    for lid in line_ids:
        paid.append(
            pay_payroll_line(lid, user_id, payment_mode, payment_date, bank_account_id)
        )
    return paid


def rollback_payroll_line_payment(line_id, user_id, reason=""):
    """Undo a paid salary voucher — admin only (cash/bank + GL reverse)."""
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("Reason is required.")
    from database import get_connection
    with get_connection() as conn:
        apply_hr(conn, __import__("database"))
        _require_admin_user_id(conn, user_id, action="undo a paid salary voucher")
        row = conn.execute(
            """SELECT pl.payroll_id, pr.status, pl.paid_status, pl.payment_document_no
               FROM payroll_lines pl
               JOIN payroll_runs pr ON pr.id=pl.payroll_id
               WHERE pl.id=?""",
            (line_id,),
        ).fetchone()
        if not row:
            raise ValueError("Payroll line not found.")
        if (row[1] or "") == "closed":
            raise ValueError("Payroll month is closed — reopen before undoing a payment.")
        if (row[2] or "") != "paid":
            raise ValueError("This line is not marked paid.")
        payroll_id = row[0]
        _undo_payroll_line_payment(conn, line_id)
        _refresh_payroll_paid_status(conn, payroll_id, user_id)
        conn.execute(
            "UPDATE payroll_runs SET notes=COALESCE(notes,'') || ? WHERE id=?",
            (
                f"\nAdmin unlocked paid voucher {row[3] or line_id} "
                f"({now()}): {reason}",
                payroll_id,
            ),
        )


# ---------- Advances ----------
# Recoveries on draft/approved payroll are provisional — cash is still outstanding
# until the salary run is posted or paid.
_PAYROLL_RECOVERY_FINAL = frozenset({"posted", "paid"})


def _payroll_recovery_is_final(status) -> bool:
    return str(status or "").strip().lower() in _PAYROLL_RECOVERY_FINAL


def _provisional_advance_recovery_map(conn, employee_id=None) -> dict[int, float]:
    """advance_id → amount recovered only on non-final payroll (and employee not yet paid)."""
    q = """SELECT s.advance_id, COALESCE(SUM(s.amount),0) AS amt
           FROM advance_recovery_schedule s
           JOIN employee_advances a ON a.id=s.advance_id
           JOIN payroll_runs pr ON pr.id=s.payroll_id
           WHERE COALESCE(s.recovered,0)=1
             AND LOWER(COALESCE(pr.status,'')) NOT IN ('posted','paid')
             AND NOT EXISTS (
                 SELECT 1 FROM payroll_lines pl
                 WHERE pl.payroll_id=s.payroll_id
                   AND pl.employee_id=a.employee_id
                   AND COALESCE(pl.paid_status,'')='paid'
             )"""
    p = []
    if employee_id is not None:
        q += " AND a.employee_id=?"
        p.append(int(employee_id))
    q += " GROUP BY s.advance_id"
    return {int(r[0]): float(r[1] or 0) for r in conn.execute(q, p).fetchall()}


def _provisional_loan_recovery_map(conn, employee_id=None) -> dict[int, float]:
    """loan_id → installment amount recovered only on non-final unpaid payroll lines."""
    q = """SELECT i.loan_id, COALESCE(SUM(i.amount),0) AS amt
           FROM loan_installments i
           JOIN employee_loans l ON l.id=i.loan_id
           JOIN payroll_runs pr ON pr.id=i.payroll_id
           WHERE COALESCE(i.recovered,0)=1
             AND LOWER(COALESCE(pr.status,'')) NOT IN ('posted','paid')
             AND NOT EXISTS (
                 SELECT 1 FROM payroll_lines pl
                 WHERE pl.payroll_id=i.payroll_id
                   AND pl.employee_id=l.employee_id
                   AND COALESCE(pl.paid_status,'')='paid'
             )"""
    p = []
    if employee_id is not None:
        q += " AND l.employee_id=?"
        p.append(int(employee_id))
    q += " GROUP BY i.loan_id"
    return {int(r[0]): float(r[1] or 0) for r in conn.execute(q, p).fetchall()}


def _annotate_advance_effective(row: dict, provisional: dict[int, float]) -> dict:
    """Add effective_outstanding / display status (draft recoveries still outstanding)."""
    bump = float(provisional.get(int(row["id"]), 0) or 0)
    stored = float(row.get("outstanding_amount") or 0)
    effective = round(stored + bump, 2)
    amt = float(row.get("amount") or 0)
    row["effective_outstanding"] = effective
    row["effective_recovered"] = round(max(0.0, amt - effective), 2)
    st = (row.get("status") or "").lower()
    if effective > 0.009 and st in ("issued", "closed"):
        row["display_status"] = "issued"
    else:
        row["display_status"] = st or "issued"
    return row


def _annotate_loan_effective(row: dict, provisional: dict[int, float]) -> dict:
    bump = float(provisional.get(int(row["id"]), 0) or 0)
    stored = float(row.get("outstanding_amount") or 0)
    effective = round(stored + bump, 2)
    amt = float(row.get("amount") or 0)
    row["effective_outstanding"] = effective
    row["effective_recovered"] = round(max(0.0, amt - effective), 2)
    st = (row.get("status") or "").lower()
    if effective > 0.009 and st in ("issued", "closed"):
        row["display_status"] = "issued"
    else:
        row["display_status"] = st or "issued"
    return row


def _effective_advance_outstanding(conn, employee_id: int) -> float:
    stored = float(conn.execute(
        """SELECT COALESCE(SUM(outstanding_amount),0) FROM employee_advances
           WHERE employee_id=? AND status IN ('issued','closed')""",
        (int(employee_id),),
    ).fetchone()[0] or 0)
    bump = sum(_provisional_advance_recovery_map(conn, employee_id).values())
    return round(stored + bump, 2)


def _effective_loan_outstanding(conn, employee_id: int) -> float:
    stored = float(conn.execute(
        """SELECT COALESCE(SUM(outstanding_amount),0) FROM employee_loans
           WHERE employee_id=? AND status IN ('issued','closed')""",
        (int(employee_id),),
    ).fetchone()[0] or 0)
    bump = sum(_provisional_loan_recovery_map(conn, employee_id).values())
    return round(stored + bump, 2)


def _normalize_salary_month(raw) -> str | None:
    """Return YYYY-MM or None."""
    if raw is None or raw == "":
        return None
    s = str(raw).strip()[:7]
    if len(s) >= 7 and s[4] == "-":
        try:
            y, m = int(s[:4]), int(s[5:7])
            if 1 <= m <= 12:
                return f"{y:04d}-{m:02d}"
        except ValueError:
            pass
    return None


def _salary_month_due_date(salary_month: str | None, fallback_date: str) -> str:
    """Last day of salary month, else fallback (+0)."""
    import calendar
    sm = _normalize_salary_month(salary_month)
    if sm:
        y, m = int(sm[:4]), int(sm[5:7])
        return f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"
    return str(fallback_date)[:10]


def get_employee_advance_context(employee_id: int) -> dict | None:
    """Salary + ledger/outstanding snapshot for Advance / Loan New Request.

    Outstanding ignores recoveries that only sit on draft/approved payroll
    (cash is still out until salary is posted/paid).
    """
    emp = get_employee_hr(employee_id)
    if not emp:
        return None
    _, entries = get_employee_ledger(employee_id)
    closing = float(entries[-1]["balance"]) if entries else 0.0
    from database import get_connection
    with get_connection() as conn:
        apply_hr(conn, __import__("database"))
        adv_out = _effective_advance_outstanding(conn, int(employee_id))
        loan_out = _effective_loan_outstanding(conn, int(employee_id))
        basic = float(emp.get("basic_salary") or 0)
        struct = conn.execute(
            """SELECT basic_salary FROM salary_structures
               WHERE employee_id=? AND is_active=1
               ORDER BY effective_from DESC LIMIT 1""",
            (int(employee_id),),
        ).fetchone()
        if struct and float(struct[0] or 0) > 0:
            basic = float(struct[0] or 0)
    return {
        "employee_id": int(employee_id),
        "code": emp.get("code"),
        "full_name": emp.get("full_name"),
        "basic_salary": round(basic, 2),
        "ledger_balance": round(closing, 2),
        "advance_outstanding": round(adv_out, 2),
        "loan_outstanding": round(loan_out, 2),
    }


_LEDGER_NIL_TOL = 0.01
_FINAL_EXIT_STATUSES = frozenset({"left", "resigned", "terminated"})


def employee_final_settlement_status(employee_id: int) -> dict:
    """Whether employee ledger is clear enough to close final settlement.

    Ledger balance must be NIL (within 1 paisa). Positive = employee owes company;
    negative = company owes employee (unpaid salary / refund).
    """
    ctx = get_employee_advance_context(int(employee_id)) or {}
    bal = float(ctx.get("ledger_balance") or 0)
    adv = float(ctx.get("advance_outstanding") or 0)
    loan = float(ctx.get("loan_outstanding") or 0)
    clear = abs(bal) < _LEDGER_NIL_TOL
    return {
        "clear": clear,
        "ledger_balance": round(bal, 2),
        "advance_outstanding": round(adv, 2),
        "loan_outstanding": round(loan, 2),
        "message": (
            "Final settlement clear — ledger balance NIL."
            if clear
            else (
                f"Final settlement not done — ledger balance {bal:,.2f} "
                f"(advance {adv:,.2f}, loan {loan:,.2f}). "
                "Settle until balance is NIL before marking left."
            )
        ),
    }


def assert_final_settlement_clear(employee_id: int) -> None:
    """Raise if employee still has a non-NIL ledger balance."""
    st = employee_final_settlement_status(employee_id)
    if not st.get("clear"):
        raise ValueError(st["message"])


def save_advance(data, user_id=None):
    from database import get_connection, ensure_document_no
    with get_connection() as conn:
        apply_hr(conn, __import__("database"))
        months = max(1, int(data.get("recovery_months", 1)))
        monthly = round(data["amount"] / months, 2)
        salary_month = _normalize_salary_month(data.get("salary_month"))
        cur = conn.execute(
            """INSERT INTO employee_advances(document_no,employee_id,request_date,amount,reason,
               recovery_months,monthly_recovery,outstanding_amount,status,salary_month,created_by)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (ensure_document_no("ADV", data.get("document_no"), conn), data["employee_id"], data["request_date"],
             data["amount"], data.get("reason"), months, monthly, data["amount"], "pending",
             salary_month, user_id),
        )
        return cur.lastrowid


def get_advances(status=None, employee_id=None):
    from database import get_connection, rows_to_list
    q = """SELECT a.*, e.full_name AS employee_name, e.code AS employee_code
           FROM employee_advances a
           JOIN employees e ON a.employee_id=e.id WHERE 1=1"""
    p = []
    if status:
        q += " AND a.status=?"; p.append(status)
    if employee_id:
        q += " AND a.employee_id=?"; p.append(employee_id)
    q += " ORDER BY a.request_date DESC"
    with get_connection() as conn:
        apply_hr(conn, __import__("database"))
        rows = rows_to_list(conn.execute(q, p).fetchall())
        prov = _provisional_advance_recovery_map(conn, employee_id)
    for r in rows:
        code = (r.get("employee_code") or "").strip()
        name = (r.get("employee_name") or "").strip()
        if code and name:
            r["employee_name"] = f"{code} - {name}"
        _annotate_advance_effective(r, prov)
    return rows


def approve_advance(advance_id, user_id, approve=True):
    from database import get_connection
    ts = now()
    with get_connection() as conn:
        apply_hr(conn, __import__("database"))
        adv = conn.execute("SELECT * FROM employee_advances WHERE id=?", (advance_id,)).fetchone()
        if not adv or adv["status"] != "pending":
            raise ValueError("Invalid advance request")
        if approve:
            conn.execute(
                "UPDATE employee_advances SET status='approved',approved_by=?,approved_at=? WHERE id=?",
                (user_id, ts, advance_id),
            )
        else:
            conn.execute("UPDATE employee_advances SET status='rejected' WHERE id=?", (advance_id,))


def issue_advance(advance_id, user_id, payment_mode="cash", bank_account_id=None):
    """Issue approved salary advance: GL + cash/bank book voucher.

    GL: Dr Employee Advance, Cr Cash/Bank (posting date).
    Cash Book: CP/BP payment row so the till/bank book moves.
    """
    import database as db
    from db_v3 import post_gl, post_gl_account_id, resolve_cash_account_id

    mode = (payment_mode or "cash").lower()
    if mode not in ("cash", "bank"):
        raise ValueError("Payment mode must be cash or bank.")
    if mode == "bank" and not bank_account_id:
        raise ValueError("Select a bank account for bank payment.")

    with db.get_connection() as conn:
        apply_hr(conn, db)
        adv = conn.execute(
            """SELECT a.*, e.full_name AS employee_name, e.code AS emp_code
               FROM employee_advances a
               JOIN employees e ON e.id=a.employee_id
               WHERE a.id=?""",
            (advance_id,),
        ).fetchone()
        if not adv or adv["status"] != "approved":
            raise ValueError("Advance must be approved before issue")
        adv = dict(adv)
        amt = round(float(adv["amount"] or 0), 2)
        if amt <= 0:
            raise ValueError("Advance amount must be greater than zero.")
        post_date = str(adv["request_date"])[:10]
        emp_lbl = f"{adv.get('employee_name') or ''} ({adv.get('emp_code') or ''})".strip()
        label = f"Salary advance {adv['document_no']} - {emp_lbl}"
        ref = adv["document_no"]
        adv_acct = conn.execute(
            "SELECT id FROM chart_of_accounts WHERE code=?", (HR_AC["employee_advance"],)
        ).fetchone()
        adv_acct_id = int(adv_acct[0]) if adv_acct else None

        if mode == "cash":
            entry_id, doc_no = db._add_cash_payment(
                conn, post_date, label, ref, amt, user_id,
                account_id=adv_acct_id,
                party_type="account", party_id=adv_acct_id,
            )
            asset_id = resolve_cash_account_id(conn)
        else:
            entry_id, doc_no = db._add_bank_payment(
                conn, post_date, label, ref, amt, bank_account_id, user_id,
                party_type="account", party_id=adv_acct_id,
            )
            asset_id = bank_account_id

        if not asset_id:
            raise ValueError("Cash/bank account not found for advance issue.")

        # GL on posting date; recovery targets salary_month
        # Both legs use advance_id (do not set voucher_id — that FK is journal_vouchers only)
        post_gl(
            conn, post_date, HR_AC["employee_advance"], amt, 0,
            label, "employee_advance", advance_id, doc_no, user_id,
        )
        post_gl_account_id(
            conn, post_date, asset_id, 0, amt,
            label, "employee_advance", advance_id, doc_no, user_id,
        )
        conn.execute(
            """UPDATE employee_advances
               SET status='issued', issued_by=?, issued_at=?,
                   payment_mode=?, payment_document_no=?
               WHERE id=?""",
            (user_id, now(), mode, doc_no, advance_id),
        )
        from datetime import timedelta
        due0 = _salary_month_due_date(adv.get("salary_month"), post_date)
        base = datetime.strptime(due0, "%Y-%m-%d")
        monthly = adv["monthly_recovery"]
        for i in range(int(adv["recovery_months"] or 1)):
            if i == 0:
                due = due0
            else:
                due = (base + timedelta(days=30 * i)).strftime("%Y-%m-%d")
            conn.execute(
                "INSERT INTO advance_recovery_schedule(advance_id,installment_no,due_date,amount) VALUES(?,?,?,?)",
                (advance_id, i + 1, due, monthly),
            )
        sync = _sync_employee_recoveries_on_draft_payroll(
            conn, adv["employee_id"], adv.get("salary_month"),
        )
        out = {
            "document_no": adv["document_no"],
            "payment_document_no": doc_no,
            "payment_id": entry_id,
            "vch_source": "cash_payment" if mode == "cash" else "bank_payment",
            "amount": amt,
            "payment_mode": mode,
            "employee": adv.get("employee_name"),
        }
        if sync:
            out["payroll_sync"] = sync
        return out


def list_advances_for_cash_return(limit: int = 50):
    """Issued advances, plus closed ones recovered only on a draft payroll (cash return still needed)."""
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        apply_hr(conn, __import__("database"))
        rows = rows_to_list(conn.execute(
            """SELECT a.*, e.full_name AS employee_name, e.code AS employee_code,
                      COALESCE(a.outstanding_amount,0) AS outstanding_amount
               FROM employee_advances a
               JOIN employees e ON e.id=a.employee_id
               WHERE (
                   (a.status='issued' AND COALESCE(a.outstanding_amount,0)>0.01)
                   OR (
                       a.status='closed'
                       AND TRIM(COALESCE(a.settlement_document_no,''))=''
                       AND EXISTS (
                           SELECT 1 FROM advance_recovery_schedule s
                           JOIN payroll_runs pr ON pr.id=s.payroll_id
                           WHERE s.advance_id=a.id
                             AND COALESCE(s.recovered,0)=1
                             AND pr.status='draft'
                       )
                   )
               )
               ORDER BY a.id DESC
               LIMIT ?""",
            (int(limit),),
        ).fetchall())
    for r in rows:
        code = (r.get("employee_code") or "").strip()
        name = (r.get("employee_name") or "").strip()
        if code and name:
            r["employee_name"] = f"{code} - {name}"
        out = float(r.get("outstanding_amount") or 0)
        if out <= 0.01:
            # Draft-closed: show original amount as still due until cash settled
            out = round(float(r.get("amount") or 0) - float(r.get("recovered_amount") or 0), 2)
            if out <= 0.01:
                out = round(float(r.get("amount") or 0), 2)
            r["outstanding_amount"] = out
        r["effective_outstanding"] = out
    return rows


def settle_advance_cash_return(
    advance_id,
    user_id,
    *,
    return_date=None,
    payment_mode="cash",
    bank_account_id=None,
    notes=None,
):
    """Employee returned salary-advance cash (same/next day) — close without payroll.

    GL: Dr Cash/Bank, Cr Employee Advance (100180).
    Cash/Bank Book: CR/BR receipt. Advance status → closed; draft payroll recovery cleared.
    """
    import database as db
    from db_v3 import post_gl, post_gl_account_id, resolve_cash_account_id

    mode = (payment_mode or "cash").lower()
    if mode not in ("cash", "bank"):
        raise ValueError("Payment mode must be cash or bank.")
    if mode == "bank" and not bank_account_id:
        raise ValueError("Select a bank account for bank receipt.")

    with db.get_connection() as conn:
        apply_hr(conn, db)
        adv = conn.execute(
            """SELECT a.*, e.full_name AS employee_name, e.code AS emp_code
               FROM employee_advances a
               JOIN employees e ON e.id=a.employee_id
               WHERE a.id=?""",
            (int(advance_id),),
        ).fetchone()
        if not adv:
            raise ValueError("Advance not found.")
        adv = dict(adv)
        status = (adv.get("status") or "").lower()
        if status not in ("issued", "closed"):
            raise ValueError("Only issued (or draft-recovered) advances can be settled by cash return.")

        # Revert draft-only payroll recoveries so outstanding is the cash still due
        draft_rows = conn.execute(
            """SELECT s.id, s.amount, s.payroll_id, pr.document_no, pr.status
               FROM advance_recovery_schedule s
               LEFT JOIN payroll_runs pr ON pr.id=s.payroll_id
               WHERE s.advance_id=? AND COALESCE(s.recovered,0)=1""",
            (int(advance_id),),
        ).fetchall()
        if status == "closed" and not draft_rows:
            raise ValueError(
                "Advance is already closed with no draft payroll recovery to reverse. "
                "Cash return is only for advances still open or recovered only on a draft payroll."
            )
        for row in draft_rows:
            pr_status = str((row["status"] if row else "") or "").lower()
            if pr_status and pr_status not in ("draft", ""):
                raise ValueError(
                    f"Advance already recovered on payroll {row['document_no'] or row['payroll_id']} "
                    f"({pr_status}). Cannot settle by cash return."
                )
            amt = round(float(row["amount"] or 0), 2)
            if amt > 0:
                cur = conn.execute(
                    "SELECT recovered_amount, outstanding_amount, amount FROM employee_advances WHERE id=?",
                    (int(advance_id),),
                ).fetchone()
                if cur:
                    new_rec = max(0.0, float(cur[0] or 0) - amt)
                    new_out = min(float(cur[2] or 0), float(cur[1] or 0) + amt)
                    conn.execute(
                        """UPDATE employee_advances
                           SET recovered_amount=?, outstanding_amount=?, status='issued'
                           WHERE id=?""",
                        (new_rec, new_out, int(advance_id)),
                    )
            conn.execute(
                """UPDATE advance_recovery_schedule
                   SET recovered=0, recovered_date=NULL, payroll_id=NULL WHERE id=?""",
                (int(row["id"]),),
            )

        adv = dict(conn.execute(
            """SELECT a.*, e.full_name AS employee_name, e.code AS emp_code
               FROM employee_advances a
               JOIN employees e ON e.id=a.employee_id
               WHERE a.id=?""",
            (int(advance_id),),
        ).fetchone())
        out_amt = round(float(adv.get("outstanding_amount") or 0), 2)
        if out_amt <= 0.01:
            raise ValueError("Advance outstanding is already NIL.")

        post_date = str(return_date or date.today())[:10]
        emp_lbl = f"{adv.get('employee_name') or ''} ({adv.get('emp_code') or ''})".strip()
        label = f"Advance return {adv['document_no']} - {emp_lbl}"
        if notes:
            label = f"{label} — {str(notes).strip()[:80]}"
        ref = adv["document_no"]
        adv_acct = conn.execute(
            "SELECT id FROM chart_of_accounts WHERE code=?", (HR_AC["employee_advance"],)
        ).fetchone()
        adv_acct_id = int(adv_acct[0]) if adv_acct else None
        if not adv_acct_id:
            raise ValueError("Employee Advance account (100180) not found.")

        if mode == "cash":
            entry_id, doc_no = db._add_cash_receipt(
                conn, post_date, label, ref, out_amt, user_id,
                account_id=adv_acct_id,
                party_type="account", party_id=adv_acct_id,
            )
            asset_id = resolve_cash_account_id(conn)
        else:
            entry_id, doc_no = db._add_bank_receipt(
                conn, post_date, label, ref, out_amt, bank_account_id, user_id,
                party_type="account", party_id=adv_acct_id,
            )
            asset_id = bank_account_id

        if not asset_id:
            raise ValueError("Cash/bank account not found for settlement receipt.")

        # Reverse the advance receivable: Dr Cash/Bank, Cr Employee Advance
        post_gl_account_id(
            conn, post_date, asset_id, out_amt, 0,
            label, "employee_advance_return", int(advance_id), doc_no, user_id,
        )
        post_gl(
            conn, post_date, HR_AC["employee_advance"], 0, out_amt,
            label, "employee_advance_return", int(advance_id), doc_no, user_id,
        )

        new_rec = round(float(adv.get("recovered_amount") or 0) + out_amt, 2)
        conn.execute(
            """UPDATE employee_advances
               SET recovered_amount=?, outstanding_amount=0, status='closed',
                   settlement_document_no=?, settled_at=?, settled_by=?,
                   settlement_notes=?
               WHERE id=?""",
            (
                new_rec, doc_no, now(), user_id,
                (str(notes).strip() if notes else None),
                int(advance_id),
            ),
        )
        conn.execute(
            "DELETE FROM advance_recovery_schedule WHERE advance_id=?",
            (int(advance_id),),
        )

        sync = _sync_employee_recoveries_on_draft_payroll(
            conn, adv["employee_id"], adv.get("salary_month"),
        )
        return {
            "document_no": adv["document_no"],
            "settlement_document_no": doc_no,
            "receipt_id": entry_id,
            "vch_source": "cash_receipt" if mode == "cash" else "bank_receipt",
            "amount": out_amt,
            "payment_mode": mode,
            "employee": adv.get("employee_name"),
            "return_date": post_date,
            "payroll_sync": sync,
        }


def backfill_advance_cash_voucher(advance_id, user_id=None):
    """Create missing cash/bank book voucher for an already-issued advance (GL already posted)."""
    import database as db

    with db.get_connection() as conn:
        apply_hr(conn, db)
        adv = conn.execute(
            """SELECT a.*, e.full_name AS employee_name, e.code AS emp_code
               FROM employee_advances a
               JOIN employees e ON e.id=a.employee_id
               WHERE a.id=?""",
            (int(advance_id),),
        ).fetchone()
        if not adv:
            raise ValueError("Advance not found.")
        adv = dict(adv)
        if (adv.get("status") or "") != "issued":
            raise ValueError("Only issued advances can be backfilled.")
        existing = (adv.get("payment_document_no") or "").strip()
        if existing:
            row = conn.execute(
                "SELECT id FROM cash_payments WHERE document_no=? UNION ALL "
                "SELECT id FROM bank_payments WHERE document_no=?",
                (existing, existing),
            ).fetchone()
            if row:
                return {"payment_document_no": existing, "created": False}
        # Avoid duplicate if CP already linked by ADV reference
        dup = conn.execute(
            "SELECT document_no FROM cash_payments WHERE reference_no=? LIMIT 1",
            (adv["document_no"],),
        ).fetchone()
        if dup:
            conn.execute(
                "UPDATE employee_advances SET payment_mode=?, payment_document_no=? WHERE id=?",
                ("cash", dup[0], advance_id),
            )
            return {"payment_document_no": dup[0], "created": False}

        amt = round(float(adv["amount"] or 0), 2)
        post_date = str(adv["request_date"])[:10]
        emp_lbl = f"{adv.get('employee_name') or ''} ({adv.get('emp_code') or ''})".strip()
        label = f"Salary advance {adv['document_no']} - {emp_lbl}"
        adv_acct = conn.execute(
            "SELECT id FROM chart_of_accounts WHERE code=?", (HR_AC["employee_advance"],)
        ).fetchone()
        adv_acct_id = int(adv_acct[0]) if adv_acct else None
        entry_id, doc_no = db._add_cash_payment(
            conn, post_date, label, adv["document_no"], amt, user_id,
            account_id=adv_acct_id,
            party_type="account", party_id=adv_acct_id,
        )
        conn.execute(
            "UPDATE employee_advances SET payment_mode=?, payment_document_no=? WHERE id=?",
            ("cash", doc_no, advance_id),
        )
        # GL already posted on issue — do not post again
        return {
            "payment_document_no": doc_no,
            "entry_id": int(entry_id),
            "amount": amt,
            "created": True,
            "document_no": adv["document_no"],
        }


# ---------- Loans ----------
def save_loan(data, user_id=None):
    """Create pending loan. Installments by months or fixed monthly amount."""
    import math
    from database import get_connection, ensure_document_no

    amt = round(float(data.get("amount") or 0), 2)
    if amt <= 0:
        raise ValueError("Loan amount must be greater than zero.")

    mode = (data.get("installment_mode") or "months").strip().lower()
    if mode in ("amount", "monthly", "fixed"):
        monthly = round(float(data.get("monthly_installment") or 0), 2)
        if monthly <= 0:
            raise ValueError("Enter a monthly recovery amount greater than zero.")
        if monthly > amt:
            raise ValueError("Monthly recovery cannot exceed the loan amount.")
        inst = max(1, int(math.ceil(amt / monthly - 1e-9)))
        # Keep user-entered monthly; last installment absorbs remainder on issue
    else:
        inst = max(1, int(data.get("installments") or 12))
        monthly = round(amt / inst, 2)

    with get_connection() as conn:
        apply_hr(conn, __import__("database"))
        cur = conn.execute(
            """INSERT INTO employee_loans(document_no,employee_id,issue_date,amount,installments,
               monthly_installment,outstanding_amount,reason,status,created_by)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (ensure_document_no("LON", data.get("document_no"), conn), data["employee_id"], data["issue_date"],
             amt, inst, monthly, amt, data.get("reason"), "pending", user_id),
        )
        return cur.lastrowid


def get_loans(status=None, employee_id=None):
    from database import get_connection, rows_to_list
    q = """SELECT l.*, e.full_name AS employee_name, e.code AS employee_code
           FROM employee_loans l
           JOIN employees e ON l.employee_id=e.id WHERE 1=1"""
    p = []
    if status:
        q += " AND l.status=?"; p.append(status)
    if employee_id:
        q += " AND l.employee_id=?"; p.append(employee_id)
    q += " ORDER BY l.issue_date DESC"
    with get_connection() as conn:
        apply_hr(conn, __import__("database"))
        rows = rows_to_list(conn.execute(q, p).fetchall())
        prov = _provisional_loan_recovery_map(conn, employee_id)
    for r in rows:
        code = (r.get("employee_code") or "").strip()
        name = (r.get("employee_name") or "").strip()
        if code and name:
            r["employee_name"] = f"{code} - {name}"
        _annotate_loan_effective(r, prov)
    return rows


def approve_loan(loan_id, user_id, approve=True):
    from database import get_connection
    ts = now()
    with get_connection() as conn:
        ln = conn.execute("SELECT * FROM employee_loans WHERE id=?", (loan_id,)).fetchone()
        if not ln or ln["status"] != "pending":
            raise ValueError("Invalid loan request")
        if approve:
            conn.execute(
                "UPDATE employee_loans SET status='approved',approved_by=?,approved_at=? WHERE id=?",
                (user_id, ts, loan_id),
            )
        else:
            conn.execute("UPDATE employee_loans SET status='rejected' WHERE id=?", (loan_id,))


def issue_loan(loan_id, user_id, payment_mode="cash", bank_account_id=None):
    """Issue approved loan: GL + cash/bank book voucher."""
    import database as db
    from db_v3 import post_gl, post_gl_account_id, resolve_cash_account_id

    mode = (payment_mode or "cash").lower()
    if mode not in ("cash", "bank"):
        raise ValueError("Payment mode must be cash or bank.")
    if mode == "bank" and not bank_account_id:
        raise ValueError("Select a bank account for bank payment.")

    with db.get_connection() as conn:
        apply_hr(conn, db)
        ln = conn.execute(
            """SELECT l.*, e.full_name AS employee_name, e.code AS emp_code
               FROM employee_loans l
               JOIN employees e ON e.id=l.employee_id
               WHERE l.id=?""",
            (loan_id,),
        ).fetchone()
        if not ln or ln["status"] != "approved":
            raise ValueError("Loan must be approved before issue")
        ln = dict(ln)
        amt = round(float(ln["amount"] or 0), 2)
        if amt <= 0:
            raise ValueError("Loan amount must be greater than zero.")
        post_date = str(ln["issue_date"])[:10]
        emp_lbl = f"{ln.get('employee_name') or ''} ({ln.get('emp_code') or ''})".strip()
        label = f"Employee loan {ln['document_no']} - {emp_lbl}"
        ref = ln["document_no"]
        adv_acct = conn.execute(
            "SELECT id FROM chart_of_accounts WHERE code=?", (HR_AC["employee_advance"],)
        ).fetchone()
        adv_acct_id = int(adv_acct[0]) if adv_acct else None

        if mode == "cash":
            entry_id, doc_no = db._add_cash_payment(
                conn, post_date, label, ref, amt, user_id,
                account_id=adv_acct_id,
                party_type="account", party_id=adv_acct_id,
            )
            asset_id = resolve_cash_account_id(conn)
        else:
            entry_id, doc_no = db._add_bank_payment(
                conn, post_date, label, ref, amt, bank_account_id, user_id,
                party_type="account", party_id=adv_acct_id,
            )
            asset_id = bank_account_id

        if not asset_id:
            raise ValueError("Cash/bank account not found for loan issue.")

        post_gl(
            conn, post_date, HR_AC["employee_advance"], amt, 0,
            label, "employee_loan", loan_id, doc_no, user_id,
        )
        post_gl_account_id(
            conn, post_date, asset_id, 0, amt,
            label, "employee_loan", loan_id, doc_no, user_id,
        )
        conn.execute(
            """UPDATE employee_loans
               SET status='issued', issued_by=?, issued_at=?,
                   payment_mode=?, payment_document_no=?
               WHERE id=?""",
            (user_id, now(), mode, doc_no, loan_id),
        )
        from datetime import timedelta
        base = datetime.strptime(post_date, "%Y-%m-%d")
        n_inst = max(1, int(ln["installments"] or 1))
        monthly = round(float(ln["monthly_installment"] or 0), 2)
        remaining = amt
        for i in range(n_inst):
            due = (base + timedelta(days=30 * (i + 1))).strftime("%Y-%m-%d")
            if i == n_inst - 1:
                part = round(remaining, 2)
            else:
                part = round(min(monthly, remaining), 2)
                remaining = round(remaining - part, 2)
            if part <= 0:
                break
            conn.execute(
                "INSERT INTO loan_installments(loan_id,installment_no,due_date,amount) VALUES(?,?,?,?)",
                (loan_id, i + 1, due, part),
            )
        return {
            "document_no": ln["document_no"],
            "payment_document_no": doc_no,
            "payment_id": entry_id,
            "vch_source": "cash_payment" if mode == "cash" else "bank_payment",
            "amount": amt,
            "payment_mode": mode,
            "employee": ln.get("employee_name"),
        }


def resolve_cash_bank_voucher(document_no):
    """Map CP-/BP- document_no → {id, vch_source, document_no} for print toolbar."""
    from database import get_connection

    doc = (document_no or "").strip()
    if not doc:
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM cash_payments WHERE document_no=?", (doc,),
        ).fetchone()
        if row:
            return {"id": int(row[0]), "vch_source": "cash_payment", "document_no": doc}
        row = conn.execute(
            "SELECT id FROM bank_payments WHERE document_no=?", (doc,),
        ).fetchone()
        if row:
            return {"id": int(row[0]), "vch_source": "bank_payment", "document_no": doc}
    return None


# ---------- Expense claims ----------
def save_expense_claim(data, user_id=None):
    from database import get_connection, ensure_document_no
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO expense_claims(document_no,employee_id,claim_date,description,amount,status,created_by)
               VALUES(?,?,?,?,?,?,?)""",
            (ensure_document_no("EXP", data.get("document_no"), conn), data["employee_id"], data["claim_date"],
             data["description"], data["amount"], "pending", user_id),
        )
        return cur.lastrowid


def get_expense_claims(status=None):
    from database import get_connection, rows_to_list
    q = """SELECT c.*, e.full_name AS employee_name FROM expense_claims c
           JOIN employees e ON c.employee_id=e.id WHERE 1=1"""
    p = []
    if status:
        q += " AND c.status=?"; p.append(status)
    q += " ORDER BY c.claim_date DESC"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


def approve_expense_claim(claim_id, user_id, approve=True):
    from database import get_connection
    ts = now()
    with get_connection() as conn:
        if approve:
            conn.execute(
                "UPDATE expense_claims SET status='approved',approved_by=?,approved_at=? WHERE id=? AND status='pending'",
                (user_id, ts, claim_id),
            )
        else:
            conn.execute("UPDATE expense_claims SET status='rejected' WHERE id=?", (claim_id,))


def reimburse_expense_claim(claim_id, user_id, payment_mode="cash"):
    from database import get_connection
    from db_v3 import post_gl, resolve_cash_account_code, AC
    with get_connection() as conn:
        cl = conn.execute("SELECT * FROM expense_claims WHERE id=?", (claim_id,)).fetchone()
        if not cl or cl["status"] != "approved" or cl["reimbursed"]:
            raise ValueError("Claim must be approved and not yet reimbursed")
        cl = dict(cl)
        acct = AC["bank"] if payment_mode == "bank" else resolve_cash_account_code(conn)
        post_gl(conn, cl["claim_date"], HR_AC["salary_expense"], cl["amount"], 0,
                "Expense reimbursement", "expense_claim", claim_id, cl["document_no"], user_id)
        post_gl(conn, cl["claim_date"], acct, 0, cl["amount"],
                "Expense reimbursement", "expense_claim", claim_id, cl["document_no"], user_id)
        conn.execute(
            "UPDATE expense_claims SET reimbursed=1,reimbursed_date=?,payment_mode=? WHERE id=?",
            (now()[:10], payment_mode, claim_id),
        )


# ---------- HR Reports ----------
def report_employee_list(active_only=True):
    """Active employee master (includes joining date + service tenure)."""
    return report_employee_service(active_only=active_only)


def _iso_date_or_none(raw):
    s = str(raw or "").strip()[:10]
    if not s:
        return None
    try:
        y, m, d = int(s[:4]), int(s[5:7]), int(s[8:10])
        return date(y, m, d)
    except (TypeError, ValueError):
        return None


def _service_ym(join_d: date, as_of: date) -> tuple[int, int, int]:
    """Return (years, months, total_months) from join_d to as_of inclusive of calendar span."""
    if as_of < join_d:
        return 0, 0, 0
    total_months = (as_of.year - join_d.year) * 12 + (as_of.month - join_d.month)
    if as_of.day < join_d.day:
        total_months -= 1
    if total_months < 0:
        total_months = 0
    return total_months // 12, total_months % 12, total_months


def report_employee_service(active_only=True, as_of_date=None, department_id=None):
    """Employee joining / service tenure report.

    Service is measured to ``as_of_date`` (default today), or to leaving_date when
    the employee has already left (whichever is earlier).
    """
    as_of = _iso_date_or_none(as_of_date) or date.today()
    rows = get_employees_hr(active_only=False)
    out = []
    for r in rows or []:
        if active_only and not r.get("is_active"):
            continue
        if department_id is not None and int(r.get("department_id") or 0) != int(department_id):
            continue
        join_d = _iso_date_or_none(r.get("joining_date"))
        leave_d = _iso_date_or_none(r.get("leaving_date"))
        end_d = as_of
        if leave_d and leave_d < end_d:
            end_d = leave_d
        if join_d:
            years, months, total_m = _service_ym(join_d, end_d)
            if years and months:
                service_lbl = f"{years} year{'s' if years != 1 else ''} {months} month{'s' if months != 1 else ''}"
            elif years:
                service_lbl = f"{years} year{'s' if years != 1 else ''}"
            elif months:
                service_lbl = f"{months} month{'s' if months != 1 else ''}"
            else:
                service_lbl = "Under 1 month"
        else:
            years = months = total_m = None
            service_lbl = "—"
        out.append({
            "code": r.get("code"),
            "full_name": r.get("full_name"),
            "department_name": r.get("department_name") or r.get("department") or "—",
            "designation_name": r.get("designation_name") or r.get("designation") or "—",
            "mobile": r.get("mobile") or r.get("phone") or "—",
            "joining_date": str(join_d) if join_d else "",
            "leaving_date": str(leave_d) if leave_d else "",
            "service_years": years if years is not None else "",
            "service_months": months if months is not None else "",
            "service_total_months": total_m if total_m is not None else "",
            "service": service_lbl,
            "employment_status": r.get("employment_status") or ("active" if r.get("is_active") else "inactive"),
            "basic_salary": float(r.get("basic_salary") or 0),
            "is_active": "Active" if r.get("is_active") else "Inactive",
            "as_of": str(end_d),
        })
    out.sort(
        key=lambda x: (
            str(x.get("department_name") or ""),
            str(x.get("full_name") or ""),
            str(x.get("code") or ""),
        )
    )
    return out


def report_attendance(from_date, to_date, employee_id=None):
    return get_attendance(from_date, to_date, employee_id)


def report_leave(from_date=None, to_date=None):
    from database import get_connection, rows_to_list
    q = """SELECT lr.*, e.full_name AS employee_name, lt.name AS leave_type_name
           FROM leave_requests lr JOIN employees e ON lr.employee_id=e.id
           JOIN leave_types lt ON lr.leave_type_id=lt.id WHERE 1=1"""
    p = []
    if from_date:
        q += " AND lr.from_date>=?"; p.append(from_date)
    if to_date:
        q += " AND lr.to_date<=?"; p.append(to_date)
    q += " ORDER BY lr.from_date DESC"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


def report_overtime(from_date, to_date):
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            """SELECT e.id AS employee_id, e.code, e.full_name,
                      COALESCE(d.name, e.department, 'Unassigned') AS department_name,
                      SUM(a.overtime_hrs) AS total_overtime_hrs, COUNT(*) AS days
               FROM attendance a
               JOIN employees e ON a.employee_id=e.id
               LEFT JOIN departments d ON e.department_id=d.id
               WHERE a.att_date>=? AND a.att_date<=? AND a.overtime_hrs>0
               GROUP BY e.id
               ORDER BY COALESCE(d.name, e.department, 'Unassigned'), total_overtime_hrs DESC""",
            (from_date, to_date),
        ).fetchall())


def report_payroll_register(from_date=None, to_date=None):
    from database import get_connection, rows_to_list
    q = """SELECT pr.document_no, pr.payroll_month, pr.payroll_year, pr.run_date, pr.status,
                  pr.total_gross, pr.total_deductions, pr.total_net,
                  pl.*, e.full_name AS employee_name,
                  COALESCE(d.name, e.department, 'Unassigned') AS department_name
           FROM payroll_runs pr JOIN payroll_lines pl ON pr.id=pl.payroll_id
           JOIN employees e ON pl.employee_id=e.id
           LEFT JOIN departments d ON e.department_id=d.id
           WHERE 1=1"""
    p = []
    if from_date:
        q += " AND pr.run_date>=?"; p.append(from_date)
    if to_date:
        q += " AND pr.run_date<=?"; p.append(to_date)
    q += """ ORDER BY pr.payroll_year DESC, pr.payroll_month DESC,
                     COALESCE(d.name, e.department, 'Unassigned'), e.full_name"""
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


def report_salary_sheet(payroll_id):
    return get_payroll_run(payroll_id)


def report_outstanding_advances():
    """Advances still owed — includes those only recovered on draft payroll."""
    rows = get_advances() or []
    out = []
    for r in rows:
        if (r.get("status") or "").lower() in ("rejected", "pending", "approved"):
            continue
        if float(r.get("effective_outstanding") or 0) > 0.009:
            # Expose effective figures as the report columns
            r = dict(r)
            r["outstanding_amount"] = r["effective_outstanding"]
            r["recovered_amount"] = r.get("effective_recovered")
            r["status"] = r.get("display_status") or r.get("status")
            out.append(r)
    return out


def report_outstanding_loans():
    rows = get_loans() or []
    out = []
    for r in rows:
        if (r.get("status") or "").lower() in ("rejected", "pending", "approved"):
            continue
        if float(r.get("effective_outstanding") or 0) > 0.009:
            r = dict(r)
            r["outstanding_amount"] = r["effective_outstanding"]
            r["recovered_amount"] = r.get("effective_recovered")
            r["status"] = r.get("display_status") or r.get("status")
            out.append(r)
    return out


def report_dept_salary_cost(payroll_id):
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            """SELECT COALESCE(d.name, e.department, 'Unassigned') AS department,
                      COUNT(pl.id) AS employees, SUM(pl.gross_salary) AS gross,
                      SUM(pl.total_deductions) AS deductions, SUM(pl.net_salary) AS net
               FROM payroll_lines pl
               JOIN employees e ON pl.employee_id=e.id
               LEFT JOIN departments d ON e.department_id=d.id
               WHERE pl.payroll_id=?
               GROUP BY COALESCE(d.name, e.department, 'Unassigned')
               ORDER BY net DESC""",
            (payroll_id,),
        ).fetchall())


def get_employee_ledger(employee_id, from_date=None, to_date=None):
    """Employee sub-ledger: advances, loans, payroll recoveries, and net salary.

    Sign: Debit increases balance (employee owes / advance issued / salary paid).
    Credit decreases balance (recoveries / net salary accrued).
    Closing should equal outstanding advances+loans minus unpaid net salary.

    Historical payroll imports often include recoveries without matching issue
    documents. A computed Opening Balance bridges that gap so the running
    balance stays meaningful.
    """
    from database import get_connection, rows_to_list

    emp = get_employee_hr(employee_id)
    if not emp:
        return None, []

    fd = str(from_date)[:10] if from_date else None
    td = str(to_date)[:10] if to_date else None

    raw = []
    out_adv = 0.0
    out_loan = 0.0

    with get_connection() as conn:
        out_adv = _effective_advance_outstanding(conn, int(employee_id))
        out_loan = _effective_loan_outstanding(conn, int(employee_id))

        for adv in rows_to_list(conn.execute(
            """SELECT document_no, request_date, issued_at, amount, outstanding_amount, status
               FROM employee_advances WHERE employee_id=? AND status IN ('issued','closed')""",
            (employee_id,),
        ).fetchall()):
            dt = adv.get("issued_at") or adv.get("request_date")
            raw.append((dt, adv["document_no"], "Advance issued", float(adv["amount"] or 0), 0.0))

        for ln in rows_to_list(conn.execute(
            """SELECT document_no, issue_date, issued_at, amount, outstanding_amount, status
               FROM employee_loans WHERE employee_id=? AND status IN ('issued','closed')""",
            (employee_id,),
        ).fetchall()):
            dt = ln.get("issued_at") or ln.get("issue_date")
            raw.append((dt, ln["document_no"], "Loan issued", float(ln["amount"] or 0), 0.0))

        payroll_rows = rows_to_list(conn.execute(
            """SELECT pr.document_no, pr.run_date, pr.payroll_month, pr.payroll_year, pr.status,
                      pl.advance_recovery, pl.loan_recovery, pl.net_salary,
                      pl.paid_status, pl.paid_amount, pl.paid_date,
                      pl.payment_document_no, pl.payment_mode
               FROM payroll_lines pl
               JOIN payroll_runs pr ON pl.payroll_id=pr.id
               WHERE pl.employee_id=?
               ORDER BY pr.run_date, pr.id""",
            (employee_id,),
        ).fetchall())
        for pr in payroll_rows:
            dt = pr.get("run_date")
            ref = pr.get("document_no") or "PAY"
            period = f"{pr.get('payroll_month')}/{pr.get('payroll_year')}"
            adv_rec = float(pr.get("advance_recovery") or 0)
            loan_rec = float(pr.get("loan_recovery") or 0)
            net = float(pr.get("net_salary") or 0)
            line_paid = (pr.get("paid_status") or "") in ("paid", "partial")
            # Draft payroll recoveries/net become final once this employee voucher is paid
            recovery_final = _payroll_recovery_is_final(pr.get("status")) or line_paid
            if recovery_final:
                if adv_rec:
                    raw.append((dt, ref, f"Advance recovery ({period})", 0.0, adv_rec))
                if loan_rec:
                    raw.append((dt, ref, f"Loan recovery ({period})", 0.0, loan_rec))
            if net and (pr.get("status") in ("posted", "paid", "approved") or line_paid):
                raw.append((dt, ref, f"Net salary ({period})", 0.0, net))
            paid_amt = float(pr.get("paid_amount") or 0)
            if paid_amt > 0 and line_paid:
                pay_dt = pr.get("paid_date") or dt
                doc = pr.get("payment_document_no") or ref
                mode = (pr.get("payment_mode") or "cash").title()
                raw.append((pay_dt, doc, f"Salary paid {mode} ({period})", paid_amt, 0.0))

        # Unpaid net salary (company owes employee) — use live line amounts
        unpaid_row = conn.execute(
            """SELECT COALESCE(SUM(
                   CASE
                     WHEN pr.status IN ('posted','paid','approved')
                       THEN MAX(0, COALESCE(pl.net_salary,0) - COALESCE(pl.paid_amount,0))
                     ELSE 0
                   END
               ), 0)
               FROM payroll_lines pl
               JOIN payroll_runs pr ON pl.payroll_id=pr.id
               WHERE pl.employee_id=?""",
            (employee_id,),
        ).fetchone()
        unpaid_salary = float(unpaid_row[0] if unpaid_row else 0)

    raw.sort(key=lambda x: (str(x[0] or ""), str(x[1] or ""), x[2] or ""))

    natural = 0.0
    for _dt, _ref, _desc, debit, credit in raw:
        natural = round(natural + debit - credit, 2)

    # Positive = employee owes company; negative = company owes employee
    desired_closing = round(out_adv + out_loan - unpaid_salary, 2)
    opening = round(desired_closing - natural, 2)

    full = []
    balance = 0.0
    open_dr = opening if opening > 0 else 0.0
    open_cr = abs(opening) if opening < 0 else 0.0
    balance = round(balance + open_dr - open_cr, 2)
    full.append({
        "date": "",
        "ref": "",
        "description": "Opening Balance",
        "debit": open_dr,
        "credit": open_cr,
        "balance": balance,
    })
    for dt, ref, desc, debit, credit in raw:
        balance = round(balance + debit - credit, 2)
        full.append({
            "date": str(dt)[:10] if dt else "",
            "ref": ref or "",
            "description": desc,
            "debit": debit,
            "credit": credit,
            "balance": balance,
        })

    if not fd and not td:
        return emp, full

    # Date filter: bring forward balance before From, then period lines
    entries = []
    bf = 0.0
    period_rows = []
    for row in full:
        d = (row.get("date") or "")[:10]
        if not d:
            # Opening always belongs before any dated movement
            bf = float(row["balance"])
            continue
        if fd and d < fd:
            bf = float(row["balance"])
            continue
        if td and d > td:
            continue
        period_rows.append(row)

    bf = round(bf, 2)
    bf_dr = bf if bf > 0 else 0.0
    bf_cr = abs(bf) if bf < 0 else 0.0
    entries.append({
        "date": fd or "",
        "ref": "",
        "description": "Balance b/f",
        "debit": bf_dr,
        "credit": bf_cr,
        "balance": bf,
    })
    bal = bf
    for row in period_rows:
        bal = round(bal + float(row["debit"] or 0) - float(row["credit"] or 0), 2)
        entries.append({
            "date": row["date"],
            "ref": row["ref"],
            "description": row["description"],
            "debit": row["debit"],
            "credit": row["credit"],
            "balance": bal,
        })
    return emp, entries


def report_employee_history(employee_id):
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        emp = get_employee_hr(employee_id)
        payroll = rows_to_list(conn.execute(
            "SELECT payroll_id, gross_salary, net_salary, total_deductions FROM payroll_lines WHERE employee_id=?",
            (employee_id,),
        ).fetchall())
        leaves = rows_to_list(conn.execute(
            "SELECT * FROM leave_requests WHERE employee_id=? ORDER BY from_date DESC", (employee_id,),
        ).fetchall())
        advances = rows_to_list(conn.execute(
            "SELECT * FROM employee_advances WHERE employee_id=?", (employee_id,),
        ).fetchall())
        loans = rows_to_list(conn.execute(
            "SELECT * FROM employee_loans WHERE employee_id=?", (employee_id,),
        ).fetchall())
        return {"employee": emp, "payroll": payroll, "leaves": leaves, "advances": advances, "loans": loans}
