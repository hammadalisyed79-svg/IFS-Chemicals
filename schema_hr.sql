-- IFS Chemicals ERP - HR & Payroll schema (additive)

CREATE TABLE IF NOT EXISTS designations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now')),
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT
);

CREATE TABLE IF NOT EXISTS leave_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    days_per_year REAL DEFAULT 0,
    is_paid INTEGER DEFAULT 1,
    is_active INTEGER DEFAULT 1,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS leave_balances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    leave_type_id INTEGER NOT NULL REFERENCES leave_types(id),
    year INTEGER NOT NULL,
    allocated REAL DEFAULT 0,
    used REAL DEFAULT 0,
    balance REAL DEFAULT 0,
    UNIQUE(employee_id, leave_type_id, year)
);

CREATE TABLE IF NOT EXISTS leave_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no TEXT UNIQUE NOT NULL,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    leave_type_id INTEGER NOT NULL REFERENCES leave_types(id),
    from_date TEXT NOT NULL,
    to_date TEXT NOT NULL,
    days REAL NOT NULL,
    reason TEXT,
    status TEXT DEFAULT 'pending',
    approved_by INTEGER REFERENCES users(id),
    approved_at TEXT,
    rejected_by INTEGER REFERENCES users(id),
    rejected_at TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now')),
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT
);

CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    att_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'present',
    check_in TEXT,
    check_out TEXT,
    late_mins REAL DEFAULT 0,
    overtime_hrs REAL DEFAULT 0,
    notes TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now')),
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT,
    UNIQUE(employee_id, att_date)
);

CREATE TABLE IF NOT EXISTS salary_structures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    basic_salary REAL DEFAULT 0,
    housing_allowance REAL DEFAULT 0,
    transport_allowance REAL DEFAULT 0,
    medical_allowance REAL DEFAULT 0,
    other_allowance REAL DEFAULT 0,
    effective_from TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now')),
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT
);

CREATE TABLE IF NOT EXISTS payroll_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no TEXT UNIQUE NOT NULL,
    payroll_month INTEGER NOT NULL,
    payroll_year INTEGER NOT NULL,
    run_date TEXT NOT NULL,
    status TEXT DEFAULT 'draft',
    total_gross REAL DEFAULT 0,
    total_deductions REAL DEFAULT 0,
    total_net REAL DEFAULT 0,
    notes TEXT,
    approved_by INTEGER REFERENCES users(id),
    approved_at TEXT,
    posted_by INTEGER REFERENCES users(id),
    posted_at TEXT,
    paid_by INTEGER REFERENCES users(id),
    paid_at TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now')),
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT,
    UNIQUE(payroll_month, payroll_year)
);

CREATE TABLE IF NOT EXISTS payroll_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payroll_id INTEGER NOT NULL REFERENCES payroll_runs(id) ON DELETE CASCADE,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    basic_salary REAL DEFAULT 0,
    allowances REAL DEFAULT 0,
    overtime REAL DEFAULT 0,
    bonus REAL DEFAULT 0,
    gross_salary REAL DEFAULT 0,
    tax_deduction REAL DEFAULT 0,
    eobi REAL DEFAULT 0,
    social_security REAL DEFAULT 0,
    advance_recovery REAL DEFAULT 0,
    loan_recovery REAL DEFAULT 0,
    other_deductions REAL DEFAULT 0,
    total_deductions REAL DEFAULT 0,
    net_salary REAL DEFAULT 0,
    days_present REAL DEFAULT 0,
    days_absent REAL DEFAULT 0,
    overtime_hrs REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS employee_advances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no TEXT UNIQUE NOT NULL,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    request_date TEXT NOT NULL,
    amount REAL NOT NULL,
    reason TEXT,
    recovery_months INTEGER DEFAULT 1,
    monthly_recovery REAL DEFAULT 0,
    recovered_amount REAL DEFAULT 0,
    outstanding_amount REAL DEFAULT 0,
    status TEXT DEFAULT 'pending',
    approved_by INTEGER REFERENCES users(id),
    approved_at TEXT,
    issued_by INTEGER REFERENCES users(id),
    issued_at TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now')),
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT
);

CREATE TABLE IF NOT EXISTS advance_recovery_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    advance_id INTEGER NOT NULL REFERENCES employee_advances(id) ON DELETE CASCADE,
    installment_no INTEGER NOT NULL,
    due_date TEXT NOT NULL,
    amount REAL NOT NULL,
    recovered INTEGER DEFAULT 0,
    recovered_date TEXT,
    payroll_id INTEGER REFERENCES payroll_runs(id)
);

CREATE TABLE IF NOT EXISTS employee_loans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no TEXT UNIQUE NOT NULL,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    issue_date TEXT NOT NULL,
    amount REAL NOT NULL,
    installments INTEGER DEFAULT 12,
    monthly_installment REAL DEFAULT 0,
    recovered_amount REAL DEFAULT 0,
    outstanding_amount REAL DEFAULT 0,
    reason TEXT,
    status TEXT DEFAULT 'pending',
    approved_by INTEGER REFERENCES users(id),
    approved_at TEXT,
    issued_by INTEGER REFERENCES users(id),
    issued_at TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now')),
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT
);

CREATE TABLE IF NOT EXISTS loan_installments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loan_id INTEGER NOT NULL REFERENCES employee_loans(id) ON DELETE CASCADE,
    installment_no INTEGER NOT NULL,
    due_date TEXT NOT NULL,
    amount REAL NOT NULL,
    recovered INTEGER DEFAULT 0,
    recovered_date TEXT,
    payroll_id INTEGER REFERENCES payroll_runs(id)
);

CREATE TABLE IF NOT EXISTS expense_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no TEXT UNIQUE NOT NULL,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    claim_date TEXT NOT NULL,
    description TEXT NOT NULL,
    amount REAL NOT NULL,
    status TEXT DEFAULT 'pending',
    approved_by INTEGER REFERENCES users(id),
    approved_at TEXT,
    reimbursed INTEGER DEFAULT 0,
    reimbursed_date TEXT,
    payment_mode TEXT DEFAULT 'cash',
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now')),
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_attendance_emp_date ON attendance(employee_id, att_date);
CREATE INDEX IF NOT EXISTS idx_leave_req_emp ON leave_requests(employee_id);
CREATE INDEX IF NOT EXISTS idx_payroll_lines_emp ON payroll_lines(employee_id);
CREATE INDEX IF NOT EXISTS idx_payroll_runs_period ON payroll_runs(payroll_year, payroll_month);
