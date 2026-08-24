"""V17.0 — Extensibility: plugins, rules, workflows, scripts, webhooks, migrations."""

from __future__ import annotations


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
    row = conn.execute("SELECT value FROM schema_meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def _meta_set(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO schema_meta(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


_EXTRA_TENANT_TABLES = (
    "quotations", "delivery_notes", "goods_receipt_notes", "journal_vouchers",
    "purchase_requisitions", "sales_invoice_items",
)


def migrate_v17_0_extensibility(conn, db_module=None) -> None:
    from erp_version import SCHEMA_V17_KEY, SCHEMA_V17_VALUE

    if _meta_get(conn, SCHEMA_V17_KEY) == SCHEMA_V17_VALUE:
        return

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_plugins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plugin_id TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            version TEXT,
            manifest_json TEXT,
            is_active INTEGER DEFAULT 1,
            installed_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_plugin_hooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plugin_id TEXT NOT NULL,
            hook_type TEXT NOT NULL,
            hook_name TEXT NOT NULL,
            config_json TEXT,
            UNIQUE(plugin_id, hook_type, hook_name)
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_business_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_code TEXT NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            condition_json TEXT NOT NULL,
            action_json TEXT NOT NULL,
            priority INTEGER DEFAULT 100,
            company_id INTEGER DEFAULT 1,
            is_active INTEGER DEFAULT 1,
            UNIQUE(rule_code, company_id)
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_workflow_definitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            definition_json TEXT NOT NULL,
            company_id INTEGER DEFAULT 1,
            is_active INTEGER DEFAULT 1,
            UNIQUE(code, company_id)
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_scripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            trigger_point TEXT NOT NULL,
            doc_type TEXT,
            script_body TEXT NOT NULL,
            company_id INTEGER DEFAULT 1,
            is_active INTEGER DEFAULT 1,
            UNIQUE(code, company_id)
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_webhooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            event_types TEXT NOT NULL,
            secret TEXT,
            company_id INTEGER DEFAULT 1,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_api_rate_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_key TEXT NOT NULL,
            window_start TEXT NOT NULL,
            request_count INTEGER DEFAULT 0,
            UNIQUE(client_key, window_start)
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_migration_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            migration_id TEXT NOT NULL UNIQUE,
            version TEXT NOT NULL,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
            duration_ms REAL,
            checksum TEXT,
            status TEXT DEFAULT 'applied'
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_event_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            subscriber_type TEXT NOT NULL,
            subscriber_ref TEXT NOT NULL,
            config_json TEXT,
            company_id INTEGER DEFAULT 1,
            is_active INTEGER DEFAULT 1
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_tenant_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            sql_fragment TEXT,
            bypassed INTEGER DEFAULT 0,
            recorded_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    conn.execute("CREATE INDEX IF NOT EXISTS idx_rules_category ON erp_business_rules(category, company_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_workflows_doctype ON erp_workflow_definitions(doc_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scripts_trigger ON erp_scripts(trigger_point, doc_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_event_subs ON erp_event_subscriptions(event_type, is_active)")

    for table in _EXTRA_TENANT_TABLES:
        _add_col(conn, table, "company_id", "INTEGER DEFAULT 1")
        _add_col(conn, table, "branch_id", "INTEGER DEFAULT 1")

    _seed_v17(conn)
    _meta_set(conn, SCHEMA_V17_KEY, SCHEMA_V17_VALUE)
    _meta_set(conn, "erp_version", "V17.0")


def ensure_tenant_columns(conn) -> None:
    """Idempotent — add tenant cols to tables added after initial V17 release."""
    for table in _EXTRA_TENANT_TABLES:
        _add_col(conn, table, "company_id", "INTEGER DEFAULT 1")
        _add_col(conn, table, "branch_id", "INTEGER DEFAULT 1")


def _seed_v17(conn) -> None:
    rules = [
        ("CREDIT_LIMIT", "Credit limit check", "credit_limit",
         '{"field":"total","op":"lte","ref":"customer.credit_limit"}',
         '{"action":"block","message":"Credit limit exceeded"}'),
        ("DISCOUNT_APPROVAL", "Discount requires approval", "discount",
         '{"field":"discount_pct","op":"gt","value":10}',
         '{"action":"require_approval","level":1}'),
        ("TAX_REQUIRED", "Tax validation", "tax",
         '{"field":"tax_rate_id","op":"required"}',
         '{"action":"block","message":"Tax rate required"}'),
        ("NEGATIVE_STOCK", "Inventory guard", "inventory",
         '{"field":"stock_qty","op":"gte","value":0}',
         '{"action":"block","message":"Insufficient stock"}'),
        ("PRICE_MIN", "Minimum price", "price",
         '{"field":"rate","op":"gt","value":0}',
         '{"action":"block","message":"Invalid price"}'),
    ]
    for code, name, cat, cond, act in rules:
        conn.execute(
            """INSERT OR IGNORE INTO erp_business_rules(
                rule_code,name,category,condition_json,action_json,company_id)
               VALUES(?,?,?,?,?,1)""",
            (code, name, cat, cond, act),
        )

    wf = {
        "states": ["draft", "submitted", "approved", "rejected", "posted"],
        "transitions": [
            {"from": "draft", "to": "submitted", "action": "submit"},
            {"from": "submitted", "to": "approved", "action": "approve", "approver_role": "SALES_MGR"},
            {"from": "submitted", "to": "rejected", "action": "reject"},
            {"from": "approved", "to": "posted", "action": "post"},
        ],
        "notifications": {"approved": "internal", "rejected": "creator"},
    }
    import json
    conn.execute(
        """INSERT OR IGNORE INTO erp_workflow_definitions(code,name,doc_type,definition_json,company_id)
           VALUES('SALES_INVOICE_STD','Standard Sales Invoice','sales_invoice',?,1)""",
        (json.dumps(wf),),
    )

    for section, key, val in (
        ("api", "rate_limit_per_minute", "120"),
        ("api", "webhook_enabled", "1"),
        ("observability", "prometheus_enabled", "1"),
        ("observability", "trace_enabled", "1"),
    ):
        if _table_exists(conn, "erp_config"):
            conn.execute(
                "INSERT OR IGNORE INTO erp_config(section,key,value,company_id) VALUES(?,?,?,1)",
                (section, key, val),
            )
