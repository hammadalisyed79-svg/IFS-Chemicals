"""IFS Chemicals ERP - Schema v3 migration and extended business logic."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA_V3_PATH = Path(__file__).parent / "schema_v3.sql"

# Account codes for auto-posting (defaults; override via Finance → Chart of Accounts → Posting Setup)
AC = {
    "cash": "1000", "bank": "1100", "ar": "1200", "ap": "2000",
    "raw_inv": "1310", "pack_inv": "1320", "fg_inv": "1330", "wip": "1340",
    "sales": "4000", "st_payable": "2100", "st_receivable": "1210",
    "wht_receivable": "1215", "wht_payable": "2115",
    "cogs": "5000", "prod_var": "5100", "inv_reval": "5180",
    "labour": "5200", "overhead": "5300", "admin": "6100",
    "equity": "3000", "pl_clearing": "3999",
}

POSTING_ROLE_LABELS = {
    "cash": ("Cash in Hand", "Cash receipts, cash payments, invoice cash paid"),
    "bank": ("Bank Account", "Bank receipts and bank payments"),
    "ar": ("Accounts Receivable (control)", "All customers — sub-ledger: Customer Ledger"),
    "ap": ("Accounts Payable (control)", "All suppliers — sub-ledger: Supplier Ledger"),
    "sales": ("Sales Revenue", "Credit on approved sales invoices"),
    "cogs": ("Cost of Goods Sold", "Debit when sales invoice posts inventory COGS"),
    "raw_inv": ("Raw Material Inventory", "Purchases, production issues/receipts"),
    "pack_inv": ("Packing Material Inventory", "Packaging stock movements"),
    "fg_inv": ("Finished Goods Inventory", "Production output & sales COGS"),
    "wip": ("Work in Process", "Materials issued to production"),
    "st_payable": ("Sales Tax Payable", "Output tax on sales"),
    "st_receivable": ("Purchase Tax Receivable", "Input tax on purchases"),
    "wht_receivable": ("WHT Receivable", "Withholding tax receivable on sales"),
    "wht_payable": ("WHT Payable", "Withholding tax payable on purchases"),
    "prod_var": ("Production Variance", "Production cost variances"),
    "inv_reval": ("Inventory Revaluation", "Stock revaluation gain/loss (P&L)"),
    "labour": ("Direct Labour", "Production labour (manual JV or production costs)"),
    "overhead": ("Factory Overheads", "Utility, packing, overhead on production orders"),
    "admin": ("Admin / Operating Expenses", "Journal vouchers & expense payments"),
    "equity": ("Retained Earnings / Equity", "Year-end P&L transfer destination"),
    "pl_clearing": ("P&L Clearing Account", "Temporary account for year-end P&L close"),
}


def _party_subledger_code(conn, party_type, party_id):
    """Party chart account when code matches COA; else AR/AP control account."""
    party_type = str(party_type or "").strip().lower()
    try:
        pid = int(party_id)
    except (TypeError, ValueError):
        pid = None
    if party_type not in ("customer", "supplier") or not pid:
        return gl_account_code("ap" if party_type == "supplier" else "ar")
    table = "suppliers" if party_type == "supplier" else "customers"
    row = conn.execute(f"SELECT code FROM {table} WHERE id=?", (pid,)).fetchone()
    code = str(row["code"] or "").strip() if row else ""
    if code:
        acc = conn.execute(
            "SELECT id FROM chart_of_accounts WHERE TRIM(code)=TRIM(?) AND is_active=1",
            (code,),
        ).fetchone()
        if acc:
            return code
    return gl_account_code("ap" if party_type == "supplier" else "ar")


def gl_account_code(role):
    """Resolve GL account code for a posting role (custom setting or default)."""
    custom = get_setting(f"gl_role_{role}", "").strip()
    if custom:
        return custom
    # Live FMYE books use CASH A/C 000000; legacy seed used 1000 Cash in Hand.
    if role == "cash":
        try:
            from database import get_connection
            with get_connection() as conn:
                for code in ("000000", "1000", "100000"):
                    row = conn.execute(
                        "SELECT code FROM chart_of_accounts WHERE code=? AND is_active=1",
                        (code,),
                    ).fetchone()
                    if row:
                        return row["code"] if hasattr(row, "keys") else row[0]
        except Exception:
            pass
    return AC.get(role)


def get_posting_setup():
    from database import get_connection, row_to_dict
    rows = []
    with get_connection() as conn:
        for role, (label, hint) in POSTING_ROLE_LABELS.items():
            code = gl_account_code(role)
            acc = row_to_dict(conn.execute(
                "SELECT id, code, name FROM chart_of_accounts WHERE code=?", (code,)
            ).fetchone()) if code else None
            rows.append({
                "role": role, "label": label, "hint": hint,
                "account_code": code, "account_name": acc["name"] if acc else "— Missing —",
                "account_id": acc["id"] if acc else None,
            })
    return rows


def save_posting_role(role, account_code, user_id=None):
    from database import get_connection
    if role not in POSTING_ROLE_LABELS:
        raise ValueError(f"Unknown posting role: {role}")
    code = (account_code or "").strip()
    if not code:
        set_setting(f"gl_role_{role}", "")
        return
    with get_connection() as conn:
        acc = conn.execute("SELECT id FROM chart_of_accounts WHERE code=? AND is_active=1", (code,)).fetchone()
        if not acc:
            raise ValueError(f"Account code {code} not found in Chart of Accounts.")
    set_setting(f"gl_role_{role}", code)


def _gl_account_balance(conn, account_code, as_of=None):
    row = conn.execute(
        """SELECT a.opening_balance, g.group_type,
                  COALESCE((SELECT SUM(debit)-SUM(credit) FROM general_ledger gl
                            WHERE gl.account_id=a.id AND (? IS NULL OR gl.entry_date<=?)), 0) AS movement
           FROM chart_of_accounts a
           JOIN account_groups g ON a.account_group_id=g.id
           WHERE a.code=?""",
        (as_of, as_of, account_code),
    ).fetchone()
    if not row:
        return 0.0
    return float(row[0] or 0) + float(row[2] or 0)


def _signed_balance(group_type, raw_balance):
    """Present credit-nature accounts (liability, equity, income) as positive when credited."""
    if group_type in ("liability", "equity", "income"):
        return -float(raw_balance or 0)
    return float(raw_balance or 0)


def get_control_account_reconciliation(as_of=None):
    """Compare AR/AP control GL balances with customer/supplier sub-ledger totals."""
    from database import get_connection
    ar_code = gl_account_code("ar")
    ap_code = gl_account_code("ap")
    with get_connection() as conn:
        cust_total = float(conn.execute(
            "SELECT COALESCE(SUM(current_balance),0) FROM customers WHERE is_active=1"
        ).fetchone()[0])
        sup_total = float(conn.execute(
            "SELECT COALESCE(SUM(current_balance),0) FROM suppliers WHERE is_active=1"
        ).fetchone()[0])
        ar_gl = _gl_account_balance(conn, ar_code, as_of)
        ap_gl_raw = _gl_account_balance(conn, ap_code, as_of)
    ap_gl_display = _signed_balance("liability", ap_gl_raw)
    return {
        "ar_code": ar_code,
        "ar_gl_balance": ar_gl,
        "ar_subledger_total": cust_total,
        "ar_difference": round(ar_gl - cust_total, 2),
        "ap_code": ap_code,
        "ap_gl_balance": ap_gl_display,
        "ap_subledger_total": sup_total,
        "ap_difference": round(ap_gl_display - sup_total, 2),
    }


def now():
    """Current PC local date/time (system clock), never UTC."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _table_exists(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def apply_v3(conn, db_module):
    """Safe v3 migration - never drops data."""
    ver = _schema_ver(conn)
    if ver < 3:
        if SCHEMA_V3_PATH.exists():
            conn.executescript(SCHEMA_V3_PATH.read_text(encoding="utf-8"))
        _alter_columns(conn)
        _seed_v3(conn, db_module)
        _extend_invoice_columns(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('schema_version','3') "
            "ON CONFLICT(key) DO UPDATE SET value='3'"
        )
    if _schema_ver(conn) < 4:
        _apply_bom_production_v4(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('schema_version','4') "
            "ON CONFLICT(key) DO UPDATE SET value='4'"
        )
    if _schema_ver(conn) < 5:
        _apply_performance_indexes_v5(conn)
        _ensure_equity_accounts(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('schema_version','5') "
            "ON CONFLICT(key) DO UPDATE SET value='5'"
        )
    if _schema_ver(conn) < 6:
        _apply_fiscal_year_v6(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('schema_version','6') "
            "ON CONFLICT(key) DO UPDATE SET value='6'"
        )
    if _schema_ver(conn) < 7:
        _apply_party_transfer_v7(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('schema_version','7') "
            "ON CONFLICT(key) DO UPDATE SET value='7'"
        )
    if _schema_ver(conn) < 8:
        _apply_finance_attachments_v8(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('schema_version','8') "
            "ON CONFLICT(key) DO UPDATE SET value='8'"
        )
    if _schema_ver(conn) < 9:
        import db_job_cards
        db_job_cards.apply_job_cards(conn, db_module)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('schema_version','9') "
            "ON CONFLICT(key) DO UPDATE SET value='9'"
        )
    if _schema_ver(conn) < 10:
        import db_groups
        db_groups.apply_master_groups(conn, db_module)
    # v11 holidays — groups migration can jump 9→12 and skip this block
    import db_holidays
    if _schema_ver(conn) < 11 or not _table_exists(conn, "weekly_holidays"):
        db_holidays.apply_holidays(conn, db_module)
    import db_cash_day
    if _schema_ver(conn) < 13 or not _table_exists(conn, "cash_day_closes"):
        db_cash_day.apply_cash_day_schema(conn, db_module)
    if _schema_ver(conn) < 14:
        _apply_performance_indexes_v14(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('schema_version','14') "
            "ON CONFLICT(key) DO UPDATE SET value='14'"
        )
    import db_v13_13
    db_v13_13.migrate_v13_13_professional_workflow_completion(conn, db_module)
    import db_v13_14
    db_v13_14.migrate_v13_14_enterprise_workflow_integration(conn, db_module)
    import db_v14_rc1
    db_v14_rc1.migrate_v14_rc1_enterprise(conn, db_module)
    import db_v15
    db_v15.migrate_v15_0_mobile_portal_distributor(conn, db_module)
    import db_v16
    db_v16.migrate_v16_0_enterprise_platform(conn, db_module)
    import db_v17
    db_v17.migrate_v17_0_extensibility(conn, db_module)
    db_v17.ensure_tenant_columns(conn)
    import db_v17_1
    db_v17_1.migrate_v17_1_manufacturing(conn, db_module)
    import db_v17_2
    db_v17_2.migrate_v17_2_validation(conn, db_module)
    import db_v17_3
    db_v17_3.migrate_v17_3_certification(conn, db_module)
    import db_stock_costing
    db_stock_costing.apply_stock_costing(conn, db_module)
    _ensure_expense_bills_schema(conn)
    _ensure_cash_advances_schema(conn)
    _ensure_cash_borrows_schema(conn)


def _ensure_expense_bills_schema(conn):
    """Idempotent multi-expense bill tables + document sequence."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS expense_bills (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_no TEXT UNIQUE NOT NULL,
        bill_date TEXT NOT NULL,
        party_type TEXT NOT NULL,
        party_id INTEGER NOT NULL,
        settlement TEXT NOT NULL,
        bank_account_id INTEGER REFERENCES chart_of_accounts(id),
        reference_no TEXT,
        description TEXT,
        total_amount REAL NOT NULL DEFAULT 0,
        status TEXT DEFAULT 'posted',
        cash_entry_id INTEGER,
        cash_entry_source TEXT,
        created_by INTEGER REFERENCES users(id),
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        posted_by INTEGER REFERENCES users(id),
        posted_at TEXT
    );
    CREATE TABLE IF NOT EXISTS expense_bill_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bill_id INTEGER NOT NULL REFERENCES expense_bills(id) ON DELETE CASCADE,
        line_no INTEGER NOT NULL DEFAULT 1,
        expense_account_id INTEGER NOT NULL REFERENCES chart_of_accounts(id),
        narration TEXT,
        amount REAL NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_expense_bills_date ON expense_bills(bill_date);
    CREATE INDEX IF NOT EXISTS idx_expense_bills_party ON expense_bills(party_type, party_id);
    CREATE INDEX IF NOT EXISTS idx_expense_bill_lines_bill ON expense_bill_lines(bill_id);
    """)
    conn.execute(
        "INSERT OR IGNORE INTO document_sequences (doc_type, prefix, padding) VALUES ('EB', 'EB', 4)"
    )


def _ensure_cash_advances_schema(conn):
    """Cash float / rider-driver advances: issue now, settle bills later."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS cash_advances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_no TEXT UNIQUE NOT NULL,
        issue_date TEXT NOT NULL,
        person_name TEXT NOT NULL,
        purpose TEXT,
        amount REAL NOT NULL DEFAULT 0,
        settled_bills REAL NOT NULL DEFAULT 0,
        cash_returned REAL NOT NULL DEFAULT 0,
        outstanding_amount REAL NOT NULL DEFAULT 0,
        advance_account_id INTEGER NOT NULL REFERENCES chart_of_accounts(id),
        payment_mode TEXT NOT NULL DEFAULT 'cash',
        bank_account_id INTEGER REFERENCES chart_of_accounts(id),
        issue_entry_id INTEGER,
        issue_entry_source TEXT,
        issue_doc_no TEXT,
        status TEXT NOT NULL DEFAULT 'open',
        created_by INTEGER REFERENCES users(id),
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        modified_by INTEGER REFERENCES users(id),
        modified_at TEXT
    );
    CREATE TABLE IF NOT EXISTS cash_advance_settlements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_no TEXT UNIQUE NOT NULL,
        advance_id INTEGER NOT NULL REFERENCES cash_advances(id),
        settle_date TEXT NOT NULL,
        bills_total REAL NOT NULL DEFAULT 0,
        cash_returned REAL NOT NULL DEFAULT 0,
        description TEXT,
        cash_entry_id INTEGER,
        cash_entry_source TEXT,
        cash_doc_no TEXT,
        created_by INTEGER REFERENCES users(id),
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS cash_advance_settlement_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        settlement_id INTEGER NOT NULL REFERENCES cash_advance_settlements(id) ON DELETE CASCADE,
        line_no INTEGER NOT NULL DEFAULT 1,
        expense_account_id INTEGER NOT NULL REFERENCES chart_of_accounts(id),
        narration TEXT,
        amount REAL NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_cash_advances_status ON cash_advances(status);
    CREATE INDEX IF NOT EXISTS idx_cash_advances_date ON cash_advances(issue_date);
    CREATE INDEX IF NOT EXISTS idx_cash_adv_settle_adv ON cash_advance_settlements(advance_id);
    CREATE INDEX IF NOT EXISTS idx_cash_adv_settle_lines ON cash_advance_settlement_lines(settlement_id);
    """)
    for col, typ in (
        ("cash_entry_id", "INTEGER"),
        ("cash_doc_no", "TEXT"),
    ):
        try:
            conn.execute(f"ALTER TABLE cash_advance_settlement_lines ADD COLUMN {col} {typ}")
        except Exception:
            pass
    conn.execute(
        "INSERT OR IGNORE INTO document_sequences (doc_type, prefix, padding) VALUES ('CA', 'CA', 4)"
    )
    conn.execute(
        "INSERT OR IGNORE INTO document_sequences (doc_type, prefix, padding) VALUES ('CAS', 'CAS', 4)"
    )
    ensure_advance_payment_others_account(conn)
    reclass_open_cash_advances_to_others_once(conn)


# 100180 = employee advances only (HR). Cash/rider floats use ADVANCE PAYMENT OTHERS.
EMPLOYEE_ADVANCE_ACCOUNT_CODE = "100180"
CASH_ADVANCE_OTHERS_ACCOUNT_CODE = "100193"
CASH_ADVANCE_OTHERS_ACCOUNT_NAME = "ADVANCE PAYMENT OTHERS"


def ensure_advance_payment_others_account(conn):
    """Create GL head for non-employee advances (riders, cash float, etc.)."""
    row = conn.execute(
        "SELECT id FROM chart_of_accounts WHERE code=? AND is_active=1",
        (CASH_ADVANCE_OTHERS_ACCOUNT_CODE,),
    ).fetchone()
    if row:
        return int(row["id"])
    existing = conn.execute(
        "SELECT id, is_active FROM chart_of_accounts WHERE code=?",
        (CASH_ADVANCE_OTHERS_ACCOUNT_CODE,),
    ).fetchone()
    if existing:
        if not existing["is_active"]:
            conn.execute(
                "UPDATE chart_of_accounts SET is_active=1, name=? WHERE id=?",
                (CASH_ADVANCE_OTHERS_ACCOUNT_NAME, existing["id"]),
            )
        return int(existing["id"])
    by_name = conn.execute(
        """SELECT id FROM chart_of_accounts
           WHERE is_active=1 AND UPPER(TRIM(name))=? LIMIT 1""",
        (CASH_ADVANCE_OTHERS_ACCOUNT_NAME,),
    ).fetchone()
    if by_name:
        return int(by_name["id"])
    # Prefer same asset group / company as 100180 when present
    src = conn.execute(
        """SELECT account_group_id, company_id, branch_id FROM chart_of_accounts
           WHERE code=? LIMIT 1""",
        (EMPLOYEE_ADVANCE_ACCOUNT_CODE,),
    ).fetchone()
    if src:
        gid = int(src["account_group_id"])
        company_id = src["company_id"]
        branch_id = src["branch_id"]
    else:
        ag = conn.execute(
            "SELECT id FROM account_groups WHERE group_type='asset' LIMIT 1"
        ).fetchone()
        if not ag:
            return None
        gid = int(ag["id"])
        company_id = None
        branch_id = None
    cur = conn.execute(
        """INSERT INTO chart_of_accounts(
               code, name, account_group_id, opening_balance, current_balance,
               is_active, company_id, branch_id, created_by
           ) VALUES (?,?,?,0,0,1,?,?,1)""",
        (CASH_ADVANCE_OTHERS_ACCOUNT_CODE, CASH_ADVANCE_OTHERS_ACCOUNT_NAME, gid, company_id, branch_id),
    )
    return int(cur.lastrowid)


def resolve_employee_advance_account_code(conn=None):
    """GL code for HR employee advances/loans — always 100180 when present."""
    import database as db

    def _find(c):
        row = c.execute(
            "SELECT code FROM chart_of_accounts WHERE code=? AND is_active=1",
            (EMPLOYEE_ADVANCE_ACCOUNT_CODE,),
        ).fetchone()
        return EMPLOYEE_ADVANCE_ACCOUNT_CODE if row else "1360"

    if conn is not None:
        return _find(conn)
    with db.get_connection() as c:
        return _find(c)


def resolve_cash_advance_account_id(conn=None):
    """Non-employee advances (Cash Advance register) → ADVANCE PAYMENT OTHERS.

    100180 is reserved for employee advances only.
    """
    import database as db

    def _find(c):
        aid = ensure_advance_payment_others_account(c)
        if aid:
            return aid
        row = c.execute(
            """SELECT id FROM chart_of_accounts
               WHERE is_active=1
                 AND UPPER(name) LIKE '%ADVANCE PAYMENT%OTHER%'
               ORDER BY code LIMIT 1"""
        ).fetchone()
        return int(row["id"]) if row else None

    if conn is not None:
        return _find(conn)
    with db.get_connection() as c:
        return _find(c)


def reclass_open_cash_advances_to_others_once(conn, user_id=1):
    """Move open/partial cash-advance control from 100180 → 100193 (one-time)."""
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_meta'"
    ).fetchone():
        return
    done = conn.execute(
        "SELECT 1 FROM schema_meta WHERE key='cash_adv_others_reclass_v1'"
    ).fetchone()
    if done:
        return
    emp_row = conn.execute(
        "SELECT id FROM chart_of_accounts WHERE code=?",
        (EMPLOYEE_ADVANCE_ACCOUNT_CODE,),
    ).fetchone()
    others_id = ensure_advance_payment_others_account(conn)
    if not emp_row or not others_id:
        return
    emp_id = int(emp_row["id"])
    if emp_id == others_id:
        return
    opens = conn.execute(
        """SELECT id, document_no, outstanding_amount FROM cash_advances
           WHERE advance_account_id=? AND status IN ('open','partial')
             AND COALESCE(outstanding_amount,0) > 0.005""",
        (emp_id,),
    ).fetchall()
    total = round(sum(float(r["outstanding_amount"] or 0) for r in opens), 2)
    if total > 0.005:
        from datetime import date as _date
        today = _date.today().isoformat()
        post_gl_account_id(
            conn, today, others_id, total, 0,
            "Reclass open cash advances to ADVANCE PAYMENT OTHERS",
            "cash_advance_reclass", None, "CA-RECLASS-OTHERS", user_id,
        )
        post_gl_account_id(
            conn, today, emp_id, 0, total,
            "Reclass open cash advances to ADVANCE PAYMENT OTHERS",
            "cash_advance_reclass", None, "CA-RECLASS-OTHERS", user_id,
        )
    conn.execute(
        """UPDATE cash_advances SET advance_account_id=?
           WHERE advance_account_id=? AND status IN ('open','partial')""",
        (others_id, emp_id),
    )
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta(key,value) VALUES('cash_adv_others_reclass_v1','1')"
    )


def _ensure_cash_borrows_schema(conn):
    """Temporary cash borrowings: receive now, repay with cash and/or GL lines later."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS cash_borrows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_no TEXT UNIQUE NOT NULL,
        borrow_date TEXT NOT NULL,
        lender_name TEXT NOT NULL,
        purpose TEXT,
        amount REAL NOT NULL DEFAULT 0,
        settled_lines REAL NOT NULL DEFAULT 0,
        cash_repaid REAL NOT NULL DEFAULT 0,
        outstanding_amount REAL NOT NULL DEFAULT 0,
        borrow_account_id INTEGER NOT NULL REFERENCES chart_of_accounts(id),
        payment_mode TEXT NOT NULL DEFAULT 'cash',
        bank_account_id INTEGER REFERENCES chart_of_accounts(id),
        receive_entry_id INTEGER,
        receive_entry_source TEXT,
        receive_doc_no TEXT,
        status TEXT NOT NULL DEFAULT 'open',
        created_by INTEGER REFERENCES users(id),
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        modified_by INTEGER REFERENCES users(id),
        modified_at TEXT
    );
    CREATE TABLE IF NOT EXISTS cash_borrow_repayments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_no TEXT UNIQUE NOT NULL,
        borrow_id INTEGER NOT NULL REFERENCES cash_borrows(id),
        repay_date TEXT NOT NULL,
        lines_total REAL NOT NULL DEFAULT 0,
        cash_repaid REAL NOT NULL DEFAULT 0,
        description TEXT,
        cash_entry_id INTEGER,
        cash_entry_source TEXT,
        cash_doc_no TEXT,
        created_by INTEGER REFERENCES users(id),
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS cash_borrow_repayment_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        repayment_id INTEGER NOT NULL REFERENCES cash_borrow_repayments(id) ON DELETE CASCADE,
        line_no INTEGER NOT NULL DEFAULT 1,
        account_id INTEGER NOT NULL REFERENCES chart_of_accounts(id),
        narration TEXT,
        amount REAL NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_cash_borrows_status ON cash_borrows(status);
    CREATE INDEX IF NOT EXISTS idx_cash_borrows_date ON cash_borrows(borrow_date);
    CREATE INDEX IF NOT EXISTS idx_cash_borrow_repay_borrow ON cash_borrow_repayments(borrow_id);
    CREATE INDEX IF NOT EXISTS idx_cash_borrow_repay_lines ON cash_borrow_repayment_lines(repayment_id);
    """)
    conn.execute(
        "INSERT OR IGNORE INTO document_sequences (doc_type, prefix, padding) VALUES ('BRW', 'BRW', 4)"
    )
    conn.execute(
        "INSERT OR IGNORE INTO document_sequences (doc_type, prefix, padding) VALUES ('BRWS', 'BRWS', 4)"
    )


def resolve_cash_borrow_account_id(conn=None):
    """Prefer SHORT TERM BORROWINGS (200180); fall back to liability name match."""
    import database as db

    def _find(c):
        for code in ("200180",):
            row = c.execute(
                "SELECT id FROM chart_of_accounts WHERE code=? AND is_active=1", (code,),
            ).fetchone()
            if row:
                return int(row["id"])
        row = c.execute(
            """SELECT a.id FROM chart_of_accounts a
               JOIN account_groups g ON a.account_group_id=g.id
               WHERE a.is_active=1 AND g.group_type='liability'
                 AND (UPPER(a.name) LIKE '%BORROW%' OR UPPER(a.name) LIKE '%SHORT TERM%')
               ORDER BY a.code LIMIT 1"""
        ).fetchone()
        return int(row["id"]) if row else None

    if conn is not None:
        return _find(conn)
    with db.get_connection() as c:
        return _find(c)


def _schema_ver(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_meta'").fetchone():
        return 0
    r = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
    return int(r[0]) if r else 0


def _col_exists(conn, table, col):
    return col in [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _add_col(conn, table, col, ddl):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
        if not _col_exists(conn, table, col):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


def _alter_columns(conn):
    for t, col, ddl in [
        ("products", "weight_unit", "TEXT DEFAULT 'kg'"),
        ("products", "standard_weight", "REAL DEFAULT 0"),
        ("products", "packing_size", "TEXT"),
        ("products", "tax_rate_id", "INTEGER"),
        ("products", "min_stock", "REAL DEFAULT 0"),
        ("customers", "ntn", "TEXT"),
        ("customers", "strn", "TEXT"),
        ("customers", "payment_term_id", "INTEGER"),
        ("customers", "tax_rate_id", "INTEGER"),
        ("suppliers", "ntn", "TEXT"),
        ("suppliers", "strn", "TEXT"),
        ("suppliers", "payment_term_id", "INTEGER"),
        ("suppliers", "tax_rate_id", "INTEGER"),
        ("users", "role_id", "INTEGER"),
        ("sales_invoices", "status", "TEXT DEFAULT 'posted'"),
        ("sales_invoices", "quotation_id", "INTEGER"),
        ("sales_invoices", "order_id", "INTEGER"),
        ("sales_invoices", "dn_id", "INTEGER"),
        ("sales_invoices", "tax_inclusive", "INTEGER DEFAULT 0"),
        ("sales_invoices", "sales_tax", "REAL DEFAULT 0"),
        ("sales_invoices", "further_tax", "REAL DEFAULT 0"),
        ("sales_invoices", "extra_tax", "REAL DEFAULT 0"),
        ("sales_invoices", "wht_tax", "REAL DEFAULT 0"),
        ("sales_invoices", "posted_by", "INTEGER"),
        ("sales_invoices", "posted_at", "TEXT"),
        ("purchase_invoices", "status", "TEXT DEFAULT 'posted'"),
        ("purchase_invoices", "grn_id", "INTEGER"),
        ("purchase_invoices", "order_id", "INTEGER"),
        ("purchase_invoices", "tax_inclusive", "INTEGER DEFAULT 0"),
        ("purchase_invoices", "sales_tax", "REAL DEFAULT 0"),
        ("purchase_invoices", "further_tax", "REAL DEFAULT 0"),
        ("purchase_invoices", "extra_tax", "REAL DEFAULT 0"),
        ("purchase_invoices", "wht_tax", "REAL DEFAULT 0"),
        ("purchase_invoices", "posted_by", "INTEGER"),
        ("purchase_invoices", "posted_at", "TEXT"),
        ("sales_invoice_items", "unit_id", "INTEGER"),
        ("sales_invoice_items", "gross_weight", "REAL DEFAULT 0"),
        ("sales_invoice_items", "tare_weight", "REAL DEFAULT 0"),
        ("sales_invoice_items", "net_weight", "REAL DEFAULT 0"),
        ("sales_invoice_items", "line_discount", "REAL DEFAULT 0"),
        ("sales_invoice_items", "tax_amount", "REAL DEFAULT 0"),
        ("sales_invoice_items", "batch_id", "INTEGER"),
        ("purchase_invoice_items", "unit_id", "INTEGER"),
        ("purchase_invoice_items", "gross_weight", "REAL DEFAULT 0"),
        ("purchase_invoice_items", "tare_weight", "REAL DEFAULT 0"),
        ("purchase_invoice_items", "net_weight", "REAL DEFAULT 0"),
        ("purchase_invoice_items", "line_discount", "REAL DEFAULT 0"),
        ("purchase_invoice_items", "tax_amount", "REAL DEFAULT 0"),
        ("purchase_invoice_items", "batch_no", "TEXT"),
        ("sales_orders", "quotation_id", "INTEGER"),
        ("sales_orders", "status", "TEXT DEFAULT 'open'"),
        ("sales_orders", "posted_by", "INTEGER"),
        ("sales_orders", "posted_at", "TEXT"),
        ("sales_order_items", "discount_pct", "REAL DEFAULT 0"),
        ("purchase_orders", "requisition_id", "INTEGER"),
        ("purchase_orders", "status", "TEXT DEFAULT 'open'"),
        ("journal_vouchers", "posted_by", "INTEGER"),
        ("journal_vouchers", "posted_at", "TEXT"),
    ]:
        _add_col(conn, t, col, ddl)


def _extend_invoice_columns(conn):
    pass  # columns added above


def _seed_v3(conn, db):
    admin = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    if not admin:
        return
    aid = admin[0]

    settings = [
        ("allow_negative_stock", "0"),
        ("company_name", "IFS Chemicals"),
        ("company_address", ""),
        ("company_ntn", ""),
        ("company_strn", ""),
    ]
    for k, v in settings:
        conn.execute("INSERT OR IGNORE INTO system_settings(key,value) VALUES(?,?)", (k, v))

    if conn.execute("SELECT COUNT(*) FROM departments").fetchone()[0] == 0:
        for c, n in [("DEP001", "Production"), ("DEP002", "Sales"), ("DEP003", "Purchase"), ("DEP004", "Accounts")]:
            conn.execute("INSERT INTO departments(code,name,created_by) VALUES(?,?,?)", (c, n, aid))

    if conn.execute("SELECT COUNT(*) FROM roles").fetchone()[0] == 0:
        conn.execute("INSERT INTO roles(code,name,description,created_by) VALUES('ADMIN','Administrator','Full access',?)", (aid,))
        conn.execute("INSERT INTO roles(code,name,description,created_by) VALUES('USER','Standard User','Limited access',?)", (aid,))
        admin_role = conn.execute("SELECT id FROM roles WHERE code='ADMIN'").fetchone()[0]
        modules = ["Dashboard", "Masters", "Sales", "Purchase", "Inventory", "Production", "Finance", "HR", "Reports", "Admin"]
        for m in modules:
            conn.execute(
                "INSERT INTO role_permissions(role_id,module_name,can_view,can_add,can_edit,can_delete,can_post,can_approve) "
                "VALUES(?,?,1,1,1,1,1,1)", (admin_role, m))

    if conn.execute("SELECT COUNT(*) FROM tax_rates").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO tax_rates(code,name,sales_tax_pct,further_tax_pct,extra_tax_pct,wht_pct,is_exempt,created_by) VALUES(?,?,?,?,?,?,?,?)",
            [
                ("STD18", "Standard 18%", 18, 0, 0, 0, 0, aid),
                ("REDUCED", "Reduced 5%", 5, 0, 0, 0, 0, aid),
                ("EXEMPT", "Tax Exempt", 0, 0, 0, 0, 1, aid),
            ],
        )

    if conn.execute("SELECT COUNT(*) FROM payment_terms").fetchone()[0] == 0:
        for c, n, d in [("COD", "Cash on Delivery", 0), ("NET15", "Net 15 Days", 15), ("NET30", "Net 30 Days", 30), ("NET60", "Net 60 Days", 60)]:
            conn.execute("INSERT INTO payment_terms(code,name,days,created_by) VALUES(?,?,?,?)", (c, n, d, aid))

    if conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 0:
        conn.execute("INSERT INTO vehicles(code,registration_no,driver_name,vehicle_type,created_by) VALUES('VH001','ABC-1234','Driver 1','Truck',?)", (aid,))

    if conn.execute("SELECT COUNT(*) FROM machines").fetchone()[0] == 0:
        conn.execute("INSERT INTO machines(code,name,production_line,capacity,created_by) VALUES('MC001','Mixing Line 1','Line-A',1000,?)", (aid,))

    seq = [
        ("QT", "QT", 4), ("DN", "DN", 4), ("PRQ", "PRQ", 4), ("GRN", "GRN", 4),
        ("WS", "WS", 4), ("BOM", "BOM", 4), ("PRO", "PRO", 4), ("BAT", "BAT", 4),
    ]
    for dt, px, pad in seq:
        conn.execute("INSERT OR IGNORE INTO document_sequences(doc_type,prefix,padding) VALUES(?,?,?)", (dt, px, pad))

    # Extended chart of accounts
    extra_accounts = [
        ("1310", "Raw Material Inventory", "asset"), ("1320", "Packing Material Inventory", "asset"),
        ("1330", "Finished Goods Inventory", "asset"), ("1340", "Work in Process", "asset"),
        ("2100", "Sales Tax Payable", "liability"), ("1210", "Purchase Tax Receivable", "asset"),
        ("5100", "Production Variance", "expense"), ("5200", "Direct Labour", "expense"),
        ("5300", "Factory Overheads", "expense"), ("6100", "Admin Expenses", "expense"),
        ("3000", "Retained Earnings / Owner's Equity", "equity"),
        ("3999", "Profit & Loss Clearing", "expense"),
    ]
    groups = {r["group_type"]: r["id"] for r in conn.execute("SELECT id, group_type FROM account_groups").fetchall()}
    for code, name, gtype in extra_accounts:
        if not conn.execute("SELECT 1 FROM chart_of_accounts WHERE code=?", (code,)).fetchone():
            conn.execute(
                "INSERT INTO chart_of_accounts(code,name,account_group_id,created_by) VALUES(?,?,?,?)",
                (code, name, groups.get(gtype, list(groups.values())[0]), aid),
            )


def _apply_performance_indexes_v14(conn):
    """Line-item and stock lookup indexes."""
    for ddl in [
        "CREATE INDEX IF NOT EXISTS idx_ws_product ON warehouse_stock(product_id)",
        "CREATE INDEX IF NOT EXISTS idx_sii_invoice ON sales_invoice_items(invoice_id)",
        "CREATE INDEX IF NOT EXISTS idx_pii_invoice ON purchase_invoice_items(invoice_id)",
    ]:
        conn.execute(ddl)


def _apply_performance_indexes_v5(conn):
    """Search and register performance indexes (skip if table/column missing on older DBs)."""
    def _table(name):
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()

    for ddl in [
        "CREATE INDEX IF NOT EXISTS idx_si_date ON sales_invoices(invoice_date)",
        "CREATE INDEX IF NOT EXISTS idx_si_status ON sales_invoices(status)",
        "CREATE INDEX IF NOT EXISTS idx_si_customer ON sales_invoices(customer_id)",
        "CREATE INDEX IF NOT EXISTS idx_pi_date ON purchase_invoices(invoice_date)",
        "CREATE INDEX IF NOT EXISTS idx_pi_status ON purchase_invoices(status)",
        "CREATE INDEX IF NOT EXISTS idx_pi_supplier ON purchase_invoices(supplier_id)",
        "CREATE INDEX IF NOT EXISTS idx_cr_party ON cash_receipts(party_type, party_id)",
        "CREATE INDEX IF NOT EXISTS idx_cp_party ON cash_payments(party_type, party_id)",
        "CREATE INDEX IF NOT EXISTS idx_cr_date ON cash_receipts(receipt_date)",
        "CREATE INDEX IF NOT EXISTS idx_cp_date ON cash_payments(payment_date)",
        "CREATE INDEX IF NOT EXISTS idx_gl_date ON general_ledger(entry_date)",
        "CREATE INDEX IF NOT EXISTS idx_gl_ref ON general_ledger(reference_type, reference_id)",
    ]:
        conn.execute(ddl)
    if _table("weight_slips"):
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ws_date ON weight_slips(slip_date)")
        if _col_exists(conn, "weight_slips", "status"):
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ws_status ON weight_slips(status)")
    if _table("gate_passes"):
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gp_date ON gate_passes(pass_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gp_type ON gate_passes(pass_type)")
        if _col_exists(conn, "gate_passes", "status"):
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gp_status ON gate_passes(status)")


def _apply_fiscal_year_v6(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS fiscal_years (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fy_code TEXT UNIQUE NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            is_active INTEGER DEFAULT 0,
            is_closed INTEGER DEFAULT 0,
            closed_by INTEGER REFERENCES users(id),
            closed_at TEXT,
            pl_close_ref TEXT,
            net_profit REAL DEFAULT 0,
            notes TEXT,
            created_by INTEGER REFERENCES users(id),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS fiscal_closure_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fiscal_year_id INTEGER NOT NULL REFERENCES fiscal_years(id),
            action TEXT NOT NULL,
            reason TEXT,
            user_id INTEGER REFERENCES users(id),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_fy_dates ON fiscal_years(start_date, end_date);
        CREATE INDEX IF NOT EXISTS idx_fy_active ON fiscal_years(is_active);
    """)
    if conn.execute("SELECT COUNT(*) FROM fiscal_years").fetchone()[0] == 0:
        admin = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
        aid = admin[0] if admin else 1
        y = datetime.now().year
        conn.execute(
            "INSERT INTO fiscal_years(fy_code, start_date, end_date, is_active, is_closed, created_by) VALUES(?,?,?,1,0,?)",
            (str(y), f"{y}-01-01", f"{y}-12-31", aid),
        )


def _apply_party_transfer_v7(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS party_transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_no TEXT UNIQUE NOT NULL,
            transfer_date TEXT NOT NULL,
            transfer_type TEXT NOT NULL,
            from_party_type TEXT NOT NULL,
            from_party_id INTEGER NOT NULL,
            to_party_type TEXT NOT NULL,
            to_party_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            reference_no TEXT,
            description TEXT,
            created_by INTEGER REFERENCES users(id),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_pt_date ON party_transfers(transfer_date);
    """)
    conn.execute("INSERT OR IGNORE INTO document_sequences(doc_type,prefix,padding) VALUES('PT','PT',4)")


def _ensure_equity_accounts(conn):
    admin = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    aid = admin[0] if admin else 1
    groups = {r["group_type"]: r["id"] for r in conn.execute("SELECT id, group_type FROM account_groups").fetchall()}
    for code, name, gtype in [
        ("3000", "Retained Earnings / Owner's Equity", "equity"),
        ("3999", "Profit & Loss Clearing", "expense"),
    ]:
        if not conn.execute("SELECT 1 FROM chart_of_accounts WHERE code=?", (code,)).fetchone():
            conn.execute(
                "INSERT INTO chart_of_accounts(code,name,account_group_id,created_by) VALUES(?,?,?,?)",
                (code, name, groups.get(gtype, list(groups.values())[0]), aid),
            )


def get_setting(key, default=""):
    from database import get_connection, row_to_dict
    with get_connection() as conn:
        r = conn.execute("SELECT value FROM system_settings WHERE key=?", (key,)).fetchone()
        return r[0] if r else default


def set_setting(key, value, user_id=None):
    from database import get_connection
    with get_connection() as conn:
        conn.execute("INSERT INTO system_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    try:
        from db_audit import log_event
        log_event(
            "system_settings", None, "settings", user_id=user_id, module="Admin",
            summary=f"Setting {key} updated",
            details={"key": key, "value": str(value)[:200]},
        )
    except Exception:
        pass


def log_audit(table_name, record_id, action, details, user_id):
    from db_audit import log_event
    log_event(table_name, record_id, action, details, user_id)


def user_can(user, module, action="view"):
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    from erp_core.v15_security import is_portal_user
    if is_portal_user(user):
        return module == "Portal" and action in ("view", "add", "edit", "print")
    from database import get_connection, row_to_dict
    action_map = {
        "view": "can_view", "add": "can_add", "edit": "can_edit",
        "delete": "can_delete_draft", "delete_draft": "can_delete_draft",
        "approve": "can_approve", "reject": "can_reject", "post": "can_post",
        "print": "can_print", "export": "can_export", "admin_override": "can_admin_override",
    }
    col = action_map.get(action, f"can_{action}")
    with get_connection() as conn:
        role_id = user.get("role_id")
        if not role_id:
            r = conn.execute("SELECT id FROM roles WHERE code='ADMIN'").fetchone()
            role_id = r[0] if r else None
        if not role_id:
            return user.get("role") == "admin"
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='role_permission_matrix'"
        ).fetchone():
            row = conn.execute(
                f"SELECT {col} FROM role_permission_matrix WHERE role_id=? AND module_name=?",
                (role_id, module),
            ).fetchone()
            if row is not None:
                return bool(row[0])
        row = conn.execute(
            f"SELECT {col.replace('can_delete_draft', 'can_delete').replace('can_reject', 'can_approve').replace('can_print', 'can_view').replace('can_export', 'can_view').replace('can_admin_override', 'can_post')} "
            f"FROM role_permissions WHERE role_id=? AND module_name=?",
            (role_id, module),
        ).fetchone()
        return bool(row and row[0]) if row else user.get("role") == "admin"


def _acct_id(conn, code):
    r = conn.execute("SELECT id FROM chart_of_accounts WHERE code=?", (code,)).fetchone()
    return r[0] if r else None


def _gl_party_label(conn, ref_type, ref_id):
    """Supplier/customer label for invoice-linked GL narrations."""
    if not ref_id:
        return ""
    if ref_type == "purchase_invoice":
        row = conn.execute(
            """SELECT s.code, s.name FROM purchase_invoices p
               JOIN suppliers s ON s.id=p.supplier_id WHERE p.id=?""",
            (ref_id,),
        ).fetchone()
        if row:
            code, name = row[0] or "", row[1] or ""
            return f"{code} - {name}".strip(" -") if (code or name) else ""
    if ref_type == "sales_invoice":
        row = conn.execute(
            """SELECT c.code, c.name FROM sales_invoices s
               JOIN customers c ON c.id=s.customer_id WHERE s.id=?""",
            (ref_id,),
        ).fetchone()
        if row:
            code, name = row[0] or "", row[1] or ""
            return f"{code} - {name}".strip(" -") if (code or name) else ""
    return ""


def _gl_narration(base, party_label):
    base = (base or "").strip() or "Entry"
    party = (party_label or "").strip()
    if not party:
        return base
    # Avoid duplicating if already present
    if party.lower() in base.lower():
        return base
    return f"{base} - {party}"


def post_gl_account_id(conn, entry_date, account_id, debit, credit, description, ref_type, ref_id, ref_no, user_id, voucher_id=None):
    if not account_id:
        return
    validate_fiscal_open(entry_date, ref_type=ref_type)
    conn.execute(
        """INSERT INTO general_ledger(entry_date,account_id,debit,credit,description,reference_type,reference_id,reference_no,voucher_id,created_by)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (entry_date, account_id, debit, credit, description, ref_type, ref_id, ref_no, voucher_id, user_id),
    )
    if debit:
        conn.execute("UPDATE chart_of_accounts SET current_balance=current_balance+? WHERE id=?", (debit, account_id))
    if credit:
        conn.execute("UPDATE chart_of_accounts SET current_balance=current_balance-? WHERE id=?", (credit, account_id))


def post_gl(conn, entry_date, account_code, debit, credit, description, ref_type, ref_id, ref_no, user_id, voucher_id=None):
    validate_fiscal_open(entry_date, ref_type=ref_type)
    aid = _acct_id(conn, account_code)
    if not aid:
        return
    conn.execute(
        """INSERT INTO general_ledger(entry_date,account_id,debit,credit,description,reference_type,reference_id,reference_no,voucher_id,created_by)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (entry_date, aid, debit, credit, description, ref_type, ref_id, ref_no, voucher_id, user_id),
    )
    if debit:
        conn.execute("UPDATE chart_of_accounts SET current_balance=current_balance+? WHERE id=?", (debit, aid))
    if credit:
        conn.execute("UPDATE chart_of_accounts SET current_balance=current_balance-? WHERE id=?", (credit, aid))


def calc_line_tax(subtotal, tax_rate_row, tax_inclusive=False):
    from tax_engine import calc_line
    cl = calc_line(1, float(subtotal or 0), 0, tax_rate_row, tax_inclusive)
    return cl["sales_tax"], cl["further_tax"], cl["extra_tax"], cl["wht_tax"]


def _doc_totals(data, lines):
    from tax_engine import compute_document_totals
    return compute_document_totals(lines, data, get_tax_rate)


def get_tax_rate(tax_id):
    from database import get_connection, row_to_dict
    with get_connection() as conn:
        return row_to_dict(conn.execute("SELECT * FROM tax_rates WHERE id=?", (tax_id,)).fetchone())


# ---------- Generic master CRUD ----------
def _master_list(table, search=None, active_col="is_active", order="name"):
    from database import get_connection, rows_to_list
    q = f"SELECT * FROM {table} WHERE 1=1"
    p = []
    if search:
        q += " AND (code LIKE ? OR name LIKE ?)"
        p.extend([f"%{search}%", f"%{search}%"])
    q += f" ORDER BY {order}"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


def _master_get(table, rid):
    from database import get_connection, row_to_dict
    with get_connection() as conn:
        return row_to_dict(conn.execute(f"SELECT * FROM {table} WHERE id=?", (rid,)).fetchone())


def _master_delete(table, rid, user_id=None):
    from database import get_connection
    with get_connection() as conn:
        conn.execute(f"DELETE FROM {table} WHERE id=?", (rid,))
    log_audit(table, rid, "delete", None, user_id)


# Departments
get_departments = lambda s=None: _master_list("departments", s)
get_department = lambda i: _master_get("departments", i)
def add_department(data, user_id=None):
    from database import get_connection, next_code
    with get_connection() as conn:
        cur = conn.execute("INSERT INTO departments(code,name,created_by) VALUES(?,?,?)",
                           (data.get("code") or next_code("DEP","departments"), data["name"], user_id))
        return cur.lastrowid
def update_department(rid, data, user_id=None):
    from database import get_connection
    with get_connection() as conn:
        conn.execute("UPDATE departments SET code=?,name=?,is_active=?,modified_by=?,modified_at=? WHERE id=?",
                     (data["code"], data["name"], data.get("is_active",1), user_id, now(), rid))
delete_department = _master_delete


# Tax rates
def get_tax_rates(search=None):
    from db_cache import cached_read

    key = f"tax_rates:{search or ''}"

    def _load():
        return _master_list("tax_rates", search)

    return cached_read(key, _load)


def default_tax_rate_id():
    """Default invoice tax category: Tax Exempt when present, else first rate."""
    rates = get_tax_rates()
    for r in rates:
        if r.get("is_exempt") in (1, True, "1"):
            return r["id"]
        if str(r.get("code", "")).strip().upper() == "EXEMPT":
            return r["id"]
    return rates[0]["id"] if rates else None
get_tax_rate_by_id = lambda i: _master_get("tax_rates", i)
def add_tax_rate(data, user_id=None):
    from database import get_connection, next_code
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO tax_rates(code,name,sales_tax_pct,further_tax_pct,extra_tax_pct,wht_pct,fed_pct,is_exempt,created_by)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (data.get("code") or next_code("TAX","tax_rates"), data["name"], data.get("sales_tax_pct",0),
             data.get("further_tax_pct",0), data.get("extra_tax_pct",0), data.get("wht_pct",0),
             data.get("fed_pct",0), data.get("is_exempt",0), user_id))
        from db_cache import invalidate
        invalidate("tax_rates")
        return cur.lastrowid
def update_tax_rate(rid, data, user_id=None):
    from database import get_connection
    with get_connection() as conn:
        conn.execute(
            """UPDATE tax_rates SET code=?,name=?,sales_tax_pct=?,further_tax_pct=?,extra_tax_pct=?,
               wht_pct=?,fed_pct=?,is_exempt=?,is_active=?,modified_by=?,modified_at=? WHERE id=?""",
            (data["code"], data["name"], data.get("sales_tax_pct",0), data.get("further_tax_pct",0),
             data.get("extra_tax_pct",0), data.get("wht_pct",0), data.get("fed_pct",0),
             data.get("is_exempt",0), data.get("is_active",1), user_id, now(), rid))
    from db_cache import invalidate
    invalidate("tax_rates")

def delete_tax_rate(rid, user_id=None):
    _master_delete("tax_rates", rid, user_id)
    from db_cache import invalidate
    invalidate("tax_rates")


# Payment terms
get_payment_terms = lambda s=None: _master_list("payment_terms", s)
def add_payment_term(data, user_id=None):
    from database import get_connection, next_code
    with get_connection() as conn:
        cur = conn.execute("INSERT INTO payment_terms(code,name,days,created_by) VALUES(?,?,?,?)",
                           (data.get("code") or next_code("PT","payment_terms"), data["name"], data.get("days",0), user_id))
        return cur.lastrowid
def update_payment_term(rid, data, user_id=None):
    from database import get_connection
    with get_connection() as conn:
        conn.execute("UPDATE payment_terms SET code=?,name=?,days=?,is_active=?,modified_by=?,modified_at=? WHERE id=?",
                     (data["code"], data["name"], data.get("days",0), data.get("is_active",1), user_id, now(), rid))
delete_payment_term = lambda i,u=None: _master_delete("payment_terms", i, u)


# Vehicles
get_vehicles = lambda s=None: _master_list("vehicles", s, order="registration_no")
def add_vehicle(data, user_id=None):
    from database import get_connection, next_code
    with get_connection() as conn:
        cur = conn.execute("INSERT INTO vehicles(code,registration_no,driver_name,vehicle_type,created_by) VALUES(?,?,?,?,?)",
                           (data.get("code") or next_code("VH","vehicles"), data["registration_no"],
                            data.get("driver_name"), data.get("vehicle_type"), user_id))
        return cur.lastrowid
def update_vehicle(rid, data, user_id=None):
    from database import get_connection
    with get_connection() as conn:
        conn.execute("UPDATE vehicles SET code=?,registration_no=?,driver_name=?,vehicle_type=?,is_active=?,modified_by=?,modified_at=? WHERE id=?",
                     (data["code"], data["registration_no"], data.get("driver_name"), data.get("vehicle_type"),
                      data.get("is_active",1), user_id, now(), rid))
delete_vehicle = lambda i,u=None: _master_delete("vehicles", i, u)


# Machines
get_machines = lambda s=None: _master_list("machines", s)
def add_machine(data, user_id=None):
    from database import get_connection, next_code
    with get_connection() as conn:
        cur = conn.execute("INSERT INTO machines(code,name,production_line,capacity,created_by) VALUES(?,?,?,?,?)",
                           (data.get("code") or next_code("MC","machines"), data["name"],
                            data.get("production_line"), data.get("capacity",0), user_id))
        return cur.lastrowid
def update_machine(rid, data, user_id=None):
    from database import get_connection
    with get_connection() as conn:
        conn.execute("UPDATE machines SET code=?,name=?,production_line=?,capacity=?,is_active=?,modified_by=?,modified_at=? WHERE id=?",
                     (data["code"], data["name"], data.get("production_line"), data.get("capacity",0),
                      data.get("is_active",1), user_id, now(), rid))
delete_machine = lambda i,u=None: _master_delete("machines", i, u)


# Roles
def get_roles():
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        return rows_to_list(conn.execute("SELECT * FROM roles ORDER BY name").fetchall())

def get_role_permissions(role_id):
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        return rows_to_list(conn.execute("SELECT * FROM role_permissions WHERE role_id=?", (role_id,)).fetchall())

def save_role_permissions(role_id, perms, user_id=None):
    from database import get_connection
    with get_connection() as conn:
        conn.execute("DELETE FROM role_permissions WHERE role_id=?", (role_id,))
        for p in perms:
            conn.execute(
                "INSERT INTO role_permissions(role_id,module_name,can_view,can_add,can_edit,can_delete,can_post,can_approve) VALUES(?,?,?,?,?,?,?,?)",
                (role_id, p["module"], p.get("view",1), p.get("add",0), p.get("edit",0),
                 p.get("delete",0), p.get("post",0), p.get("approve",0)))


# Weight slips
def get_weight_slips():
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            "SELECT ws.*, v.registration_no FROM weight_slips ws LEFT JOIN vehicles v ON ws.vehicle_id=v.id ORDER BY slip_date DESC"
        ).fetchall())

def save_weight_slip(data, slip_id=None, user_id=None):
    from database import get_connection, ensure_document_no
    net = abs(data.get("first_weight",0) - data.get("second_weight",0) - data.get("tare_weight",0))
    with get_connection() as conn:
        if slip_id:
            conn.execute(
                """UPDATE weight_slips SET slip_date=?,vehicle_id=?,driver_name=?,first_weight=?,second_weight=?,
                   tare_weight=?,gross_weight=?,net_weight=?,remarks=?,modified_by=?,modified_at=? WHERE id=?""",
                (data["slip_date"], data.get("vehicle_id"), data.get("driver_name"), data.get("first_weight",0),
                 data.get("second_weight",0), data.get("tare_weight",0), data.get("gross_weight",0), net,
                 data.get("remarks"), user_id, now(), slip_id))
        else:
            cur = conn.execute(
                """INSERT INTO weight_slips(document_no,slip_date,vehicle_id,driver_name,first_weight,second_weight,
                   tare_weight,gross_weight,net_weight,remarks,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (ensure_document_no("WS", data.get("document_no"), conn), data["slip_date"], data.get("vehicle_id"),
                 data.get("driver_name"), data.get("first_weight",0), data.get("second_weight",0),
                 data.get("tare_weight",0), data.get("gross_weight",0), net, data.get("remarks"), user_id))
            slip_id = cur.lastrowid
        return slip_id

def delete_weight_slip(sid, user_id=None):
    _master_delete("weight_slips", sid, user_id)


def _apply_bom_production_v4(conn):
    for col, ddl in [
        ("composition_type", "TEXT DEFAULT 'detergent_powder'"),
        ("composition_date", "TEXT"),
        ("description", "TEXT"),
    ]:
        _add_col(conn, "bom_formulas", col, ddl)
    _add_col(conn, "production_orders", "production_type", "TEXT")


COMPOSITION_TYPES = {
    "detergent_powder": "Detergent Powder (dry mix / spray dry)",
    "detergent_liquid": "Liquid Detergent (blending / filling)",
    "dishwash_bar": "Dishwash Bar (extrusion / stamping)",
    "dishwash_liquid": "Dishwash Liquid (blending / filling)",
    "corrugated_box": "Corrugated Box (board / conversion)",
    "flexible_wrapper": "Flexible Wrapper / Gravure Printing",
    "other": "Other / General Assembly",
}


def infer_composition_type(product_name: str = "", description: str = "") -> str:
    """Guess composition type from finished-product name / BOM description."""
    blob = f"{product_name or ''} {description or ''}".upper()
    if any(k in blob for k in ("DISH LIQUID", "DISHWASH LIQUID", "DISH WASH LIQUID")):
        return "dishwash_liquid"
    if any(k in blob for k in ("DISHWASH", "DISH BAR", "DISHBAR", "LAUNDARY BAR", "LAUNDRY BAR")):
        return "dishwash_bar"
    if "LIQUID" in blob and "DETERGENT" in blob:
        return "detergent_liquid"
    if any(k in blob for k in ("BASE POWDER", "DETERGENT", "DENSITY BASE")) or (
        "POWDER" in blob and "SALT" not in blob
    ):
        return "detergent_powder"
    return "other"


def repair_bom_composition_types(conn=None) -> int:
    """Re-tag FMYE/imported BOMs still marked 'other' using product name heuristics."""
    from database import get_connection

    def _run(c):
        rows = c.execute(
            """SELECT b.id, b.description, p.name AS pname
               FROM bom_formulas b
               JOIN products p ON p.id = b.finished_product_id
               WHERE COALESCE(b.composition_type, 'other') = 'other'"""
        ).fetchall()
        n = 0
        for r in rows:
            inferred = infer_composition_type(r["pname"], r["description"])
            if inferred == "other":
                continue
            c.execute(
                "UPDATE bom_formulas SET composition_type=? WHERE id=?",
                (inferred, r["id"]),
            )
            n += 1
        return n

    if conn is not None:
        return _run(conn)
    with get_connection() as c:
        return _run(c)


def _consolidate_bom_lines(lines):
    """Merge duplicate raw materials into one line (sum qty & cost)."""
    merged = {}
    for ln in lines:
        pid = ln["raw_product_id"]
        if pid in merged:
            merged[pid]["quantity"] = float(merged[pid]["quantity"]) + float(ln["quantity"])
            merged[pid]["line_cost"] = float(merged[pid].get("line_cost") or 0) + float(ln.get("line_cost") or 0)
            wp = float(ln.get("wastage_pct") or 0)
            if wp > float(merged[pid].get("wastage_pct") or 0):
                merged[pid]["wastage_pct"] = wp
        else:
            merged[pid] = dict(ln)
    return list(merged.values())


def get_bom_by_product_version(finished_product_id, version_no):
    from database import get_connection
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM bom_formulas WHERE finished_product_id=? AND version_no=?",
            (finished_product_id, version_no),
        ).fetchone()
        return row[0] if row else None


def suggest_next_bom_version(finished_product_id):
    from database import get_connection
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT version_no FROM bom_formulas WHERE finished_product_id=? ORDER BY id",
            (finished_product_id,),
        ).fetchall()
    if not rows:
        return "1.0"
    nums = []
    for r in rows:
        try:
            nums.append(float(str(r[0]).strip()))
        except ValueError:
            nums.append(len(nums) + 1)
    return f"{max(nums) + 0.1:.1f}"


def search_bom_formulas(
    q=None, composition_type=None, status=None, finished_product_id=None,
    page=1, page_size=50, export_all=False, **_ignored,
):
    from database import run_paginated_list
    where, params = ["1=1"], []
    if q:
        like = f"%{q.strip()}%"
        where.append(
            "(b.document_no LIKE ? OR p.name LIKE ? OR p.code LIKE ? OR COALESCE(b.description,'') LIKE ? OR COALESCE(b.notes,'') LIKE ?)"
        )
        params.extend([like, like, like, like, like])
    if composition_type and composition_type != "All":
        where.append("COALESCE(b.composition_type,'other') = ?")
        params.append(composition_type)
    if status and status != "All":
        where.append("b.status = ?")
        params.append(status)
    if finished_product_id:
        where.append("b.finished_product_id = ?")
        params.append(finished_product_id)
    return run_paginated_list(
        "bom_formulas b JOIN products p ON b.finished_product_id=p.id",
        "b.*, p.name AS finished_product_name, p.code AS finished_product_code",
        where, params, "b.id DESC", page, page_size, export_all,
        sum_exprs=["COALESCE(SUM(b.standard_cost),0)"],
    )


def get_bom_list():
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            """SELECT b.*, p.name AS finished_product_name, p.code AS finished_product_code
               FROM bom_formulas b
               JOIN products p ON b.finished_product_id=p.id ORDER BY b.id DESC"""
        ).fetchall())

def get_bom(bom_id):
    from database import get_connection, row_to_dict, rows_to_list
    with get_connection() as conn:
        h = row_to_dict(conn.execute(
            """SELECT b.*, p.name AS finished_product_name FROM bom_formulas b
               JOIN products p ON b.finished_product_id=p.id WHERE b.id=?""", (bom_id,)).fetchone())
        if h:
            h["lines"] = rows_to_list(conn.execute(
                """SELECT bl.*, p.name AS raw_product_name, p.code AS raw_product_code,
                          p.product_type AS raw_product_type, u.symbol AS unit
                   FROM bom_formula_lines bl
                   JOIN products p ON bl.raw_product_id=p.id
                   LEFT JOIN units_of_measure u ON bl.unit_id=u.id
                   WHERE bl.bom_id=?""", (bom_id,)).fetchall())
        return h

def save_bom(data, lines, bom_id=None, user_id=None):
    from database import get_connection, ensure_document_no
    lines = _consolidate_bom_lines(lines)
    if not lines:
        raise ValueError("Add at least one raw material / component line.")
    std_cost = sum(l.get("line_cost", l.get("quantity", 0) * l.get("standard_cost", 0)) for l in lines)
    version_no = data.get("version_no", "1.0")
    with get_connection() as conn:
        if not bom_id:
            existing = conn.execute(
                "SELECT id, status FROM bom_formulas WHERE finished_product_id=? AND version_no=?",
                (data["finished_product_id"], version_no),
            ).fetchone()
            if existing:
                raise ValueError(
                    f"Composition version {version_no} already exists for this finished product. "
                    f"Open it in Edit / Approve, or use version {suggest_next_bom_version(data['finished_product_id'])}."
                )
        else:
            dup = conn.execute(
                "SELECT id FROM bom_formulas WHERE finished_product_id=? AND version_no=? AND id!=?",
                (data["finished_product_id"], version_no, bom_id),
            ).fetchone()
            if dup:
                raise ValueError(f"Version {version_no} is already used for this product.")
        if bom_id:
            conn.execute("DELETE FROM bom_formula_lines WHERE bom_id=?", (bom_id,))
            conn.execute(
                """UPDATE bom_formulas SET finished_product_id=?,version_no=?,standard_output_qty=?,output_unit_id=?,
                   standard_cost=?,status=?,notes=?,composition_type=?,composition_date=?,description=?,
                   modified_by=?,modified_at=? WHERE id=?""",
                (data["finished_product_id"], version_no, data.get("standard_output_qty", 1),
                 data.get("output_unit_id"), std_cost, data.get("status", "draft"), data.get("notes"),
                 data.get("composition_type", "other"), data.get("composition_date"), data.get("description"),
                 user_id, now(), bom_id),
            )
        else:
            cur = conn.execute(
                """INSERT INTO bom_formulas(document_no,finished_product_id,version_no,standard_output_qty,output_unit_id,
                   standard_cost,status,notes,composition_type,composition_date,description,created_by)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (ensure_document_no("BOM", data.get("document_no"), conn), data["finished_product_id"], version_no,
                 data.get("standard_output_qty", 1), data.get("output_unit_id"), std_cost,
                 data.get("status", "draft"), data.get("notes"), data.get("composition_type", "other"),
                 data.get("composition_date"), data.get("description"), user_id),
            )
            bom_id = cur.lastrowid
        for l in lines:
            lc = l.get("line_cost", l["quantity"] * l.get("standard_cost", 0))
            conn.execute(
                "INSERT INTO bom_formula_lines(bom_id,raw_product_id,quantity,unit_id,weight_required,wastage_pct,standard_cost,line_cost) VALUES(?,?,?,?,?,?,?,?)",
                (bom_id, l["raw_product_id"], l["quantity"], l.get("unit_id"), l.get("weight_required", 0),
                 l.get("wastage_pct", 0), l.get("standard_cost", 0), lc),
            )
        return bom_id

def approve_bom(bom_id, user_id):
    from database import get_connection
    with get_connection() as conn:
        conn.execute("UPDATE bom_formulas SET status='approved',approved_by=?,approved_at=?,modified_at=? WHERE id=?",
                     (user_id, now(), now(), bom_id))


def set_bom_status(bom_id, status, user_id=None):
    """Set composition status: draft | approved | inactive."""
    from database import get_connection
    status = (status or "").strip().lower()
    if status not in ("draft", "approved", "inactive"):
        raise ValueError("Status must be draft, approved, or inactive.")
    with get_connection() as conn:
        row = conn.execute("SELECT id, document_no FROM bom_formulas WHERE id=?", (bom_id,)).fetchone()
        if not row:
            raise ValueError("Composition not found.")
        if status == "approved":
            conn.execute(
                "UPDATE bom_formulas SET status='approved', approved_by=?, approved_at=?, modified_by=?, modified_at=? WHERE id=?",
                (user_id, now(), user_id, now(), bom_id),
            )
        else:
            conn.execute(
                "UPDATE bom_formulas SET status=?, modified_by=?, modified_at=? WHERE id=?",
                (status, user_id, now(), bom_id),
            )
    return row[1] if not hasattr(row, "keys") else row["document_no"]


def bom_production_usage(bom_id):
    """How many production orders reference this composition."""
    from database import get_connection
    with get_connection() as conn:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM production_orders WHERE bom_id=?", (bom_id,),
            ).fetchone()[0]
        )


def copy_bom(bom_id, new_version, user_id):
    b = get_bom(bom_id)
    if not b:
        return None
    data = {
        "finished_product_id": b["finished_product_id"],
        "version_no": new_version,
        "standard_output_qty": b["standard_output_qty"],
        "output_unit_id": b.get("output_unit_id"),
        "composition_type": b.get("composition_type") or "other",
        "composition_date": b.get("composition_date"),
        "description": b.get("description"),
        "notes": f"Copied from v{b['version_no']}",
        "status": "draft",
    }
    lines = [{"raw_product_id": l["raw_product_id"], "quantity": l["quantity"], "unit_id": l.get("unit_id"),
              "weight_required": l.get("weight_required",0), "wastage_pct": l.get("wastage_pct",0),
              "standard_cost": l.get("standard_cost",0), "line_cost": l.get("line_cost",0)} for l in b["lines"]]
    return save_bom(data, lines, None, user_id)

def delete_bom(bom_id, user_id=None, allow_used=False):
    from database import get_connection
    with get_connection() as conn:
        row = conn.execute(
            "SELECT document_no, status FROM bom_formulas WHERE id=?", (bom_id,),
        ).fetchone()
        if not row:
            raise ValueError("Composition not found.")
        used = conn.execute(
            "SELECT COUNT(*) FROM production_orders WHERE bom_id=?", (bom_id,),
        ).fetchone()[0]
        if used and not allow_used:
            raise ValueError(
                f"Cannot delete: **{used}** production order(s) use this composition. "
                "Set status to **inactive**, or tick force delete."
            )
        conn.execute("DELETE FROM bom_formula_lines WHERE bom_id=?", (bom_id,))
        conn.execute("DELETE FROM bom_formulas WHERE id=?", (bom_id,))


# Production
def get_production_orders():
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            """SELECT po.*, p.name AS product_name, b.document_no AS bom_no FROM production_orders po
               JOIN products p ON po.finished_product_id=p.id
               JOIN bom_formulas b ON po.bom_id=b.id ORDER BY po.id DESC"""
        ).fetchall())

def get_production_order(po_id):
    from database import get_connection, row_to_dict, rows_to_list
    with get_connection() as conn:
        h = row_to_dict(conn.execute("SELECT * FROM production_orders WHERE id=?", (po_id,)).fetchone())
        if h:
            h["issues"] = rows_to_list(conn.execute(
                "SELECT pi.*, p.name AS product_name FROM production_material_issues pi JOIN products p ON pi.product_id=p.id WHERE production_order_id=?",
                (po_id,)).fetchall())
            h["receipts"] = rows_to_list(conn.execute("SELECT * FROM production_finished_receipts WHERE production_order_id=?", (po_id,)).fetchall())
        return h

def calc_bom_requirements(bom_id, planned_qty):
    b = get_bom(bom_id)
    if not b:
        return []
    factor = planned_qty / (b.get("standard_output_qty") or 1)
    req = []
    for l in b["lines"]:
        qty = l["quantity"] * factor * (1 + (l.get("wastage_pct") or 0) / 100)
        req.append({
            "product_id": l["raw_product_id"],
            "product_name": l["raw_product_name"],
            "product_code": l.get("raw_product_code") or "",
            "quantity": round(qty, 4),
            "unit_id": l.get("unit_id"),
            "weight": round((l.get("weight_required") or 0) * factor * (1 + (l.get("wastage_pct") or 0) / 100), 3),
            "wastage_pct": l.get("wastage_pct") or 0,
            "base_qty": round(l["quantity"] * factor, 4),
        })
    return req

def save_production_order(data, user_id=None):
    from database import get_connection, ensure_document_no
    bom = get_bom(data["bom_id"]) if data.get("bom_id") else None
    prod_type = data.get("production_type") or (bom.get("composition_type") if bom else None)
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO production_orders(document_no,batch_no,order_date,bom_id,finished_product_id,warehouse_id,
               machine_id,planned_qty,labour_cost,utility_cost,packing_cost,overhead_cost,production_type,notes,created_by)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ensure_document_no("PRO", data.get("document_no"), conn), ensure_document_no("BAT", data.get("batch_no"), conn),
             data["order_date"], data["bom_id"], data["finished_product_id"], data.get("warehouse_id"),
             data.get("machine_id"), data["planned_qty"], data.get("labour_cost", 0), data.get("utility_cost", 0),
             data.get("packing_cost", 0), data.get("overhead_cost", 0), prod_type, data.get("notes"), user_id),
        )
        return cur.lastrowid


def update_production_order(production_order_id, data, user_id=None):
    """Update a draft production order (not issued yet)."""
    import database as db
    with db.get_connection() as conn:
        row = conn.execute("SELECT * FROM production_orders WHERE id=?", (production_order_id,)).fetchone()
        if not row:
            raise ValueError("Production order not found.")
        status = (row["status"] or "draft").lower()
        if status != "draft":
            raise ValueError(
                f"Only **draft** orders can be edited (this order is **{status}**)."
            )
        n_issues = conn.execute(
            "SELECT COUNT(*) FROM production_material_issues WHERE production_order_id=?",
            (production_order_id,),
        ).fetchone()[0]
        if n_issues:
            raise ValueError(
                "Materials were already issued — this order cannot be edited. "
                "Complete or cancel the batch workflow first."
            )
        batch_no = (data.get("batch_no") or row["batch_no"] or "").strip()
        if not batch_no:
            raise ValueError("Batch number is required.")
        dup = conn.execute(
            "SELECT id FROM production_orders WHERE batch_no=? AND id!=?",
            (batch_no, production_order_id),
        ).fetchone()
        if dup:
            raise ValueError(f"Batch number **{batch_no}** is already used on another order.")
        bom_id = data.get("bom_id") or row["bom_id"]
        bom = get_bom(bom_id)
        if not bom:
            raise ValueError("Composition (BOM) not found.")
        if bom.get("status") != "approved":
            raise ValueError("Selected composition must be **approved**.")
        finished_id = data.get("finished_product_id") or bom["finished_product_id"]
        prod_type = data.get("production_type") or bom.get("composition_type") or row["production_type"]
        planned = float(data.get("planned_qty") or row["planned_qty"] or 0)
        if planned <= 0:
            raise ValueError("Planned quantity must be greater than zero.")
        conn.execute(
            """UPDATE production_orders SET order_date=?, bom_id=?, finished_product_id=?,
               warehouse_id=?, machine_id=?, planned_qty=?, batch_no=?,
               labour_cost=?, utility_cost=?, packing_cost=?, overhead_cost=?,
               production_type=?, notes=?, modified_by=?, modified_at=? WHERE id=?""",
            (
                data.get("order_date") or row["order_date"],
                bom_id,
                finished_id,
                data.get("warehouse_id"),
                data.get("machine_id"),
                planned,
                batch_no,
                float(data.get("labour_cost") or 0),
                float(data.get("utility_cost") or 0),
                float(data.get("packing_cost") or 0),
                float(data.get("overhead_cost") or 0),
                prod_type,
                data.get("notes"),
                user_id,
                now(),
                production_order_id,
            ),
        )
    try:
        from db_audit import log_event
        log_event(
            "production_orders", production_order_id, "update", user_id=user_id,
            module="Production", document_no=row["document_no"],
            summary=f"Updated draft production order {row['document_no']}",
        )
    except Exception:
        pass


def delete_production_order(production_order_id, user_id=None, reason="", allow_force=False):
    """Delete a production order; reverses stock/GL for issued or completed entries."""
    import database as db
    from database import row_to_dict
    reason = (reason or "").strip() or "Deleted by user"
    # Completed daily/QC posts: rollback FG + materials first, then delete the draft shell.
    po_peek = get_production_order(production_order_id)
    if not po_peek:
        raise ValueError("Production order not found.")
    if (po_peek.get("status") or "").lower() == "completed":
        rollback_production_completion(
            production_order_id, user_id=user_id, reason=reason, allow_force=allow_force,
        )
    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM production_orders WHERE id=?", (production_order_id,),
        ).fetchone()
        if not row:
            raise ValueError("Production order not found.")
        po = row_to_dict(row)
        status = (po.get("status") or "draft").lower()
        if status not in ("draft", "issued"):
            raise ValueError(
                f"Only draft, issued, or completed orders can be deleted (status: **{status}**)."
            )
        n_receipts = conn.execute(
            "SELECT COUNT(*) FROM production_finished_receipts WHERE production_order_id=?",
            (production_order_id,),
        ).fetchone()[0]
        if n_receipts:
            raise ValueError(
                "Finished goods were received on this order — rollback completion before delete."
            )
        n_issues = conn.execute(
            "SELECT COUNT(*) FROM production_material_issues WHERE production_order_id=?",
            (production_order_id,),
        ).fetchone()[0]
        if n_issues:
            _unissue_production_materials(conn, production_order_id, po, user_id)
        doc_no = po["document_no"]
        _clear_production_ledger(conn, production_order_id)
        conn.execute(
            "DELETE FROM production_finished_receipts WHERE production_order_id=?",
            (production_order_id,),
        )
        conn.execute(
            "DELETE FROM production_material_issues WHERE production_order_id=?",
            (production_order_id,),
        )
        conn.execute("DELETE FROM production_orders WHERE id=?", (production_order_id,))
    _invalidate_production_stock_cache()
    try:
        from db_audit import log_event
        log_event(
            "production_orders", production_order_id, "delete", user_id=user_id,
            module="Production", document_no=doc_no,
            summary=f"Deleted production order {doc_no}",
            details={"reason": reason},
        )
    except Exception:
        pass


def production_material_shortages(production_order_id):
    """Materials where warehouse qty is below BOM requirement (for issue confirmation)."""
    import database as db
    po = get_production_order(production_order_id)
    if not po:
        return []
    reqs = calc_bom_requirements(po["bom_id"], po["planned_qty"])
    shortages = []
    with db.get_connection() as conn:
        wh = po.get("warehouse_id") or db._default_warehouse_id(conn)
        for r in reqs:
            row = conn.execute(
                "SELECT COALESCE(quantity,0) FROM warehouse_stock WHERE warehouse_id=? AND product_id=?",
                (wh, r["product_id"]),
            ).fetchone()
            avail = float(row[0] if row else 0)
            need = float(r["quantity"] or 0)
            if avail + 1e-9 < need:
                shortages.append({
                    "product_id": r["product_id"],
                    "product_name": r["product_name"],
                    "required": need,
                    "available": avail,
                    "shortfall": round(need - avail, 4),
                })
    return shortages


def issue_production_materials(production_order_id, user_id=None, allow_insufficient=False):
    import database as db
    po = get_production_order(production_order_id)
    if not po:
        raise ValueError("Production order not found.")
    if (po.get("status") or "").lower() != "draft":
        raise ValueError(
            f"Only **draft** orders can issue materials (current status: **{po.get('status')}**)."
        )
    if po.get("issues"):
        raise ValueError(
            "Materials were already issued for this order. Roll back completion or reopen to draft first."
        )
    reqs = calc_bom_requirements(po["bom_id"], po["planned_qty"])
    allow_neg = get_setting("allow_negative_stock") == "1"
    if not allow_neg and not allow_insufficient:
        short = production_material_shortages(production_order_id)
        if short:
            names = ", ".join(s["product_name"] for s in short[:5])
            extra = f" (+{len(short) - 5} more)" if len(short) > 5 else ""
            raise ValueError(
                f"Insufficient stock: {names}{extra}. "
                "Confirm issue on the production screen to post anyway (stock may go negative)."
            )
    with db.get_connection() as conn:
        wh = po.get("warehouse_id") or db._default_warehouse_id(conn)
        total_mat = 0
        for r in reqs:
            stock = conn.execute("SELECT COALESCE(quantity,0) FROM warehouse_stock WHERE warehouse_id=? AND product_id=?",
                                 (wh, r["product_id"])).fetchone()
            avail = stock[0] if stock else 0
            if avail < r["quantity"] and not allow_neg and not allow_insufficient:
                raise ValueError(f"Insufficient stock for {r['product_name']}")
            from db_stock_costing import get_unit_cost
            rate = get_unit_cost(conn, wh, r["product_id"])
            amt = r["quantity"] * rate
            total_mat += amt
            conn.execute(
                "INSERT INTO production_material_issues(production_order_id,product_id,quantity,unit_id,weight,rate,amount) VALUES(?,?,?,?,?,?,?)",
                (production_order_id, r["product_id"], r["quantity"], r.get("unit_id"), r.get("weight",0), rate, amt))
            db._adjust_warehouse_stock(conn, r["product_id"], wh, -r["quantity"])
            db._record_movement(conn, r["product_id"], wh, "out", r["quantity"], "production", production_order_id, po["document_no"], user_id)
            from db_stock_costing import inventory_role_for_product
            pt = conn.execute(
                "SELECT product_type FROM products WHERE id=?", (r["product_id"],)
            ).fetchone()
            inv_role = inventory_role_for_product(pt[0] if pt else "raw")
            # Finished components rare in BOM — treat as raw inventory head
            if inv_role == "fg_inv":
                inv_role = "raw_inv"
            post_gl(conn, po["order_date"], gl_account_code("wip"), amt, 0, "Material issue", "production", production_order_id, po["document_no"], user_id)
            post_gl(conn, po["order_date"], gl_account_code(inv_role), 0, amt, "Material issue", "production", production_order_id, po["document_no"], user_id)
        conn.execute(
            "UPDATE production_orders SET status='issued', modified_by=?, modified_at=? WHERE id=?",
            (user_id, now(), production_order_id),
        )
    _invalidate_production_stock_cache()
    return total_mat


def _invalidate_production_stock_cache():
    try:
        from db_cache import invalidate_stock
        invalidate_stock()
    except Exception:
        pass


def _apply_product_batch_delta(conn, batch_no, product_id, warehouse_id, delta_qty, user_id=None):
    """Adjust batch ledger qty; removes row when balance reaches ~0."""
    if not batch_no:
        return
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='product_batches'"
    ).fetchone():
        return
    delta_qty = float(delta_qty)
    row = conn.execute(
        "SELECT quantity FROM product_batches WHERE batch_no=? AND product_id=? AND warehouse_id=?",
        (batch_no, product_id, warehouse_id),
    ).fetchone()
    if row:
        new_q = float(row[0] or 0) + delta_qty
        if new_q <= 1e-9:
            conn.execute(
                "DELETE FROM product_batches WHERE batch_no=? AND product_id=? AND warehouse_id=?",
                (batch_no, product_id, warehouse_id),
            )
        else:
            conn.execute(
                "UPDATE product_batches SET quantity=? WHERE batch_no=? AND product_id=? AND warehouse_id=?",
                (new_q, batch_no, product_id, warehouse_id),
            )
    elif delta_qty > 1e-9:
        conn.execute(
            "INSERT INTO product_batches(batch_no,product_id,warehouse_id,quantity,mfg_date,created_by) "
            "VALUES(?,?,?,?,date('now'),?)",
            (batch_no, product_id, warehouse_id, delta_qty, user_id),
        )


def _clear_production_ledger(conn, production_order_id):
    """Remove GL and inventory movements tied to a production order (no stock qty change)."""
    for desc in ("Material issue", "FG receipt"):
        _delete_gl_production_phase(conn, production_order_id, desc)
    conn.execute(
        "DELETE FROM inventory_movements WHERE reference_type='production' AND reference_id=?",
        (production_order_id,),
    )


def _delete_gl_production_phase(conn, production_order_id, description):
    """Remove GL for one production step and reverse chart balances."""
    rows = conn.execute(
        """SELECT account_id, debit, credit FROM general_ledger
           WHERE reference_type='production' AND reference_id=? AND description=?""",
        (production_order_id, description),
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
        "DELETE FROM general_ledger WHERE reference_type='production' AND reference_id=? AND description=?",
        (production_order_id, description),
    )


def _production_fg_reversible_qty(conn, warehouse_id, product_id, batch_no, production_order_id):
    """Qty still attributable to this completion (batch balance or open production receipt)."""
    reversible = 0.0
    if batch_no and conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='product_batches'"
    ).fetchone():
        brow = conn.execute(
            "SELECT quantity FROM product_batches WHERE batch_no=? AND product_id=? AND warehouse_id=?",
            (batch_no, product_id, warehouse_id),
        ).fetchone()
        if brow is not None:
            reversible = max(reversible, float(brow[0] or 0))
    in_row = conn.execute(
        """SELECT COALESCE(SUM(quantity),0) FROM inventory_movements
           WHERE reference_type='production' AND reference_id=? AND product_id=? AND movement_type='in'""",
        (production_order_id, product_id),
    ).fetchone()
    reversible = max(reversible, float(in_row[0] if in_row else 0))
    return reversible


def reopen_rolled_back_production_to_draft(production_order_id, user_id=None):
    """Fix orders left as **issued** after QC rollback (pre-draft fix) — unissue and set draft."""
    po = get_production_order(production_order_id)
    if not po:
        raise ValueError("Production order not found.")
    status = (po.get("status") or "").lower()
    if status == "draft":
        return
    if status != "issued":
        raise ValueError(f"Order is **{status}** — only issued orders after QC rollback can be reopened to draft.")
    if "QC/completion rolled back" not in (po.get("notes") or ""):
        raise ValueError("This order was not reopened by QC rollback.")
    if po.get("receipts"):
        raise ValueError("Finished goods are still on this order — rollback QC completion first.")
    import database as db
    with db.get_connection() as conn:
        _unissue_production_materials(conn, production_order_id, po, user_id)
        conn.execute(
            """UPDATE production_orders SET status='draft', qc_status='Pending',
               modified_by=?, modified_at=? WHERE id=?""",
            (user_id, now(), production_order_id),
        )
    _invalidate_production_stock_cache()


def _unissue_production_materials(conn, production_order_id, po, user_id=None):
    """Reverse material issue — raw stock restored, movements & WIP GL cleared."""
    import database as db
    wh = po.get("warehouse_id") or db._default_warehouse_id(conn)
    doc_no = po.get("document_no") or ""
    issues = conn.execute(
        "SELECT product_id, quantity FROM production_material_issues WHERE production_order_id=?",
        (production_order_id,),
    ).fetchall()
    for row in issues:
        qty = float(row[1] or 0)
        if qty <= 0:
            continue
        db._adjust_warehouse_stock(conn, row[0], wh, qty)
        db._record_movement(
            conn, row[0], wh, "in", qty, "production", production_order_id,
            f"Material unissue: {doc_no}", user_id,
        )
    conn.execute(
        """DELETE FROM inventory_movements
           WHERE reference_type='production' AND reference_id=? AND movement_type='out'""",
        (production_order_id,),
    )
    conn.execute(
        "DELETE FROM production_material_issues WHERE production_order_id=?",
        (production_order_id,),
    )
    _delete_gl_production_phase(conn, production_order_id, "Material issue")


def rollback_production_completion(production_order_id, user_id=None, reason="", allow_force=False):
    """Undo QC completion / FG receipt — order returns to **draft** (materials un-issued) for Edit Draft."""
    import database as db
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("Reason is required to rollback production completion.")
    po = get_production_order(production_order_id)
    if not po:
        raise ValueError("Production order not found.")
    if (po.get("status") or "").lower() != "completed":
        raise ValueError(
            f"Only **completed** orders can be rolled back (this order is **{po.get('status')}**)."
        )
    actual_qty = float(po.get("actual_qty") or 0)
    if actual_qty <= 0:
        raise ValueError("No finished quantity recorded on this order.")
    receipts = po.get("receipts") or []
    receipt_qty = sum(float(r.get("quantity") or 0) for r in receipts)
    if receipt_qty <= 0:
        receipt_qty = actual_qty
    with db.get_connection() as conn:
        wh = po.get("warehouse_id") or db._default_warehouse_id(conn)
        fp_id = po["finished_product_id"]
        batch_no = po["batch_no"]
        allow_neg = get_setting("allow_negative_stock") == "1"
        reversible = _production_fg_reversible_qty(conn, wh, fp_id, batch_no, production_order_id)
        if reversible + 1e-9 < receipt_qty and not allow_neg and not allow_force:
            raise ValueError(
                f"Cannot rollback: only **{reversible:,.4f}** from batch **{batch_no}** / this production receipt "
                f"is still available (received **{receipt_qty:,.4f}**). "
                "Some quantity may already have been sold or transferred. "
                "Enable **negative stock** in settings, or tick **Confirm rollback** to reverse anyway."
            )
        db._adjust_warehouse_stock(conn, fp_id, wh, -receipt_qty)
        db._record_movement(
            conn, fp_id, wh, "out", receipt_qty, "production", production_order_id,
            f"FG rollback: {po.get('document_no', '')}", user_id,
        )
        conn.execute(
            """DELETE FROM inventory_movements
               WHERE reference_type='production' AND reference_id=?
                 AND product_id=? AND movement_type='in'""",
            (production_order_id, fp_id),
        )
        _apply_product_batch_delta(conn, batch_no, fp_id, wh, -receipt_qty, user_id)
        conn.execute(
            "DELETE FROM production_finished_receipts WHERE production_order_id=?",
            (production_order_id,),
        )
        _delete_gl_production_phase(conn, production_order_id, "FG receipt")
        _unissue_production_materials(conn, production_order_id, po, user_id)
        note = f"\nQC/completion rolled back: {reason}"
        conn.execute(
            """UPDATE production_orders SET status='draft', actual_qty=0, wastage_qty=0,
               actual_cost=0, cost_per_unit=0, qc_status='Pending',
               approved_by=NULL, approved_at=NULL,
               notes=COALESCE(notes,'') || ?, modified_by=?, modified_at=? WHERE id=?""",
            (note, user_id, now(), production_order_id),
        )
    _invalidate_production_stock_cache()
    try:
        from db_audit import log_event
        log_event(
            "production_orders", production_order_id, "rollback_completion",
            user_id=user_id, module="Production", document_no=po["document_no"],
            summary=f"Rolled back completion on {po['document_no']}",
            details={"reason": reason, "qty_reversed": receipt_qty},
        )
    except Exception:
        pass


def complete_production(production_order_id, actual_qty, wastage_qty, qc_status, user_id=None):
    import database as db
    po = get_production_order(production_order_id)
    if not po:
        raise ValueError("Production order not found.")
    if (po.get("status") or "").lower() != "issued":
        raise ValueError(
            f"Only **issued** orders can be completed (current status: **{po.get('status')}**). "
            "Issue materials first."
        )
    if not po.get("issues"):
        raise ValueError("Issue materials to production before completing.")
    if po.get("receipts"):
        raise ValueError("This order already has a finished-goods receipt — rollback before completing again.")
    actual_qty = float(actual_qty or 0)
    if actual_qty <= 0:
        raise ValueError("Actual output quantity must be greater than zero.")
    # DB CHECK: qc_status IN ('Pending','Passed','Failed')
    _qc_map = {
        "pending": "Pending", "passed": "Passed", "failed": "Failed",
        "Pending": "Pending", "Passed": "Passed", "Failed": "Failed",
    }
    qc_status = _qc_map.get(str(qc_status or "").strip(), None) or "Passed"
    with db.get_connection() as conn:
        wh = po.get("warehouse_id") or db._default_warehouse_id(conn)
        mat_cost = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM production_material_issues WHERE production_order_id=?",
            (production_order_id,),
        ).fetchone()[0]
        total_cost = (
            float(mat_cost or 0)
            + float(po.get("labour_cost") or 0)
            + float(po.get("utility_cost") or 0)
            + float(po.get("packing_cost") or 0)
            + float(po.get("overhead_cost") or 0)
        )
        cpu = total_cost / actual_qty if actual_qty else 0
        batch_no = po["batch_no"]
        conn.execute(
            "INSERT INTO production_finished_receipts(production_order_id,product_id,batch_no,quantity) VALUES(?,?,?,?)",
            (production_order_id, po["finished_product_id"], batch_no, actual_qty),
        )
        _apply_product_batch_delta(conn, batch_no, po["finished_product_id"], wh, actual_qty, user_id)
        # Blend FG warehouse average cost at production unit cost
        from db_stock_costing import apply_purchase_inbound_cost
        apply_purchase_inbound_cost(
            conn, wh, po["finished_product_id"], actual_qty, cpu, update_last_rate=True,
        )
        db._adjust_warehouse_stock(conn, po["finished_product_id"], wh, actual_qty)
        db._record_movement(
            conn, po["finished_product_id"], wh, "in", actual_qty, "production",
            production_order_id, po["document_no"], user_id,
        )
        post_gl(
            conn, po["order_date"], gl_account_code("fg_inv"), total_cost, 0, "FG receipt",
            "production", production_order_id, po["document_no"], user_id,
        )
        post_gl(
            conn, po["order_date"], gl_account_code("wip"), 0, total_cost, "FG receipt",
            "production", production_order_id, po["document_no"], user_id,
        )
        conn.execute(
            """UPDATE production_orders SET status='completed',actual_qty=?,wastage_qty=?,actual_cost=?,cost_per_unit=?,
               qc_status=?,approved_by=?,approved_at=?,modified_at=?,modified_by=? WHERE id=?""",
            (actual_qty, wastage_qty, total_cost, cpu, qc_status, user_id, now(), now(), user_id, production_order_id),
        )
    _invalidate_production_stock_cache()


def production_order_stock_check(production_order_id):
    """Compare warehouse qty deltas implied by movements vs material issues / FG receipts."""
    import database as db
    po = get_production_order(production_order_id)
    if not po:
        return {"ok": False, "messages": ["Order not found."]}
    messages = []
    wh = po.get("warehouse_id")
    with db.get_connection() as conn:
        if not wh:
            wh = db._default_warehouse_id(conn)
        for issue in po.get("issues") or []:
            pid = issue["product_id"]
            issued = float(issue.get("quantity") or 0)
            moved = conn.execute(
                """SELECT COALESCE(SUM(quantity),0) FROM inventory_movements
                   WHERE reference_type='production' AND reference_id=? AND product_id=?
                     AND movement_type='out'""",
                (production_order_id, pid),
            ).fetchone()[0]
            if abs(float(moved or 0) - issued) > 1e-6 and (po.get("status") or "") in ("issued", "completed"):
                messages.append(
                    f"Material {issue.get('product_name')}: issued {issued:,.4f} vs movement out {float(moved):,.4f}"
                )
        if (po.get("status") or "").lower() == "completed":
            fp_id = po["finished_product_id"]
            actual = float(po.get("actual_qty") or 0)
            moved_in = conn.execute(
                """SELECT COALESCE(SUM(quantity),0) FROM inventory_movements
                   WHERE reference_type='production' AND reference_id=? AND product_id=?
                     AND movement_type='in'""",
                (production_order_id, fp_id),
            ).fetchone()[0]
            net_in = float(moved_in or 0)
            receipt_sum = sum(float(r.get("quantity") or 0) for r in (po.get("receipts") or []))
            expect = receipt_sum or actual
            if expect and abs(net_in - expect) > 1e-6:
                messages.append(
                    f"FG expected {expect:,.4f} vs movement in {net_in:,.4f}"
                )
    return {"ok": not messages, "messages": messages}


# Quotation CRUD (generic doc pattern)
def _save_doc_header(conn, table, data, fields, doc_id=None, user_id=None):
    pass  # implemented inline below

def get_quotations():
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            "SELECT q.*, c.name AS customer_name FROM quotations q JOIN customers c ON q.customer_id=c.id ORDER BY q.quote_date DESC"
        ).fetchall())


def search_quotations(
    q=None, from_date=None, to_date=None, customer_id=None, status=None,
    page=1, page_size=50, export_all=False, **_ignored,
):
    from database import run_paginated_list
    where, params = ["1=1"], []
    if q:
        like = f"%{q.strip()}%"
        where.append("(q.document_no LIKE ? OR c.name LIKE ? OR c.code LIKE ? OR COALESCE(q.notes,'') LIKE ?)")
        params.extend([like, like, like, like])
    if from_date:
        where.append("q.quote_date >= ?"); params.append(from_date)
    if to_date:
        where.append("q.quote_date <= ?"); params.append(to_date)
    if customer_id:
        where.append("q.customer_id = ?"); params.append(customer_id)
    if status and status != "All":
        where.append("COALESCE(q.status,'draft') = ?"); params.append(status)
    return run_paginated_list(
        "quotations q JOIN customers c ON q.customer_id=c.id",
        "q.*, c.name AS customer_name, c.code AS customer_code",
        where, params, "q.quote_date DESC, q.id DESC", page, page_size, export_all,
        sum_exprs=["COALESCE(SUM(q.total),0)"],
    )

def get_quotation(qid):
    from database import get_connection, row_to_dict, rows_to_list
    with get_connection() as conn:
        h = row_to_dict(conn.execute(
            "SELECT q.*, c.name AS customer_name FROM quotations q JOIN customers c ON q.customer_id=c.id WHERE q.id=?",
            (qid,)).fetchone())
        if h:
            h["items"] = rows_to_list(conn.execute(
                """SELECT qi.*, p.name AS product_name, u.symbol AS unit FROM quotation_items qi
                   JOIN products p ON qi.product_id=p.id LEFT JOIN units_of_measure u ON qi.unit_id=u.id WHERE qi.quotation_id=?""",
                (qid,)).fetchall())
        return h

def save_quotation(data, lines, qid=None, user_id=None):
    from database import get_connection, ensure_document_no
    r = _doc_totals(data, lines)
    lines = r["lines"]
    subtotal = r["subtotal"]
    tax_total = r["total_tax"]
    total = r["total"]
    discount = r["discount_amt"]
    with get_connection() as conn:
        if qid:
            conn.execute("DELETE FROM quotation_items WHERE quotation_id=?", (qid,))
            conn.execute(
                "UPDATE quotations SET document_no=?,quote_date=?,customer_id=?,valid_until=?,subtotal=?,discount=?,tax_total=?,total=?,status=?,notes=?,modified_by=?,modified_at=? WHERE id=?",
                (data["document_no"], data["quote_date"], data["customer_id"], data.get("valid_until"), subtotal,
                 discount, tax_total, total, data.get("status","draft"), data.get("notes"), user_id, now(), qid))
        else:
            cur = conn.execute(
                "INSERT INTO quotations(document_no,quote_date,customer_id,valid_until,subtotal,discount,tax_total,total,status,notes,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (ensure_document_no("QT", data.get("document_no"), conn), data["quote_date"], data["customer_id"],
                 data.get("valid_until"), subtotal, discount, tax_total, total,
                 data.get("status","draft"), data.get("notes"), user_id))
            qid = cur.lastrowid
        for l in lines:
            conn.execute(
                "INSERT INTO quotation_items(quotation_id,product_id,quantity,unit_id,net_weight,rate,discount,tax_amount,amount) VALUES(?,?,?,?,?,?,?,?,?)",
                (qid, l["product_id"], l["quantity"], l.get("unit_id"), l.get("net_weight",0), l["rate"],
                 l.get("line_discount", 0), l.get("tax_amount",0), l["line_amount"]))
        return qid

def delete_quotation(qid, user_id=None):
    from database import get_connection
    with get_connection() as conn:
        conn.execute("DELETE FROM quotation_items WHERE quotation_id=?", (qid,))
        conn.execute("DELETE FROM quotations WHERE id=?", (qid,))


def get_quotations_for_conversion(customer_id=None):
    """Quotations available to convert to order or invoice."""
    from database import get_connection, rows_to_list
    q = """SELECT q.*, c.name AS customer_name FROM quotations q
           JOIN customers c ON q.customer_id=c.id
           WHERE COALESCE(q.status,'draft') NOT IN ('cancelled','closed','converted')
             AND NOT EXISTS (
                 SELECT 1 FROM sales_orders so WHERE so.quotation_id=q.id
             )
             AND NOT EXISTS (
                 SELECT 1 FROM sales_invoices si
                 WHERE si.quotation_id=q.id AND COALESCE(si.status,'draft') NOT IN ('cancelled','rejected')
             )"""
    p = []
    if customer_id:
        q += " AND q.customer_id=?"
        p.append(customer_id)
    q += " ORDER BY q.quote_date DESC, q.id DESC"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


def quotation_to_lines(qid):
    """Convert quotation items to order/invoice line dicts."""
    q = get_quotation(qid)
    if not q:
        raise ValueError("Quotation not found.")
    lines = []
    for item in q["items"]:
        qty = float(item["quantity"])
        rate = float(item["rate"])
        nw = float(item.get("net_weight") or 0)
        if nw <= 0:
            from database import get_connection
            with get_connection() as conn:
                pr = conn.execute(
                    "SELECT standard_weight FROM products WHERE id=?", (item["product_id"],)
                ).fetchone()
                sw = float(pr[0] or 0) if pr else 0
            nw = round(qty * sw, 3) if sw > 0 else qty
        lines.append({
            "product_id": item["product_id"],
            "item_id": item["product_id"],
            "quantity": qty,
            "rate": rate,
            "amount": round(qty * rate, 2),
            "net_weight": nw,
            "unit_id": item.get("unit_id"),
        })
    return lines, q


# Sales orders (use existing table)
def get_sales_orders_list():
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            """SELECT so.*, c.name AS customer_name
               FROM sales_orders so JOIN customers c ON so.customer_id=c.id
               ORDER BY CASE LOWER(COALESCE(so.status,'open'))
                            WHEN 'open' THEN 0
                            WHEN 'partial' THEN 1
                            WHEN 'closed' THEN 2
                            WHEN 'cancelled' THEN 3
                            WHEN 'canceled' THEN 3
                            ELSE 4
                        END,
                        so.order_date DESC, so.id DESC"""
        ).fetchall())


def search_sales_orders(
    q=None, from_date=None, to_date=None, customer_id=None, status=None,
    page=1, page_size=50, export_all=False, **_ignored,
):
    """List sales orders. Pending (open/partial / Active) stay visible even when a date period is set."""
    from database import run_paginated_list
    where, params = ["1=1"], []
    if q:
        like = f"%{q.strip()}%"
        where.append("(so.document_no LIKE ? OR c.name LIKE ? OR c.code LIKE ? OR COALESCE(so.notes,'') LIKE ?)")
        params.extend([like, like, like, like])
    if customer_id:
        where.append("so.customer_id = ?"); params.append(customer_id)

    # Status: "Pending" = open + partial (shown as Active / Partial in UI)
    st_raw = (status or "").strip()
    st_l = st_raw.lower() if st_raw and st_raw != "All" else None
    pending_sql = "LOWER(COALESCE(so.status,'open')) IN ('open','partial')"
    if st_l in ("pending", "active"):
        where.append(pending_sql)
        apply_date = False  # all pending regardless of date
    elif st_l:
        where.append("LOWER(COALESCE(so.status,'open')) = ?")
        params.append(st_l)
        # Filtering to a pending status alone → ignore dates
        apply_date = st_l not in ("open", "partial")
    else:
        apply_date = True

    if apply_date and (from_date or to_date):
        date_parts, date_params = [], []
        if from_date:
            date_parts.append("so.order_date >= ?")
            date_params.append(from_date)
        if to_date:
            date_parts.append("so.order_date <= ?")
            date_params.append(to_date)
        date_sql = " AND ".join(date_parts)
        if st_l is None:
            # Period filter + always include pending outside the period
            where.append(f"(({date_sql}) OR {pending_sql})")
            params.extend(date_params)
        else:
            where.append(f"({date_sql})")
            params.extend(date_params)

    return run_paginated_list(
        "sales_orders so JOIN customers c ON so.customer_id=c.id",
        "so.*, c.name AS customer_name, c.code AS customer_code, COALESCE(c.city, '') AS customer_city",
        where, params,
        """CASE LOWER(COALESCE(so.status,'open'))
               WHEN 'open' THEN 0
               WHEN 'partial' THEN 1
               WHEN 'closed' THEN 2
               WHEN 'cancelled' THEN 3
               WHEN 'canceled' THEN 3
               ELSE 4
           END,
           so.order_date DESC, so.id DESC""",
        page, page_size, export_all,
        sum_exprs=["COALESCE(SUM(so.total),0)"],
    )


def get_sales_order(so_id):
    from database import get_connection, row_to_dict, rows_to_list
    from product_rates_legacy import _implied_line_discount_pct
    with get_connection() as conn:
        _add_col(conn, "sales_order_items", "discount_pct", "REAL DEFAULT 0")
        header = row_to_dict(conn.execute(
            """SELECT so.*, c.name AS customer_name, c.code AS customer_code
               FROM sales_orders so JOIN customers c ON so.customer_id=c.id WHERE so.id=?""",
            (so_id,),
        ).fetchone())
        if not header:
            return None
        header["items"] = rows_to_list(conn.execute(
            """SELECT soi.*, p.code AS product_code, p.name AS product_name,
                      p.standard_weight, u.symbol AS unit
               FROM sales_order_items soi
               JOIN products p ON soi.product_id=p.id
               LEFT JOIN units_of_measure u ON p.unit_id=u.id
               WHERE soi.order_id=? ORDER BY soi.id""",
            (so_id,),
        ).fetchall())
        for li in header["items"]:
            qty = float(li.get("quantity") or 0)
            rate = float(li.get("rate") or 0)
            stored = float(li.get("discount_pct") or 0)
            if stored > 0.0001:
                li["discount_pct"] = stored
            else:
                li["discount_pct"] = _implied_line_discount_pct(
                    qty, rate, 0, li.get("amount"), 0,
                )
        return header


def get_sales_orders_for_invoice(customer_id=None):
    """Open/partial sales orders with quantity still to deliver.

    Partial orders remain selectable after the first invoice so remaining
    quantity can be billed on a later sale invoice.
    """
    from database import get_connection, rows_to_list
    q = """SELECT so.*, c.name AS customer_name, COALESCE(c.city, '') AS customer_city,
                  COALESCE(SUM(soi.quantity - COALESCE(soi.delivered_qty, 0)), 0) AS pending_qty
           FROM sales_orders so
           JOIN customers c ON so.customer_id=c.id
           JOIN sales_order_items soi ON soi.order_id=so.id
           WHERE so.status IN ('open', 'partial')
             AND soi.quantity > COALESCE(soi.delivered_qty, 0)"""
    p = []
    if customer_id:
        q += " AND so.customer_id=?"
        p.append(customer_id)
    q += " GROUP BY so.id HAVING pending_qty > 0 ORDER BY so.id DESC, so.order_date DESC"
    with get_connection() as conn:
        rows = rows_to_list(conn.execute(q, p).fetchall())
    try:
        from erp_core.dispatch_planning import resolve_dispatch_to
        for r in rows:
            town = (r.get("dispatch_town") or "").strip()
            r["dispatch_to"] = town or resolve_dispatch_to(r.get("notes"), r.get("customer_city"))
            if r["dispatch_to"] == "-":
                r["dispatch_to"] = ""
    except Exception:
        for r in rows:
            r["dispatch_to"] = (r.get("dispatch_town") or "").strip()
    return rows


def sales_order_invoice_lines(so_id):
    """Convert pending sales order lines to sales invoice line dicts."""
    order = get_sales_order(so_id)
    if not order:
        raise ValueError("Sales order not found.")
    lines = []
    for item in order["items"]:
        pending = round(float(item["quantity"]) - float(item.get("delivered_qty") or 0), 3)
        if pending <= 0:
            continue
        sw = float(item.get("standard_weight") or 0)
        net_wt = round(pending * sw, 3) if sw > 0 else pending
        rate = float(item["rate"])
        disc = float(item.get("discount_pct") or 0)
        amt = round(pending * rate * (1 - disc / 100.0), 2)
        lines.append({
            "item_id": item["product_id"],
            "product_id": item["product_id"],
            "quantity": pending,
            "rate": rate,
            "discount_pct": disc,
            "amount": amt,
            "line_discount": round(pending * rate - amt, 2) if disc else 0,
            "net_weight": net_wt,
        })
    return lines


def mark_quotation_converted(conn, quotation_id):
    if quotation_id:
        conn.execute(
            "UPDATE quotations SET status='converted', modified_at=? WHERE id=?",
            (now(), quotation_id),
        )


def reverse_sales_order_delivery(conn, order_id, invoice_id):
    """Undo sales order delivery reserved by an invoice (delete/reject/edit)."""
    if not order_id:
        return
    items = conn.execute(
        "SELECT product_id, quantity FROM sales_invoice_items WHERE invoice_id=?", (invoice_id,)
    ).fetchall()
    for row in items:
        conn.execute(
            """UPDATE sales_order_items SET delivered_qty=
               CASE WHEN COALESCE(delivered_qty,0) - ? < 0 THEN 0
                    ELSE COALESCE(delivered_qty,0) - ? END
               WHERE order_id=? AND product_id=?""",
            (float(row["quantity"]), float(row["quantity"]), order_id, row["product_id"]),
        )
    pending = conn.execute(
        """SELECT COUNT(*) FROM sales_order_items
           WHERE order_id=? AND quantity > COALESCE(delivered_qty, 0) + 0.0001""",
        (order_id,),
    ).fetchone()[0]
    any_delivered = conn.execute(
        """SELECT COUNT(*) FROM sales_order_items
           WHERE order_id=? AND COALESCE(delivered_qty,0) > 0.0001""",
        (order_id,),
    ).fetchone()[0]
    if pending == 0 and any_delivered:
        new_status = "closed"
    elif any_delivered:
        new_status = "partial"
    else:
        new_status = "open"
    conn.execute(
        "UPDATE sales_orders SET status=?, modified_at=? WHERE id=?",
        (new_status, now(), order_id),
    )


def apply_sales_order_delivery(conn, order_id, invoice_id):
    """Mark sales order lines delivered when invoice is saved."""
    if not order_id:
        return
    items = conn.execute(
        "SELECT product_id, quantity FROM sales_invoice_items WHERE invoice_id=?", (invoice_id,)
    ).fetchall()
    for row in items:
        conn.execute(
            """UPDATE sales_order_items SET delivered_qty=COALESCE(delivered_qty,0)+?
               WHERE order_id=? AND product_id=?""",
            (float(row["quantity"]), order_id, row["product_id"]),
        )
    pending = conn.execute(
        """SELECT COUNT(*) FROM sales_order_items
           WHERE order_id=? AND quantity > COALESCE(delivered_qty, 0) + 0.0001""",
        (order_id,),
    ).fetchone()[0]
    new_status = "closed" if pending == 0 else "partial"
    conn.execute(
        "UPDATE sales_orders SET status=?, modified_at=? WHERE id=?",
        (new_status, now(), order_id),
    )


def save_sales_order(data, lines, so_id=None, user_id=None, *, skip_portal_sync=False):
    from database import get_connection, ensure_document_no
    from erp_core.transaction_validation import validate_document, DOC_SALES
    from product_rates_legacy import _implied_line_discount_pct
    r = _doc_totals(data, lines)
    vr = validate_document(
        data, r["lines"], r, doc_kind=DOC_SALES, doc_label="Sales order",
        require_rate=True, stage="draft",
    )
    vr.raise_if_invalid()
    lines = r["lines"]
    with get_connection() as conn:
        _add_col(conn, "sales_order_items", "discount_pct", "REAL DEFAULT 0")
        _add_col(conn, "sales_orders", "dispatch_town", "TEXT")
        if so_id:
            conn.execute("DELETE FROM sales_order_items WHERE order_id=?", (so_id,))
            conn.execute(
                """UPDATE sales_orders SET document_no=?,customer_id=?,order_date=?,subtotal=?,discount=?,tax=?,total=?,
                   status=?,notes=?,dispatch_town=?,modified_by=?,modified_at=? WHERE id=?""",
                (data["document_no"], data["customer_id"], data["order_date"], r["subtotal"], r["discount_amt"],
                 r["total_tax"], r["total"], data.get("status","open"), data.get("notes"),
                 (data.get("dispatch_town") or "").strip() or None,
                 user_id, now(), so_id))
        else:
            cur = conn.execute(
                "INSERT INTO sales_orders(document_no,customer_id,order_date,warehouse_id,subtotal,discount,tax,total,status,notes,quotation_id,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (ensure_document_no("SO", data.get("document_no"), conn), data["customer_id"], data["order_date"],
                 data.get("warehouse_id"), r["subtotal"], r["discount_amt"], r["total_tax"], r["total"],
                 data.get("status","open"), data.get("notes"), data.get("quotation_id"), user_id, now()),
            )
            so_id = cur.lastrowid
            town = (data.get("dispatch_town") or "").strip()
            if town:
                conn.execute(
                    "UPDATE sales_orders SET dispatch_town=? WHERE id=?", (town, so_id),
                )
            # Link portal / channel when staff or portal creates the SO
            poid = data.get("portal_order_id")
            sch = (data.get("source_channel") or "").strip()
            if poid or sch:
                conn.execute(
                    """UPDATE sales_orders SET
                           portal_order_id=COALESCE(?, portal_order_id),
                           source_channel=COALESCE(NULLIF(?, ''), source_channel, 'internal')
                       WHERE id=?""",
                    (poid, sch, so_id),
                )
        for l in lines:
            pid = l.get("product_id") or l.get("item_id")
            qty = float(l.get("quantity") or 0)
            rate = float(l.get("rate") or 0)
            amt = float(l.get("line_amount", l.get("amount", 0)) or 0)
            disc = float(l.get("discount_pct") or 0)
            if disc <= 0.0001:
                disc = _implied_line_discount_pct(qty, rate, l.get("line_discount"), amt, 0)
            delivered = float(l.get("delivered_qty") or 0)
            conn.execute(
                "INSERT INTO sales_order_items(order_id,product_id,quantity,rate,amount,delivered_qty,discount_pct) VALUES(?,?,?,?,?,?,?)",
                (so_id, pid, qty, rate, amt, delivered, disc),
            )
        if data.get("quotation_id"):
            mark_quotation_converted(conn, data["quotation_id"])
    # Keep distributor My Orders in sync when staff edit a portal-linked SO
    if not skip_portal_sync:
        try:
            from erp_core.portal_service import sync_portal_order_from_sales_order
            sync_portal_order_from_sales_order(so_id, notify_user=True, user_id=user_id)
        except Exception:
            pass
    return so_id


def delete_sales_order(so_id, user_id=None):
    """Delete a sales order when no active invoice is linked."""
    from database import get_connection
    with get_connection() as conn:
        linked = conn.execute(
            """SELECT COUNT(*) FROM sales_invoices
               WHERE order_id=? AND COALESCE(status,'draft') NOT IN ('cancelled','rejected')""",
            (so_id,),
        ).fetchone()[0]
        if linked:
            raise ValueError("Cannot delete — a sales invoice is linked to this order.")
        delivered = conn.execute(
            """SELECT COALESCE(SUM(COALESCE(delivered_qty,0)),0) FROM sales_order_items WHERE order_id=?""",
            (so_id,),
        ).fetchone()[0]
        if float(delivered or 0) > 0.0001:
            raise ValueError("Cannot delete — quantity already delivered against this order.")
        conn.execute(
            "UPDATE portal_orders SET sales_order_id=NULL WHERE sales_order_id=?",
            (so_id,),
        )
        conn.execute(
            "UPDATE delivery_notes SET sales_order_id=NULL WHERE sales_order_id=?",
            (so_id,),
        )
        conn.execute(
            "UPDATE sales_orders SET portal_order_id=NULL WHERE id=?",
            (so_id,),
        )
        conn.execute("DELETE FROM sales_order_items WHERE order_id=?", (so_id,))
        conn.execute("DELETE FROM sales_orders WHERE id=?", (so_id,))
        return True


def abandon_sales_order_remaining(so_id, reason="", user_id=None):
    """Close an open/partial SO — remaining qty abandoned (no future invoice/dispatch)."""
    from database import get_connection
    reason = (reason or "").strip()
    with get_connection() as conn:
        hdr = conn.execute(
            "SELECT id, document_no, status, notes, portal_order_id FROM sales_orders WHERE id=?",
            (so_id,),
        ).fetchone()
        if not hdr:
            raise ValueError("Sales order not found.")
        st = (hdr["status"] or "open").lower()
        if st in ("cancelled", "canceled", "closed"):
            raise ValueError(f"Order is already {st}.")

        pending = conn.execute(
            """SELECT COUNT(*) FROM sales_order_items
               WHERE order_id=? AND quantity > COALESCE(delivered_qty, 0) + 0.0001""",
            (so_id,),
        ).fetchone()[0]
        if not pending:
            raise ValueError("No pending quantity on this order.")

        draft_inv = conn.execute(
            """SELECT COUNT(*) FROM sales_invoices
               WHERE order_id=? AND COALESCE(status,'draft') IN ('draft','pending_approval')""",
            (so_id,),
        ).fetchone()[0]
        if draft_inv:
            raise ValueError(
                "A draft or pending invoice is linked — cancel or post it before abandoning remaining qty."
            )

        conn.execute(
            "UPDATE sales_order_items SET delivered_qty=quantity WHERE order_id=?",
            (so_id,),
        )
        stamp = str(now())[:10]
        note_line = f"Remaining qty abandoned {stamp}"
        if reason:
            note_line += f": {reason}"
        old_notes = (hdr["notes"] or "").strip()
        new_notes = f"{old_notes}\n{note_line}".strip() if old_notes else note_line
        conn.execute(
            """UPDATE sales_orders SET status='closed', notes=?, modified_by=?, modified_at=?
               WHERE id=?""",
            (new_notes, user_id, now(), so_id),
        )
        try:
            from db_audit import log_event
            log_event(
                "sales_orders", so_id, "abandon_remaining", user_id=user_id, module="Sales",
                document_no=hdr["document_no"], summary=note_line,
            )
        except Exception:
            pass
    try:
        from erp_core.portal_service import sync_portal_order_from_sales_order
        sync_portal_order_from_sales_order(so_id, notify_user=True, user_id=user_id)
    except Exception:
        pass
    return so_id


# Delivery notes
def get_delivery_notes():
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            "SELECT d.*, c.name AS customer_name FROM delivery_notes d JOIN customers c ON d.customer_id=c.id ORDER BY d.dn_date DESC"
        ).fetchall())


def search_delivery_notes(
    q=None, from_date=None, to_date=None, customer_id=None, status=None,
    page=1, page_size=50, export_all=False, **_ignored,
):
    from database import run_paginated_list
    where, params = ["1=1"], []
    if q:
        like = f"%{q.strip()}%"
        where.append("(d.document_no LIKE ? OR c.name LIKE ? OR c.code LIKE ? OR COALESCE(d.notes,'') LIKE ?)")
        params.extend([like, like, like, like])
    if from_date:
        where.append("d.dn_date >= ?"); params.append(from_date)
    if to_date:
        where.append("d.dn_date <= ?"); params.append(to_date)
    if customer_id:
        where.append("d.customer_id = ?"); params.append(customer_id)
    if status and status != "All":
        where.append("COALESCE(d.status,'draft') = ?"); params.append(status)
    return run_paginated_list(
        "delivery_notes d JOIN customers c ON d.customer_id=c.id",
        "d.*, c.name AS customer_name, c.code AS customer_code",
        where, params, "d.dn_date DESC, d.id DESC", page, page_size, export_all,
        sum_exprs=["COALESCE(SUM(d.total),0)"],
    )

def save_delivery_note(data, lines, dn_id=None, user_id=None):
    from database import get_connection, ensure_document_no
    if data.get("tax_rate_id") or data.get("discount_pct"):
        r = _doc_totals(data, lines)
        lines = r["lines"]
        total = r["total"]
    else:
        total = sum(l.get("line_amount", l.get("amount", 0)) for l in lines)
    with get_connection() as conn:
        if dn_id:
            conn.execute("DELETE FROM delivery_note_items WHERE dn_id=?", (dn_id,))
            conn.execute(
                "UPDATE delivery_notes SET document_no=?,dn_date=?,customer_id=?,sales_order_id=?,warehouse_id=?,vehicle_id=?,driver_name=?,total=?,status=?,notes=?,modified_by=?,modified_at=? WHERE id=?",
                (data["document_no"], data["dn_date"], data["customer_id"], data.get("sales_order_id"),
                 data.get("warehouse_id"), data.get("vehicle_id"), data.get("driver_name"), total,
                 data.get("status","draft"), data.get("notes"), user_id, now(), dn_id))
        else:
            cur = conn.execute(
                "INSERT INTO delivery_notes(document_no,dn_date,customer_id,sales_order_id,warehouse_id,vehicle_id,driver_name,total,status,notes,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (ensure_document_no("DN", data.get("document_no"), conn), data["dn_date"], data["customer_id"],
                 data.get("sales_order_id"), data.get("warehouse_id"), data.get("vehicle_id"),
                 data.get("driver_name"), total, data.get("status","draft"), data.get("notes"), user_id))
            dn_id = cur.lastrowid
        for l in lines:
            amt = l.get("line_amount", l.get("amount", 0))
            conn.execute(
                "INSERT INTO delivery_note_items(dn_id,product_id,batch_id,quantity,unit_id,gross_weight,tare_weight,net_weight,rate,amount) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (dn_id, l["product_id"], l.get("batch_id"), l["quantity"], l.get("unit_id"),
                 l.get("gross_weight",0), l.get("tare_weight",0), l.get("net_weight",0), l["rate"], amt))
        return dn_id

def post_delivery_note(dn_id, user_id):
    import database as db
    from erp_core.period_lock import assert_period_open
    with db.get_connection() as conn:
        dn_row = conn.execute("SELECT * FROM delivery_notes WHERE id=?", (dn_id,)).fetchone()
        if dn_row:
            assert_period_open(str(dn_row["dn_date"]), user_id, action="post")
        dn = conn.execute("SELECT * FROM delivery_notes WHERE id=?", (dn_id,)).fetchone()
        if not dn or dn["status"] == "posted":
            return
        wh = dn["warehouse_id"] or db._default_warehouse_id(conn)
        items = conn.execute("SELECT * FROM delivery_note_items WHERE dn_id=?", (dn_id,)).fetchall()
        allow_neg = get_setting("allow_negative_stock") == "1"
        for it in items:
            stock = conn.execute("SELECT COALESCE(quantity,0) FROM warehouse_stock WHERE warehouse_id=? AND product_id=?",
                                 (wh, it["product_id"])).fetchone()
            if (stock[0] if stock else 0) < it["quantity"] and not allow_neg:
                raise ValueError("Insufficient stock for delivery")
            db._adjust_warehouse_stock(conn, it["product_id"], wh, -it["quantity"])
            db._record_movement(conn, it["product_id"], wh, "out", it["quantity"], "delivery_note", dn_id, dn["document_no"], user_id)
        conn.execute("UPDATE delivery_notes SET status='posted',posted_by=?,posted_at=? WHERE id=?", (user_id, now(), dn_id))


# Purchase requisitions, PO, GRN - similar patterns
def get_purchase_requisitions():
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        return rows_to_list(conn.execute("SELECT * FROM purchase_requisitions ORDER BY req_date DESC").fetchall())


def search_purchase_requisitions(
    q=None, from_date=None, to_date=None, status=None,
    page=1, page_size=50, export_all=False, **_ignored,
):
    from database import run_paginated_list
    where, params = ["1=1"], []
    if q:
        like = f"%{q.strip()}%"
        where.append("(document_no LIKE ? OR COALESCE(notes,'') LIKE ?)")
        params.extend([like, like])
    if from_date:
        where.append("req_date >= ?"); params.append(from_date)
    if to_date:
        where.append("req_date <= ?"); params.append(to_date)
    if status and status != "All":
        where.append("COALESCE(status,'draft') = ?"); params.append(status)
    return run_paginated_list(
        "purchase_requisitions",
        "*",
        where, params, "req_date DESC, id DESC", page, page_size, export_all,
        sum_exprs=["COALESCE(SUM(subtotal),0)"],
    )

def save_purchase_requisition(data, lines, rid=None, user_id=None):
    from database import get_connection, ensure_document_no
    subtotal = sum(l.get("amount",0) for l in lines)
    with get_connection() as conn:
        if rid:
            conn.execute("DELETE FROM purchase_requisition_items WHERE requisition_id=?", (rid,))
            conn.execute("UPDATE purchase_requisitions SET document_no=?,req_date=?,department_id=?,subtotal=?,status=?,notes=?,modified_by=?,modified_at=? WHERE id=?",
                         (data["document_no"], data["req_date"], data.get("department_id"), subtotal, data.get("status","draft"), data.get("notes"), user_id, now(), rid))
        else:
            cur = conn.execute("INSERT INTO purchase_requisitions(document_no,req_date,department_id,subtotal,status,notes,created_by) VALUES(?,?,?,?,?,?,?)",
                               (ensure_document_no("PRQ", data.get("document_no"), conn), data["req_date"], data.get("department_id"), subtotal, data.get("status","draft"), data.get("notes"), user_id))
            rid = cur.lastrowid
        for l in lines:
            conn.execute("INSERT INTO purchase_requisition_items(requisition_id,product_id,quantity,unit_id,estimated_rate,amount) VALUES(?,?,?,?,?,?)",
                         (rid, l["product_id"], l["quantity"], l.get("unit_id"), l.get("estimated_rate",0), l.get("amount",0)))
        return rid

def get_purchase_orders_list():
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            "SELECT po.*, s.name AS supplier_name FROM purchase_orders po JOIN suppliers s ON po.supplier_id=s.id ORDER BY po.order_date DESC"
        ).fetchall())


def search_purchase_orders(
    q=None, from_date=None, to_date=None, supplier_id=None, status=None,
    page=1, page_size=50, export_all=False, **_ignored,
):
    """List purchase orders. Pending (open/partial) stay visible even when a date period is set."""
    from database import run_paginated_list
    where, params = ["1=1"], []
    if q:
        like = f"%{q.strip()}%"
        where.append("(po.document_no LIKE ? OR s.name LIKE ? OR s.code LIKE ? OR COALESCE(po.notes,'') LIKE ?)")
        params.extend([like, like, like, like])
    if supplier_id:
        where.append("po.supplier_id = ?"); params.append(supplier_id)

    st_raw = (status or "").strip()
    st_l = st_raw.lower() if st_raw and st_raw != "All" else None
    pending_sql = "LOWER(COALESCE(po.status,'open')) IN ('open','partial')"
    if st_l in ("pending", "active"):
        where.append(pending_sql)
        apply_date = False
    elif st_l:
        where.append("LOWER(COALESCE(po.status,'open')) = ?")
        params.append(st_l)
        apply_date = st_l not in ("open", "partial")
    else:
        apply_date = True

    if apply_date and (from_date or to_date):
        date_parts, date_params = [], []
        if from_date:
            date_parts.append("po.order_date >= ?")
            date_params.append(from_date)
        if to_date:
            date_parts.append("po.order_date <= ?")
            date_params.append(to_date)
        date_sql = " AND ".join(date_parts)
        if st_l is None:
            where.append(f"(({date_sql}) OR {pending_sql})")
            params.extend(date_params)
        else:
            where.append(f"({date_sql})")
            params.extend(date_params)

    pending_expr = """COALESCE((
        SELECT SUM(poi.quantity - COALESCE(poi.received_qty, 0))
        FROM purchase_order_items poi
        WHERE poi.order_id = po.id
    ), 0)"""
    return run_paginated_list(
        "purchase_orders po JOIN suppliers s ON po.supplier_id=s.id",
        f"po.*, s.name AS supplier_name, s.code AS supplier_code, {pending_expr} AS pending_qty",
        where, params,
        """CASE LOWER(COALESCE(po.status,'open'))
               WHEN 'open' THEN 0
               WHEN 'partial' THEN 1
               WHEN 'closed' THEN 2
               WHEN 'cancelled' THEN 3
               WHEN 'canceled' THEN 3
               ELSE 4
           END,
           po.order_date DESC, po.id DESC""",
        page, page_size, export_all,
        sum_exprs=["COALESCE(SUM(po.total),0)"],
    )


def get_purchase_order(po_id):
    from database import get_connection, row_to_dict, rows_to_list
    with get_connection() as conn:
        header = row_to_dict(conn.execute(
            """SELECT po.*, s.name AS supplier_name, s.code AS supplier_code
               FROM purchase_orders po JOIN suppliers s ON po.supplier_id=s.id WHERE po.id=?""",
            (po_id,),
        ).fetchone())
        if not header:
            return None
        header["items"] = rows_to_list(conn.execute(
            """SELECT poi.*, p.code AS product_code, p.name AS product_name,
                      p.standard_weight, u.symbol AS unit
               FROM purchase_order_items poi
               JOIN products p ON poi.product_id=p.id
               LEFT JOIN units_of_measure u ON p.unit_id=u.id
               WHERE poi.order_id=? ORDER BY poi.id""",
            (po_id,),
        ).fetchall())
        pending_total = 0.0
        for li in header["items"]:
            ordered = float(li.get("quantity") or 0)
            received = float(li.get("received_qty") or 0)
            pending = round(max(ordered - received, 0), 3)
            li["ordered_qty"] = ordered
            li["received_qty"] = received
            li["pending_qty"] = pending
            pending_total += pending
        header["pending_qty"] = round(pending_total, 3)
        return header


def get_purchase_orders_for_invoice(supplier_id=None):
    """Open/partial purchase orders with quantity still to receive."""
    from database import get_connection, rows_to_list
    q = """SELECT po.*, s.name AS supplier_name,
                  COALESCE(SUM(poi.quantity - COALESCE(poi.received_qty, 0)), 0) AS pending_qty
           FROM purchase_orders po
           JOIN suppliers s ON po.supplier_id=s.id
           JOIN purchase_order_items poi ON poi.order_id=po.id
           WHERE po.status IN ('open', 'partial')
             AND poi.quantity > COALESCE(poi.received_qty, 0)"""
    p = []
    if supplier_id:
        q += " AND po.supplier_id=?"
        p.append(supplier_id)
    q += " GROUP BY po.id HAVING pending_qty > 0 ORDER BY po.order_date DESC, po.id DESC"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


def purchase_order_invoice_lines(po_id):
    """Convert pending PO lines to purchase invoice line dicts."""
    order = get_purchase_order(po_id)
    if not order:
        raise ValueError("Purchase order not found.")
    lines = []
    for item in order["items"]:
        pending = round(float(item["quantity"]) - float(item.get("received_qty") or 0), 3)
        if pending <= 0:
            continue
        sw = float(item.get("standard_weight") or 0)
        net_wt = round(pending * sw, 3) if sw > 0 else pending
        rate = float(item["rate"])
        lines.append({
            "item_id": item["product_id"],
            "product_id": item["product_id"],
            "quantity": pending,
            "rate": rate,
            "amount": round(pending * rate, 2),
            "net_weight": net_wt,
        })
    return lines


def _refresh_purchase_order_status(conn, order_id):
    """Set PO status from line received vs ordered quantities."""
    rows = conn.execute(
        """SELECT quantity, COALESCE(received_qty, 0) AS received_qty
           FROM purchase_order_items WHERE order_id=?""",
        (order_id,),
    ).fetchall()
    if not rows:
        return
    any_received = any(float(r["received_qty"]) > 0.0001 for r in rows)
    any_pending = any(
        float(r["quantity"]) > float(r["received_qty"]) + 0.0001 for r in rows
    )
    if any_pending:
        new_status = "partial"
    elif any_received:
        new_status = "closed"
    else:
        new_status = "open"
    conn.execute(
        "UPDATE purchase_orders SET status=?, modified_at=? WHERE id=?",
        (new_status, now(), order_id),
    )


def _apply_purchase_order_receipt_items(conn, order_id, items):
    """Increase received_qty on PO lines (capped at ordered quantity)."""
    if not order_id or not items:
        return
    for row in items:
        qty = float(row["quantity"] if isinstance(row, dict) else row[1])
        pid = row["product_id"] if isinstance(row, dict) else row[0]
        conn.execute(
            """UPDATE purchase_order_items SET received_qty=
               CASE WHEN COALESCE(received_qty,0) + ? > quantity THEN quantity
                    ELSE COALESCE(received_qty,0) + ? END
               WHERE order_id=? AND product_id=?""",
            (qty, qty, order_id, pid),
        )


def _reverse_purchase_order_receipt_items(conn, order_id, items):
    """Decrease received_qty on PO lines (floored at zero)."""
    if not order_id or not items:
        return
    for row in items:
        qty = float(row["quantity"] if isinstance(row, dict) else row[1])
        pid = row["product_id"] if isinstance(row, dict) else row[0]
        conn.execute(
            """UPDATE purchase_order_items SET received_qty=
               CASE WHEN COALESCE(received_qty,0) - ? < 0 THEN 0
                    ELSE COALESCE(received_qty,0) - ? END
               WHERE order_id=? AND product_id=?""",
            (qty, qty, order_id, pid),
        )


def reverse_purchase_order_delivery(conn, order_id, invoice_id):
    """Undo PO received qty reserved by a purchase invoice."""
    if not order_id:
        return
    items = conn.execute(
        "SELECT product_id, quantity FROM purchase_invoice_items WHERE invoice_id=?", (invoice_id,)
    ).fetchall()
    _reverse_purchase_order_receipt_items(conn, order_id, items)
    _refresh_purchase_order_status(conn, order_id)


def apply_purchase_order_delivery(conn, order_id, invoice_id):
    """Mark PO lines as received from purchase invoice quantities."""
    if not order_id:
        return
    items = conn.execute(
        "SELECT product_id, quantity FROM purchase_invoice_items WHERE invoice_id=?", (invoice_id,)
    ).fetchall()
    _apply_purchase_order_receipt_items(conn, order_id, items)
    _refresh_purchase_order_status(conn, order_id)


def get_purchase_requisition(req_id):
    from database import get_connection, row_to_dict, rows_to_list
    with get_connection() as conn:
        h = row_to_dict(conn.execute("SELECT * FROM purchase_requisitions WHERE id=?", (req_id,)).fetchone())
        if h:
            h["items"] = rows_to_list(conn.execute(
                """SELECT pri.*, p.name AS product_name, p.code AS product_code
                   FROM purchase_requisition_items pri
                   JOIN products p ON pri.product_id=p.id WHERE pri.requisition_id=?""",
                (req_id,),
            ).fetchall())
        return h


def get_purchase_requisitions_for_conversion():
    from database import get_connection, rows_to_list
    q = """SELECT pr.* FROM purchase_requisitions pr
           WHERE COALESCE(pr.status,'draft') NOT IN ('cancelled','closed','converted')
             AND NOT EXISTS (SELECT 1 FROM purchase_orders po WHERE po.requisition_id=pr.id)
           ORDER BY pr.req_date DESC, pr.id DESC"""
    with get_connection() as conn:
        return rows_to_list(conn.execute(q).fetchall())


def requisition_to_po_lines(req_id):
    req = get_purchase_requisition(req_id)
    if not req:
        raise ValueError("Purchase requisition not found.")
    lines = []
    for item in req["items"]:
        qty = float(item["quantity"])
        rate = float(item.get("estimated_rate") or item.get("rate") or 0)
        lines.append({
            "product_id": item["product_id"],
            "quantity": qty,
            "rate": rate,
            "amount": round(qty * rate, 2),
            "net_weight": qty,
        })
    return lines, req


def mark_requisition_converted(conn, requisition_id):
    if requisition_id:
        conn.execute(
            "UPDATE purchase_requisitions SET status='converted', modified_at=? WHERE id=?",
            (now(), requisition_id),
        )

def save_purchase_order(data, lines, po_id=None, user_id=None):
    from database import get_connection, ensure_document_no
    from erp_core.transaction_validation import validate_document, DOC_PURCHASE
    r = _doc_totals(data, lines)
    vr = validate_document(
        data, r["lines"], r, doc_kind=DOC_PURCHASE, doc_label="Purchase order",
        require_rate=True, stage="draft",
    )
    vr.raise_if_invalid()
    lines = r["lines"]
    with get_connection() as conn:
        if po_id:
            conn.execute("DELETE FROM purchase_order_items WHERE order_id=?", (po_id,))
            conn.execute("UPDATE purchase_orders SET document_no=?,supplier_id=?,order_date=?,subtotal=?,discount=?,tax=?,total=?,status=?,notes=?,requisition_id=COALESCE(?,requisition_id),modified_by=?,modified_at=? WHERE id=?",
                         (data["document_no"], data["supplier_id"], data["order_date"], r["subtotal"], r["discount_amt"],
                          r["total_tax"], r["total"], data.get("status","open"), data.get("notes"), data.get("requisition_id"), user_id, now(), po_id))
        else:
            cur = conn.execute(
                "INSERT INTO purchase_orders(document_no,supplier_id,order_date,warehouse_id,subtotal,discount,tax,total,status,notes,requisition_id,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (ensure_document_no("PO", data.get("document_no"), conn), data["supplier_id"], data["order_date"],
                 data.get("warehouse_id"), r["subtotal"], r["discount_amt"], r["total_tax"], r["total"],
                 data.get("status","open"), data.get("notes"), data.get("requisition_id"), user_id, now()),
            )
            po_id = cur.lastrowid
        for l in lines:
            qty = float(l.get("quantity") or 0)
            received = min(float(l.get("received_qty") or 0), qty)
            conn.execute(
                "INSERT INTO purchase_order_items(order_id,product_id,quantity,rate,amount,received_qty) VALUES(?,?,?,?,?,?)",
                (po_id, l["product_id"], qty, l["rate"], l["line_amount"], received),
            )
        if po_id:
            st = (data.get("status") or "open").lower()
            if st != "cancelled":
                _refresh_purchase_order_status(conn, po_id)
        if data.get("requisition_id"):
            mark_requisition_converted(conn, data["requisition_id"])
        return po_id


def delete_purchase_order(po_id, user_id=None):
    """Delete a purchase order when nothing has been received against it."""
    from database import get_connection
    with get_connection() as conn:
        linked = conn.execute(
            """SELECT COUNT(*) FROM purchase_invoices
               WHERE order_id=? AND COALESCE(status,'draft') NOT IN ('cancelled','rejected')""",
            (po_id,),
        ).fetchone()[0]
        if linked:
            raise ValueError("Cannot delete — a purchase invoice is linked to this order.")
        grn_linked = conn.execute(
            """SELECT COUNT(*) FROM goods_receipt_notes
               WHERE purchase_order_id=? AND COALESCE(status,'draft') != 'cancelled'""",
            (po_id,),
        ).fetchone()[0]
        if grn_linked:
            raise ValueError("Cannot delete — a GRN is linked to this order.")
        received = conn.execute(
            """SELECT COALESCE(SUM(COALESCE(received_qty,0)),0) FROM purchase_order_items WHERE order_id=?""",
            (po_id,),
        ).fetchone()[0]
        if float(received or 0) > 0.0001:
            raise ValueError("Cannot delete — quantity already received against this order.")
        conn.execute("DELETE FROM purchase_order_items WHERE order_id=?", (po_id,))
        conn.execute("DELETE FROM purchase_orders WHERE id=?", (po_id,))
        return True


def get_grns():
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            "SELECT g.*, s.name AS supplier_name FROM goods_receipt_notes g JOIN suppliers s ON g.supplier_id=s.id ORDER BY g.grn_date DESC"
        ).fetchall())


def search_grns(
    q=None, from_date=None, to_date=None, supplier_id=None, status=None,
    page=1, page_size=50, export_all=False, **_ignored,
):
    from database import run_paginated_list
    where, params = ["1=1"], []
    if q:
        like = f"%{q.strip()}%"
        where.append("(g.document_no LIKE ? OR s.name LIKE ? OR s.code LIKE ? OR COALESCE(g.notes,'') LIKE ?)")
        params.extend([like, like, like, like])
    if from_date:
        where.append("g.grn_date >= ?"); params.append(from_date)
    if to_date:
        where.append("g.grn_date <= ?"); params.append(to_date)
    if supplier_id:
        where.append("g.supplier_id = ?"); params.append(supplier_id)
    if status and status != "All":
        where.append("COALESCE(g.status,'draft') = ?"); params.append(status)
    return run_paginated_list(
        "goods_receipt_notes g JOIN suppliers s ON g.supplier_id=s.id",
        "g.*, s.name AS supplier_name, s.code AS supplier_code",
        where, params, "g.grn_date DESC, g.id DESC", page, page_size, export_all,
        sum_exprs=["COALESCE(SUM(g.total),0)"],
    )

def save_grn(data, lines, grn_id=None, user_id=None):
    from database import get_connection, ensure_document_no
    from erp_core.transaction_validation import validate_document, DOC_PURCHASE
    r = _doc_totals(data, lines)
    vr = validate_document(
        data, r["lines"], r, doc_kind=DOC_PURCHASE, doc_label="GRN",
        require_rate=True, stage="draft",
    )
    vr.raise_if_invalid()
    lines = r["lines"]
    subtotal = r["subtotal"]
    tax_total = r["total_tax"]
    total = r["total"]
    with get_connection() as conn:
        if grn_id:
            conn.execute("DELETE FROM grn_items WHERE grn_id=?", (grn_id,))
            conn.execute("UPDATE goods_receipt_notes SET document_no=?,grn_date=?,supplier_id=?,purchase_order_id=?,warehouse_id=?,weight_slip_id=?,subtotal=?,tax_total=?,total=?,status=?,notes=?,modified_by=?,modified_at=? WHERE id=?",
                         (data["document_no"], data["grn_date"], data["supplier_id"], data.get("purchase_order_id"), data.get("warehouse_id"), data.get("weight_slip_id"), subtotal, tax_total, total, data.get("status","draft"), data.get("notes"), user_id, now(), grn_id))
        else:
            cur = conn.execute("INSERT INTO goods_receipt_notes(document_no,grn_date,supplier_id,purchase_order_id,warehouse_id,weight_slip_id,subtotal,tax_total,total,status,notes,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                               (ensure_document_no("GRN", data.get("document_no"), conn), data["grn_date"], data["supplier_id"], data.get("purchase_order_id"), data.get("warehouse_id"), data.get("weight_slip_id"), subtotal, tax_total, total, data.get("status","draft"), data.get("notes"), user_id))
            grn_id = cur.lastrowid
        for l in lines:
            conn.execute("INSERT INTO grn_items(grn_id,product_id,batch_no,expiry_date,quantity,unit_id,gross_weight,tare_weight,net_weight,rate,tax_amount,amount) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                         (grn_id, l["product_id"], l.get("batch_no"), l.get("expiry_date"), l["quantity"], l.get("unit_id"),
                          l.get("gross_weight",0), l.get("tare_weight",0), l.get("net_weight",0), l["rate"], l.get("tax_amount",0), l["line_amount"]))
        return grn_id

def post_grn(grn_id, user_id):
    import database as db
    from erp_core.period_lock import assert_period_open
    with db.get_connection() as conn:
        g = conn.execute("SELECT * FROM goods_receipt_notes WHERE id=?", (grn_id,)).fetchone()
        if g:
            assert_period_open(str(g["grn_date"]), user_id, action="post")
        if not g or g["status"] == "posted":
            return
        wh = g["warehouse_id"] or db._default_warehouse_id(conn)
        from db_stock_costing import apply_purchase_inbound_cost
        for it in conn.execute("SELECT * FROM grn_items WHERE grn_id=?", (grn_id,)).fetchall():
            qty = float(it["quantity"] or 0)
            rate = float(it["rate"] or 0)
            if rate <= 0:
                pp = conn.execute(
                    "SELECT COALESCE(purchase_price,0) FROM products WHERE id=?", (it["product_id"],)
                ).fetchone()
                rate = float(pp[0] if pp else 0)
            apply_purchase_inbound_cost(conn, wh, it["product_id"], qty, rate)
            db._adjust_warehouse_stock(conn, it["product_id"], wh, qty)
            if it["batch_no"]:
                conn.execute("INSERT OR REPLACE INTO product_batches(batch_no,product_id,warehouse_id,quantity,expiry_date,created_by) VALUES(?,?,?,?,?,?)",
                             (it["batch_no"], it["product_id"], wh, qty, it.get("expiry_date"), user_id))
            db._record_movement(conn, it["product_id"], wh, "in", qty, "grn", grn_id, g["document_no"], user_id)
        po_id = g["purchase_order_id"]
        if po_id:
            grn_lines = conn.execute(
                "SELECT product_id, quantity FROM grn_items WHERE grn_id=?", (grn_id,)
            ).fetchall()
            _apply_purchase_order_receipt_items(conn, po_id, grn_lines)
            _refresh_purchase_order_status(conn, po_id)
        conn.execute("UPDATE goods_receipt_notes SET status='posted',posted_by=?,posted_at=? WHERE id=?", (user_id, now(), grn_id))


# Journal vouchers
def get_journal_vouchers():
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        return rows_to_list(conn.execute("SELECT * FROM journal_vouchers ORDER BY voucher_date DESC").fetchall())


def search_journal_vouchers(q=None, page=1, page_size=50, export_all=False):
    """Paginated journal voucher search for enterprise search / document hub."""
    from database import get_connection, rows_to_list

    page = max(1, int(page or 1))
    page_size = min(200, max(5, int(page_size or 50)))
    where = ["1=1"]
    params: list = []
    if q:
        like = f"%{q.strip()}%"
        where.append("(document_no LIKE ? OR COALESCE(description,'') LIKE ?)")
        params.extend([like, like])
    clause = " AND ".join(where)
    with get_connection() as conn:
        total = int(conn.execute(
            f"SELECT COUNT(*) FROM journal_vouchers WHERE {clause}", params,
        ).fetchone()[0])
        if export_all:
            rows = rows_to_list(conn.execute(
                f"SELECT * FROM journal_vouchers WHERE {clause} ORDER BY voucher_date DESC, id DESC",
                params,
            ).fetchall())
            return rows
        offset = (page - 1) * page_size
        rows = rows_to_list(conn.execute(
            f"""SELECT * FROM journal_vouchers WHERE {clause}
                ORDER BY voucher_date DESC, id DESC
                LIMIT ? OFFSET ?""",
            [*params, page_size, offset],
        ).fetchall())
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


def get_journal_voucher(vid):
    from database import get_connection, row_to_dict, rows_to_list
    with get_connection() as conn:
        h = row_to_dict(conn.execute("SELECT * FROM journal_vouchers WHERE id=?", (vid,)).fetchone())
        if h:
            h["lines"] = rows_to_list(conn.execute(
                """SELECT jvl.*, a.code AS account_code, a.name AS account_name FROM journal_voucher_lines jvl
                   JOIN chart_of_accounts a ON jvl.account_id=a.id WHERE jvl.voucher_id=?""", (vid,)).fetchall())
        return h

def save_journal_voucher(data, lines, vid=None, user_id=None):
    from database import get_connection, ensure_document_no
    cleaned = []
    for i, l in enumerate(lines or []):
        dr = float(l.get("debit") or 0)
        cr = float(l.get("credit") or 0)
        if dr > 0.0005 and cr > 0.0005:
            raise ValueError(
                f"Line {i + 1}: enter either Debit or Credit, not both "
                f"(Dr {dr:,.2f} / Cr {cr:,.2f})."
            )
        if abs(dr) < 0.0005 and abs(cr) < 0.0005:
            continue
        row = dict(l)
        row["debit"] = dr if dr > 0.0005 else 0.0
        row["credit"] = cr if cr > 0.0005 else 0.0
        cleaned.append(row)
    lines = cleaned
    td = sum(l.get("debit", 0) for l in lines)
    tc = sum(l.get("credit", 0) for l in lines)
    if abs(td - tc) > 0.01:
        raise ValueError("Debit and credit must balance")
    if not lines:
        raise ValueError("Add at least one journal line with Debit or Credit.")
    with get_connection() as conn:
        if vid:
            conn.execute("DELETE FROM journal_voucher_lines WHERE voucher_id=?", (vid,))
            conn.execute("UPDATE journal_vouchers SET document_no=?,voucher_date=?,description=?,total_debit=?,total_credit=?,status=?,modified_by=?,modified_at=? WHERE id=?",
                         (data["document_no"], data["voucher_date"], data.get("description"), td, tc, data.get("status","draft"), user_id, now(), vid))
        else:
            cur = conn.execute(
                "INSERT INTO journal_vouchers(document_no,voucher_date,description,total_debit,total_credit,status,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (ensure_document_no("JV", data.get("document_no"), conn), data["voucher_date"], data.get("description"), td, tc, data.get("status","draft"), user_id, now()),
            )
            vid = cur.lastrowid
        for l in lines:
            line_desc = (l.get("description") or "").strip() or (data.get("description") or "").strip() or None
            conn.execute(
                "INSERT INTO journal_voucher_lines(voucher_id,account_id,description,debit,credit) VALUES(?,?,?,?,?)",
                (vid, l["account_id"], line_desc, l.get("debit", 0), l.get("credit", 0)),
            )
        return vid

def post_journal_voucher(vid, user_id):
    from database import get_connection
    from erp_core.period_lock import assert_period_open
    jv = get_journal_voucher(vid)
    if not jv or jv["status"] == "posted":
        return
    assert_period_open(str(jv["voucher_date"]), user_id, action="post")
    with get_connection() as conn:
        for l in jv["lines"]:
            acode = conn.execute("SELECT code FROM chart_of_accounts WHERE id=?", (l["account_id"],)).fetchone()[0]
            post_gl(conn, jv["voucher_date"], acode, l.get("debit",0), l.get("credit",0), l.get("description") or jv.get("description"),
                    "journal", vid, jv["document_no"], user_id, vid)
            _apply_journal_line_to_party_balance(
                conn, l["account_id"], l.get("debit", 0), l.get("credit", 0), reverse=False,
            )
        conn.execute("UPDATE journal_vouchers SET status='posted',posted_by=?,posted_at=? WHERE id=?", (user_id, now(), vid))


def _apply_journal_line_to_party_balance(conn, account_id, debit, credit, *, reverse=False):
    """When JV hits a COA account whose code = customer/supplier code, update party balance."""
    if not account_id:
        return
    row = conn.execute("SELECT code FROM chart_of_accounts WHERE id=?", (account_id,)).fetchone()
    if not row or not (row["code"] or "").strip():
        return
    code = str(row["code"]).strip()
    delta = (float(debit or 0) - float(credit or 0)) * (-1 if reverse else 1)
    if abs(delta) < 0.0005:
        return
    cust = conn.execute("SELECT id FROM customers WHERE code=?", (code,)).fetchone()
    if cust:
        conn.execute(
            "UPDATE customers SET current_balance=current_balance+?, modified_at=? WHERE id=?",
            (delta, now(), cust["id"]),
        )
        return
    sup = conn.execute("SELECT id FROM suppliers WHERE code=?", (code,)).fetchone()
    if sup:
        conn.execute(
            "UPDATE suppliers SET current_balance=current_balance+?, modified_at=? WHERE id=?",
            (delta, now(), sup["id"]),
        )


def _delete_gl_reference(conn, ref_type, ref_id=None, ref_no=None):
    """Remove GL rows and reverse chart_of_accounts balances."""
    q = "SELECT id, account_id, debit, credit FROM general_ledger WHERE reference_type=?"
    params: list = [ref_type]
    if ref_id is not None:
        q += " AND reference_id=?"
        params.append(ref_id)
    if ref_no is not None:
        q += " AND reference_no=?"
        params.append(ref_no)
    rows = conn.execute(q, params).fetchall()
    for row in rows:
        aid, dr, cr = row["account_id"], float(row["debit"] or 0), float(row["credit"] or 0)
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
        if str(ref_type or "").lower() in ("journal", "journal_voucher", "jv"):
            _apply_journal_line_to_party_balance(conn, aid, dr, cr, reverse=True)
    if not rows:
        return 0
    ids = [r["id"] for r in rows]
    conn.execute(
        f"DELETE FROM general_ledger WHERE id IN ({','.join('?' * len(ids))})",
        ids,
    )
    return len(rows)


def reverse_journal_voucher(vid, user_id, reason=""):
    """Unpost a journal voucher (remove GL) and set status back to draft."""
    from database import get_connection
    from erp_core.period_lock import assert_period_open

    jv = get_journal_voucher(vid)
    if not jv:
        raise ValueError("Journal voucher not found.")
    assert_period_open(str(jv["voucher_date"]), user_id, action="edit")
    with get_connection() as conn:
        if (jv.get("status") or "").lower() == "posted":
            _delete_gl_reference(conn, "journal", ref_id=int(vid))
            # Legacy/import rows sometimes key only by document no
            _delete_gl_reference(conn, "journal", ref_no=jv.get("document_no"))
        conn.execute(
            """UPDATE journal_vouchers
               SET status='draft', posted_by=NULL, posted_at=NULL,
                   modified_by=?, modified_at=?
               WHERE id=?""",
            (user_id, now(), vid),
        )
    try:
        from db_audit import log_event
        log_event(
            "journal_vouchers", vid, "unpost", user_id=user_id, module="Finance",
            document_no=jv.get("document_no"),
            summary=f"Unposted journal {jv.get('document_no')}" + (f" — {reason}" if reason else ""),
        )
    except Exception:
        pass


def update_journal_voucher(vid, data, lines, user_id, *, repost=True):
    """Edit a journal voucher; reverses posted GL, saves lines, optionally re-posts."""
    jv = get_journal_voucher(vid)
    if not jv:
        raise ValueError("Journal voucher not found.")
    if not data.get("document_no"):
        data = {**data, "document_no": jv["document_no"]}
    reverse_journal_voucher(vid, user_id, reason="edit")
    save_journal_voucher(data, lines, vid=vid, user_id=user_id)
    if repost:
        post_journal_voucher(vid, user_id)
    return vid


def delete_journal_voucher(vid, user_id, reason=""):
    """Delete journal voucher (unpost GL first if needed)."""
    from database import get_connection

    jv = get_journal_voucher(vid)
    if not jv:
        raise ValueError("Journal voucher not found.")
    reverse_journal_voucher(vid, user_id, reason=reason or "delete")
    with get_connection() as conn:
        conn.execute("DELETE FROM journal_voucher_lines WHERE voucher_id=?", (vid,))
        conn.execute("DELETE FROM journal_vouchers WHERE id=?", (vid,))
    try:
        from db_audit import log_event
        log_event(
            "journal_vouchers", vid, "delete", user_id=user_id, module="Finance",
            document_no=jv.get("document_no"),
            summary=f"Deleted journal {jv.get('document_no')}" + (f" — {reason}" if reason else ""),
        )
    except Exception:
        pass


# Finance reports
def get_general_ledger(account_id=None, from_date=None, to_date=None, account_group_id=None):
    from database import get_connection, rows_to_list
    q = """SELECT gl.*, a.code AS account_code, a.name AS account_name,
                  mg.code AS group_code, mg.name AS group_name
           FROM general_ledger gl
           JOIN chart_of_accounts a ON gl.account_id=a.id
           LEFT JOIN master_groups mg ON a.group_id=mg.id AND mg.entity_type='account'
           WHERE 1=1"""
    p = []
    if account_id:
        q += " AND gl.account_id=?"; p.append(account_id)
    if account_group_id:
        q += " AND a.group_id=?"; p.append(account_group_id)
    if from_date:
        q += " AND gl.entry_date>=?"; p.append(from_date)
    if to_date:
        q += " AND gl.entry_date<=?"; p.append(to_date)
    q += " ORDER BY gl.entry_date, gl.id"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


def get_account_ledger(account_id, from_date=None, to_date=None):
    """Single chart account ledger with opening, period lines, running balance, and summary KPIs.

    Same shape as customer/supplier ledger: (account_dict, entries).
    When the chart account code matches a customer/supplier master, the ledger is
    synchronized with that party ledger (invoices, payments, JVs) so Account Ledger
    and Customer/Supplier Ledger always agree.
    """
    import database as db
    from database import get_connection, row_to_dict, rows_to_list, _ledger_period_summary, _opening_summary_row

    if not account_id:
        return None, []

    with get_connection() as conn:
        account = row_to_dict(conn.execute(
            """SELECT a.id, a.code, a.name, g.group_type AS account_type,
                      a.opening_balance, a.current_balance AS balance, a.is_active
               FROM chart_of_accounts a
               JOIN account_groups g ON a.account_group_id=g.id
               WHERE a.id=?""",
            (account_id,),
        ).fetchone())
        if not account:
            return None, []

        party_type, party_id = db._resolve_cash_bank_party(
            conn, account["id"], account["code"], account.get("account_type"),
        )
        if party_type == "supplier" and party_id:
            party, entries = db.get_supplier_ledger(
                int(party_id), from_date, to_date, include_linked=False,
            )
            if party and entries:
                summary = party.get("ledger_summary") or _ledger_period_summary(
                    entries, float(entries[0].get("balance") or 0), "supplier",
                )
                account["balance"] = summary.get("closing", account.get("balance"))
                account["ledger_summary"] = summary
                account["party_sync"] = "supplier"
                return account, entries
        if party_type == "customer" and party_id:
            party, entries = db.get_customer_ledger(
                int(party_id), from_date, to_date, include_linked=False,
            )
            if party and entries:
                summary = party.get("ledger_summary") or _ledger_period_summary(
                    entries, float(entries[0].get("balance") or 0), "customer",
                )
                account["balance"] = summary.get("closing", account.get("balance"))
                account["ledger_summary"] = summary
                account["party_sync"] = "customer"
                return account, entries

        master_ob = float(account.get("opening_balance") or 0)
        opening = master_ob
        if from_date:
            prior = conn.execute(
                """SELECT COALESCE(SUM(debit),0) AS dr, COALESCE(SUM(credit),0) AS cr
                   FROM general_ledger
                   WHERE account_id=? AND entry_date<?""",
                (account_id, from_date),
            ).fetchone()
            opening = round(
                master_ob + float(prior["dr"] or 0) - float(prior["cr"] or 0),
                2,
            )

        q = """SELECT id, entry_date AS date,
                      COALESCE(reference_no, '') AS ref,
                      COALESCE(description, '') AS description,
                      COALESCE(debit, 0) AS debit,
                      COALESCE(credit, 0) AS credit,
                      reference_type, reference_id, voucher_id
               FROM general_ledger
               WHERE account_id=?"""
        params = [account_id]
        if from_date:
            q += " AND entry_date>=?"
            params.append(from_date)
        if to_date:
            q += " AND entry_date<=?"
            params.append(to_date)
        q += " ORDER BY entry_date, id"
        movements = rows_to_list(conn.execute(q, params).fetchall())

        # Enrich invoice narrations with party (existing "Input tax" rows, etc.)
        party_cache = {}
        for m in movements:
            rt = m.get("reference_type") or ""
            rid = m.get("reference_id")
            if rt not in ("purchase_invoice", "sales_invoice") or not rid:
                continue
            key = (rt, int(rid))
            if key not in party_cache:
                party_cache[key] = _gl_party_label(conn, rt, rid)
            party = party_cache[key]
            if party:
                m["description"] = _gl_narration(m.get("description") or "", party)

    entries = [_opening_summary_row(opening, from_date, kind="customer")]
    balance = opening
    entries[0]["balance"] = opening
    for m in movements:
        e = {
            "date": str(m.get("date") or "")[:10],
            "ref": m.get("ref") or "",
            "description": m.get("description") or "",
            "debit": float(m.get("debit") or 0),
            "credit": float(m.get("credit") or 0),
            "voucher_type": (m.get("reference_type") or "").upper(),
        }
        balance = round(balance + e["debit"] - e["credit"], 2)
        e["balance"] = balance
        entries.append(e)

    account["ledger_summary"] = _ledger_period_summary(entries, opening, "customer")
    account["balance"] = account["ledger_summary"]["closing"]
    return account, entries


def get_trial_balance(from_date=None, to_date=None, account_group_id=None, view_mode="detail"):
    from database import get_connection, rows_to_list
    from db_report_groups import summarize_trial_balance, TRIAL_VIEW_DETAIL

    q = """SELECT a.code, a.name, g.group_type,
                  a.group_id AS master_group_id, mg.code AS group_code, mg.name AS group_name,
                  a.opening_balance + COALESCE(SUM(gl.debit),0) - COALESCE(SUM(gl.credit),0) AS balance,
                  COALESCE(SUM(gl.debit),0) AS period_debit, COALESCE(SUM(gl.credit),0) AS period_credit
           FROM chart_of_accounts a
           JOIN account_groups g ON a.account_group_id=g.id
           LEFT JOIN master_groups mg ON a.group_id=mg.id AND mg.entity_type='account'
           LEFT JOIN general_ledger gl ON gl.account_id=a.id
               AND (? IS NULL OR gl.entry_date>=?) AND (? IS NULL OR gl.entry_date<=?)
           WHERE a.is_active=1"""
    p = [from_date, from_date, to_date, to_date]
    if account_group_id:
        q += " AND a.group_id=?"
        p.append(account_group_id)
    q += " GROUP BY a.id ORDER BY a.code"
    with get_connection() as conn:
        rows = rows_to_list(conn.execute(q, p).fetchall())
    mode = view_mode or TRIAL_VIEW_DETAIL
    return summarize_trial_balance(rows, mode)

def get_balance_sheet(as_of=None, account_group_id=None, view_mode="detail"):
    from database import get_connection, rows_to_list
    from db_report_groups import summarize_balance_sheet_rows, TRIAL_VIEW_DETAIL  # noqa: F401

    q = """SELECT g.group_type, a.code, a.name,
                  a.group_id AS master_group_id, mg.code AS group_code, mg.name AS group_name,
                  a.opening_balance + COALESCE((SELECT SUM(debit)-SUM(credit) FROM general_ledger
                      WHERE account_id=a.id AND (? IS NULL OR entry_date<=?)),0) AS balance
           FROM chart_of_accounts a
           JOIN account_groups g ON a.account_group_id=g.id
           LEFT JOIN master_groups mg ON a.group_id=mg.id AND mg.entity_type='account'
           WHERE a.is_active=1"""
    p = [as_of, as_of]
    if account_group_id:
        q += " AND a.group_id=?"
        p.append(account_group_id)
    q += " ORDER BY a.code"
    with get_connection() as conn:
        rows = rows_to_list(conn.execute(q, p).fetchall())
    for r in rows:
        r["raw_balance"] = r["balance"]
        r["balance"] = _signed_balance(r["group_type"], r["balance"])
    assets = sum(r["balance"] for r in rows if r["group_type"] == "asset")
    liab = sum(r["balance"] for r in rows if r["group_type"] == "liability")
    equity = sum(r["balance"] for r in rows if r["group_type"] == "equity")
    display_rows = summarize_balance_sheet_rows(rows, view_mode or TRIAL_VIEW_DETAIL)
    return {
        "rows": display_rows,
        "detail_rows": rows,
        "total_assets": assets,
        "total_liabilities": liab,
        "total_equity": equity,
    }


def get_customer_outstanding(
    customer_group_id=None,
    view_mode="detail",
    from_date=None,
    to_date=None,
):
    """Customer balances as of To date, with optional From–To period Debit/Credit.

    When no dates are passed, To defaults to today (live as-of). Group filter and
    dual-role netting match Report Hub / Outstanding behaviour.
    """
    from database import get_customer_balances_for_period
    from db_report_groups import summarize_party_outstanding

    rows = get_customer_balances_for_period(
        from_date=from_date,
        to_date=to_date,
        customer_group_id=customer_group_id,
        # Group reports (e.g. ZAIDI SB) keep every member; otherwise hide nil balances
        include_zero=bool(customer_group_id),
    )
    return summarize_party_outstanding(rows, view_mode)

def get_supplier_outstanding(supplier_group_id=None, view_mode="detail"):
    from database import get_connection, rows_to_list, net_dual_role_party_balances
    from db_report_groups import summarize_party_outstanding

    with get_connection() as conn:
        net = net_dual_role_party_balances(conn)
        group_map = {
            (r["code"] or "").strip().upper(): r
            for r in rows_to_list(conn.execute(
                """SELECT s.code, s.group_id, mg.code AS group_code, mg.name AS group_name, s.phone
                   FROM suppliers s
                   LEFT JOIN master_groups mg ON s.group_id=mg.id AND mg.entity_type='supplier'
                   WHERE s.is_active=1"""
            ).fetchall())
        }
        rows = []
        for r in net["payables"]:
            meta = group_map.get((r.get("code") or "").strip().upper()) or {}
            if supplier_group_id and int(meta.get("group_id") or 0) != int(supplier_group_id):
                continue
            rows.append({
                "code": r["code"],
                "name": r["name"],
                "phone": r.get("phone") or meta.get("phone") or "",
                "outstanding": r["balance"],
                "group_code": meta.get("group_code"),
                "group_name": meta.get("group_name"),
                "group_id": meta.get("group_id"),
            })
    return summarize_party_outstanding(rows, view_mode)

def get_batch_stock():
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            """SELECT pb.*, p.code AS product_code, p.name AS product_name, w.name AS warehouse_name
               FROM product_batches pb JOIN products p ON pb.product_id=p.id JOIN warehouses w ON pb.warehouse_id=w.id
               ORDER BY pb.batch_no"""
        ).fetchall())

def get_product_wise_sales(from_date=None, to_date=None, product_group_id=None, view_mode="detail"):
    from database import get_connection, rows_to_list
    from db_report_groups import summarize_product_sales

    q = """SELECT p.code, p.name, p.group_id,
                  mg.code AS group_code, mg.name AS group_name,
                  SUM(si.quantity) AS qty, SUM(si.amount) AS amount
           FROM sales_invoice_items si JOIN products p ON si.product_id=p.id
           JOIN sales_invoices s ON si.invoice_id=s.id
           LEFT JOIN master_groups mg ON p.group_id=mg.id AND mg.entity_type='product'
           WHERE s.status='approved'"""
    p = []
    if from_date:
        q += " AND s.invoice_date>=?"; p.append(from_date)
    if to_date:
        q += " AND s.invoice_date<=?"; p.append(to_date)
    if product_group_id:
        q += " AND p.group_id=?"
        p.append(product_group_id)
    q += " GROUP BY p.id ORDER BY amount DESC"
    with get_connection() as conn:
        rows = rows_to_list(conn.execute(q, p).fetchall())
    return summarize_product_sales(rows, view_mode)

def get_tax_report(from_date=None, to_date=None):
    from database import get_connection, rows_to_list
    q = """SELECT document_no AS invoice_no, invoice_date, subtotal, discount, taxable_amount,
                  sales_tax, further_tax, extra_tax, fed_tax, wht_tax, total
           FROM sales_invoices WHERE status='approved'"""
    p = []
    if from_date:
        q += " AND invoice_date>=?"; p.append(from_date)
    if to_date:
        q += " AND invoice_date<=?"; p.append(to_date)
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


def _invoice_tax_payable(inv):
    return round(
        (inv.get("sales_tax") or 0) + (inv.get("further_tax") or 0)
        + (inv.get("extra_tax") or 0) + (inv.get("fed_tax") or 0),
        2,
    ) or round(inv.get("tax") or 0, 2)


def _invoice_taxable(inv):
    if inv.get("taxable_amount"):
        return round(inv["taxable_amount"], 2)
    return round((inv.get("subtotal") or 0) - (inv.get("discount") or 0), 2)

def record_customer_receipt(customer_id, receipt_date, amount, reference_no="", description="", user_id=None,
                            payment_mode="cash", bank_account_id=None):
    """Record customer payment: cash/bank book, AR GL, and reduce customer balance."""
    import database as db
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    mode = (payment_mode or "cash").lower()
    if mode not in ("cash", "bank"):
        raise ValueError("Payment mode must be cash or bank.")
    if mode == "bank" and not bank_account_id:
        raise ValueError("Select a bank account for bank receipt.")
    with db.get_connection() as conn:
        cust = conn.execute("SELECT name, code FROM customers WHERE id=?", (customer_id,)).fetchone()
        if not cust:
            raise ValueError("Customer not found.")
        label = description or f"Receipt from {cust['name']}"
        ref = reference_no or ""
        if mode == "cash":
            entry_id, doc_no = db._add_cash_receipt(
                conn, receipt_date, label, ref, amount, user_id,
                party_type="customer", party_id=customer_id,
            )
            asset_id = _acct_id(conn, gl_account_code("cash"))
        else:
            entry_id, doc_no = db._add_bank_receipt(
                conn, receipt_date, label, ref, amount, bank_account_id, user_id,
                party_type="customer", party_id=customer_id,
            )
            asset_id = bank_account_id
        conn.execute(
            "UPDATE customers SET current_balance=current_balance-?, modified_at=? WHERE id=?",
            (amount, now(), customer_id),
        )
        gl_ref = doc_no
        post_gl_account_id(conn, receipt_date, asset_id, amount, 0, label, "customer_receipt", entry_id, gl_ref, user_id)
        post_gl(
            conn, receipt_date, _party_subledger_code(conn, "customer", customer_id), 0, amount,
            label, "customer_receipt", customer_id, gl_ref, user_id,
        )
        return {"id": entry_id, "document_no": doc_no, "payment_mode": mode,
                "vch_source": "cash_receipt" if mode == "cash" else "bank_receipt"}


def record_supplier_payment(supplier_id, payment_date, amount, reference_no="", description="", user_id=None,
                            payment_mode="cash", bank_account_id=None):
    """Record supplier payment: cash/bank book, AP GL, and reduce supplier balance."""
    import database as db
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    mode = (payment_mode or "cash").lower()
    if mode not in ("cash", "bank"):
        raise ValueError("Payment mode must be cash or bank.")
    if mode == "bank" and not bank_account_id:
        raise ValueError("Select a bank account for bank payment.")
    with db.get_connection() as conn:
        sup = conn.execute("SELECT name, code FROM suppliers WHERE id=?", (supplier_id,)).fetchone()
        if not sup:
            raise ValueError("Supplier not found.")
        label = description or f"Payment to {sup['name']}"
        ref = reference_no or ""
        if mode == "cash":
            entry_id, doc_no = db._add_cash_payment(
                conn, payment_date, label, ref, amount, user_id,
                party_type="supplier", party_id=supplier_id,
            )
            asset_id = _acct_id(conn, gl_account_code("cash"))
        else:
            entry_id, doc_no = db._add_bank_payment(
                conn, payment_date, label, ref, amount, bank_account_id, user_id,
                party_type="supplier", party_id=supplier_id,
            )
            asset_id = bank_account_id
        conn.execute(
            "UPDATE suppliers SET current_balance=current_balance-?, modified_at=? WHERE id=?",
            (amount, now(), supplier_id),
        )
        gl_ref = doc_no
        post_gl(
            conn, payment_date, _party_subledger_code(conn, "supplier", supplier_id), amount, 0,
            label, "supplier_payment", supplier_id, gl_ref, user_id,
        )
        post_gl_account_id(conn, payment_date, asset_id, 0, amount, label, "supplier_payment", entry_id, gl_ref, user_id)
        return {"id": entry_id, "document_no": doc_no, "payment_mode": mode,
                "vch_source": "cash_payment" if mode == "cash" else "bank_payment"}


def _void_cash_bank_book_effects(conn, *, book, entry_id, entry_type, row):
    """Reverse GL + party balances for an existing cash/bank book row (does not delete the row)."""
    doc = (row.get("document_no") or "").strip()
    amt = float(row.get("amount") or 0)
    pt = (row.get("party_type") or "").lower() or None
    pid = row.get("party_id")
    if pt == "customer" and pid and amt:
        # record_customer_receipt subtracted balance
        conn.execute(
            "UPDATE customers SET current_balance=current_balance+?, modified_at=? WHERE id=?",
            (amt, now(), int(pid)),
        )
    elif pt == "supplier" and pid and amt:
        conn.execute(
            "UPDATE suppliers SET current_balance=current_balance+?, modified_at=? WHERE id=?",
            (amt, now(), int(pid)),
        )
    if doc:
        for ref_type in (
            "customer_receipt",
            "supplier_payment",
            "cash_bank_gl",
            "expense_payment",
            "customer_payment",
            "supplier_receipt",
        ):
            _delete_gl_reference(conn, ref_type, ref_no=doc)
    if entry_id is not None:
        for ref_type in (
            "customer_receipt",
            "supplier_payment",
            "cash_bank_gl",
            "expense_payment",
        ):
            _delete_gl_reference(conn, ref_type, ref_id=int(entry_id))


def _load_cash_bank_book_row(conn, book, entry_id, entry_type):
    book = (book or "cash").lower()
    is_receipt = (entry_type or "").lower() in ("credit", "receipt")
    if book == "cash":
        table = "cash_receipts" if is_receipt else "cash_payments"
        date_col = "receipt_date" if is_receipt else "payment_date"
    else:
        table = "bank_receipts" if is_receipt else "bank_payments"
        date_col = "receipt_date" if is_receipt else "payment_date"
    row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (entry_id,)).fetchone()
    if not row:
        # Fallback: search both tables (edit form may pass wrong type after user toggles)
        for tbl, dcol, et in (
            (f"{book}_receipts", "receipt_date", "credit"),
            (f"{book}_payments", "payment_date", "debit"),
        ):
            row = conn.execute(f"SELECT * FROM {tbl} WHERE id=?", (entry_id,)).fetchone()
            if row:
                table, date_col, is_receipt = tbl, dcol, et == "credit"
                break
    if not row:
        return None
    from database import row_to_dict
    d = row_to_dict(row)
    d["_table"] = table
    d["_date_col"] = date_col
    d["_is_receipt"] = is_receipt
    d["entry_date"] = d.get(date_col)
    d["entry_type"] = "credit" if is_receipt else "debit"
    return d


def void_cash_bank_book_entry(book, entry_id, entry_type=None, *, _skip_close_check=False):
    """Delete cash/bank voucher and reverse GL + customer/supplier balances."""
    import database as db
    from db_cash_day import assert_cash_day_open
    with db.get_connection() as conn:
        row = _load_cash_bank_book_row(conn, book, entry_id, entry_type)
        if not row:
            raise ValueError("Voucher not found.")
        if book == "cash" and not _skip_close_check:
            assert_cash_day_open(row.get("entry_date"), "delete")
        _void_cash_bank_book_effects(
            conn, book=book, entry_id=entry_id, entry_type=row["entry_type"], row=row,
        )
        conn.execute(f"DELETE FROM {row['_table']} WHERE id=?", (entry_id,))
    return True


def update_cash_bank_book_entry(
    book,
    entry_id,
    old_entry_type,
    *,
    entry_date,
    description,
    reference_no,
    entry_type,
    amount,
    party_type=None,
    party_id=None,
    bank_account_id=None,
    user_id=None,
):
    """Update cash/bank voucher including account title (party/GL), keeping document no when possible."""
    import database as db
    from db_cash_day import assert_cash_day_open

    if amount is None or float(amount) <= 0:
        raise ValueError("Amount must be greater than zero.")
    amount = float(amount)
    book = (book or "cash").lower()
    new_is_receipt = (entry_type or "").lower() in ("credit", "receipt")
    new_et = "credit" if new_is_receipt else "debit"
    pt = (party_type or "").lower() or None
    pid = int(party_id) if party_id not in (None, "", 0, "0") else None
    if pt and not pid:
        raise ValueError("Select an account title.")
    if pt in ("customer",) and not new_is_receipt:
        raise ValueError("Customer account title is only valid on Receipt vouchers.")
    if pt in ("supplier",) and new_is_receipt:
        raise ValueError("Supplier account title is only valid on Payment vouchers.")

    validate_fiscal_open(entry_date)
    if book == "cash":
        assert_cash_day_open(entry_date, "post")

    with db.get_connection() as conn:
        old = _load_cash_bank_book_row(conn, book, entry_id, old_entry_type)
        if not old:
            raise ValueError("Voucher not found.")
        if book == "cash":
            assert_cash_day_open(old.get("entry_date"), "edit or delete")
        doc_no = old.get("document_no")
        old_bank_id = old.get("account_id") if book == "bank" else None
        bank_id = bank_account_id or old_bank_id

        _void_cash_bank_book_effects(
            conn, book=book, entry_id=entry_id, entry_type=old["entry_type"], row=old,
        )

        label = (description or "").strip()
        ref = (reference_no or "").strip()
        same_side = bool(old["_is_receipt"]) == new_is_receipt

        if same_side:
            # Keep same row id + document number
            date_col = old["_date_col"]
            conn.execute(
                f"""UPDATE {old['_table']}
                    SET {date_col}=?, description=?, reference_no=?, amount=?,
                        party_type=?, party_id=?, account_id=?
                    WHERE id=?""",
                (
                    entry_date, label, ref, amount,
                    pt, pid,
                    bank_id if book == "bank" else old.get("account_id"),
                    entry_id,
                ),
            )
            new_id = entry_id
        else:
            conn.execute(f"DELETE FROM {old['_table']} WHERE id=?", (entry_id,))
            if book == "cash":
                if new_is_receipt:
                    new_id, doc_no = db._add_cash_receipt(
                        conn, entry_date, label, ref, amount, user_id,
                        party_type=pt, party_id=pid,
                    )
                else:
                    new_id, doc_no = db._add_cash_payment(
                        conn, entry_date, label, ref, amount, user_id,
                        party_type=pt, party_id=pid,
                    )
            else:
                if not bank_id:
                    raise ValueError("Bank account is required.")
                if new_is_receipt:
                    new_id, doc_no = db._add_bank_receipt(
                        conn, entry_date, label, ref, amount, bank_id, user_id,
                        party_type=pt, party_id=pid,
                    )
                else:
                    new_id, doc_no = db._add_bank_payment(
                        conn, entry_date, label, ref, amount, bank_id, user_id,
                        party_type=pt, party_id=pid,
                    )

        # Repost effects for new account title
        cash_id = _acct_id(conn, gl_account_code("cash"))
        asset_id = bank_id if book == "bank" else cash_id
        if not asset_id:
            raise ValueError("Cash/bank GL account is not configured.")

        if pt == "customer" and pid:
            if not label:
                cust = conn.execute("SELECT name FROM customers WHERE id=?", (pid,)).fetchone()
                label = f"Receipt from {cust['name']}" if cust else "Customer receipt"
                conn.execute(
                    f"UPDATE {('cash_receipts' if book=='cash' else 'bank_receipts')} SET description=? WHERE id=?",
                    (label, new_id),
                )
            conn.execute(
                "UPDATE customers SET current_balance=current_balance-?, modified_at=? WHERE id=?",
                (amount, now(), pid),
            )
            post_gl_account_id(
                conn, entry_date, asset_id, amount, 0, label, "customer_receipt", new_id, doc_no, user_id,
            )
            post_gl(
                conn, entry_date, _party_subledger_code(conn, "customer", pid), 0, amount,
                label, "customer_receipt", pid, doc_no, user_id,
            )
        elif pt == "supplier" and pid:
            if not label:
                sup = conn.execute("SELECT name FROM suppliers WHERE id=?", (pid,)).fetchone()
                label = f"Payment to {sup['name']}" if sup else "Supplier payment"
                conn.execute(
                    f"UPDATE {('cash_payments' if book=='cash' else 'bank_payments')} SET description=? WHERE id=?",
                    (label, new_id),
                )
            conn.execute(
                "UPDATE suppliers SET current_balance=current_balance-?, modified_at=? WHERE id=?",
                (amount, now(), pid),
            )
            post_gl(
                conn, entry_date, _party_subledger_code(conn, "supplier", pid), amount, 0,
                label, "supplier_payment", pid, doc_no, user_id,
            )
            post_gl_account_id(
                conn, entry_date, asset_id, 0, amount, label, "supplier_payment", new_id, doc_no, user_id,
            )
        elif pt in ("account", "expense") and pid:
            acc = conn.execute(
                """SELECT a.id, a.name, g.group_type FROM chart_of_accounts a
                   JOIN account_groups g ON a.account_group_id=g.id WHERE a.id=?""",
                (pid,),
            ).fetchone()
            if not acc:
                raise ValueError("Account title not found.")
            if not label:
                label = f"{'Payment to' if not new_is_receipt else 'Receipt from'} {acc['name']}"
                tbl = (
                    ("cash_receipts" if new_is_receipt else "cash_payments")
                    if book == "cash"
                    else ("bank_receipts" if new_is_receipt else "bank_payments")
                )
                conn.execute(f"UPDATE {tbl} SET description=? WHERE id=?", (label, new_id))
            # Align party_type with expense vs account
            real_pt = "expense" if acc["group_type"] == "expense" else "account"
            tbl = (
                ("cash_receipts" if new_is_receipt else "cash_payments")
                if book == "cash"
                else ("bank_receipts" if new_is_receipt else "bank_payments")
            )
            conn.execute(
                f"UPDATE {tbl} SET party_type=?, party_id=? WHERE id=?",
                (real_pt, pid, new_id),
            )
            ref_type = "expense_payment" if (not new_is_receipt and real_pt == "expense") else "cash_bank_gl"
            if new_is_receipt:
                post_gl_account_id(conn, entry_date, asset_id, amount, 0, label, ref_type, new_id, doc_no, user_id)
                post_gl_account_id(conn, entry_date, pid, 0, amount, label, ref_type, new_id, doc_no, user_id)
            else:
                post_gl_account_id(conn, entry_date, pid, amount, 0, label, ref_type, new_id, doc_no, user_id)
                post_gl_account_id(conn, entry_date, asset_id, 0, amount, label, ref_type, new_id, doc_no, user_id)
        # else: book-only entry — no GL / party

    return {"id": new_id, "document_no": doc_no}


def search_customer_receipts(q=None, customer_id=None, from_date=None, to_date=None, page=1, page_size=50):
    """List customer receipts from cash and bank books."""
    from database import run_paginated_list
    from_clause = """
        (
            SELECT cr.id, cr.document_no, cr.receipt_date AS txn_date, cr.amount, cr.description, cr.reference_no,
                   'cash' AS payment_mode, 'cash_receipt' AS vch_source,
                   cr.party_id AS customer_id, c.name AS customer_name, cr.created_at
            FROM cash_receipts cr
            JOIN customers c ON cr.party_id=c.id
            WHERE cr.party_type='customer'
            UNION ALL
            SELECT br.id, br.document_no, br.receipt_date AS txn_date, br.amount, br.description, br.reference_no,
                   'bank' AS payment_mode, 'bank_receipt' AS vch_source,
                   br.party_id AS customer_id, c.name AS customer_name, br.created_at
            FROM bank_receipts br
            JOIN customers c ON br.party_id=c.id
            WHERE br.party_type='customer'
        ) t
    """
    where, params = [], []
    if customer_id:
        where.append("customer_id=?"); params.append(customer_id)
    if from_date:
        where.append("txn_date>=?"); params.append(from_date)
    if to_date:
        where.append("txn_date<=?"); params.append(to_date)
    if q:
        like = f"%{q.strip()}%"
        where.append("(document_no LIKE ? OR customer_name LIKE ? OR description LIKE ? OR reference_no LIKE ?)")
        params.extend([like, like, like, like])
    return run_paginated_list(
        from_clause,
        "id, document_no, txn_date, amount, description, reference_no, payment_mode, vch_source, customer_id, customer_name, created_at",
        where or None,
        params,
        "txn_date DESC, id DESC",
        page,
        page_size,
    )


def search_supplier_payments(q=None, supplier_id=None, from_date=None, to_date=None, page=1, page_size=50):
    """List supplier payments from cash and bank books."""
    from database import run_paginated_list
    from_clause = """
        (
            SELECT cp.id, cp.document_no, cp.payment_date AS txn_date, cp.amount, cp.description, cp.reference_no,
                   'cash' AS payment_mode, 'cash_payment' AS vch_source,
                   cp.party_id AS supplier_id, s.name AS supplier_name, cp.created_at
            FROM cash_payments cp
            JOIN suppliers s ON cp.party_id=s.id
            WHERE cp.party_type='supplier'
            UNION ALL
            SELECT bp.id, bp.document_no, bp.payment_date AS txn_date, bp.amount, bp.description, bp.reference_no,
                   'bank' AS payment_mode, 'bank_payment' AS vch_source,
                   bp.party_id AS supplier_id, s.name AS supplier_name, bp.created_at
            FROM bank_payments bp
            JOIN suppliers s ON bp.party_id=s.id
            WHERE bp.party_type='supplier'
        ) t
    """
    where, params = [], []
    if supplier_id:
        where.append("supplier_id=?"); params.append(supplier_id)
    if from_date:
        where.append("txn_date>=?"); params.append(from_date)
    if to_date:
        where.append("txn_date<=?"); params.append(to_date)
    if q:
        like = f"%{q.strip()}%"
        where.append("(document_no LIKE ? OR supplier_name LIKE ? OR description LIKE ? OR reference_no LIKE ?)")
        params.extend([like, like, like, like])
    return run_paginated_list(
        from_clause,
        "id, document_no, txn_date, amount, description, reference_no, payment_mode, vch_source, supplier_id, supplier_name, created_at",
        where or None,
        params,
        "txn_date DESC, id DESC",
        page,
        page_size,
    )


def record_cash_bank_gl_voucher(
    account_id, txn_date, amount, *, side="payment", reference_no="", description="",
    user_id=None, payment_mode="cash", bank_account_id=None,
):
    """Cash/bank receipt or payment against any GL account (expense, liability, equity, etc.).

    Payment: Dr account, Cr cash/bank.
    Receipt: Dr cash/bank, Cr account.
    When the GL head matches a customer/supplier code, the voucher is linked to that
    party so Cash/Bank Book, party ledger, and GL stay aligned.
    """
    import database as db
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    side = (side or "payment").lower()
    if side not in ("payment", "receipt"):
        raise ValueError("Side must be payment or receipt.")
    mode = (payment_mode or "cash").lower()
    if mode not in ("cash", "bank"):
        raise ValueError("Payment mode must be cash or bank.")
    if mode == "bank" and not bank_account_id:
        raise ValueError("Select a bank account for bank voucher.")
    party_fix = None
    with db.get_connection() as conn:
        acc = conn.execute(
            """SELECT a.id, a.code, a.name, g.group_type
               FROM chart_of_accounts a JOIN account_groups g ON a.account_group_id=g.id
               WHERE a.id=? AND a.is_active=1""",
            (account_id,),
        ).fetchone()
        if not acc:
            raise ValueError("Account not found or inactive.")
        cash_id = _acct_id(conn, gl_account_code("cash"))
        asset_id = bank_account_id if mode == "bank" else cash_id
        if not asset_id:
            raise ValueError("Cash/bank GL account is not configured.")
        if int(account_id) == int(asset_id):
            raise ValueError("Cannot post cash/bank against the same cash/bank account.")
        label = description or (
            f"{'Payment to' if side == 'payment' else 'Receipt from'} {acc['name']}"
        )
        ref = reference_no or ""
        # Keep expense payments discoverable in Expense Payment register
        if acc["group_type"] == "expense":
            party_type = "expense"
            party_id = account_id
        else:
            mapped_party_type, mapped_party_id = db._resolve_cash_bank_party(
                conn, account_id, acc["code"], acc["group_type"],
            )
            if mapped_party_type and mapped_party_id:
                party_type = mapped_party_type
                party_id = mapped_party_id
                party_fix = (mapped_party_type, int(mapped_party_id))
            else:
                party_type = "account"
                party_id = account_id
        if mode == "cash":
            if side == "payment":
                entry_id, doc_no = db._add_cash_payment(
                    conn, txn_date, label, ref, amount, user_id,
                    party_type=party_type, party_id=party_id,
                )
            else:
                entry_id, doc_no = db._add_cash_receipt(
                    conn, txn_date, label, ref, amount, user_id,
                    party_type=party_type, party_id=party_id,
                )
        else:
            if side == "payment":
                entry_id, doc_no = db._add_bank_payment(
                    conn, txn_date, label, ref, amount, bank_account_id, user_id,
                    party_type=party_type, party_id=party_id,
                )
            else:
                entry_id, doc_no = db._add_bank_receipt(
                    conn, txn_date, label, ref, amount, bank_account_id, user_id,
                    party_type=party_type, party_id=party_id,
                )
        gl_ref = doc_no
        ref_type = "expense_payment" if (side == "payment" and party_type == "expense") else "cash_bank_gl"
        if side == "payment":
            post_gl_account_id(conn, txn_date, account_id, amount, 0, label, ref_type, entry_id, gl_ref, user_id)
            post_gl_account_id(conn, txn_date, asset_id, 0, amount, label, ref_type, entry_id, gl_ref, user_id)
        else:
            post_gl_account_id(conn, txn_date, asset_id, amount, 0, label, ref_type, entry_id, gl_ref, user_id)
            post_gl_account_id(conn, txn_date, account_id, 0, amount, label, ref_type, entry_id, gl_ref, user_id)
        res = {
            "id": entry_id,
            "document_no": doc_no,
            "payment_mode": mode,
            "vch_source": (
                ("cash_payment" if side == "payment" else "cash_receipt")
                if mode == "cash"
                else ("bank_payment" if side == "payment" else "bank_receipt")
            ),
            "party_type": party_type,
            "account_name": acc["name"],
        }
    if party_fix:
        db.sync_party_current_balance(*party_fix)
    return res


def record_expense_payment(expense_account_id, payment_date, amount, reference_no="", description="",
                           user_id=None, payment_mode="cash", bank_account_id=None):
    """Pay an expense: debit expense GL, credit cash/bank, post to cash/bank book."""
    import database as db
    with db.get_connection() as conn:
        acc = conn.execute(
            """SELECT a.id, g.group_type
               FROM chart_of_accounts a JOIN account_groups g ON a.account_group_id=g.id
               WHERE a.id=? AND a.is_active=1""",
            (expense_account_id,),
        ).fetchone()
        if not acc:
            raise ValueError("Expense account not found.")
        if acc["group_type"] != "expense":
            raise ValueError("Selected account must be an expense account.")
    return record_cash_bank_gl_voucher(
        expense_account_id, payment_date, amount,
        side="payment", reference_no=reference_no, description=description,
        user_id=user_id, payment_mode=payment_mode, bank_account_id=bank_account_id,
    )


def record_expense_bill(
    party_type, party_id, bill_date, lines, *,
    settlement="credit", bank_account_id=None, reference_no="", description="", user_id=None,
):
    """Post a multi-expense bill for one customer/supplier.

    lines: [{expense_account_id, narration, amount}, ...] — each head on its own line.
    settlement: cash | bank | credit
      cash/bank: Dr expenses, Cr cash/bank (party balance unchanged; linked on cash/bank voucher)
      credit + supplier: Dr expenses, Cr AP; +supplier balance
      credit + customer: Dr expenses, Cr AR; -customer balance (party credit / we owe them)
    """
    import database as db
    from database import ensure_document_no

    party_type = (party_type or "").lower().strip()
    settlement = (settlement or "credit").lower().strip()
    if party_type not in ("customer", "supplier"):
        raise ValueError("Party type must be customer or supplier.")
    if settlement not in ("cash", "bank", "credit"):
        raise ValueError("Settlement must be cash, bank, or credit.")
    if not party_id:
        raise ValueError("Select a party.")
    if settlement == "bank" and not bank_account_id:
        raise ValueError("Select a bank account for bank settlement.")
    if not lines:
        raise ValueError("Add at least one expense line.")

    clean = []
    for i, ln in enumerate(lines):
        aid = ln.get("expense_account_id") or ln.get("account_id")
        amt = float(ln.get("amount") or 0)
        if not aid:
            raise ValueError(f"Line {i + 1}: select an expense account.")
        if amt <= 0:
            raise ValueError(f"Line {i + 1}: amount must be greater than zero.")
        clean.append({
            "expense_account_id": int(aid),
            "narration": (ln.get("narration") or ln.get("description") or "").strip(),
            "amount": amt,
            "line_no": i + 1,
        })
    total = sum(l["amount"] for l in clean)
    if total <= 0:
        raise ValueError("Bill total must be greater than zero.")

    with db.get_connection() as conn:
        _ensure_expense_bills_schema(conn)
        if party_type == "customer":
            party = conn.execute(
                "SELECT id, code, name FROM customers WHERE id=? AND is_active=1", (party_id,)
            ).fetchone()
        else:
            party = conn.execute(
                "SELECT id, code, name FROM suppliers WHERE id=? AND is_active=1", (party_id,)
            ).fetchone()
        if not party:
            raise ValueError("Party not found or inactive.")

        for ln in clean:
            acc = conn.execute(
                """SELECT a.id, a.code, a.name, g.group_type
                   FROM chart_of_accounts a JOIN account_groups g ON a.account_group_id=g.id
                   WHERE a.id=? AND a.is_active=1""",
                (ln["expense_account_id"],),
            ).fetchone()
            if not acc:
                raise ValueError(f"Expense account not found (line {ln['line_no']}).")
            if acc["group_type"] != "expense":
                raise ValueError(f"{acc['code']} is not an expense account (line {ln['line_no']}).")
            code = str(acc["code"] or "")
            name_l = str(acc["name"] or "").lower()
            clearing = (gl_account_code("pl_clearing") or "3999").strip()
            if code == clearing or code == "3999" or "clearing" in name_l or "profit & loss" in name_l:
                raise ValueError(
                    f"{acc['code']} — {acc['name']} is a system / year-end clearing account "
                    f"(line {ln['line_no']}). Choose an operating expense head."
                )
            ln["account_code"] = acc["code"]
            ln["account_name"] = acc["name"]

        doc_no = ensure_document_no("EB", None, conn)
        bill_note = (description or "").strip() or f"Expense bill — {party['name']}"
        ts = now()

        cur = conn.execute(
            """INSERT INTO expense_bills(
                   document_no, bill_date, party_type, party_id, settlement, bank_account_id,
                   reference_no, description, total_amount, status, created_by, created_at, posted_by, posted_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                doc_no, str(bill_date), party_type, int(party_id), settlement,
                bank_account_id if settlement == "bank" else None,
                reference_no or "", bill_note, total, "posted", user_id, ts, user_id, ts,
            ),
        )
        bill_id = cur.lastrowid
        for ln in clean:
            conn.execute(
                """INSERT INTO expense_bill_lines(bill_id, line_no, expense_account_id, narration, amount)
                   VALUES (?,?,?,?,?)""",
                (bill_id, ln["line_no"], ln["expense_account_id"], ln["narration"], ln["amount"]),
            )

        cash_entry_id = None
        cash_entry_source = None
        gl_label = bill_note

        # Dr each expense
        for ln in clean:
            line_lbl = ln["narration"] or f"{ln['account_code']} — {ln['account_name']}"
            post_gl_account_id(
                conn, str(bill_date), ln["expense_account_id"], ln["amount"], 0,
                line_lbl, "expense_bill", bill_id, doc_no, user_id,
            )

        if settlement in ("cash", "bank"):
            cash_id = _acct_id(conn, gl_account_code("cash"))
            asset_id = bank_account_id if settlement == "bank" else cash_id
            if not asset_id:
                raise ValueError("Cash/bank GL account is not configured.")
            post_gl_account_id(
                conn, str(bill_date), asset_id, 0, total,
                gl_label, "expense_bill", bill_id, doc_no, user_id,
            )
            ref = reference_no or ""
            if settlement == "cash":
                cash_entry_id, _ = db._add_cash_payment(
                    conn, str(bill_date), gl_label, ref, total, user_id,
                    party_type=party_type, party_id=int(party_id),
                )
                cash_entry_source = "cash_payment"
            else:
                cash_entry_id, _ = db._add_bank_payment(
                    conn, str(bill_date), gl_label, ref, total, bank_account_id, user_id,
                    party_type=party_type, party_id=int(party_id),
                )
                cash_entry_source = "bank_payment"
            conn.execute(
                "UPDATE expense_bills SET cash_entry_id=?, cash_entry_source=? WHERE id=?",
                (cash_entry_id, cash_entry_source, bill_id),
            )
        else:
            # Credit settlement — party ledger + AP/AR
            if party_type == "supplier":
                post_gl(
                    conn, str(bill_date), gl_account_code("ap"), 0, total,
                    gl_label, "expense_bill", bill_id, doc_no, user_id,
                )
                conn.execute(
                    "UPDATE suppliers SET current_balance=current_balance-?, modified_at=? WHERE id=?",
                    (total, ts, int(party_id)),
                )
            else:
                post_gl(
                    conn, str(bill_date), gl_account_code("ar"), 0, total,
                    gl_label, "expense_bill", bill_id, doc_no, user_id,
                )
                conn.execute(
                    "UPDATE customers SET current_balance=current_balance-?, modified_at=? WHERE id=?",
                    (total, ts, int(party_id)),
                )

        return {
            "id": bill_id,
            "document_no": doc_no,
            "total_amount": total,
            "settlement": settlement,
            "party_type": party_type,
            "party_id": int(party_id),
            "party_name": party["name"],
            "vch_source": cash_entry_source,
            "cash_entry_id": cash_entry_id,
        }


def get_expense_bill(bill_id):
    from database import get_connection, row_to_dict, rows_to_list
    with get_connection() as conn:
        _ensure_expense_bills_schema(conn)
        h = row_to_dict(conn.execute("SELECT * FROM expense_bills WHERE id=?", (bill_id,)).fetchone())
        if not h:
            return None
        if h["party_type"] == "customer":
            p = conn.execute("SELECT code, name FROM customers WHERE id=?", (h["party_id"],)).fetchone()
        else:
            p = conn.execute("SELECT code, name FROM suppliers WHERE id=?", (h["party_id"],)).fetchone()
        h["party_code"] = p["code"] if p else ""
        h["party_name"] = p["name"] if p else ""
        h["lines"] = rows_to_list(conn.execute(
            """SELECT l.*, a.code AS expense_code, a.name AS expense_name
               FROM expense_bill_lines l
               JOIN chart_of_accounts a ON l.expense_account_id=a.id
               WHERE l.bill_id=? ORDER BY l.line_no, l.id""",
            (bill_id,),
        ).fetchall())
        return h


def search_expense_bills(
    q=None, party_type=None, party_id=None, from_date=None, to_date=None,
    page=1, page_size=50, export_all=False,
):
    from database import get_connection, rows_to_list
    page = max(1, int(page or 1))
    page_size = min(200, max(5, int(page_size or 50)))
    where = ["1=1"]
    params: list = []
    if party_type:
        where.append("b.party_type=?")
        params.append(party_type)
    if party_id:
        where.append("b.party_id=?")
        params.append(int(party_id))
    if from_date:
        where.append("b.bill_date>=?")
        params.append(from_date)
    if to_date:
        where.append("b.bill_date<=?")
        params.append(to_date)
    if q:
        like = f"%{q.strip()}%"
        where.append(
            "(b.document_no LIKE ? OR COALESCE(b.reference_no,'') LIKE ? OR COALESCE(b.description,'') LIKE ?)"
        )
        params.extend([like, like, like])
    clause = " AND ".join(where)
    with get_connection() as conn:
        _ensure_expense_bills_schema(conn)
        total = int(conn.execute(
            f"SELECT COUNT(*) FROM expense_bills b WHERE {clause}", params,
        ).fetchone()[0])
        sql = f"""
            SELECT b.*,
                   CASE WHEN b.party_type='customer' THEN c.code ELSE s.code END AS party_code,
                   CASE WHEN b.party_type='customer' THEN c.name ELSE s.name END AS party_name
            FROM expense_bills b
            LEFT JOIN customers c ON b.party_type='customer' AND b.party_id=c.id
            LEFT JOIN suppliers s ON b.party_type='supplier' AND b.party_id=s.id
            WHERE {clause}
            ORDER BY b.bill_date DESC, b.id DESC
        """
        if export_all:
            rows = rows_to_list(conn.execute(sql, params).fetchall())
            return rows
        offset = (page - 1) * page_size
        rows = rows_to_list(conn.execute(sql + " LIMIT ? OFFSET ?", [*params, page_size, offset]).fetchall())
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


def issue_cash_advance(
    issue_date, amount, person_name, *, purpose="", reference_no="",
    payment_mode="cash", bank_account_id=None, advance_account_id=None, user_id=None,
):
    """Give cash/bank float to a rider/driver before expense bills are known.

    Shadow in Cash Advance register + GL (Dr Advance, Cr Cash/Bank).
    Does **not** post to Cash Book / Bank Book — bills are booked on settlement.
    """
    import database as db
    from database import ensure_document_no

    amount = float(amount or 0)
    if amount <= 0:
        raise ValueError("Advance amount must be greater than zero.")
    person = (person_name or "").strip()
    if not person:
        raise ValueError("Enter who received the advance (rider / driver name).")
    mode = (payment_mode or "cash").lower()
    if mode not in ("cash", "bank"):
        raise ValueError("Payment mode must be cash or bank.")
    if mode == "bank" and not bank_account_id:
        raise ValueError("Select a bank account for bank advance.")
    validate_fiscal_open(str(issue_date))

    with db.get_connection() as conn:
        _ensure_cash_advances_schema(conn)
        adv_aid = int(advance_account_id or 0) or resolve_cash_advance_account_id(conn)
        if not adv_aid:
            raise ValueError(
                "Advance account not found. Create GL head 100193 — ADVANCE PAYMENT OTHERS first."
            )
        acc = conn.execute(
            """SELECT a.id, a.code, a.name FROM chart_of_accounts a
               WHERE a.id=? AND a.is_active=1""",
            (adv_aid,),
        ).fetchone()
        if not acc:
            raise ValueError("Advance account is inactive or missing.")

        purpose_txt = (purpose or "").strip()
        label = f"Advance to {person}"
        if purpose_txt:
            label = f"{label} — {purpose_txt}"
        ref = (reference_no or "").strip()
        doc_no = ensure_document_no("CA", None, conn)
        ts = now()

        cur = conn.execute(
            """INSERT INTO cash_advances(
                   document_no, issue_date, person_name, purpose, amount,
                   settled_bills, cash_returned, outstanding_amount,
                   advance_account_id, payment_mode, bank_account_id,
                   status, created_by, created_at
               ) VALUES (?,?,?,?,?,0,0,?,?,?,?,'open',?,?)""",
            (
                doc_no, str(issue_date), person, purpose_txt, amount,
                amount, adv_aid, mode,
                bank_account_id if mode == "bank" else None,
                user_id, ts,
            ),
        )
        adv_id = cur.lastrowid

        if mode == "cash":
            asset_id = _acct_id(conn, gl_account_code("cash"))
        else:
            asset_id = bank_account_id
        if not asset_id:
            raise ValueError("Cash/bank GL account is not configured.")

        # GL only — shadow float; Cash Book posts when bills are settled.
        post_gl_account_id(
            conn, str(issue_date), adv_aid, amount, 0, label,
            "cash_advance", adv_id, doc_no, user_id,
        )
        post_gl_account_id(
            conn, str(issue_date), asset_id, 0, amount, label,
            "cash_advance", adv_id, doc_no, user_id,
        )
        conn.execute(
            """UPDATE cash_advances
               SET issue_entry_id=NULL, issue_entry_source=NULL, issue_doc_no=? WHERE id=?""",
            (doc_no, adv_id),
        )
        try:
            from db_audit import log_event
            log_event(
                "cash_advances", adv_id, "create", user_id=user_id, module="Finance",
                document_no=doc_no,
                summary=f"Issued cash advance {doc_no} to {person} — {amount:,.2f}",
            )
        except Exception:
            pass
        return {
            "id": adv_id,
            "document_no": doc_no,
            "issue_doc_no": doc_no,
            "amount": amount,
            "person_name": person,
            "outstanding_amount": amount,
            "status": "open",
        }


def settle_cash_advance(
    advance_id, settle_date, lines, *, cash_returned=0.0, description="", user_id=None,
):
    """Allocate bills / GL lines (and optional cash return) against an open cash advance.

    lines: [{expense_account_id|account_id, narration, amount}, ...]
    Each bill line: Dr GL account, Cr Cash (Cash Book CP) + GL-only Dr Cash / Cr Advance
    to clear the shadow advance without double-counting GL cash.
    Cash return: GL Dr Cash / Cr Advance only — not in Cash Book.
    """
    import database as db
    from database import ensure_document_no
    from db_cash_day import assert_cash_day_open

    if not advance_id:
        raise ValueError("Select an advance to settle.")
    cash_returned = round(float(cash_returned or 0), 2)
    if cash_returned < 0:
        raise ValueError("Cash returned cannot be negative.")

    clean = []
    for i, ln in enumerate(lines or []):
        aid = ln.get("expense_account_id") or ln.get("account_id")
        amt = round(float(ln.get("amount") or 0), 2)
        if not aid and amt <= 0:
            continue
        if not aid:
            raise ValueError(f"Line {i + 1}: select a GL account.")
        if amt <= 0:
            raise ValueError(f"Line {i + 1}: amount must be greater than zero.")
        clean.append({
            "expense_account_id": int(aid),
            "narration": (ln.get("narration") or ln.get("description") or "").strip(),
            "amount": amt,
            "line_no": i + 1,
        })
    bills_total = round(sum(l["amount"] for l in clean), 2)
    cleared = round(bills_total + cash_returned, 2)
    if cleared <= 0:
        raise ValueError("Enter bill amounts and/or cash returned.")

    validate_fiscal_open(str(settle_date))

    with db.get_connection() as conn:
        _ensure_cash_advances_schema(conn)
        adv = conn.execute("SELECT * FROM cash_advances WHERE id=?", (int(advance_id),)).fetchone()
        if not adv:
            raise ValueError("Advance not found.")
        adv = dict(adv)
        if (adv.get("status") or "").lower() in ("settled", "cancelled"):
            raise ValueError(f"Advance {adv['document_no']} is already {adv['status']}.")
        outstanding = round(float(adv.get("outstanding_amount") or 0), 2)
        if cleared - outstanding > 0.01:
            raise ValueError(
                f"Bills ({bills_total:,.2f}) + cash return ({cash_returned:,.2f}) = {cleared:,.2f} "
                f"exceeds outstanding {outstanding:,.2f}."
            )

        adv_aid = int(adv["advance_account_id"])
        pay_mode = (adv.get("payment_mode") or "cash").lower()
        cash_code = gl_account_code("cash")
        cash_id = _acct_id(conn, cash_code) if cash_code else None
        if pay_mode == "cash":
            asset_id = cash_id
        else:
            asset_id = int(adv.get("bank_account_id") or 0) or None
        if bills_total > 0.005:
            if not asset_id:
                raise ValueError("Cash/bank GL account is not configured.")
            if pay_mode == "cash":
                assert_cash_day_open(str(settle_date), "post")

        for ln in clean:
            acc = conn.execute(
                """SELECT a.id, a.code, a.name, g.group_type
                   FROM chart_of_accounts a
                   JOIN account_groups g ON a.account_group_id=g.id
                   WHERE a.id=? AND a.is_active=1""",
                (ln["expense_account_id"],),
            ).fetchone()
            if not acc:
                raise ValueError(f"GL account not found (line {ln['line_no']}).")
            if int(ln["expense_account_id"]) == adv_aid:
                raise ValueError(
                    f"Cannot settle to the advance control account itself "
                    f"({acc['code']}, line {ln['line_no']})."
                )
            if acc["code"] in ("000000", "1000", "100000") or (
                cash_id and int(ln["expense_account_id"]) == int(cash_id)
            ):
                raise ValueError(
                    f"Use **Cash returned** for leftover cash — do not post cash account "
                    f"{acc['code']} on a settlement line (line {ln['line_no']})."
                )
            ln["account_code"] = acc["code"]
            ln["account_name"] = acc["name"]

        settle_doc = ensure_document_no("CAS", None, conn)
        note = (description or "").strip() or (
            f"Settle {adv['document_no']} — {adv['person_name']}"
        )
        ts = now()

        cur = conn.execute(
            """INSERT INTO cash_advance_settlements(
                   document_no, advance_id, settle_date, bills_total, cash_returned,
                   description, created_by, created_at
               ) VALUES (?,?,?,?,?,?,?,?)""",
            (
                settle_doc, int(advance_id), str(settle_date), bills_total, cash_returned,
                note, user_id, ts,
            ),
        )
        settle_id = cur.lastrowid
        cash_doc_nos = []
        for ln in clean:
            line_lbl = ln["narration"] or f"{ln['account_code']} — {ln['account_name']}"
            line_lbl = f"{line_lbl} ({adv['document_no']})"
            ref = f"{settle_doc}-L{ln['line_no']}"
            amt = ln["amount"]
            cash_entry_id = None
            cash_doc = None
            entry_source = None

            if pay_mode == "cash":
                cash_entry_id, cash_doc = db._add_cash_payment(
                    conn, str(settle_date), line_lbl, ref, amt, user_id,
                    party_type="account", party_id=ln["expense_account_id"],
                )
                entry_source = "cash_payment"
            elif pay_mode == "bank":
                cash_entry_id, cash_doc = db._add_bank_payment(
                    conn, str(settle_date), line_lbl, ref, amt, asset_id, user_id,
                    party_type="account", party_id=ln["expense_account_id"],
                )
                entry_source = "bank_payment"
            if cash_doc:
                cash_doc_nos.append(cash_doc)

            conn.execute(
                """INSERT INTO cash_advance_settlement_lines(
                       settlement_id, line_no, expense_account_id, narration, amount,
                       cash_entry_id, cash_doc_no
                   ) VALUES (?,?,?,?,?,?,?)""",
                (
                    settle_id, ln["line_no"], ln["expense_account_id"], ln["narration"], amt,
                    cash_entry_id, cash_doc,
                ),
            )
            # Dr expense / Cr cash (or bank) — Cash Book voucher on cash mode
            post_gl_account_id(
                conn, str(settle_date), ln["expense_account_id"], amt, 0,
                line_lbl, "cash_advance_settlement", settle_id, settle_doc, user_id,
            )
            post_gl_account_id(
                conn, str(settle_date), asset_id, 0, amt,
                line_lbl, "cash_advance_settlement", settle_id, settle_doc, user_id,
            )
            # GL-only: Dr cash / Cr advance — clears shadow advance without Cash Book receipt
            post_gl_account_id(
                conn, str(settle_date), asset_id, amt, 0,
                f"Clear advance — {line_lbl}", "cash_advance_settlement", settle_id, settle_doc, user_id,
            )
            post_gl_account_id(
                conn, str(settle_date), adv_aid, 0, amt,
                f"Clear advance — {line_lbl}", "cash_advance_settlement", settle_id, settle_doc, user_id,
            )

        cash_entry_id = None
        cash_entry_source = None
        cash_doc_no = cash_doc_nos[0] if cash_doc_nos else None
        if cash_doc_nos:
            cash_entry_id = conn.execute(
                """SELECT cash_entry_id FROM cash_advance_settlement_lines
                   WHERE settlement_id=? AND cash_entry_id IS NOT NULL
                   ORDER BY line_no LIMIT 1""",
                (settle_id,),
            ).fetchone()
            cash_entry_id = cash_entry_id[0] if cash_entry_id else None
            cash_entry_source = "cash_payment" if pay_mode == "cash" else "bank_payment"
            conn.execute(
                """UPDATE cash_advance_settlements
                   SET cash_entry_id=?, cash_entry_source=?, cash_doc_no=? WHERE id=?""",
                (cash_entry_id, cash_entry_source, cash_doc_no, settle_id),
            )

        if cash_returned > 0.005:
            ret_lbl = f"Cash returned by {adv['person_name']} ({adv['document_no']})"
            cash_id = _acct_id(conn, gl_account_code("cash"))
            if not cash_id:
                raise ValueError("Cash GL account is not configured.")
            # GL only — cash-advance returns are not Cash Book vouchers.
            post_gl_account_id(
                conn, str(settle_date), cash_id, cash_returned, 0, ret_lbl,
                "cash_advance_settlement", settle_id, settle_doc, user_id,
            )
            post_gl_account_id(
                conn, str(settle_date), adv_aid, 0, cash_returned, ret_lbl,
                "cash_advance_settlement", settle_id, settle_doc, user_id,
            )

        new_bills = round(float(adv.get("settled_bills") or 0) + bills_total, 2)
        new_returned = round(float(adv.get("cash_returned") or 0) + cash_returned, 2)
        new_out = round(float(adv["amount"]) - new_bills - new_returned, 2)
        if new_out < 0:
            new_out = 0.0
        status = "settled" if new_out <= 0.01 else "partial"
        conn.execute(
            """UPDATE cash_advances
               SET settled_bills=?, cash_returned=?, outstanding_amount=?,
                   status=?, modified_by=?, modified_at=?
               WHERE id=?""",
            (new_bills, new_returned, new_out if status != "settled" else 0.0,
             status, user_id, ts, int(advance_id)),
        )
        try:
            from db_audit import log_event
            log_event(
                "cash_advance_settlements", settle_id, "create", user_id=user_id,
                module="Finance", document_no=settle_doc,
                summary=(
                    f"Settled {adv['document_no']}: bills {bills_total:,.2f}, "
                    f"cash return {cash_returned:,.2f}, outstanding {new_out:,.2f}"
                ),
            )
        except Exception:
            pass
        return {
            "id": settle_id,
            "document_no": settle_doc,
            "advance_id": int(advance_id),
            "advance_no": adv["document_no"],
            "bills_total": bills_total,
            "cash_returned": cash_returned,
            "cash_doc_no": cash_doc_no,
            "cash_doc_nos": cash_doc_nos,
            "outstanding_amount": 0.0 if status == "settled" else new_out,
            "status": status,
        }


def backfill_cash_advance_settlement_cash_book(
    settlement_id=None, document_no=None, user_id=None,
):
    """Post missing Cash Book CP for settlements saved under old Dr GL / Cr Advance flow."""
    import database as db
    from database import get_connection

    with get_connection() as conn:
        _ensure_cash_advances_schema(conn)
        if document_no:
            settle = conn.execute(
                "SELECT * FROM cash_advance_settlements WHERE document_no=?",
                (document_no.strip(),),
            ).fetchone()
        elif settlement_id:
            settle = conn.execute(
                "SELECT * FROM cash_advance_settlements WHERE id=?", (int(settlement_id),),
            ).fetchone()
        else:
            raise ValueError("Provide settlement_id or document_no.")
        if not settle:
            raise ValueError("Settlement not found.")
        settle = dict(settle)
        adv = conn.execute(
            "SELECT * FROM cash_advances WHERE id=?", (int(settle["advance_id"]),),
        ).fetchone()
        if not adv:
            raise ValueError("Linked advance not found.")
        adv = dict(adv)
        pay_mode = (adv.get("payment_mode") or "cash").lower()
        if pay_mode != "cash":
            raise ValueError("Backfill is only implemented for cash-mode advances.")
        adv_aid = int(adv["advance_account_id"])
        cash_id = _acct_id(conn, gl_account_code("cash"))
        if not cash_id:
            raise ValueError("Cash GL account is not configured.")

        lines = conn.execute(
            """SELECT l.*, a.code, a.name
               FROM cash_advance_settlement_lines l
               JOIN chart_of_accounts a ON a.id=l.expense_account_id
               WHERE l.settlement_id=? ORDER BY l.line_no""",
            (int(settle["id"]),),
        ).fetchall()
        settle_doc = settle["document_no"]
        settle_id = int(settle["id"])
        posted = []

        for ln in lines:
            ln = dict(ln)
            amt = round(float(ln.get("amount") or 0), 2)
            if amt <= 0 or ln.get("cash_entry_id"):
                continue
            line_lbl = (ln.get("narration") or f"{ln['code']} — {ln['name']}")
            line_lbl = f"{line_lbl} ({adv['document_no']})"
            ref = f"{settle_doc}-L{ln['line_no']}"

            entry_id, cash_doc = db._add_cash_payment(
                conn, str(settle["settle_date"]), line_lbl, ref, amt, user_id,
                party_type="account", party_id=int(ln["expense_account_id"]),
            )
            conn.execute(
                """UPDATE cash_advance_settlement_lines
                   SET cash_entry_id=?, cash_doc_no=? WHERE id=?""",
                (entry_id, cash_doc, int(ln["id"])),
            )

            # Legacy GL was Dr expense / Cr advance — migrate to Dr expense / Cr cash
            # plus GL-only Dr cash / Cr advance (matches new settlement flow).
            cr_row = conn.execute(
                """SELECT id FROM general_ledger
                   WHERE reference_type='cash_advance_settlement'
                     AND reference_id=? AND reference_no=?
                     AND account_id=? AND credit=? AND debit=0
                   LIMIT 1""",
                (settle_id, settle_doc, adv_aid, amt),
            ).fetchone()
            if cr_row:
                conn.execute(
                    "UPDATE general_ledger SET account_id=? WHERE id=?",
                    (cash_id, cr_row["id"]),
                )
                conn.execute(
                    "UPDATE chart_of_accounts SET current_balance=current_balance+? WHERE id=?",
                    (amt, adv_aid),
                )
                conn.execute(
                    "UPDATE chart_of_accounts SET current_balance=current_balance-? WHERE id=?",
                    (amt, cash_id),
                )
                post_gl_account_id(
                    conn, str(settle["settle_date"]), cash_id, amt, 0,
                    f"Clear advance — {line_lbl}",
                    "cash_advance_settlement", settle_id, settle_doc, user_id,
                )
                post_gl_account_id(
                    conn, str(settle["settle_date"]), adv_aid, 0, amt,
                    f"Clear advance — {line_lbl}",
                    "cash_advance_settlement", settle_id, settle_doc, user_id,
                )
            posted.append({"line_no": ln["line_no"], "amount": amt, "cash_doc_no": cash_doc})

        if posted:
            first_entry = conn.execute(
                """SELECT cash_entry_id, cash_doc_no FROM cash_advance_settlement_lines
                   WHERE settlement_id=? AND cash_entry_id IS NOT NULL
                   ORDER BY line_no LIMIT 1""",
                (settle_id,),
            ).fetchone()
            if first_entry:
                conn.execute(
                    """UPDATE cash_advance_settlements
                       SET cash_entry_id=?, cash_entry_source='cash_payment', cash_doc_no=?
                       WHERE id=?""",
                    (
                        first_entry["cash_entry_id"],
                        first_entry["cash_doc_no"],
                        settle_id,
                    ),
                )

        return {
            "settlement_no": settle_doc,
            "advance_no": adv["document_no"],
            "lines_posted": len(posted),
            "cash_doc_nos": [p["cash_doc_no"] for p in posted],
        }


def backfill_all_cash_advance_settlement_cash_books(user_id=None):
    """Backfill Cash Book CP for every settlement line missing a cash voucher."""
    from database import get_connection

    with get_connection() as conn:
        _ensure_cash_advances_schema(conn)
        rows = conn.execute(
            """SELECT DISTINCT s.id, s.document_no
               FROM cash_advance_settlements s
               JOIN cash_advance_settlement_lines l ON l.settlement_id=s.id
               WHERE s.bills_total > 0
                 AND l.cash_entry_id IS NULL
                 AND l.amount > 0"""
        ).fetchall()
    return [
        backfill_cash_advance_settlement_cash_book(settlement_id=r["id"], user_id=user_id)
        for r in rows
    ]


def detach_cash_advance_issue_from_cash_book(advance_id=None, document_no=None, user_id=None):
    """Remove legacy issue CP/BP from Cash Book; advance stays open in register (shadow)."""
    import database as db
    from database import get_connection

    with get_connection() as conn:
        _ensure_cash_advances_schema(conn)
        if document_no:
            adv = conn.execute(
                "SELECT * FROM cash_advances WHERE document_no=?", (document_no.strip(),),
            ).fetchone()
        elif advance_id:
            adv = conn.execute(
                "SELECT * FROM cash_advances WHERE id=?", (int(advance_id),),
            ).fetchone()
        else:
            raise ValueError("Provide advance_id or document_no.")
        if not adv:
            raise ValueError("Cash advance not found.")
        adv = dict(adv)
        entry_id = adv.get("issue_entry_id")
        src = (adv.get("issue_entry_source") or "").lower()
        deleted = False
        if entry_id:
            if src == "cash_payment":
                conn.execute("DELETE FROM cash_payments WHERE id=?", (entry_id,))
                deleted = True
            elif src == "bank_payment":
                conn.execute("DELETE FROM bank_payments WHERE id=?", (entry_id,))
                deleted = True
        elif adv.get("issue_doc_no"):
            doc = adv["issue_doc_no"]
            if doc and doc != adv.get("document_no"):
                if conn.execute(
                    "DELETE FROM cash_payments WHERE document_no=?", (doc,)
                ).rowcount:
                    deleted = True
                elif conn.execute(
                    "DELETE FROM bank_payments WHERE document_no=?", (doc,)
                ).rowcount:
                    deleted = True
        conn.execute(
            """UPDATE cash_advances
               SET issue_entry_id=NULL, issue_entry_source=NULL, issue_doc_no=?
               WHERE id=?""",
            (adv["document_no"], int(adv["id"])),
        )
        try:
            from db_audit import log_event
            log_event(
                "cash_advances", int(adv["id"]), "update", user_id=user_id, module="Finance",
                document_no=adv["document_no"],
                summary=(
                    f"Detached issue voucher from Cash Book for {adv['document_no']} "
                    f"(shadow advance only)."
                ),
            )
        except Exception:
            pass
        return {
            "document_no": adv["document_no"],
            "cash_book_voucher_removed": deleted,
            "outstanding_amount": float(adv.get("outstanding_amount") or 0),
        }


def detach_all_cash_advance_issues_from_cash_book(user_id=None):
    """Detach every advance whose issue voucher is still linked to Cash Book."""
    from database import get_connection

    with get_connection() as conn:
        _ensure_cash_advances_schema(conn)
        rows = conn.execute(
            """SELECT id, document_no FROM cash_advances
               WHERE issue_entry_id IS NOT NULL
                  OR (issue_doc_no IS NOT NULL AND issue_doc_no != document_no)"""
        ).fetchall()
    results = []
    for r in rows:
        results.append(
            detach_cash_advance_issue_from_cash_book(advance_id=r["id"], user_id=user_id)
        )
    return results


def revert_all_cash_advance_cash_book(user_id=None):
    """Remove cash book vouchers + GL posted for cash advances; reset advance register.

    Deletes settlement cash receipts and issue cash payments linked to cash_advances.
    Clears settlements and restores each advance to **open** with full outstanding.
  """
    import database as db
    from database import get_connection

    report = {
        "settlements_removed": 0,
        "cash_receipts_deleted": 0,
        "cash_payments_deleted": 0,
        "gl_rows_deleted": 0,
        "advances_reset": 0,
    }
    with get_connection() as conn:
        _ensure_cash_advances_schema(conn)
        settlements = conn.execute(
            "SELECT * FROM cash_advance_settlements ORDER BY id DESC"
        ).fetchall()
        for s in settlements:
            s = dict(s)
            sid = int(s["id"])
            settle_doc = s.get("document_no") or ""
            report["gl_rows_deleted"] += _delete_gl_reference(
                conn, "cash_advance_settlement", ref_id=sid,
            )
            if settle_doc:
                report["gl_rows_deleted"] += _delete_gl_reference(
                    conn, "cash_advance_settlement", ref_no=settle_doc,
                )
            entry_id = s.get("cash_entry_id")
            if entry_id:
                src = (s.get("cash_entry_source") or "").lower()
                cash_doc = (s.get("cash_doc_no") or "").strip()
                # Require document_no match — bare id can collide with unrelated vouchers.
                if src == "cash_receipt" and cash_doc.startswith("CR-"):
                    cur = conn.execute(
                        "DELETE FROM cash_receipts WHERE id=? AND document_no=?",
                        (entry_id, cash_doc),
                    )
                    report["cash_receipts_deleted"] += cur.rowcount
                elif src == "bank_receipt" and cash_doc:
                    cur = conn.execute(
                        "DELETE FROM bank_receipts WHERE id=? AND document_no=?",
                        (entry_id, cash_doc),
                    )
                    report["cash_receipts_deleted"] += cur.rowcount
            conn.execute(
                "DELETE FROM cash_advance_settlement_lines WHERE settlement_id=?", (sid,),
            )
            conn.execute("DELETE FROM cash_advance_settlements WHERE id=?", (sid,))
            report["settlements_removed"] += 1

        advances = conn.execute("SELECT * FROM cash_advances ORDER BY id").fetchall()
        for adv in advances:
            adv = dict(adv)
            aid = int(adv["id"])
            adv_doc = adv.get("document_no") or ""
            report["gl_rows_deleted"] += _delete_gl_reference(
                conn, "cash_advance", ref_id=aid,
            )
            if adv_doc:
                report["gl_rows_deleted"] += _delete_gl_reference(
                    conn, "cash_advance", ref_no=adv_doc,
                )
            entry_id = adv.get("issue_entry_id")
            if entry_id:
                src = (adv.get("issue_entry_source") or "").lower()
                issue_doc = (adv.get("issue_doc_no") or "").strip()
                if src == "cash_payment" and issue_doc:
                    cur = conn.execute(
                        "DELETE FROM cash_payments WHERE id=? AND document_no=?",
                        (entry_id, issue_doc),
                    )
                    report["cash_payments_deleted"] += cur.rowcount
                elif src == "bank_payment" and issue_doc:
                    cur = conn.execute(
                        "DELETE FROM bank_payments WHERE id=? AND document_no=?",
                        (entry_id, issue_doc),
                    )
                    report["cash_payments_deleted"] += cur.rowcount
            amt = round(float(adv.get("amount") or 0), 2)
            conn.execute(
                """UPDATE cash_advances
                   SET settled_bills=0, cash_returned=0, outstanding_amount=?,
                       status='open', issue_entry_id=NULL, issue_entry_source=NULL,
                       issue_doc_no=NULL, modified_by=?, modified_at=?
                   WHERE id=?""",
                (amt, user_id, now(), aid),
            )
            report["advances_reset"] += 1

        try:
            from db_audit import log_event
            log_event(
                "cash_advances", None, "revert_cash_book", user_id=user_id, module="Finance",
                summary=(
                    f"Reverted cash advance cash book: {report['cash_payments_deleted']} payments, "
                    f"{report['cash_receipts_deleted']} receipts, {report['settlements_removed']} settlements"
                ),
            )
        except Exception:
            pass
    return report


def get_cash_advance(advance_id):
    from database import get_connection, row_to_dict, rows_to_list
    with get_connection() as conn:
        _ensure_cash_advances_schema(conn)
        h = row_to_dict(conn.execute(
            """SELECT a.*, c.code AS advance_account_code, c.name AS advance_account_name
               FROM cash_advances a
               LEFT JOIN chart_of_accounts c ON a.advance_account_id=c.id
               WHERE a.id=?""",
            (advance_id,),
        ).fetchone())
        if not h:
            return None
        settlements = rows_to_list(conn.execute(
            """SELECT * FROM cash_advance_settlements
               WHERE advance_id=? ORDER BY settle_date, id""",
            (advance_id,),
        ).fetchall())
        for s in settlements:
            s["lines"] = rows_to_list(conn.execute(
                """SELECT l.*, acc.code AS expense_code, acc.name AS expense_name
                   FROM cash_advance_settlement_lines l
                   JOIN chart_of_accounts acc ON l.expense_account_id=acc.id
                   WHERE l.settlement_id=? ORDER BY l.line_no, l.id""",
                (s["id"],),
            ).fetchall())
        h["settlements"] = settlements
        return h


def search_cash_advances(
    q=None, status=None, from_date=None, to_date=None,
    page=1, page_size=50, export_all=False, open_only=False,
):
    from database import get_connection, rows_to_list
    page = max(1, int(page or 1))
    page_size = min(200, max(5, int(page_size or 50)))
    where = ["1=1"]
    params: list = []
    if open_only:
        where.append("a.status IN ('open','partial')")
    elif status and status != "all":
        where.append("a.status=?")
        params.append(status)
    if from_date:
        where.append("a.issue_date>=?")
        params.append(from_date)
    if to_date:
        where.append("a.issue_date<=?")
        params.append(to_date)
    if q:
        like = f"%{q.strip()}%"
        where.append(
            "(a.document_no LIKE ? OR a.person_name LIKE ? OR COALESCE(a.purpose,'') LIKE ? "
            "OR COALESCE(a.issue_doc_no,'') LIKE ?)"
        )
        params.extend([like, like, like, like])
    clause = " AND ".join(where)
    with get_connection() as conn:
        _ensure_cash_advances_schema(conn)
        total = int(conn.execute(
            f"SELECT COUNT(*) FROM cash_advances a WHERE {clause}", params,
        ).fetchone()[0])
        sql = f"""
            SELECT a.*, c.code AS advance_account_code, c.name AS advance_account_name
            FROM cash_advances a
            LEFT JOIN chart_of_accounts c ON a.advance_account_id=c.id
            WHERE {clause}
            ORDER BY a.issue_date DESC, a.id DESC
        """
        if export_all:
            return rows_to_list(conn.execute(sql, params).fetchall())
        offset = (page - 1) * page_size
        rows = rows_to_list(
            conn.execute(sql + " LIMIT ? OFFSET ?", [*params, page_size, offset]).fetchall()
        )
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


def search_expense_payments(q=None, expense_account_id=None, from_date=None, to_date=None, page=1, page_size=50, export_all=False):
    """List expense payments from cash and bank books."""
    from database import run_paginated_list
    from_clause = """
        (
            SELECT cp.id, cp.document_no, cp.payment_date AS txn_date, cp.amount, cp.description, cp.reference_no,
                   'cash' AS payment_mode, 'cash_payment' AS vch_source,
                   cp.party_id AS expense_account_id,
                   a.code AS expense_code, a.name AS expense_name, cp.created_at
            FROM cash_payments cp
            JOIN chart_of_accounts a ON cp.party_id=a.id
            WHERE cp.party_type='expense'
            UNION ALL
            SELECT bp.id, bp.document_no, bp.payment_date AS txn_date, bp.amount, bp.description, bp.reference_no,
                   'bank' AS payment_mode, 'bank_payment' AS vch_source,
                   bp.party_id AS expense_account_id,
                   a.code AS expense_code, a.name AS expense_name, bp.created_at
            FROM bank_payments bp
            JOIN chart_of_accounts a ON bp.party_id=a.id
            WHERE bp.party_type='expense'
        ) t
    """
    where, params = [], []
    if expense_account_id:
        where.append("expense_account_id=?"); params.append(expense_account_id)
    if from_date:
        where.append("txn_date>=?"); params.append(from_date)
    if to_date:
        where.append("txn_date<=?"); params.append(to_date)
    if q:
        like = f"%{q.strip()}%"
        where.append("(document_no LIKE ? OR expense_name LIKE ? OR expense_code LIKE ? OR description LIKE ? OR reference_no LIKE ?)")
        params.extend([like, like, like, like, like])
    return run_paginated_list(
        from_clause,
        "id, document_no, txn_date, amount, description, reference_no, payment_mode, vch_source, expense_account_id, expense_code, expense_name, created_at",
        where or None,
        params,
        "txn_date DESC, id DESC",
        page,
        page_size,
        export_all=export_all,
    )


def close_pl_to_equity(close_date, from_date=None, to_date=None, user_id=None, description=""):
    """Transfer net P&L for a period to retained earnings via GL."""
    import database as db
    fd = from_date or "1900-01-01"
    td = to_date or close_date
    pl = db.get_profit_loss(fd, td)
    net = round(float(pl.get("net_profit") or 0), 2)
    if abs(net) < 0.01:
        raise ValueError("Net profit/loss is zero — nothing to close for this period.")
    equity_code = gl_account_code("equity") or "3000"
    clearing_code = gl_account_code("pl_clearing") or "3999"
    ref = f"PL-CLOSE-{td}"
    label = description or f"P&L close {fd} to {td} (net {'profit' if net > 0 else 'loss'} Rs. {abs(net):,.2f})"
    with db.get_connection() as conn:
        existing = conn.execute(
            "SELECT 1 FROM general_ledger WHERE reference_type='pl_close' AND reference_no=? LIMIT 1",
            (ref,),
        ).fetchone()
        if existing:
            raise ValueError(f"P&L already closed for period ending {td} (reference {ref}).")
        if net > 0:
            post_gl(conn, close_date, clearing_code, net, 0, label, "pl_close", 0, ref, user_id)
            post_gl(conn, close_date, equity_code, 0, net, label, "pl_close", 0, ref, user_id)
        else:
            loss = abs(net)
            post_gl(conn, close_date, equity_code, loss, 0, label, "pl_close", 0, ref, user_id)
            post_gl(conn, close_date, clearing_code, 0, loss, label, "pl_close", 0, ref, user_id)
    return {"reference_no": ref, "net_profit": net, "from_date": fd, "to_date": td}


# ---------------------------------------------------------------------------
# Fiscal year
# ---------------------------------------------------------------------------

def validate_fiscal_open(txn_date, ref_type=None):
    """Block GL/cash posting into a closed fiscal year."""
    if ref_type in ("pl_close", "fiscal_reopen", "party_transfer"):
        return None
    from database import get_connection, row_to_dict
    if not txn_date:
        return None
    with get_connection() as conn:
        if not conn.execute("SELECT 1 FROM fiscal_years LIMIT 1").fetchone():
            return None
        row = conn.execute(
            """SELECT id, fy_code, is_closed FROM fiscal_years
               WHERE ? >= start_date AND ? <= end_date ORDER BY id DESC LIMIT 1""",
            (str(txn_date), str(txn_date)),
        ).fetchone()
        if row and row["is_closed"]:
            raise ValueError(
                f"Fiscal year **{row['fy_code']}** is closed — cannot post transactions dated {txn_date}."
            )
        return row_to_dict(row) if row else None


def get_fiscal_years():
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            """SELECT fy.*, u.full_name AS closed_by_name
               FROM fiscal_years fy
               LEFT JOIN users u ON fy.closed_by=u.id
               ORDER BY fy.start_date DESC"""
        ).fetchall())


def get_active_fiscal_year():
    from database import get_connection, row_to_dict
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM fiscal_years WHERE is_active=1 AND is_closed=0 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row_to_dict(row) if row else None


def get_fiscal_year(fy_id):
    from database import get_connection, row_to_dict
    with get_connection() as conn:
        return row_to_dict(conn.execute("SELECT * FROM fiscal_years WHERE id=?", (fy_id,)).fetchone())


def suggest_next_fiscal_year():
    from datetime import timedelta
    rows = get_fiscal_years()
    if not rows:
        y = datetime.now().year
        return str(y), f"{y}-01-01", f"{y}-12-31"
    last = rows[0]
    try:
        end = datetime.strptime(last["end_date"], "%Y-%m-%d").date()
        start = end + timedelta(days=1)
        next_end = start.replace(year=start.year + 1) - timedelta(days=1)
        code = str(int(last["fy_code"]) + 1) if str(last["fy_code"]).isdigit() else str(start.year)
        return code, start.isoformat(), next_end.isoformat()
    except ValueError:
        y = datetime.now().year + 1
        return str(y), f"{y}-01-01", f"{y}-12-31"


def create_fiscal_year(fy_code, start_date, end_date, user_id=None, make_active=True):
    from database import get_connection
    code = (fy_code or "").strip()
    if not code:
        raise ValueError("Fiscal year code is required.")
    if start_date >= end_date:
        raise ValueError("Start date must be before end date.")
    with get_connection() as conn:
        overlap = conn.execute(
            """SELECT fy_code FROM fiscal_years
               WHERE NOT (? > end_date OR ? < start_date) LIMIT 1""",
            (start_date, end_date),
        ).fetchone()
        if overlap:
            raise ValueError(f"Dates overlap with fiscal year {overlap['fy_code']}.")
        if make_active:
            conn.execute("UPDATE fiscal_years SET is_active=0")
        cur = conn.execute(
            "INSERT INTO fiscal_years(fy_code, start_date, end_date, is_active, is_closed, created_by) VALUES(?,?,?,?,0,?)",
            (code, start_date, end_date, 1 if make_active else 0, user_id),
        )
        return cur.lastrowid


def set_active_fiscal_year(fy_id, user_id=None):
    from database import get_connection
    with get_connection() as conn:
        fy = conn.execute("SELECT * FROM fiscal_years WHERE id=?", (fy_id,)).fetchone()
        if not fy:
            raise ValueError("Fiscal year not found.")
        if fy["is_closed"]:
            raise ValueError(f"Fiscal year {fy['fy_code']} is closed — create or activate an open year.")
        conn.execute("UPDATE fiscal_years SET is_active=0")
        conn.execute("UPDATE fiscal_years SET is_active=1 WHERE id=?", (fy_id,))


def get_fiscal_close_checklist(fy_id):
    """Pre-close validation checklist for a fiscal year."""
    from database import get_connection, row_to_dict
    fy = get_fiscal_year(fy_id)
    if not fy:
        raise ValueError("Fiscal year not found.")
    fd, td = fy["start_date"], fy["end_date"]
    blockers = []
    with get_connection() as conn:
        def _cnt(sql, params):
            return int(conn.execute(sql, params).fetchone()[0])

        draft_sales = _cnt(
            "SELECT COUNT(*) FROM sales_invoices WHERE invoice_date BETWEEN ? AND ? AND status IN ('draft','rejected')",
            (fd, td),
        )
        pending_sales = _cnt(
            "SELECT COUNT(*) FROM sales_invoices WHERE invoice_date BETWEEN ? AND ? AND status='pending_approval'",
            (fd, td),
        )
        draft_purchases = _cnt(
            "SELECT COUNT(*) FROM purchase_invoices WHERE invoice_date BETWEEN ? AND ? AND status IN ('draft','rejected')",
            (fd, td),
        )
        pending_purchases = _cnt(
            "SELECT COUNT(*) FROM purchase_invoices WHERE invoice_date BETWEEN ? AND ? AND status='pending_approval'",
            (fd, td),
        )
        draft_journals = _cnt(
            "SELECT COUNT(*) FROM journal_vouchers WHERE voucher_date BETWEEN ? AND ? AND status='draft'",
            (fd, td),
        )
        draft_grn = _cnt(
            "SELECT COUNT(*) FROM goods_receipt_notes WHERE grn_date BETWEEN ? AND ? AND status='draft'",
            (fd, td),
        ) if conn.execute("SELECT 1 FROM sqlite_master WHERE name='goods_receipt_notes'").fetchone() else 0

        for label, n in [
            ("draft/rejected sales invoice(s)", draft_sales),
            ("sales invoice(s) pending approval", pending_sales),
            ("draft/rejected purchase invoice(s)", draft_purchases),
            ("purchase invoice(s) pending approval", pending_purchases),
            ("draft journal voucher(s)", draft_journals),
            ("draft GRN(s)", draft_grn),
        ]:
            if n:
                blockers.append(f"{n} {label} in period")

        gl = conn.execute(
            "SELECT COALESCE(SUM(debit),0), COALESCE(SUM(credit),0) FROM general_ledger WHERE entry_date BETWEEN ? AND ?",
            (fd, td),
        ).fetchone()
        gl_debits, gl_credits = float(gl[0] or 0), float(gl[1] or 0)
        trial_ok = abs(gl_debits - gl_credits) < 0.02
        if not trial_ok:
            blockers.append(
                f"General ledger not balanced for period (debits {gl_debits:,.2f} vs credits {gl_credits:,.2f})"
            )

        pl_ref = f"PL-CLOSE-{td}"
        pl_closed = conn.execute(
            "SELECT 1 FROM general_ledger WHERE reference_type='pl_close' AND reference_no=? LIMIT 1",
            (pl_ref,),
        ).fetchone() is not None

    recon = get_control_account_reconciliation(as_of=td)
    if abs(recon["ar_difference"]) >= 0.01:
        blockers.append(f"AR control vs customer sub-ledger difference: {recon['ar_difference']:,.2f}")
    if abs(recon["ap_difference"]) >= 0.01:
        blockers.append(f"AP control vs supplier sub-ledger difference: {recon['ap_difference']:,.2f}")

    import database as db
    pl = db.get_profit_loss(fd, td)
    net_profit = round(float(pl.get("net_profit") or 0), 2)

    if fy["is_closed"]:
        blockers.append("Fiscal year is already closed.")

    return {
        "fiscal_year": fy,
        "draft_sales": draft_sales,
        "pending_sales": pending_sales,
        "draft_purchases": draft_purchases,
        "pending_purchases": pending_purchases,
        "draft_journals": draft_journals,
        "draft_grn": draft_grn,
        "gl_debits": gl_debits,
        "gl_credits": gl_credits,
        "trial_balance_ok": trial_ok,
        "ar_difference": recon["ar_difference"],
        "ap_difference": recon["ap_difference"],
        "net_profit": net_profit,
        "pl_already_closed": pl_closed,
        "can_close": len(blockers) == 0,
        "blockers": blockers,
    }


def close_fiscal_year(fy_id, user_id, description="", transfer_pl=True):
    """Close fiscal year: P&L to equity, lock period, audit log."""
    chk = get_fiscal_close_checklist(fy_id)
    if not chk["can_close"]:
        raise ValueError("Cannot close fiscal year:\n• " + "\n• ".join(chk["blockers"]))
    fy = chk["fiscal_year"]
    pl_res = None
    if transfer_pl and abs(chk["net_profit"]) >= 0.01 and not chk["pl_already_closed"]:
        pl_res = close_pl_to_equity(
            fy["end_date"], fy["start_date"], fy["end_date"], user_id,
            description or f"Fiscal year {fy['fy_code']} close",
        )
    elif chk["pl_already_closed"]:
        pl_res = {"reference_no": f"PL-CLOSE-{fy['end_date']}", "net_profit": chk["net_profit"]}

    from database import get_connection
    note = f"\nClosed: {(description or '').strip()}"
    with get_connection() as conn:
        conn.execute(
            """UPDATE fiscal_years SET is_closed=1, is_active=0, closed_by=?, closed_at=?,
               pl_close_ref=?, net_profit=?, notes=COALESCE(notes,'') || ? WHERE id=?""",
            (
                user_id, now(),
                pl_res["reference_no"] if pl_res else None,
                chk["net_profit"],
                note, fy_id,
            ),
        )
        conn.execute(
            "INSERT INTO fiscal_closure_log(fiscal_year_id, action, reason, user_id) VALUES(?,?,?,?)",
            (fy_id, "close", description or "Fiscal year closed", user_id),
        )
    try:
        from db_audit import log_event
        log_event(
            "fiscal_years", fy_id, "close", user_id=user_id, module="Finance",
            document_no=fy["fy_code"],
            summary=f"Closed fiscal year {fy['fy_code']}",
            details={"net_profit": chk["net_profit"], "description": description},
        )
    except Exception:
        pass
    return {
        "fy_code": fy["fy_code"],
        "pl_close": pl_res,
        "net_profit": chk["net_profit"],
    }


def reopen_fiscal_year(fy_id, user_id, reason):
    """Admin reopen of a closed fiscal year (audit logged)."""
    from database import get_connection
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("Reason is required to reopen a closed fiscal year.")
    with get_connection() as conn:
        fy = conn.execute("SELECT * FROM fiscal_years WHERE id=?", (fy_id,)).fetchone()
        if not fy:
            raise ValueError("Fiscal year not found.")
        if not fy["is_closed"]:
            raise ValueError(f"Fiscal year {fy['fy_code']} is not closed.")
        conn.execute(
            "UPDATE fiscal_years SET is_closed=0, closed_by=NULL, closed_at=NULL WHERE id=?",
            (fy_id,),
        )
        conn.execute(
            "INSERT INTO fiscal_closure_log(fiscal_year_id, action, reason, user_id) VALUES(?,?,?,?)",
            (fy_id, "reopen", reason, user_id),
        )
    try:
        from db_audit import log_event
        log_event(
            "fiscal_years", fy_id, "reopen", user_id=user_id, module="Finance",
            document_no=fy["fy_code"], summary=f"Reopened fiscal year {fy['fy_code']}",
            details={"reason": reason},
        )
    except Exception:
        pass
    return fy["fy_code"]


def get_fiscal_closure_log(fy_id=None, limit=50):
    from database import get_connection, rows_to_list
    q = """SELECT l.*, fy.fy_code, u.full_name AS user_name
           FROM fiscal_closure_log l
           JOIN fiscal_years fy ON l.fiscal_year_id=fy.id
           LEFT JOIN users u ON l.user_id=u.id WHERE 1=1"""
    p = []
    if fy_id:
        q += " AND l.fiscal_year_id=?"; p.append(fy_id)
    q += " ORDER BY l.created_at DESC LIMIT ?"; p.append(limit)
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


PARTY_TRANSFER_TYPES = {
    "customer_to_customer": "Customer → Customer (balance transfer)",
    "supplier_to_supplier": "Supplier → Supplier (balance transfer)",
    "customer_to_supplier": "Customer ↔ Supplier (set-off / adjustment)",
}


def _party_label(conn, party_type, party_id):
    if party_type == "customer":
        r = conn.execute("SELECT code, name FROM customers WHERE id=?", (party_id,)).fetchone()
    elif party_type == "supplier":
        r = conn.execute("SELECT code, name FROM suppliers WHERE id=?", (party_id,)).fetchone()
    else:
        return "—", "—"
    if not r:
        return "—", "—"
    return r["code"], r["name"]


def record_party_transfer(transfer_type, from_party_type, from_party_id, to_party_type, to_party_id,
                          amount, transfer_date, reference_no="", description="", user_id=None):
    """Transfer balance between parties without cash — set-off posts AR/AP GL."""
    import database as db
    if transfer_type not in PARTY_TRANSFER_TYPES:
        raise ValueError("Invalid transfer type.")
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    if from_party_id == to_party_id and from_party_type == to_party_type:
        raise ValueError("From and To party must be different.")
    validate_fiscal_open(transfer_date, ref_type="party_transfer")
    expected = {
        "customer_to_customer": ("customer", "customer"),
        "supplier_to_supplier": ("supplier", "supplier"),
        "customer_to_supplier": (("customer", "supplier"), ("supplier", "customer")),
    }
    ok = expected[transfer_type]
    if transfer_type == "customer_to_supplier":
        pair = (from_party_type, to_party_type)
        if pair not in ok:
            raise ValueError("Set-off requires one customer and one supplier.")
    elif (from_party_type, to_party_type) != ok:
        raise ValueError(f"Transfer type {transfer_type} requires {ok[0]} → {ok[1]}.")
    with db.get_connection() as conn:
        doc_no = db.ensure_document_no("PT", None, conn)
        fc, fn = _party_label(conn, from_party_type, from_party_id)
        tc, tn = _party_label(conn, to_party_type, to_party_id)
        from_lbl = f"{fc} - {fn}"
        to_lbl = f"{tc} - {tn}"
        if transfer_type == "customer_to_supplier":
            auto = f"Set-off: {from_lbl} / {to_lbl}"
        elif transfer_type == "customer_to_customer":
            auto = f"Customer transfer: {from_lbl} → {to_lbl}"
        else:
            auto = f"Supplier transfer: {from_lbl} → {to_lbl}"
        label = f"{auto} — {description.strip()}" if description.strip() else auto
        if transfer_type == "customer_to_customer":
            conn.execute(
                "UPDATE customers SET current_balance=current_balance-?, modified_at=? WHERE id=?",
                (amount, now(), from_party_id),
            )
            conn.execute(
                "UPDATE customers SET current_balance=current_balance+?, modified_at=? WHERE id=?",
                (amount, now(), to_party_id),
            )
        elif transfer_type == "supplier_to_supplier":
            # Ledger: from = Debit (+Dr), to = Credit (−Cr)
            conn.execute(
                "UPDATE suppliers SET current_balance=current_balance+?, modified_at=? WHERE id=?",
                (amount, now(), from_party_id),
            )
            conn.execute(
                "UPDATE suppliers SET current_balance=current_balance-?, modified_at=? WHERE id=?",
                (amount, now(), to_party_id),
            )
        else:
            cust_id = from_party_id if from_party_type == "customer" else to_party_id
            sup_id = from_party_id if from_party_type == "supplier" else to_party_id
            conn.execute(
                "UPDATE customers SET current_balance=current_balance-?, modified_at=? WHERE id=?",
                (amount, now(), cust_id),
            )
            # Set-off credits customer AR and debits supplier (reduces payable → +Dr)
            conn.execute(
                "UPDATE suppliers SET current_balance=current_balance+?, modified_at=? WHERE id=?",
                (amount, now(), sup_id),
            )
            post_gl(conn, transfer_date, gl_account_code("ap"), amount, 0, label, "party_transfer", 0, doc_no, user_id)
            post_gl(conn, transfer_date, gl_account_code("ar"), 0, amount, label, "party_transfer", 0, doc_no, user_id)
        cur = conn.execute(
            """INSERT INTO party_transfers(document_no, transfer_date, transfer_type,
               from_party_type, from_party_id, to_party_type, to_party_id, amount,
               reference_no, description, created_by, created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (doc_no, transfer_date, transfer_type, from_party_type, from_party_id,
             to_party_type, to_party_id, amount, reference_no, label, user_id, now()),
        )
        tid = cur.lastrowid
        # Fix set-off GL reference_id from 0 → transfer id (legacy rows still reverse by document_no)
        if transfer_type == "customer_to_supplier":
            conn.execute(
                """UPDATE general_ledger SET reference_id=?
                   WHERE reference_type='party_transfer' AND reference_no=? AND reference_id=0""",
                (tid, doc_no),
            )
        return {"id": tid, "document_no": doc_no}


def _apply_party_transfer_balances(conn, transfer_type, from_party_type, from_party_id,
                                   to_party_type, to_party_id, amount, *, reverse=False):
    """Apply or reverse party sub-ledger effects for a transfer."""
    sign = -1 if reverse else 1
    amt = float(amount) * sign
    if transfer_type == "customer_to_customer":
        conn.execute(
            "UPDATE customers SET current_balance=current_balance-?, modified_at=? WHERE id=?",
            (amt, now(), from_party_id),
        )
        conn.execute(
            "UPDATE customers SET current_balance=current_balance+?, modified_at=? WHERE id=?",
            (amt, now(), to_party_id),
        )
    elif transfer_type == "supplier_to_supplier":
        conn.execute(
            "UPDATE suppliers SET current_balance=current_balance+?, modified_at=? WHERE id=?",
            (amt, now(), from_party_id),
        )
        conn.execute(
            "UPDATE suppliers SET current_balance=current_balance-?, modified_at=? WHERE id=?",
            (amt, now(), to_party_id),
        )
    else:
        cust_id = from_party_id if from_party_type == "customer" else to_party_id
        sup_id = from_party_id if from_party_type == "supplier" else to_party_id
        conn.execute(
            "UPDATE customers SET current_balance=current_balance-?, modified_at=? WHERE id=?",
            (amt, now(), cust_id),
        )
        conn.execute(
            "UPDATE suppliers SET current_balance=current_balance+?, modified_at=? WHERE id=?",
            (amt, now(), sup_id),
        )


def reverse_party_transfer(transfer_id, user_id, reason=""):
    """Undo party transfer balances / GL and delete the voucher."""
    from database import get_connection
    from erp_core.period_lock import assert_period_open

    t = get_party_transfer(transfer_id)
    if not t:
        raise ValueError("Party transfer not found.")
    assert_period_open(str(t["transfer_date"]), user_id, action="edit")
    with get_connection() as conn:
        _apply_party_transfer_balances(
            conn, t["transfer_type"], t["from_party_type"], t["from_party_id"],
            t["to_party_type"], t["to_party_id"], t["amount"], reverse=True,
        )
        if t["transfer_type"] == "customer_to_supplier":
            _delete_gl_reference(conn, "party_transfer", ref_id=int(transfer_id))
            _delete_gl_reference(conn, "party_transfer", ref_no=t.get("document_no"))
        conn.execute("DELETE FROM party_transfers WHERE id=?", (transfer_id,))
    try:
        from db_audit import log_event
        log_event(
            "party_transfers", transfer_id, "delete", user_id=user_id, module="Finance",
            document_no=t.get("document_no"),
            summary=f"Deleted party transfer {t.get('document_no')}" + (f" — {reason}" if reason else ""),
        )
    except Exception:
        pass


def update_party_transfer(transfer_id, transfer_type, from_party_type, from_party_id,
                          to_party_type, to_party_id, amount, transfer_date,
                          reference_no="", description="", user_id=None):
    """Replace an existing party transfer with updated parties/amount/date (same document no)."""
    from database import get_connection
    from erp_core.period_lock import assert_period_open

    old = get_party_transfer(transfer_id)
    if not old:
        raise ValueError("Party transfer not found.")
    if transfer_type not in PARTY_TRANSFER_TYPES:
        raise ValueError("Invalid transfer type.")
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    if from_party_id == to_party_id and from_party_type == to_party_type:
        raise ValueError("From and To party must be different.")
    assert_period_open(str(old["transfer_date"]), user_id, action="edit")
    assert_period_open(str(transfer_date), user_id, action="post")
    validate_fiscal_open(transfer_date, ref_type="party_transfer")

    with get_connection() as conn:
        # Undo old effects
        _apply_party_transfer_balances(
            conn, old["transfer_type"], old["from_party_type"], old["from_party_id"],
            old["to_party_type"], old["to_party_id"], old["amount"], reverse=True,
        )
        if old["transfer_type"] == "customer_to_supplier":
            _delete_gl_reference(conn, "party_transfer", ref_id=int(transfer_id))
            _delete_gl_reference(conn, "party_transfer", ref_no=old.get("document_no"))

        doc_no = old["document_no"]
        fc, fn = _party_label(conn, from_party_type, from_party_id)
        tc, tn = _party_label(conn, to_party_type, to_party_id)
        from_lbl = f"{fc} - {fn}"
        to_lbl = f"{tc} - {tn}"
        if transfer_type == "customer_to_supplier":
            auto = f"Set-off: {from_lbl} / {to_lbl}"
        elif transfer_type == "customer_to_customer":
            auto = f"Customer transfer: {from_lbl} → {to_lbl}"
        else:
            auto = f"Supplier transfer: {from_lbl} → {to_lbl}"
        label = f"{auto} — {description.strip()}" if (description or "").strip() else auto

        _apply_party_transfer_balances(
            conn, transfer_type, from_party_type, from_party_id,
            to_party_type, to_party_id, amount, reverse=False,
        )
        if transfer_type == "customer_to_supplier":
            post_gl(conn, transfer_date, gl_account_code("ap"), amount, 0, label,
                    "party_transfer", transfer_id, doc_no, user_id)
            post_gl(conn, transfer_date, gl_account_code("ar"), 0, amount, label,
                    "party_transfer", transfer_id, doc_no, user_id)

        conn.execute(
            """UPDATE party_transfers SET transfer_date=?, transfer_type=?,
               from_party_type=?, from_party_id=?, to_party_type=?, to_party_id=?,
               amount=?, reference_no=?, description=? WHERE id=?""",
            (transfer_date, transfer_type, from_party_type, from_party_id,
             to_party_type, to_party_id, amount, reference_no or "", label, transfer_id),
        )
    try:
        from db_audit import log_event
        log_event(
            "party_transfers", transfer_id, "update", user_id=user_id, module="Finance",
            document_no=doc_no,
            summary=f"Updated party transfer {doc_no}",
        )
    except Exception:
        pass
    return {"id": transfer_id, "document_no": doc_no}


def get_party_transfer(transfer_id):
    from database import get_connection, row_to_dict
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM party_transfers WHERE id=?", (transfer_id,)).fetchone()
        if not row:
            return None
        t = row_to_dict(row)
        fc, fn = _party_label(conn, t["from_party_type"], t["from_party_id"])
        tc, tn = _party_label(conn, t["to_party_type"], t["to_party_id"])
        t["from_party_code"] = fc
        t["from_party_name"] = fn
        t["to_party_code"] = tc
        t["to_party_name"] = tn
        return t


def search_party_transfers(q=None, from_date=None, to_date=None, page=1, page_size=50, export_all=False):
    from database import get_connection, run_paginated_list, rows_to_list
    from_clause = """(
        SELECT pt.id, pt.document_no, pt.transfer_date AS txn_date, pt.transfer_type, pt.amount,
               pt.reference_no, pt.description, pt.created_at,
               pt.from_party_type, pt.from_party_id, pt.to_party_type, pt.to_party_id
        FROM party_transfers pt
    ) t"""
    where, params = [], []
    if from_date:
        where.append("txn_date>=?"); params.append(from_date)
    if to_date:
        where.append("txn_date<=?"); params.append(to_date)
    if q:
        like = f"%{q.strip()}%"
        where.append("(document_no LIKE ? OR description LIKE ? OR reference_no LIKE ?)")
        params.extend([like, like, like])
    result = run_paginated_list(
        from_clause,
        "id, document_no, txn_date, transfer_type, amount, reference_no, description, created_at, "
        "from_party_type, from_party_id, to_party_type, to_party_id",
        where or None, params, "txn_date DESC, id DESC", page, page_size, export_all=export_all,
    )
    with get_connection() as conn:
        for item in result["items"]:
            fc, fn = _party_label(conn, item["from_party_type"], item["from_party_id"])
            tc, tn = _party_label(conn, item["to_party_type"], item["to_party_id"])
            item["from_party_name"] = fn
            item["to_party_name"] = tn
            item["transfer_label"] = PARTY_TRANSFER_TYPES.get(item["transfer_type"], item["transfer_type"])
    return result


def get_finance_voucher(vch_source, entry_id):
    """Load cash/bank voucher with party and account details for printing."""
    from database import get_connection, row_to_dict
    tables = {
        "cash_receipt": ("cash_receipts", "receipt_date"),
        "cash_payment": ("cash_payments", "payment_date"),
        "bank_receipt": ("bank_receipts", "receipt_date"),
        "bank_payment": ("bank_payments", "payment_date"),
    }
    if vch_source not in tables:
        return None
    table, date_col = tables[vch_source]
    with get_connection() as conn:
        row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (entry_id,)).fetchone()
        if not row:
            return None
        v = row_to_dict(row)
        v["vch_source"] = vch_source
        v["txn_date"] = v.get(date_col)
        v["book"] = "cash" if vch_source.startswith("cash") else "bank"
        v["side"] = "receipt" if vch_source.endswith("receipt") else "payment"
        pt = v.get("party_type")
        pid = v.get("party_id")
        if pt == "customer" and pid:
            p = conn.execute("SELECT code, name, current_balance FROM customers WHERE id=?", (pid,)).fetchone()
            v["party_code"] = p["code"] if p else ""
            v["party_name"] = p["name"] if p else ""
            v["party_balance"] = float(p["current_balance"] or 0) if p else 0
            v["party_kind"] = "Received From" if v["side"] == "receipt" else "Customer"
        elif pt == "supplier" and pid:
            p = conn.execute("SELECT code, name, current_balance FROM suppliers WHERE id=?", (pid,)).fetchone()
            v["party_code"] = p["code"] if p else ""
            v["party_name"] = p["name"] if p else ""
            v["party_balance"] = float(p["current_balance"] or 0) if p else 0
            v["party_kind"] = "Paid To" if v["side"] == "payment" else "Supplier"
        elif pt in ("expense", "account") and pid:
            p = conn.execute("SELECT code, name FROM chart_of_accounts WHERE id=?", (pid,)).fetchone()
            v["party_code"] = p["code"] if p else ""
            v["party_name"] = p["name"] if p else ""
            if pt == "expense":
                v["party_kind"] = "Expense Account"
            else:
                v["party_kind"] = "Paid To" if v["side"] == "payment" else "Received From"
        else:
            # FMYE / legacy vouchers: resolve main party from posted GL contra head
            gl_party = _finance_voucher_gl_party(conn, v.get("document_no"), v.get("account_id"))
            if gl_party:
                v["party_code"] = gl_party.get("code") or ""
                v["party_name"] = gl_party.get("name") or ""
                v["party_kind"] = "Received From" if v["side"] == "receipt" else "Paid To"
            else:
                v["party_code"] = ""
                v["party_name"] = ""
                v["party_kind"] = "Received From" if v["side"] == "receipt" else "Paid To"
        if v.get("account_id"):
            a = conn.execute("SELECT code, name FROM chart_of_accounts WHERE id=?", (v["account_id"],)).fetchone()
            if a:
                v["bank_account"] = f"{a['code']} - {a['name']}"
        if v["book"] == "cash":
            v["payment_mode"] = "Cash"
        else:
            v["payment_mode"] = "Bank"
        return v


def _finance_voucher_gl_party(conn, document_no, exclude_account_id=None) -> dict | None:
    """Pick non-cash GL account linked to this voucher as the main party/head."""
    doc = (document_no or "").strip()
    if not doc:
        return None
    try:
        excl = int(exclude_account_id) if exclude_account_id not in (None, "") else None
    except (TypeError, ValueError):
        excl = None
    cash_like = {"000000", "1000", "100000"}
    rows = conn.execute(
        """SELECT a.id, a.code, a.name, gl.debit, gl.credit
           FROM general_ledger gl
           JOIN chart_of_accounts a ON gl.account_id=a.id
           WHERE gl.reference_no=? OR gl.reference_no=?
           ORDER BY ABS(COALESCE(gl.debit,0)+COALESCE(gl.credit,0)) DESC, gl.id""",
        (doc, f"FMYE-{doc}" if not doc.upper().startswith("FMYE-") else doc),
    ).fetchall()
    for r in rows:
        code = (r["code"] or "").strip()
        name = (r["name"] or "").strip()
        if code in cash_like:
            continue
        if excl is not None and int(r["id"]) == excl:
            continue
        if name.lower() in ("cash a/c", "cash in hand", "cash"):
            continue
        return {"code": code, "name": name}
    return None


def post_sales_invoice_gl(invoice_id, user_id):
    from database import get_connection, row_to_dict
    with get_connection() as conn:
        inv = row_to_dict(conn.execute("SELECT * FROM sales_invoices WHERE id=?", (invoice_id,)).fetchone())
        if not inv:
            return
        existing = conn.execute(
            "SELECT 1 FROM general_ledger WHERE reference_type='sales_invoice' AND reference_id=? LIMIT 1",
            (invoice_id,),
        ).fetchone()
        if existing:
            return
        total = round(inv["total"], 2)
        paid = round(inv.get("paid_amount") or 0, 2)
        taxable = _invoice_taxable(inv)
        tax_payable = _invoice_tax_payable(inv)
        wht = round(inv.get("wht_tax") or 0, 2)
        ref = inv["document_no"]
        dt = inv["invoice_date"]
        party = _gl_party_label(conn, "sales_invoice", invoice_id)

        debits = round((total - paid) + paid + wht, 2)
        credits = round(taxable + tax_payable, 2)
        if abs(debits - credits) > 0.02:
            raise ValueError(f"Sales invoice GL not balanced: debits {debits} credits {credits}")

        post_gl(
            conn, dt, _party_subledger_code(conn, "customer", inv["customer_id"]), total - paid, 0,
            _gl_narration("Sales invoice", party), "sales_invoice", invoice_id, ref, user_id,
        )
        post_gl(conn, dt, gl_account_code("sales"), 0, taxable, _gl_narration("Sales revenue", party), "sales_invoice", invoice_id, ref, user_id)
        if tax_payable:
            post_gl(conn, dt, gl_account_code("st_payable"), 0, tax_payable, _gl_narration("Sales tax / Output tax", party), "sales_invoice", invoice_id, ref, user_id)
        if wht:
            post_gl(conn, dt, gl_account_code("wht_receivable"), wht, 0, _gl_narration("WHT receivable", party), "sales_invoice", invoice_id, ref, user_id)
        if paid:
            post_gl(conn, dt, gl_account_code("cash"), paid, 0, _gl_narration("Cash received", party), "sales_invoice", invoice_id, ref, user_id)
        # COGS posting — production cost, else warehouse WAC / purchase_price
        from db_stock_costing import get_unit_cost
        from database import _default_warehouse_id
        wh = inv.get("warehouse_id") if isinstance(inv, dict) else None
        if not wh:
            try:
                wh_row = conn.execute(
                    "SELECT warehouse_id FROM sales_invoices WHERE id=?", (invoice_id,)
                ).fetchone()
                wh = wh_row[0] if wh_row else None
            except Exception:
                wh = None
        wh = wh or _default_warehouse_id(conn)
        items = conn.execute(
            """SELECT si.product_id, si.quantity, si.amount, p.purchase_price, p.product_type FROM sales_invoice_items si
               JOIN products p ON si.product_id=p.id WHERE si.invoice_id=?""",
            (invoice_id,),
        ).fetchall()
        cogs = 0
        for it in items:
            it = dict(it)
            po = conn.execute(
                "SELECT cost_per_unit FROM production_orders WHERE finished_product_id=? AND status='completed' ORDER BY id DESC LIMIT 1",
                (it["product_id"],),
            ).fetchone()
            unit_cost = po[0] if po and po[0] else get_unit_cost(
                conn, wh, it["product_id"], float(it["purchase_price"] or 0)
            )
            cogs += it["quantity"] * unit_cost
        if cogs > 0:
            post_gl(conn, dt, gl_account_code("cogs"), cogs, 0, _gl_narration("COGS", party), "sales_invoice", invoice_id, ref, user_id)
            post_gl(conn, dt, gl_account_code("fg_inv"), 0, cogs, _gl_narration("COGS", party), "sales_invoice", invoice_id, ref, user_id)


def conn_execute_invoice(invoice_id):
    from database import get_connection, row_to_dict
    with get_connection() as conn:
        return row_to_dict(conn.execute("SELECT * FROM sales_invoices WHERE id=?", (invoice_id,)).fetchone())


def post_purchase_invoice_gl(invoice_id, user_id):
    from database import get_connection
    with get_connection() as conn:
        inv = conn.execute("SELECT * FROM purchase_invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv:
            return
        existing = conn.execute(
            "SELECT 1 FROM general_ledger WHERE reference_type='purchase_invoice' AND reference_id=? LIMIT 1",
            (invoice_id,),
        ).fetchone()
        if existing:
            return
        inv = dict(inv)
        total = round(inv["total"], 2)
        paid = round(inv.get("paid_amount") or 0, 2)
        taxable = _invoice_taxable(inv)
        input_tax = _invoice_tax_payable(inv)
        wht = round(inv.get("wht_tax") or 0, 2)
        ref = inv["document_no"]
        dt = inv["invoice_date"]
        party = _gl_party_label(conn, "purchase_invoice", invoice_id)

        debits = round(taxable + input_tax, 2)
        credits = round((total - paid) + paid + wht, 2)
        if abs(debits - credits) > 0.02:
            raise ValueError(f"Purchase invoice GL not balanced: debits {debits} credits {credits}")

        post_gl(conn, dt, gl_account_code("raw_inv"), taxable, 0, _gl_narration("Purchase", party), "purchase_invoice", invoice_id, ref, user_id)
        if input_tax:
            post_gl(conn, dt, gl_account_code("st_receivable"), input_tax, 0, _gl_narration("Input tax", party), "purchase_invoice", invoice_id, ref, user_id)
        post_gl(
            conn, dt, _party_subledger_code(conn, "supplier", inv["supplier_id"]), 0, total - paid,
            _gl_narration("Supplier payable", party), "purchase_invoice", invoice_id, ref, user_id,
        )
        if wht:
            post_gl(conn, dt, gl_account_code("wht_payable"), 0, wht, _gl_narration("WHT payable", party), "purchase_invoice", invoice_id, ref, user_id)
        if paid:
            post_gl(conn, dt, gl_account_code("cash"), 0, paid, _gl_narration("Payment", party), "purchase_invoice", invoice_id, ref, user_id)


# ---------- Finance attachments (v8) ----------
ATTACHMENTS_ROOT = Path(__file__).parent / "data" / "finance_attachments"
ALLOWED_ATTACHMENT_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024

FINANCE_ATTACHMENT_TYPES = (
    "journal_voucher",
    "bank_receipt",
    "bank_payment",
    "party_transfer",
)


def _apply_finance_attachments_v8(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS finance_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            source_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            content_type TEXT,
            file_size INTEGER DEFAULT 0,
            notes TEXT,
            uploaded_by INTEGER REFERENCES users(id),
            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_fin_att_src ON finance_attachments(source_type, source_id);
    """)


def _safe_attachment_name(name):
    import re
    base = Path(name or "file").name
    base = re.sub(r"[^\w.\-]", "_", base).strip("._") or "file"
    return base[:180]


def _attachment_dir(source_type, source_id):
    d = ATTACHMENTS_ROOT / source_type / str(source_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_finance_attachment(source_type, source_id, file_bytes, file_name, content_type=None, user_id=None, notes=None):
    """Store receipt / bank slip against JV or bank voucher."""
    from database import get_connection, row_to_dict
    import uuid

    if source_type not in FINANCE_ATTACHMENT_TYPES:
        raise ValueError(f"Unsupported attachment type: {source_type}")
    if not source_id:
        raise ValueError("Document id is required.")
    if not file_bytes:
        raise ValueError("File is empty.")
    if len(file_bytes) > MAX_ATTACHMENT_BYTES:
        raise ValueError(f"File too large (max {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB).")

    safe = _safe_attachment_name(file_name)
    ext = Path(safe).suffix.lower()
    if ext not in ALLOWED_ATTACHMENT_EXT:
        raise ValueError(f"File type not allowed. Use: {', '.join(sorted(ALLOWED_ATTACHMENT_EXT))}")

    stored = f"{uuid.uuid4().hex}_{safe}"
    with get_connection() as conn:
        if source_type == "journal_voucher":
            if not conn.execute("SELECT 1 FROM journal_vouchers WHERE id=?", (source_id,)).fetchone():
                raise ValueError("Journal voucher not found.")
        elif source_type == "bank_receipt":
            if not conn.execute("SELECT 1 FROM bank_receipts WHERE id=?", (source_id,)).fetchone():
                raise ValueError("Bank receipt not found.")
        elif source_type == "bank_payment":
            if not conn.execute("SELECT 1 FROM bank_payments WHERE id=?", (source_id,)).fetchone():
                raise ValueError("Bank payment not found.")
        elif source_type == "party_transfer":
            if not conn.execute("SELECT 1 FROM party_transfers WHERE id=?", (source_id,)).fetchone():
                raise ValueError("Party transfer not found.")

        dest = _attachment_dir(source_type, source_id) / stored
        dest.write_bytes(file_bytes)
        cur = conn.execute(
            """INSERT INTO finance_attachments
               (source_type, source_id, file_name, stored_name, content_type, file_size, notes, uploaded_by)
               VALUES (?,?,?,?,?,?,?,?)""",
            (source_type, source_id, safe, stored, content_type or "", len(file_bytes), notes, user_id),
        )
        att_id = cur.lastrowid
        row = conn.execute("SELECT * FROM finance_attachments WHERE id=?", (att_id,)).fetchone()
        return row_to_dict(row)


def get_finance_attachments(source_type, source_id):
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT fa.*, u.full_name AS uploaded_by_name
               FROM finance_attachments fa
               LEFT JOIN users u ON fa.uploaded_by=u.id
               WHERE fa.source_type=? AND fa.source_id=?
               ORDER BY fa.id DESC""",
            (source_type, source_id),
        ).fetchall()
        return rows_to_list(rows)


def get_finance_attachment(att_id):
    from database import get_connection, row_to_dict
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM finance_attachments WHERE id=?", (att_id,)).fetchone()
        return row_to_dict(row) if row else None


def get_finance_attachment_path(att_id):
    att = get_finance_attachment(att_id)
    if not att:
        return None
    path = _attachment_dir(att["source_type"], att["source_id"]) / att["stored_name"]
    return path if path.exists() else None


def delete_finance_attachment(att_id):
    from database import get_connection
    att = get_finance_attachment(att_id)
    if not att:
        return False
    path = _attachment_dir(att["source_type"], att["source_id"]) / att["stored_name"]
    if path.exists():
        path.unlink()
    with get_connection() as conn:
        conn.execute("DELETE FROM finance_attachments WHERE id=?", (att_id,))
    return True


def delete_attachments_for_source(source_type, source_id):
    for att in get_finance_attachments(source_type, source_id):
        delete_finance_attachment(att["id"])


def count_finance_attachments(source_type, source_id):
    from database import get_connection
    with get_connection() as conn:
        return int(conn.execute(
            "SELECT COUNT(*) FROM finance_attachments WHERE source_type=? AND source_id=?",
            (source_type, source_id),
        ).fetchone()[0])


def vch_source_to_attachment_type(vch_source):
    """Map cash/bank voucher source to attachment source_type (bank only for slips)."""
    mapping = {
        "bank_receipt": "bank_receipt",
        "bank_payment": "bank_payment",
        "journal_voucher": "journal_voucher",
        "party_transfer": "party_transfer",
    }
    return mapping.get(vch_source)


def _attachment_doc_label(source_type):
    return {
        "journal_voucher": "Journal Voucher",
        "bank_receipt": "Bank Receipt",
        "bank_payment": "Bank Payment",
        "party_transfer": "Party Transfer",
    }.get(source_type, source_type)


def get_finance_document_meta(source_type, source_id):
    """Return voucher header for attachment UI."""
    from database import get_connection, row_to_dict
    with get_connection() as conn:
        if source_type == "journal_voucher":
            row = conn.execute(
                """SELECT id, document_no, voucher_date AS txn_date, description, total_debit AS amount
                   FROM journal_vouchers WHERE id=?""",
                (source_id,),
            ).fetchone()
        elif source_type == "bank_receipt":
            row = conn.execute(
                """SELECT id, document_no, receipt_date AS txn_date, description, amount, reference_no
                   FROM bank_receipts WHERE id=?""",
                (source_id,),
            ).fetchone()
        elif source_type == "bank_payment":
            row = conn.execute(
                """SELECT id, document_no, payment_date AS txn_date, description, amount, reference_no
                   FROM bank_payments WHERE id=?""",
                (source_id,),
            ).fetchone()
        elif source_type == "party_transfer":
            row = conn.execute(
                """SELECT id, document_no, transfer_date AS txn_date, description, amount, reference_no
                   FROM party_transfers WHERE id=?""",
                (source_id,),
            ).fetchone()
        else:
            return None
        if not row:
            return None
        d = row_to_dict(row)
        d["source_type"] = source_type
        d["doc_label"] = _attachment_doc_label(source_type)
        return d


def search_finance_documents_for_attachment(q, source_types=None, limit=20):
    """Search vouchers by document no, numeric id, reference, or description."""
    from database import get_connection, rows_to_list
    if not q or not str(q).strip():
        return []
    q = str(q).strip()
    types = tuple(source_types) if source_types else FINANCE_ATTACHMENT_TYPES
    like = f"%{q}%"
    out = []
    with get_connection() as conn:
        if "journal_voucher" in types:
            out.extend(rows_to_list(conn.execute(
                """SELECT id, document_no, voucher_date AS txn_date, description,
                          total_debit AS amount, 'journal_voucher' AS source_type,
                          'Journal Voucher' AS doc_label, '' AS reference_no
                   FROM journal_vouchers
                   WHERE document_no LIKE ? OR CAST(id AS TEXT)=? OR description LIKE ?
                   ORDER BY id DESC LIMIT ?""",
                (like, q, like, limit),
            ).fetchall()))
        if "bank_receipt" in types:
            out.extend(rows_to_list(conn.execute(
                """SELECT id, document_no, receipt_date AS txn_date, description, amount,
                          'bank_receipt' AS source_type, 'Bank Receipt' AS doc_label,
                          COALESCE(reference_no,'') AS reference_no
                   FROM bank_receipts
                   WHERE document_no LIKE ? OR CAST(id AS TEXT)=? OR reference_no LIKE ?
                         OR description LIKE ?
                   ORDER BY id DESC LIMIT ?""",
                (like, q, like, like, limit),
            ).fetchall()))
        if "bank_payment" in types:
            out.extend(rows_to_list(conn.execute(
                """SELECT id, document_no, payment_date AS txn_date, description, amount,
                          'bank_payment' AS source_type, 'Bank Payment' AS doc_label,
                          COALESCE(reference_no,'') AS reference_no
                   FROM bank_payments
                   WHERE document_no LIKE ? OR CAST(id AS TEXT)=? OR reference_no LIKE ?
                         OR description LIKE ?
                   ORDER BY id DESC LIMIT ?""",
                (like, q, like, like, limit),
            ).fetchall()))
        if "party_transfer" in types:
            out.extend(rows_to_list(conn.execute(
                """SELECT id, document_no, transfer_date AS txn_date, description, amount,
                          'party_transfer' AS source_type, 'Party Transfer' AS doc_label,
                          COALESCE(reference_no,'') AS reference_no
                   FROM party_transfers
                   WHERE document_no LIKE ? OR CAST(id AS TEXT)=? OR reference_no LIKE ?
                         OR description LIKE ?
                   ORDER BY id DESC LIMIT ?""",
                (like, q, like, like, limit),
            ).fetchall()))
    seen = set()
    deduped = []
    for r in sorted(out, key=lambda x: x["id"], reverse=True):
        key = (r["source_type"], r["id"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped[:limit]
