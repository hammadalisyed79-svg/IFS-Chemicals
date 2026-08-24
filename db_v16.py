"""V16.0 — Enterprise Platform: multi-company, jobs, documents, events, config."""

from __future__ import annotations

_CORE_TABLES_FOR_TENANCY = (
    "customers", "suppliers", "products", "warehouses", "sales_invoices", "purchase_invoices",
    "sales_orders", "purchase_orders", "chart_of_accounts", "employees", "portal_orders",
)


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


def migrate_v16_0_enterprise_platform(conn, db_module=None) -> None:
    from erp_version import SCHEMA_V16_KEY, SCHEMA_V16_VALUE

    if _meta_get(conn, SCHEMA_V16_KEY) == SCHEMA_V16_VALUE:
        return

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            legal_name TEXT,
            tax_id TEXT,
            currency TEXT DEFAULT 'PKR',
            timezone TEXT DEFAULT 'Asia/Karachi',
            logo_path TEXT,
            address TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_branches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL REFERENCES erp_companies(id),
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            address TEXT,
            phone TEXT,
            is_head_office INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            document_prefix TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(company_id, code)
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_user_companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            company_id INTEGER NOT NULL REFERENCES erp_companies(id),
            branch_id INTEGER REFERENCES erp_branches(id),
            is_default INTEGER DEFAULT 0,
            UNIQUE(user_id, company_id)
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            company_id INTEGER DEFAULT 1,
            branch_id INTEGER,
            description TEXT,
            UNIQUE(section, key, company_id, branch_id)
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER DEFAULT 1,
            branch_id INTEGER,
            doc_category TEXT NOT NULL,
            ref_type TEXT,
            ref_id INTEGER,
            title TEXT NOT NULL,
            file_name TEXT,
            file_path TEXT NOT NULL,
            mime_type TEXT,
            file_size INTEGER,
            version_no INTEGER DEFAULT 1,
            is_current INTEGER DEFAULT 1,
            tags TEXT,
            uploaded_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_document_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL REFERENCES erp_documents(id) ON DELETE CASCADE,
            version_no INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            file_size INTEGER,
            change_note TEXT,
            uploaded_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_job_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_type TEXT NOT NULL,
            payload TEXT,
            status TEXT DEFAULT 'pending',
            priority INTEGER DEFAULT 5,
            attempts INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 3,
            scheduled_at TEXT,
            started_at TEXT,
            completed_at TEXT,
            error_message TEXT,
            company_id INTEGER DEFAULT 1,
            created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_domain_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            aggregate_type TEXT,
            aggregate_id INTEGER,
            payload TEXT,
            company_id INTEGER DEFAULT 1,
            branch_id INTEGER,
            user_id INTEGER,
            published_at TEXT DEFAULT CURRENT_TIMESTAMP,
            processed INTEGER DEFAULT 0
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_integration_connectors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            connector_type TEXT NOT NULL,
            name TEXT NOT NULL,
            config_json TEXT,
            is_active INTEGER DEFAULT 0,
            company_id INTEGER DEFAULT 1,
            last_sync_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_report_designs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            base_report TEXT,
            layout_json TEXT NOT NULL,
            filters_json TEXT,
            role_codes TEXT,
            company_id INTEGER DEFAULT 1,
            is_active INTEGER DEFAULT 1,
            created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(code, company_id)
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_import_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            file_name TEXT,
            status TEXT DEFAULT 'pending',
            total_rows INTEGER DEFAULT 0,
            success_rows INTEGER DEFAULT 0,
            error_rows INTEGER DEFAULT 0,
            error_log TEXT,
            company_id INTEGER DEFAULT 1,
            created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_app_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_name TEXT NOT NULL,
            metric_value REAL,
            tags TEXT,
            recorded_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_slow_queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sql_text TEXT,
            duration_ms REAL,
            params TEXT,
            recorded_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_api_clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id TEXT NOT NULL UNIQUE,
            client_secret_hash TEXT NOT NULL,
            name TEXT,
            scopes TEXT,
            company_id INTEGER DEFAULT 1,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    for table in _CORE_TABLES_FOR_TENANCY:
        _add_col(conn, table, "company_id", "INTEGER DEFAULT 1")
        _add_col(conn, table, "branch_id", "INTEGER DEFAULT 1")

    _add_col(conn, "users", "default_company_id", "INTEGER DEFAULT 1")
    _add_col(conn, "users", "default_branch_id", "INTEGER DEFAULT 1")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON erp_job_queue(status, scheduled_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON erp_domain_events(event_type, processed)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_ref ON erp_documents(ref_type, ref_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_config_section ON erp_config(section, company_id)")

    _seed_v16(conn)
    _meta_set(conn, SCHEMA_V16_KEY, SCHEMA_V16_VALUE)
    _meta_set(conn, "erp_version", "V16.0")


def _seed_v16(conn) -> None:
    if conn.execute("SELECT COUNT(*) FROM erp_companies").fetchone()[0] == 0:
        name = "IFS Chemicals"
        if _table_exists(conn, "system_settings"):
            row = conn.execute("SELECT value FROM system_settings WHERE key='company_name'").fetchone()
            if row and row[0]:
                name = row[0]
        conn.execute(
            "INSERT INTO erp_companies(code,name,is_active) VALUES('DEFAULT',?,1)", (name,)
        )
        conn.execute(
            """INSERT INTO erp_branches(company_id,code,name,is_head_office,is_active)
               VALUES(1,'HO','Head Office',1,1)"""
        )

    defaults = [
        ("database", "driver", "sqlite", "Database driver: sqlite|postgresql|mysql|mssql"),
        ("database", "host", "", "Database host (non-sqlite)"),
        ("database", "port", "", "Database port"),
        ("database", "name", "ifs_erp", "Database name"),
        ("email", "smtp_host", "", "SMTP server"),
        ("email", "smtp_port", "587", "SMTP port"),
        ("email", "from_address", "", "Default from email"),
        ("sms", "provider", "", "SMS provider connector id"),
        ("portal", "enabled", "1", "Distributor portal enabled"),
        ("security", "jwt_secret", "", "JWT signing secret (auto-generated if empty)"),
        ("security", "jwt_expire_minutes", "60", "API token lifetime"),
        ("tax", "default_rate_id", "", "Default tax rate"),
        ("printing", "default_printer", "", "Label printer connector"),
        ("approval", "default_workflow", "standard", "Default approval workflow"),
        ("cache", "ttl_seconds", "300", "Default cache TTL"),
    ]
    for section, key, value, desc in defaults:
        conn.execute(
            """INSERT OR IGNORE INTO erp_config(section,key,value,company_id,description)
               VALUES(?,?,?,1,?)""",
            (section, key, value, desc),
        )

    import secrets
    row = conn.execute(
        "SELECT value FROM erp_config WHERE section='security' AND key='jwt_secret' AND company_id=1"
    ).fetchone()
    if row and not (row[0] or "").strip():
        conn.execute(
            "UPDATE erp_config SET value=? WHERE section='security' AND key='jwt_secret' AND company_id=1",
            (secrets.token_urlsafe(48),),
        )
