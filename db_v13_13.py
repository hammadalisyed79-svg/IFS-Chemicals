"""V13.13 Professional Stability & Workflow Completion — safe additive migration."""

from __future__ import annotations

WORKFLOW_TABLES = (
    "sales_invoices",
    "purchase_invoices",
    "sales_returns",
    "purchase_returns",
    "sales_orders",
    "purchase_orders",
    "quotations",
    "delivery_notes",
    "goods_receipt_notes",
    "purchase_requisitions",
    "stock_adjustments",
    "production_orders",
    "gate_passes",
    "journal_vouchers",
)

WORKFLOW_COLUMNS = (
    ("approval_status", "TEXT"),
    ("updated_by", "INTEGER"),
    ("updated_at", "TEXT"),
    ("printed_count", "INTEGER DEFAULT 0"),
    ("last_printed_at", "TEXT"),
)

SALES_INVOICE_EXTRA = (
    ("freight", "REAL DEFAULT 0"),
    ("loading_charges", "REAL DEFAULT 0"),
    ("other_charges", "REAL DEFAULT 0"),
    ("round_off", "REAL DEFAULT 0"),
    ("grand_weight", "REAL DEFAULT 0"),
    ("registered_taxpayer", "INTEGER DEFAULT 1"),
    ("gst_pct", "REAL"),
    ("further_tax_pct", "REAL"),
    ("fed_pct", "REAL"),
)

PURCHASE_INVOICE_EXTRA = (
    ("freight", "REAL DEFAULT 0"),
    ("loading_charges", "REAL DEFAULT 0"),
    ("other_charges", "REAL DEFAULT 0"),
    ("round_off", "REAL DEFAULT 0"),
    ("supplier_bill_no", "TEXT"),
    ("claim_input_tax", "INTEGER DEFAULT 1"),
    ("grand_weight", "REAL DEFAULT 0"),
)


def _col_exists(conn, table: str, col: str) -> bool:
    return col in [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _table_exists(conn, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


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


def migrate_v13_13_professional_workflow_completion(conn, db_module=None) -> None:
    """
    Add V13.13 workflow columns and charge fields. Never drops data.
    Safe to run multiple times.
    """
    from erp_version import SCHEMA_V13_13_KEY, SCHEMA_V13_13_VALUE

    if _meta_get(conn, SCHEMA_V13_13_KEY) == SCHEMA_V13_13_VALUE:
        return

    for table in WORKFLOW_TABLES:
        if not _table_exists(conn, table):
            continue
        for col, ddl in WORKFLOW_COLUMNS:
            _add_col(conn, table, col, ddl)
        if _col_exists(conn, table, "status") and _col_exists(conn, table, "approval_status"):
            conn.execute(
                f"""UPDATE {table} SET approval_status = COALESCE(approval_status, status)
                    WHERE approval_status IS NULL OR approval_status = ''"""
            )
        if _col_exists(conn, table, "modified_by") and _col_exists(conn, table, "updated_by"):
            conn.execute(
                f"""UPDATE {table} SET updated_by = COALESCE(updated_by, modified_by)
                    WHERE updated_by IS NULL"""
            )
        if _col_exists(conn, table, "modified_at") and _col_exists(conn, table, "updated_at"):
            conn.execute(
                f"""UPDATE {table} SET updated_at = COALESCE(updated_at, modified_at)
                    WHERE updated_at IS NULL OR updated_at = ''"""
            )

    if _table_exists(conn, "sales_invoices"):
        for col, ddl in SALES_INVOICE_EXTRA:
            _add_col(conn, "sales_invoices", col, ddl)

    if _table_exists(conn, "purchase_invoices"):
        for col, ddl in PURCHASE_INVOICE_EXTRA:
            _add_col(conn, "purchase_invoices", col, ddl)

    conn.execute(
        """CREATE TABLE IF NOT EXISTS erp_draft_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_type TEXT NOT NULL,
            doc_table TEXT NOT NULL,
            record_id INTEGER NOT NULL,
            document_no TEXT,
            doc_date TEXT,
            party_name TEXT,
            amount REAL DEFAULT 0,
            status TEXT,
            approval_status TEXT,
            created_by INTEGER,
            created_at TEXT,
            updated_by INTEGER,
            updated_at TEXT,
            UNIQUE(doc_table, record_id)
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_erp_draft_registry_status ON erp_draft_registry(status, doc_type)"
    )

    _meta_set(conn, SCHEMA_V13_13_KEY, SCHEMA_V13_13_VALUE)
    if db_module and hasattr(db_module, "now"):
        ts = db_module.now()
    else:
        from datetime import datetime
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _meta_set(conn, "erp_version", "V13.13")

    _rebuild_draft_registry(conn, ts)


def _rebuild_draft_registry(conn, ts: str) -> None:
    """Populate draft registry from live transactional tables."""
    if not _table_exists(conn, "erp_draft_registry"):
        return
    conn.execute("DELETE FROM erp_draft_registry")
    specs = [
        ("Sales Invoice", "sales_invoices", "document_no", "invoice_date", "customer_id", "customers", "total"),
        ("Purchase Invoice", "purchase_invoices", "document_no", "invoice_date", "supplier_id", "suppliers", "total"),
        ("Sales Return", "sales_returns", "document_no", "return_date", "customer_id", "customers", "total"),
        ("Purchase Return", "purchase_returns", "document_no", "return_date", "supplier_id", "suppliers", "total"),
        ("Sales Order", "sales_orders", "document_no", "order_date", "customer_id", "customers", "total"),
        ("Purchase Order", "purchase_orders", "document_no", "order_date", "supplier_id", "suppliers", "total"),
        ("Quotation", "quotations", "document_no", "quote_date", "customer_id", "customers", "total"),
        ("GRN", "goods_receipt_notes", "document_no", "grn_date", "supplier_id", "suppliers", "total"),
        ("Production Order", "production_orders", "document_no", "order_date", None, None, "actual_cost"),
        ("Journal Voucher", "journal_vouchers", "document_no", "voucher_date", None, None, "total_debit"),
    ]
    for doc_type, table, no_col, date_col, party_col, party_table, amt_col in specs:
        if not _table_exists(conn, table):
            continue
        if not _col_exists(conn, table, "status"):
            continue
        if not _col_exists(conn, table, amt_col):
            amt_col = "0"
            amt_sql = "0"
        else:
            amt_sql = f"COALESCE(t.{amt_col}, 0)"
        party_sql = "NULL"
        if party_col and party_table and _table_exists(conn, party_table):
            party_sql = f"(SELECT name FROM {party_table} p WHERE p.id = t.{party_col})"
        conn.execute(
            f"""INSERT OR IGNORE INTO erp_draft_registry
                (doc_type, doc_table, record_id, document_no, doc_date, party_name, amount,
                 status, approval_status, created_by, created_at, updated_by, updated_at)
                SELECT ?, ?, t.id, t.{no_col}, t.{date_col}, {party_sql},
                       {amt_sql}, t.status,
                       COALESCE(t.approval_status, t.status),
                       t.created_by, COALESCE(t.created_at, ?),
                       COALESCE(t.updated_by, t.modified_by), COALESCE(t.updated_at, t.modified_at)
                FROM {table} t
                WHERE LOWER(COALESCE(t.status, 'draft')) IN (
                    'draft', 'open', 'pending_approval', 'pending', 'first_weigh'
                )""",
            (doc_type, table, ts),
        )


def sync_draft_registry_row(
    conn,
    *,
    doc_type: str,
    doc_table: str,
    record_id: int,
    document_no: str = "",
    doc_date: str = "",
    party_name: str = "",
    amount: float = 0,
    status: str = "draft",
    approval_status: str | None = None,
    created_by=None,
    created_at: str = "",
    updated_by=None,
    updated_at: str = "",
) -> None:
    """Upsert or remove one draft registry row."""
    if not _table_exists(conn, "erp_draft_registry"):
        return
    st = (status or "draft").lower()
    if st not in ("draft", "open", "pending_approval", "pending", "first_weigh", "rejected"):
        conn.execute(
            "DELETE FROM erp_draft_registry WHERE doc_table=? AND record_id=?",
            (doc_table, record_id),
        )
        return
    conn.execute(
        """INSERT INTO erp_draft_registry
           (doc_type, doc_table, record_id, document_no, doc_date, party_name, amount,
            status, approval_status, created_by, created_at, updated_by, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(doc_table, record_id) DO UPDATE SET
            document_no=excluded.document_no, doc_date=excluded.doc_date,
            party_name=excluded.party_name, amount=excluded.amount,
            status=excluded.status, approval_status=excluded.approval_status,
            updated_by=excluded.updated_by, updated_at=excluded.updated_at""",
        (
            doc_type, doc_table, record_id, document_no, doc_date, party_name, float(amount or 0),
            status, approval_status or status, created_by, created_at, updated_by, updated_at,
        ),
    )


def persist_invoice_v13_extras(conn, table: str, record_id: int, data: dict) -> None:
    """Persist V13.13 charge / tax header fields when columns exist."""
    if table == "sales_invoices":
        fields = (
            "freight", "loading_charges", "other_charges", "round_off", "grand_weight",
            "registered_taxpayer", "gst_pct", "further_tax_pct", "fed_pct",
        )
    elif table == "purchase_invoices":
        fields = (
            "freight", "loading_charges", "other_charges", "round_off", "grand_weight",
            "supplier_bill_no", "claim_input_tax",
        )
    else:
        return
    if not _table_exists(conn, table):
        return
    sets = []
    vals = []
    for col in fields:
        if col in data and _col_exists(conn, table, col):
            sets.append(f"{col}=?")
            vals.append(data[col])
    if sets:
        vals.append(record_id)
        conn.execute(f"UPDATE {table} SET {', '.join(sets)} WHERE id=?", vals)
