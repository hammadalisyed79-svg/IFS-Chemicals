"""V15.0 — Multi-Access Web, Distributor Portal, expanded roles & security."""

from __future__ import annotations

PORTAL_ORDER_STATUSES = (
    "Draft",
    "Submitted",
    "Under Review",
    "Approved",
    "Rejected",
    "In Dispatch",
    "Invoiced",
    "Delivered",
    "Cancelled",
)

ENTERPRISE_ROLES = [
    ("SUPER_ADMIN", "Super Admin", "Full system access", 1),
    ("DIRECTOR", "Director", "Executive oversight", 0),
    ("GM", "General Manager", "Cross-module management", 0),
    ("FIN_MGR", "Finance Manager", "Finance module lead", 0),
    ("ACCOUNTANT", "Accountant", "Finance operations", 0),
    ("SALES_MGR", "Sales Manager", "Sales module lead", 0),
    ("SALES_OFF", "Sales Officer", "Sales operations", 0),
    ("PUR_MGR", "Purchase Manager", "Purchase module lead", 0),
    ("PUR_OFF", "Purchase Officer", "Purchase operations", 0),
    ("STORE_MGR", "Store Manager", "Inventory lead", 0),
    ("STORE_OFF", "Store Officer", "Inventory operations", 0),
    ("PROD_MGR", "Production Manager", "Production lead", 0),
    ("PROD_SUP", "Production Supervisor", "Shop floor supervision", 0),
    ("QC_OFF", "QC Officer", "Quality control", 0),
    ("HR_MGR", "HR Manager", "Human resources lead", 0),
    ("PAYROLL_OFF", "Payroll Officer", "Payroll processing", 0),
    ("AUDITOR", "Auditor", "Read-only audit access", 0),
    ("DISTRIBUTOR", "Distributor", "Portal-only distributor", 0),
    ("DIST_STAFF", "Distributor Staff", "Portal staff for distributor", 0),
    ("VIEWER", "Viewer", "Read-only internal", 0),
]

MATRIX_MODULES = [
    "Dashboard", "Masters", "Sales", "Purchase", "Inventory", "Production",
    "Finance", "HR", "Reports", "Admin", "Portal", "PriceLists",
]


def _table_exists(conn, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _col_exists(conn, table: str, col: str) -> bool:
    if not _table_exists(conn, table):
        return False
    return col in [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _add_col(conn, table: str, col: str, ddl: str) -> None:
    if _table_exists(conn, table) and not _col_exists(conn, table, col):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


def _meta_get(conn, key: str) -> str | None:
    if not _table_exists(conn, "schema_meta"):
        return None
    row = conn.execute("SELECT value FROM schema_meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def _meta_set(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO schema_meta(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def ensure_distributor_catalog_schema(conn) -> None:
    """Per-customer portal catalogue (invoice-sourced + admin overrides)."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS distributor_catalog_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            rate REAL NOT NULL DEFAULT 0,
            discount_pct REAL DEFAULT 0,
            min_qty REAL DEFAULT 1,
            effective_from TEXT NOT NULL DEFAULT (date('now')),
            source TEXT NOT NULL DEFAULT 'invoice',
            admin_changed INTEGER DEFAULT 0,
            admin_note TEXT,
            last_invoice_id INTEGER,
            last_invoice_date TEXT,
            is_active INTEGER DEFAULT 1,
            changed_at TEXT,
            changed_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(customer_id, product_id)
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_dist_cat_customer ON distributor_catalog_items(customer_id, is_active)"
    )
    _add_col(conn, "portal_orders", "delivery_date", "TEXT")
    _add_col(conn, "portal_orders", "dispatch_town", "TEXT")
    _add_col(conn, "portal_orders", "source_channel", "TEXT DEFAULT 'portal'")
    _add_col(conn, "sales_orders", "dispatch_town", "TEXT")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS portal_cart_drafts (
            user_id INTEGER PRIMARY KEY REFERENCES users(id),
            customer_id INTEGER REFERENCES customers(id),
            cart_json TEXT NOT NULL DEFAULT '[]',
            notes TEXT,
            order_date TEXT,
            delivery_date TEXT,
            saved_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    _add_col(conn, "portal_cart_drafts", "dispatch_town", "TEXT")
    # Portal self-service profile contacts (synced to customers master)
    for col, ddl in (
        ("dispatch_phone", "TEXT"),
        ("accounts_phone", "TEXT"),
        ("owner_phone", "TEXT"),
    ):
        _add_col(conn, "customers", col, ddl)
        _add_col(conn, "distributor_profiles", col, ddl)


def migrate_v15_0_mobile_portal_distributor(conn, db_module=None) -> None:
    """Additive V15 schema — portal, price lists, security, notifications."""
    from erp_version import SCHEMA_V15_KEY, SCHEMA_V15_VALUE

    # Always idempotent — safe when V15 meta already applied
    ensure_distributor_catalog_schema(conn)

    if _meta_get(conn, SCHEMA_V15_KEY) == SCHEMA_V15_VALUE:
        return

    # --- users extensions ---
    for col, ddl in (
        ("user_type", "TEXT DEFAULT 'internal'"),
        ("linked_customer_id", "INTEGER REFERENCES customers(id)"),
        ("last_login_at", "TEXT"),
        ("failed_login_count", "INTEGER DEFAULT 0"),
        ("locked_until", "TEXT"),
        ("must_change_password", "INTEGER DEFAULT 0"),
        ("last_login_ip", "TEXT"),
        ("last_login_device", "TEXT"),
    ):
        _add_col(conn, "users", col, ddl)

    # --- customers extensions ---
    for col, ddl in (
        ("is_distributor", "INTEGER DEFAULT 0"),
        ("distributor_code", "TEXT"),
        ("portal_enabled", "INTEGER DEFAULT 0"),
        ("credit_limit", "REAL DEFAULT 0"),
        ("payment_terms_id", "INTEGER REFERENCES payment_terms(id)"),
        ("assigned_price_list_id", "INTEGER"),
    ):
        _add_col(conn, "customers", col, ddl)

    # --- sales_orders extensions ---
    for col, ddl in (
        ("portal_order_id", "INTEGER"),
        ("source_channel", "TEXT DEFAULT 'internal'"),
    ):
        _add_col(conn, "sales_orders", col, ddl)

    # --- user_sessions extensions ---
    for col, ddl in (
        ("last_activity_at", "TEXT"),
        ("ip_address", "TEXT"),
        ("user_agent", "TEXT"),
    ):
        _add_col(conn, "user_sessions", col, ddl)

    conn.execute(
        """CREATE TABLE IF NOT EXISTS distributor_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL UNIQUE REFERENCES customers(id),
            business_name TEXT,
            contact_name TEXT,
            phone TEXT,
            email TEXT,
            address TEXT,
            city TEXT,
            province TEXT,
            ntn TEXT,
            strn TEXT,
            credit_limit REAL DEFAULT 0,
            payment_terms_id INTEGER REFERENCES payment_terms(id),
            assigned_price_list_id INTEGER REFERENCES price_lists(id),
            show_stock INTEGER DEFAULT 0,
            portal_enabled INTEGER DEFAULT 1,
            notes TEXT,
            created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            modified_at TEXT
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS price_lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            list_type TEXT DEFAULT 'distributor',
            currency TEXT DEFAULT 'PKR',
            is_active INTEGER DEFAULT 1,
            valid_from TEXT,
            valid_to TEXT,
            notes TEXT,
            created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            modified_at TEXT
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS price_list_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            price_list_id INTEGER NOT NULL REFERENCES price_lists(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL REFERENCES products(id),
            rate REAL NOT NULL DEFAULT 0,
            discount_pct REAL DEFAULT 0,
            min_qty REAL DEFAULT 1,
            is_active INTEGER DEFAULT 1,
            UNIQUE(price_list_id, product_id)
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS distributor_price_lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            price_list_id INTEGER NOT NULL REFERENCES price_lists(id),
            priority INTEGER DEFAULT 1,
            valid_from TEXT,
            valid_to TEXT,
            is_active INTEGER DEFAULT 1,
            created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS portal_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT NOT NULL UNIQUE,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            distributor_user_id INTEGER NOT NULL REFERENCES users(id),
            order_date TEXT NOT NULL,
            status TEXT DEFAULT 'Draft',
            subtotal REAL DEFAULT 0,
            discount REAL DEFAULT 0,
            tax REAL DEFAULT 0,
            total REAL DEFAULT 0,
            notes TEXT,
            sales_order_id INTEGER REFERENCES sales_orders(id),
            rejection_reason TEXT,
            submitted_at TEXT,
            approved_at TEXT,
            approved_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            modified_at TEXT
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS portal_order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portal_order_id INTEGER NOT NULL REFERENCES portal_orders(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL REFERENCES products(id),
            quantity REAL NOT NULL,
            rate REAL NOT NULL,
            discount_pct REAL DEFAULT 0,
            amount REAL NOT NULL,
            min_qty REAL DEFAULT 1
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS portal_payment_proofs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            portal_order_id INTEGER REFERENCES portal_orders(id),
            proof_date TEXT NOT NULL,
            amount REAL NOT NULL,
            reference_no TEXT,
            bank_name TEXT,
            notes TEXT,
            file_path TEXT,
            status TEXT DEFAULT 'pending',
            reviewed_by INTEGER,
            reviewed_at TEXT,
            created_by INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            customer_id INTEGER REFERENCES customers(id),
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT,
            ref_type TEXT,
            ref_id INTEGER,
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            user_id INTEGER REFERENCES users(id),
            success INTEGER DEFAULT 0,
            ip_address TEXT,
            user_agent TEXT,
            failure_reason TEXT,
            attempted_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS user_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            device_label TEXT,
            user_agent TEXT,
            ip_address TEXT,
            last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
            is_trusted INTEGER DEFAULT 0
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS role_permission_matrix (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            module_name TEXT NOT NULL,
            can_view INTEGER DEFAULT 0,
            can_add INTEGER DEFAULT 0,
            can_edit INTEGER DEFAULT 0,
            can_delete_draft INTEGER DEFAULT 0,
            can_approve INTEGER DEFAULT 0,
            can_reject INTEGER DEFAULT 0,
            can_post INTEGER DEFAULT 0,
            can_print INTEGER DEFAULT 0,
            can_export INTEGER DEFAULT 0,
            can_admin_override INTEGER DEFAULT 0,
            UNIQUE(role_id, module_name)
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS access_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            action TEXT NOT NULL,
            module TEXT,
            ip_address TEXT,
            user_agent TEXT,
            details TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    # Indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_portal_orders_customer ON portal_orders(customer_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_portal_orders_user ON portal_orders(distributor_user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_portal_orders_status ON portal_orders(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON erp_notifications(user_id, is_read)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_login_attempts_user ON login_attempts(username, attempted_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_price_list_items_pl ON price_list_items(price_list_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_access_log_user ON access_log(user_id, created_at)")

    conn.execute("INSERT OR IGNORE INTO document_sequences(doc_type,prefix,padding) VALUES('POR','POR',5)")

    _seed_v15(conn)
    _meta_set(conn, SCHEMA_V15_KEY, SCHEMA_V15_VALUE)
    _meta_set(conn, "erp_version", "V15.0")


def _seed_v15(conn) -> None:
    admin = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    aid = admin[0] if admin else None

    # Deployment / security settings
    for k, v in (
        ("ssl_configured", "0"),
        ("session_idle_minutes", "30"),
        ("max_failed_logins", "5"),
        ("lockout_minutes", "30"),
        ("password_min_length", "8"),
        ("portal_show_stock_default", "0"),
        ("server_public_ip", "138.201.139.157"),
    ):
        conn.execute("INSERT OR IGNORE INTO system_settings(key,value) VALUES(?,?)", (k, v))

    # Default price lists
    if conn.execute("SELECT COUNT(*) FROM price_lists").fetchone()[0] == 0:
        lists = [
            ("RETAIL", "Retail", "retail"),
            ("WHOLESALE", "Wholesale", "wholesale"),
            ("DIST", "Distributor", "distributor"),
            ("SPECIAL", "Special Customer", "special"),
            ("REGION", "Region-wise", "region"),
        ]
        for code, name, lt in lists:
            conn.execute(
                "INSERT INTO price_lists(code,name,list_type,is_active,created_by) VALUES(?,?,?,1,?)",
                (code, name, lt, aid),
            )

    # Enterprise roles (additive — keeps ADMIN/USER)
    for code, name, desc, is_admin in ENTERPRISE_ROLES:
        if not conn.execute("SELECT 1 FROM roles WHERE code=?", (code,)).fetchone():
            conn.execute(
                "INSERT INTO roles(code,name,description,created_by) VALUES(?,?,?,?)",
                (code, name, desc, aid),
            )

    _seed_role_matrix(conn, aid)
    _migrate_admin_user_type(conn)


def _seed_role_matrix(conn, admin_id) -> None:
    """Populate role_permission_matrix from defaults."""
    from erp_core.role_matrix import default_matrix_for_role

    roles = conn.execute("SELECT id, code FROM roles").fetchall()
    for role_id, code in roles:
        if conn.execute(
            "SELECT 1 FROM role_permission_matrix WHERE role_id=? LIMIT 1", (role_id,)
        ).fetchone():
            continue
        perms = default_matrix_for_role(code)
        for mod, p in perms.items():
            conn.execute(
                """INSERT INTO role_permission_matrix(
                    role_id,module_name,can_view,can_add,can_edit,can_delete_draft,
                    can_approve,can_reject,can_post,can_print,can_export,can_admin_override)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    role_id, mod,
                    int(p.get("view", 0)), int(p.get("add", 0)), int(p.get("edit", 0)),
                    int(p.get("delete_draft", 0)), int(p.get("approve", 0)),
                    int(p.get("reject", 0)), int(p.get("post", 0)), int(p.get("print", 0)),
                    int(p.get("export", 0)), int(p.get("admin_override", 0)),
                ),
            )


def _migrate_admin_user_type(conn) -> None:
    conn.execute(
        "UPDATE users SET user_type='internal' WHERE user_type IS NULL OR user_type=''"
    )
    conn.execute(
        "UPDATE users SET user_type='internal' WHERE username='admin' AND role='admin'"
    )
