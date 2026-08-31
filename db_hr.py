"""IFS Chemicals ERP - HR & Payroll module."""

from datetime import datetime
from pathlib import Path

SCHEMA_HR_PATH = Path(__file__).parent / "schema_hr.sql"

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


def user_can_hr(user, action="view"):
    from db_v3 import user_can
    return user_can(user, "HR", action)


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
        q += " AND (e.code LIKE ? OR e.full_name LIKE ? OR e.cnic LIKE ?)"
        p.extend([f"%{search}%"] * 3)
    q += " ORDER BY e.full_name"
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
                   joining_date, confirmation_date, employment_status, basic_salary, bank_account,
                   department, designation, is_active, created_by, created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                data.get("code") or next_code("EMP", "employees"),
                data["full_name"], data.get("father_name"), data.get("cnic"),
                data.get("date_of_birth"), data.get("gender"), data.get("marital_status"),
                data.get("phone"), data.get("mobile"), data.get("email"), data.get("address"),
                data.get("department_id"), data.get("designation_id"), data.get("manager_id"),
                data.get("joining_date"), data.get("confirmation_date"),
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
    with get_connection() as conn:
        conn.execute(
            """UPDATE employees SET code=?,full_name=?,father_name=?,cnic=?,date_of_birth=?,
               gender=?,marital_status=?,phone=?,mobile=?,email=?,address=?,
               department_id=?,designation_id=?,manager_id=?,joining_date=?,confirmation_date=?,
               employment_status=?,basic_salary=?,bank_account=?,department=?,designation=?,
               is_active=?,modified_by=?,modified_at=? WHERE id=?""",
            (
                data["code"], data["full_name"], data.get("father_name"), data.get("cnic"),
                data.get("date_of_birth"), data.get("gender"), data.get("marital_status"),
                data.get("phone"), data.get("mobile"), data.get("email"), data.get("address"),
                data.get("department_id"), data.get("designation_id"), data.get("manager_id"),
                data.get("joining_date"), data.get("confirmation_date"),
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
ATTENDANCE_STATUSES = ["present", "absent", "leave", "late", "overtime", "half_day"]


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
    q = """SELECT a.*, e.code AS emp_code, e.full_name AS employee_name
           FROM attendance a JOIN employees e ON a.employee_id=e.id WHERE 1=1"""
    p = []
    if employee_id:
        q += " AND a.employee_id=?"; p.append(employee_id)
    if from_date:
        q += " AND a.att_date>=?"; p.append(from_date)
    if to_date:
        q += " AND a.att_date<=?"; p.append(to_date)
    q += " ORDER BY a.att_date DESC, e.full_name"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


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
                          pl.basic_salary, pl.allowances, pl.overtime, pl.bonus, pl.gross_salary,
                          pl.tax_deduction, pl.eobi, pl.social_security, pl.advance_recovery,
                          pl.loan_recovery, pl.other_deductions, pl.total_deductions, pl.net_salary,
                          pl.days_present, pl.days_absent, pl.overtime_hrs, e.bank_account,
                          COALESCE(pl.paid_status, 'unpaid') AS paid_status,
                          pl.paid_amount, pl.paid_date, pl.payment_mode, pl.payment_document_no
                   FROM payroll_lines pl
                   LEFT JOIN employees e ON pl.employee_id=e.id
                   WHERE pl.payroll_id=? ORDER BY e.full_name, e.code""",
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
                   total_deductions,net_salary,days_present,days_absent,overtime_hrs)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pid, eid, line["basic_salary"], line["allowances"], line["overtime"], line["bonus"],
                 line["gross_salary"], line["tax_deduction"], line["eobi"], line["social_security"],
                 line["advance_recovery"], line["loan_recovery"], line["other_deductions"],
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


def _calc_payroll_line(conn, employee_id, month, year, payroll_id):
    period_start = f"{year}-{month:02d}-01"
    if month == 12:
        period_end = f"{year}-12-31"
    else:
        period_end = f"{year}-{month+1:02d}-01"
        from datetime import timedelta
        end_dt = datetime.strptime(period_end, "%Y-%m-%d") - timedelta(days=1)
        period_end = end_dt.strftime("%Y-%m-%d")

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

    att = conn.execute(
        """SELECT status, COUNT(*) AS cnt, COALESCE(SUM(overtime_hrs),0) AS ot
           FROM attendance WHERE employee_id=? AND att_date>=? AND att_date<=?
           GROUP BY status""",
        (employee_id, period_start, period_end),
    ).fetchall()
    days_present = days_absent = 0
    overtime_hrs = 0
    for row in att:
        r = dict(row)
        if r["status"] in ("present", "late", "overtime"):
            days_present += r["cnt"]
        elif r["status"] == "absent":
            days_absent += r["cnt"]
        overtime_hrs += r["ot"] or 0

    hourly = basic / 30 / 8 if basic else 0
    overtime = overtime_hrs * hourly * 1.5
    bonus = 0
    gross = basic + allowances + overtime + bonus

    # Tax / EOBI / SS default nil — enter manually on Edit Lines if required
    tax = eobi = ss = 0.0

    advance_recovery = _recover_advances(conn, employee_id, payroll_id, period_end)
    loan_recovery = _recover_loans(conn, employee_id, payroll_id, period_end)

    total_ded = tax + eobi + ss + advance_recovery + loan_recovery
    net = gross - total_ded

    return {
        "basic_salary": basic, "allowances": allowances, "overtime": overtime, "bonus": bonus,
        "gross_salary": gross, "tax_deduction": tax, "eobi": eobi, "social_security": ss,
        "advance_recovery": advance_recovery, "loan_recovery": loan_recovery, "other_deductions": 0,
        "total_deductions": total_ded, "net_salary": net,
        "days_present": days_present, "days_absent": days_absent, "overtime_hrs": overtime_hrs,
    }


def _recover_advances(conn, employee_id, payroll_id, due_date):
    total = 0
    advances = conn.execute(
        "SELECT id, monthly_recovery, outstanding_amount FROM employee_advances WHERE employee_id=? AND status='issued' AND outstanding_amount>0",
        (employee_id,),
    ).fetchall()
    for adv in advances:
        a = dict(adv)
        amt = min(a["monthly_recovery"] or a["outstanding_amount"], a["outstanding_amount"])
        if amt <= 0:
            continue
        total += amt
        new_out = a["outstanding_amount"] - amt
        new_rec = conn.execute("SELECT recovered_amount FROM employee_advances WHERE id=?", (a["id"],)).fetchone()[0] + amt
        conn.execute(
            "UPDATE employee_advances SET recovered_amount=?,outstanding_amount=? WHERE id=?",
            (new_rec, new_out, a["id"]),
        )
        sched = conn.execute(
            "SELECT id FROM advance_recovery_schedule WHERE advance_id=? AND recovered=0 ORDER BY installment_no LIMIT 1",
            (a["id"],),
        ).fetchone()
        if sched:
            conn.execute(
                "UPDATE advance_recovery_schedule SET recovered=1,recovered_date=?,payroll_id=? WHERE id=?",
                (due_date, payroll_id, sched[0]),
            )
    return total


def _undo_payroll_recoveries(conn, payroll_id):
    """Reverse advance/loan installments marked recovered during payroll generation."""
    for row in conn.execute(
        "SELECT id, advance_id, amount FROM advance_recovery_schedule WHERE payroll_id=?",
        (payroll_id,),
    ).fetchall():
        sched_id, adv_id, amt = row[0], row[1], float(row[2] or 0)
        adv = conn.execute(
            "SELECT recovered_amount, outstanding_amount FROM employee_advances WHERE id=?",
            (adv_id,),
        ).fetchone()
        if adv and amt > 0:
            conn.execute(
                "UPDATE employee_advances SET recovered_amount=?, outstanding_amount=? WHERE id=?",
                (max(0, float(adv[0] or 0) - amt), float(adv[1] or 0) + amt, adv_id),
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
            "SELECT recovered_amount, outstanding_amount FROM employee_loans WHERE id=?",
            (loan_id,),
        ).fetchone()
        if ln and amt > 0:
            conn.execute(
                "UPDATE employee_loans SET recovered_amount=?, outstanding_amount=? WHERE id=?",
                (max(0, float(ln[0] or 0) - amt), float(ln[1] or 0) + amt, loan_id),
            )
        conn.execute(
            "UPDATE loan_installments SET recovered=0, recovered_date=NULL, payroll_id=NULL WHERE id=?",
            (inst_id,),
        )


def _recover_loans(conn, employee_id, payroll_id, due_date):
    total = 0
    loans = conn.execute(
        "SELECT id, monthly_installment, outstanding_amount FROM employee_loans WHERE employee_id=? AND status='issued' AND outstanding_amount>0",
        (employee_id,),
    ).fetchall()
    for ln in loans:
        l = dict(ln)
        inst = conn.execute(
            "SELECT id, amount FROM loan_installments WHERE loan_id=? AND recovered=0 ORDER BY installment_no LIMIT 1",
            (l["id"],),
        ).fetchone()
        if inst:
            inst_amt = float(inst[1] or 0)
        else:
            inst_amt = 0.0
        amt = min(
            inst_amt or float(l["monthly_installment"] or 0) or float(l["outstanding_amount"] or 0),
            float(l["outstanding_amount"] or 0),
        )
        if amt <= 0:
            continue
        total += amt
        new_out = l["outstanding_amount"] - amt
        new_rec = conn.execute("SELECT recovered_amount FROM employee_loans WHERE id=?", (l["id"],)).fetchone()[0] + amt
        conn.execute(
            "UPDATE employee_loans SET recovered_amount=?,outstanding_amount=? WHERE id=?",
            (new_rec, new_out, l["id"]),
        )
        if inst:
            conn.execute(
                "UPDATE loan_installments SET recovered=1,recovered_date=?,payroll_id=? WHERE id=?",
                (due_date, payroll_id, inst[0]),
            )
    return total


def _recalc_payroll_line_fields(data):
    """Recompute gross, total deductions, and net from editable components."""
    basic = float(data.get("basic_salary") or 0)
    allowances = float(data.get("allowances") or 0)
    overtime = float(data.get("overtime") or 0)
    bonus = float(data.get("bonus") or 0)
    gross = round(basic + allowances + overtime + bonus, 2)
    tax = float(data.get("tax_deduction") or 0)
    eobi = float(data.get("eobi") or 0)
    ss = float(data.get("social_security") or 0)
    adv = float(data.get("advance_recovery") or 0)
    loan = float(data.get("loan_recovery") or 0)
    other = float(data.get("other_deductions") or 0)
    total_ded = round(tax + eobi + ss + adv + loan + other, 2)
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
        "total_deductions": total_ded,
        "net_salary": net,
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


def update_payroll_line(line_id, data, user_id=None):
    """Edit one payroll line (draft payroll only). Recalculates gross/net and run totals."""
    from database import get_connection
    editable = (
        "basic_salary", "allowances", "overtime", "bonus",
        "tax_deduction", "eobi", "social_security",
        "advance_recovery", "loan_recovery", "other_deductions",
        "days_present", "days_absent", "overtime_hrs",
    )
    with get_connection() as conn:
        row = conn.execute(
            """SELECT pl.*, pr.status AS payroll_status
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
        merged = dict(row)
        for k in editable:
            if k in data:
                merged[k] = data[k]
        calc = _recalc_payroll_line_fields(merged)
        conn.execute(
            """UPDATE payroll_lines SET
               basic_salary=?, allowances=?, overtime=?, bonus=?, gross_salary=?,
               tax_deduction=?, eobi=?, social_security=?, advance_recovery=?,
               loan_recovery=?, other_deductions=?, total_deductions=?, net_salary=?,
               days_present=?, days_absent=?, overtime_hrs=?
               WHERE id=?""",
            (
                calc["basic_salary"], calc["allowances"], calc["overtime"], calc["bonus"],
                calc["gross_salary"], calc["tax_deduction"], calc["eobi"], calc["social_security"],
                calc["advance_recovery"], calc["loan_recovery"], calc["other_deductions"],
                calc["total_deductions"], calc["net_salary"],
                float(merged.get("days_present") or 0),
                float(merged.get("days_absent") or 0),
                float(merged.get("overtime_hrs") or 0),
                line_id,
            ),
        )
        _refresh_payroll_run_totals(conn, row["payroll_id"])
        return calc


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
    """Reverse payroll salary accrual voucher (posted → approved). If paid, reverses payment GL first."""
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

        if status == "draft":
            raise ValueError("Payroll is not posted to GL.")
        has_accrual = conn.execute(
            "SELECT 1 FROM general_ledger WHERE reference_type='payroll' AND reference_id=? LIMIT 1",
            (payroll_id,),
        ).fetchone()
        has_payment = conn.execute(
            "SELECT 1 FROM general_ledger WHERE reference_type='payroll_payment' AND reference_id=? LIMIT 1",
            (payroll_id,),
        ).fetchone()
        if status == "approved" and not has_accrual and not has_payment:
            raise ValueError("Payroll has no GL voucher to rollback.")

        line_ids = [
            r[0] for r in conn.execute(
                "SELECT id FROM payroll_lines WHERE payroll_id=? AND paid_status='paid'",
                (payroll_id,),
            ).fetchall()
        ]
        for lid in line_ids:
            _undo_payroll_line_payment(conn, lid)

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
            if removed == 0 and removed_payment == 0:
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
        lines = conn.execute("SELECT * FROM payroll_lines WHERE payroll_id=?", (payroll_id,)).fetchall()
        gross = sum(dict(l)["gross_salary"] for l in lines)
        net = sum(dict(l)["net_salary"] for l in lines)
        adv_rec = sum(dict(l)["advance_recovery"] for l in lines)
        eobi = sum(dict(l)["eobi"] for l in lines)
        ss = sum(dict(l)["social_security"] for l in lines)
        tax = sum(dict(l)["tax_deduction"] for l in lines)
        loan_rec = sum(dict(l)["loan_recovery"] for l in lines)
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
        post_gl(conn, entry_date, HR_AC["salary_payable"], 0, net, "Net salary payable", "payroll", payroll_id, ref_no, user_id)

        conn.execute(
            "UPDATE payroll_runs SET status='posted',posted_by=?,posted_at=? WHERE id=?",
            (user_id, now(), payroll_id),
        )


def _refresh_payroll_paid_status(conn, payroll_id, user_id=None):
    """Mark payroll run paid when every line is paid."""
    total = conn.execute(
        "SELECT COUNT(*) FROM payroll_lines WHERE payroll_id=?", (payroll_id,)
    ).fetchone()[0]
    paid = conn.execute(
        "SELECT COUNT(*) FROM payroll_lines WHERE payroll_id=? AND paid_status='paid'",
        (payroll_id,),
    ).fetchone()[0]
    if total and paid >= total:
        conn.execute(
            "UPDATE payroll_runs SET status='paid', paid_by=?, paid_at=? WHERE id=?",
            (user_id, now(), payroll_id),
        )
    else:
        conn.execute(
            """UPDATE payroll_runs SET status='posted', paid_by=NULL, paid_at=NULL,
               modified_by=?, modified_at=? WHERE id=?""",
            (user_id, now(), payroll_id),
        )


def _undo_payroll_line_payment(conn, line_id):
    """Reverse one employee salary payment (GL + cash/bank book row)."""
    import database as db
    from db_v3 import gl_account_code

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
    amt = float(row.get("paid_amount") or row.get("net_salary") or 0)
    doc = row.get("payment_document_no") or ""
    for gl_row in conn.execute(
        "SELECT account_id, debit, credit FROM general_ledger WHERE reference_type='payroll_line_payment' AND reference_id=?",
        (line_id,),
    ).fetchall():
        aid, dr, cr = gl_row[0], float(gl_row[1] or 0), float(gl_row[2] or 0)
        if dr:
            conn.execute("UPDATE chart_of_accounts SET current_balance=current_balance-? WHERE id=?", (dr, aid))
        if cr:
            conn.execute("UPDATE chart_of_accounts SET current_balance=current_balance+? WHERE id=?", (cr, aid))
    conn.execute("DELETE FROM general_ledger WHERE reference_type='payroll_line_payment' AND reference_id=?", (line_id,))
    if doc:
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


def pay_payroll_line(line_id, user_id, payment_mode="cash", payment_date=None, bank_account_id=None):
    """Pay one employee net salary — cash/bank book entry + GL per line."""
    import database as db
    from db_v3 import post_gl, post_gl_account_id, gl_account_code, AC

    mode = (payment_mode or "cash").lower()
    if mode not in ("cash", "bank"):
        raise ValueError("Payment mode must be cash or bank.")
    if mode == "bank" and not bank_account_id:
        raise ValueError("Select a bank account for bank payment.")

    with db.get_connection() as conn:
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
        if row["payroll_status"] not in ("posted", "paid"):
            raise ValueError("Payroll must be posted to GL before paying employees.")
        if row.get("paid_status") == "paid":
            raise ValueError(f"Already paid ({row.get('payment_document_no') or '—'}).")
        amt = round(float(row.get("net_salary") or 0), 2)
        if amt <= 0:
            raise ValueError("Net salary is zero — nothing to pay.")
        pay_date = str(payment_date or row.get("run_date") or now()[:10])
        label = f"Salary {row['payroll_no']} — {row['employee_name']} ({row['emp_code']})"
        ref = f"{row['payroll_no']}/{row['emp_code']}"

        if mode == "cash":
            entry_id, doc_no = db._add_cash_payment(
                conn, pay_date, label, ref, amt, user_id,
                party_type="employee", party_id=row["employee_id"],
            )
            asset_id = conn.execute(
                "SELECT id FROM chart_of_accounts WHERE code=?", (AC["cash"],)
            ).fetchone()
            asset_id = asset_id[0] if asset_id else None
        else:
            entry_id, doc_no = db._add_bank_payment(
                conn, pay_date, label, ref, amt, bank_account_id, user_id,
                party_type="employee", party_id=row["employee_id"],
            )
            asset_id = bank_account_id

        post_gl(conn, pay_date, HR_AC["salary_payable"], amt, 0, label, "payroll_line_payment", line_id, doc_no, user_id)
        post_gl_account_id(conn, pay_date, asset_id, 0, amt, label, "payroll_line_payment", entry_id, doc_no, user_id)

        conn.execute(
            """UPDATE payroll_lines SET paid_status='paid', paid_amount=?, paid_date=?,
               payment_mode=?, payment_document_no=?, paid_by=?, paid_at=? WHERE id=?""",
            (amt, pay_date, mode, doc_no, user_id, now(), line_id),
        )
        _refresh_payroll_paid_status(conn, row["payroll_id"], user_id)
        return {"document_no": doc_no, "amount": amt, "payment_mode": mode, "employee": row["employee_name"]}


def pay_payroll(payroll_id, user_id, payment_mode="cash", payment_date=None, bank_account_id=None):
    """Pay all unpaid employees on this payroll (one cash/bank entry per employee)."""
    from database import get_connection
    with get_connection() as conn:
        pr = conn.execute("SELECT status FROM payroll_runs WHERE id=?", (payroll_id,)).fetchone()
        if not pr or pr[0] not in ("posted", "paid"):
            raise ValueError("Payroll must be posted before payment")
        line_ids = [
            r[0] for r in conn.execute(
                "SELECT id FROM payroll_lines WHERE payroll_id=? AND COALESCE(paid_status,'unpaid')!='paid'",
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
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("Reason is required.")
    from database import get_connection
    with get_connection() as conn:
        row = conn.execute(
            "SELECT payroll_id FROM payroll_lines WHERE id=?", (line_id,)
        ).fetchone()
        if not row:
            raise ValueError("Payroll line not found.")
        payroll_id = row[0]
        _undo_payroll_line_payment(conn, line_id)
        _refresh_payroll_paid_status(conn, payroll_id, user_id)
        conn.execute(
            "UPDATE payroll_runs SET notes=COALESCE(notes,'') || ? WHERE id=?",
            (f"\nLine payment rollback ({now()}): {reason}", payroll_id),
        )


# ---------- Advances ----------
def save_advance(data, user_id=None):
    from database import get_connection, ensure_document_no
    with get_connection() as conn:
        months = max(1, int(data.get("recovery_months", 1)))
        monthly = round(data["amount"] / months, 2)
        cur = conn.execute(
            """INSERT INTO employee_advances(document_no,employee_id,request_date,amount,reason,
               recovery_months,monthly_recovery,outstanding_amount,status,created_by)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (ensure_document_no("ADV", data.get("document_no"), conn), data["employee_id"], data["request_date"],
             data["amount"], data.get("reason"), months, monthly, data["amount"], "pending", user_id),
        )
        return cur.lastrowid


def get_advances(status=None, employee_id=None):
    from database import get_connection, rows_to_list
    q = """SELECT a.*, e.full_name AS employee_name FROM employee_advances a
           JOIN employees e ON a.employee_id=e.id WHERE 1=1"""
    p = []
    if status:
        q += " AND a.status=?"; p.append(status)
    if employee_id:
        q += " AND a.employee_id=?"; p.append(employee_id)
    q += " ORDER BY a.request_date DESC"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


def approve_advance(advance_id, user_id, approve=True):
    from database import get_connection
    ts = now()
    with get_connection() as conn:
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


def issue_advance(advance_id, user_id, payment_mode="cash"):
    from database import get_connection
    from db_v3 import post_gl, AC
    with get_connection() as conn:
        adv = conn.execute("SELECT * FROM employee_advances WHERE id=?", (advance_id,)).fetchone()
        if not adv or adv["status"] != "approved":
            raise ValueError("Advance must be approved before issue")
        adv = dict(adv)
        acct = AC["bank"] if payment_mode == "bank" else AC["cash"]
        post_gl(conn, adv["request_date"], HR_AC["employee_advance"], adv["amount"], 0,
                "Advance issue", "employee_advance", advance_id, adv["document_no"], user_id)
        post_gl(conn, adv["request_date"], acct, 0, adv["amount"],
                "Advance issue", "employee_advance", advance_id, adv["document_no"], user_id)
        conn.execute(
            "UPDATE employee_advances SET status='issued',issued_by=?,issued_at=? WHERE id=?",
            (user_id, now(), advance_id),
        )
        from datetime import timedelta
        base = datetime.strptime(adv["request_date"], "%Y-%m-%d")
        monthly = adv["monthly_recovery"]
        for i in range(adv["recovery_months"]):
            due = (base + timedelta(days=30 * (i + 1))).strftime("%Y-%m-%d")
            conn.execute(
                "INSERT INTO advance_recovery_schedule(advance_id,installment_no,due_date,amount) VALUES(?,?,?,?)",
                (advance_id, i + 1, due, monthly),
            )


# ---------- Loans ----------
def save_loan(data, user_id=None):
    from database import get_connection, ensure_document_no
    with get_connection() as conn:
        inst = max(1, int(data.get("installments", 12)))
        monthly = round(data["amount"] / inst, 2)
        cur = conn.execute(
            """INSERT INTO employee_loans(document_no,employee_id,issue_date,amount,installments,
               monthly_installment,outstanding_amount,reason,status,created_by)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (ensure_document_no("LON", data.get("document_no"), conn), data["employee_id"], data["issue_date"],
             data["amount"], inst, monthly, data["amount"], data.get("reason"), "pending", user_id),
        )
        return cur.lastrowid


def get_loans(status=None, employee_id=None):
    from database import get_connection, rows_to_list
    q = """SELECT l.*, e.full_name AS employee_name FROM employee_loans l
           JOIN employees e ON l.employee_id=e.id WHERE 1=1"""
    p = []
    if status:
        q += " AND l.status=?"; p.append(status)
    if employee_id:
        q += " AND l.employee_id=?"; p.append(employee_id)
    q += " ORDER BY l.issue_date DESC"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


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


def issue_loan(loan_id, user_id, payment_mode="cash"):
    from database import get_connection
    from db_v3 import post_gl, AC
    with get_connection() as conn:
        ln = conn.execute("SELECT * FROM employee_loans WHERE id=?", (loan_id,)).fetchone()
        if not ln or ln["status"] != "approved":
            raise ValueError("Loan must be approved before issue")
        ln = dict(ln)
        acct = AC["bank"] if payment_mode == "bank" else AC["cash"]
        post_gl(conn, ln["issue_date"], HR_AC["employee_advance"], ln["amount"], 0,
                "Loan issue", "employee_loan", loan_id, ln["document_no"], user_id)
        post_gl(conn, ln["issue_date"], acct, 0, ln["amount"],
                "Loan issue", "employee_loan", loan_id, ln["document_no"], user_id)
        conn.execute(
            "UPDATE employee_loans SET status='issued',issued_by=?,issued_at=? WHERE id=?",
            (user_id, now(), loan_id),
        )
        from datetime import timedelta
        base = datetime.strptime(ln["issue_date"], "%Y-%m-%d")
        for i in range(ln["installments"]):
            due = (base + timedelta(days=30 * (i + 1))).strftime("%Y-%m-%d")
            conn.execute(
                "INSERT INTO loan_installments(loan_id,installment_no,due_date,amount) VALUES(?,?,?,?)",
                (loan_id, i + 1, due, ln["monthly_installment"]),
            )


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
    from db_v3 import post_gl, AC
    with get_connection() as conn:
        cl = conn.execute("SELECT * FROM expense_claims WHERE id=?", (claim_id,)).fetchone()
        if not cl or cl["status"] != "approved" or cl["reimbursed"]:
            raise ValueError("Claim must be approved and not yet reimbursed")
        cl = dict(cl)
        acct = AC["bank"] if payment_mode == "bank" else AC["cash"]
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
    return get_employees_hr(active_only)


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
            """SELECT e.code, e.full_name, SUM(a.overtime_hrs) AS total_overtime_hrs, COUNT(*) AS days
               FROM attendance a JOIN employees e ON a.employee_id=e.id
               WHERE a.att_date>=? AND a.att_date<=? AND a.overtime_hrs>0
               GROUP BY e.id ORDER BY total_overtime_hrs DESC""",
            (from_date, to_date),
        ).fetchall())


def report_payroll_register(from_date=None, to_date=None):
    from database import get_connection, rows_to_list
    q = """SELECT pr.document_no, pr.payroll_month, pr.payroll_year, pr.run_date, pr.status,
                  pr.total_gross, pr.total_deductions, pr.total_net,
                  pl.*, e.full_name AS employee_name
           FROM payroll_runs pr JOIN payroll_lines pl ON pr.id=pl.payroll_id
           JOIN employees e ON pl.employee_id=e.id WHERE 1=1"""
    p = []
    if from_date:
        q += " AND pr.run_date>=?"; p.append(from_date)
    if to_date:
        q += " AND pr.run_date<=?"; p.append(to_date)
    q += " ORDER BY pr.payroll_year DESC, pr.payroll_month DESC, e.full_name"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


def report_salary_sheet(payroll_id):
    return get_payroll_run(payroll_id)


def report_outstanding_advances():
    return get_advances(status="issued")


def report_outstanding_loans():
    return get_loans(status="issued")


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
        for adv in rows_to_list(conn.execute(
            """SELECT document_no, request_date, issued_at, amount, outstanding_amount, status
               FROM employee_advances WHERE employee_id=? AND status IN ('issued','closed')""",
            (employee_id,),
        ).fetchall()):
            out_adv += float(adv.get("outstanding_amount") or 0)
            dt = adv.get("issued_at") or adv.get("request_date")
            raw.append((dt, adv["document_no"], "Advance issued", float(adv["amount"] or 0), 0.0))

        for ln in rows_to_list(conn.execute(
            """SELECT document_no, issue_date, issued_at, amount, outstanding_amount, status
               FROM employee_loans WHERE employee_id=? AND status IN ('issued','closed')""",
            (employee_id,),
        ).fetchall()):
            out_loan += float(ln.get("outstanding_amount") or 0)
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
            if adv_rec:
                raw.append((dt, ref, f"Advance recovery ({period})", 0.0, adv_rec))
            if loan_rec:
                raw.append((dt, ref, f"Loan recovery ({period})", 0.0, loan_rec))
            if net and pr.get("status") in ("posted", "paid", "approved"):
                raw.append((dt, ref, f"Net salary ({period})", 0.0, net))
            paid_amt = float(pr.get("paid_amount") or 0)
            if paid_amt > 0 and (pr.get("paid_status") or "") in ("paid", "partial"):
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
