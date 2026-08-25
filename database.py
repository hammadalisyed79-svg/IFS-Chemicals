"""IFS Chemicals ERP - SQLite database layer (schema v2)."""

import hashlib
import os
import re
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from db_cache import (
    cached_read,
    invalidate,
    invalidate_all,
    invalidate_invoices,
    invalidate_masters,
    invalidate_stock,
)

_db_default = Path(__file__).parent / "ifs_erp.db"
DB_PATH = Path(os.environ["IFS_DB_PATH"]) if os.environ.get("IFS_DB_PATH") else _db_default
_DB_INITIALIZED = False
_DB_SEQUENCES_SYNCED = False
_WAL_ENABLED = False
SCHEMA_PATH = Path(__file__).parent / "schema.sql"
SCHEMA_VERSION = "2"

LEGACY_TABLES = [
    "items", "accounts", "purchases", "purchase_items", "sales", "sale_items",
    "purchase_returns", "purchase_return_items", "sale_returns", "sale_return_items",
    "cash_book", "bank_book", "inventory_adjustments",
]

LEGACY_DROP_ORDER = [
    "purchase_return_items", "purchase_returns", "sale_return_items", "sale_returns",
    "purchase_items", "sale_items", "purchases", "sales",
    "inventory_adjustments", "cash_book", "bank_book", "items", "accounts",
]


def hash_password(password: str) -> str:
    from erp_core.password_v173 import hash_password_argon2id
    return hash_password_argon2id(password)


def _now() -> str:
    """Current PC local date/time (system clock), never UTC."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def reset_runtime_state():
    """Clear in-process caches and re-run migrations on next init (e.g. after DB restore)."""
    global _DB_INITIALIZED, _DB_SEQUENCES_SYNCED, _WAL_ENABLED
    _DB_INITIALIZED = False
    _DB_SEQUENCES_SYNCED = False
    _WAL_ENABLED = False
    invalidate_all()


@contextmanager
def get_connection():
    global _WAL_ENABLED
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if not _WAL_ENABLED:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 15000")
        _WAL_ENABLED = True
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_to_dict(row):
    return dict(row) if row else None


def rows_to_list(rows):
    return [dict(r) for r in rows]


def run_paginated_list(
    from_clause,
    select_cols,
    where_parts=None,
    params=None,
    order_by="id DESC",
    page=1,
    page_size=50,
    export_all=False,
    sum_exprs=None,
):
    """Generic server-side paginated list. sum_exprs: SQL expressions e.g. ['COALESCE(SUM(t.total),0)']."""
    where_parts = where_parts or ["1=1"]
    params = list(params or [])
    page = max(1, int(page or 1))
    page_size = min(500, max(10, int(page_size or 50)))
    clause = " AND ".join(where_parts)
    base = f"FROM {from_clause} WHERE {clause}"
    sum_exprs = sum_exprs or []
    agg_select = ", ".join(sum_exprs) if sum_exprs else "0"
    with get_connection() as conn:
        total = conn.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0]
        sums = conn.execute(f"SELECT {agg_select} {base}", params).fetchone()
        if export_all:
            rows = conn.execute(
                f"SELECT {select_cols} {base} ORDER BY {order_by}", params
            ).fetchall()
            pages = 1
            page = 1
        else:
            offset = (page - 1) * page_size
            rows = conn.execute(
                f"SELECT {select_cols} {base} ORDER BY {order_by} LIMIT ? OFFSET ?",
                params + [page_size, offset],
            ).fetchall()
            pages = max(1, (total + page_size - 1) // page_size)
            if page > pages:
                page = pages
    result = {
        "items": rows_to_list(rows),
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }
    if sum_exprs:
        for i, key in enumerate(["sum_total", "sum_paid", "sum_extra"][: len(sum_exprs)]):
            result[key] = float(sums[i] or 0) if sums else 0.0
    else:
        result["sum_total"] = 0.0
        result["sum_paid"] = 0.0
    return result


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _column_exists(conn, table: str, column: str) -> bool:
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    return column in cols


def _get_schema_version(conn) -> int:
    if not _table_exists(conn, "schema_meta"):
        return 0
    row = conn.execute(
        "SELECT value FROM schema_meta WHERE key='schema_version'"
    ).fetchone()
    return int(row[0]) if row else 0


def _set_schema_version(conn, version: int):
    conn.execute(
        "INSERT INTO schema_meta (key, value) VALUES ('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(version),),
    )


def _migration_db_module():
    """Database module ref for migration hooks (safe after Streamlit hot-reload)."""
    import importlib
    name = __name__
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    return importlib.import_module(name)


def init_db(force=False):
    """Initialize schema once per process; optional force after restore or schema repair."""
    global _DB_INITIALIZED, _DB_SEQUENCES_SYNCED
    if _DB_INITIALIZED and not force:
        return
    with get_connection() as conn:
        version = _get_schema_version(conn)
        has_legacy = any(_table_exists(conn, t) for t in LEGACY_TABLES)
        if version < 2 and has_legacy:
            _prepare_legacy_tables(conn)
        if version < 2 or not _table_exists(conn, "products"):
            _apply_schema(conn)
        _ensure_master_columns(conn)
        _seed_system_defaults(conn)
        if version < 2 and has_legacy:
            _migrate_legacy_data(conn)
            _drop_legacy_tables(conn)
        _seed_defaults(conn)
        _set_schema_version(conn, 2)

        db_mod = _migration_db_module()

        # v3 additive migration (preserves all v2 data)
        import db_v3
        db_v3.apply_v3(conn, db_mod)

        # HR & Payroll module (additive)
        import db_hr
        db_hr.apply_hr(conn, db_mod)

        import db_commercial
        db_commercial.apply_commercial(conn, db_mod)

        if not _DB_SEQUENCES_SYNCED or force:
            sync_document_sequences(conn)
            _DB_SEQUENCES_SYNCED = True

        import db_audit
        db_audit.ensure_audit_schema(conn)
        _ensure_user_sessions(conn)
        _migrate_created_at_to_localtime(conn)
        _ensure_pc_clock_triggers(conn)
    _DB_INITIALIZED = True
    try:
        from erp_core.maintenance import run_startup_maintenance
        run_startup_maintenance()
    except Exception:
        pass


def _migrate_created_at_to_localtime(conn):
    """SQLite CURRENT_TIMESTAMP is UTC; convert stored stamp columns to local once.

    New inserts should pass local ``_now()`` explicitly so this does not re-run.
    """
    row = conn.execute(
        "SELECT value FROM schema_meta WHERE key='created_at_localtime_v1'"
    ).fetchone()
    if row and str(row[0]) == "1":
        return
    # Only created_at — posted_at / approved_at / modified_at are usually set via Python local time
    targets = [
        "cash_receipts",
        "cash_payments",
        "bank_receipts",
        "bank_payments",
        "sales_invoices",
        "purchase_invoices",
        "journal_vouchers",
        "party_transfers",
        "expense_bills",
    ]
    for table in targets:
        if not _table_exists(conn, table):
            continue
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "created_at" not in existing:
            continue
        conn.execute(
            f"""UPDATE {table}
               SET created_at = datetime(created_at, 'localtime')
               WHERE created_at IS NOT NULL
                 AND length(created_at) >= 19
                 AND created_at NOT LIKE '%+%'
                 AND created_at NOT LIKE '%Z'"""
        )
    conn.execute(
        "INSERT INTO schema_meta (key, value) VALUES ('created_at_localtime_v1', '1') "
        "ON CONFLICT(key) DO UPDATE SET value='1'"
    )


def _ensure_pc_clock_triggers(conn):
    """If an insert relies on SQLite CURRENT_TIMESTAMP (UTC), rewrite to PC local time.

    When ``created_at`` was set explicitly with ``_now()`` (local), it differs from
    UTC ``now`` by the timezone offset, so the trigger does not overwrite it.
    """
    tables = [
        "cash_receipts",
        "cash_payments",
        "bank_receipts",
        "bank_payments",
        "sales_invoices",
        "purchase_invoices",
        "journal_vouchers",
        "party_transfers",
        "expense_bills",
        "sales_orders",
        "purchase_orders",
        "delivery_notes",
        "goods_receipt_notes",
        "gate_passes",
        "weight_slips",
    ]
    for table in tables:
        if not _table_exists(conn, table):
            continue
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "created_at" not in cols or "id" not in cols:
            continue
        trg = f"trg_{table}_created_at_pc_clock"
        conn.execute(f"DROP TRIGGER IF EXISTS {trg}")
        conn.execute(
            f"""
            CREATE TRIGGER {trg}
            AFTER INSERT ON {table}
            FOR EACH ROW
            WHEN NEW.created_at IS NOT NULL
             AND abs(strftime('%s', NEW.created_at) - strftime('%s', 'now')) <= 2
            BEGIN
              UPDATE {table}
                 SET created_at = datetime('now', 'localtime')
               WHERE id = NEW.id;
            END
            """
        )


def _ensure_user_sessions(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS user_sessions (
            token       TEXT PRIMARY KEY,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
            expires_at  TEXT NOT NULL
        )"""
    )
    for col, ddl in (
        ("last_activity_at", "TEXT"),
        ("ip_address", "TEXT"),
        ("user_agent", "TEXT"),
    ):
        cols = [r[1] for r in conn.execute("PRAGMA table_info(user_sessions)").fetchall()]
        if col not in cols:
            conn.execute(f"ALTER TABLE user_sessions ADD COLUMN {col} {ddl}")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_sessions_exp ON user_sessions(expires_at)"
    )
    conn.execute("DELETE FROM user_sessions WHERE expires_at < ?", (_now(),))


def _apply_schema(conn):
    if SCHEMA_PATH.exists():
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def _prepare_legacy_tables(conn):
    for table in LEGACY_TABLES:
        if _table_exists(conn, table):
            conn.execute(f"ALTER TABLE {table} RENAME TO _legacy_{table}")


def _drop_legacy_tables(conn):
    conn.execute("PRAGMA foreign_keys = OFF")
    for table in LEGACY_DROP_ORDER:
        legacy = f"_legacy_{table}"
        if _table_exists(conn, legacy):
            conn.execute(f"DROP TABLE IF EXISTS {legacy}")
    conn.execute("PRAGMA foreign_keys = ON")


def _ensure_master_columns(conn):
    alters = {
        "customers": [
            ("current_balance", "ALTER TABLE customers ADD COLUMN current_balance REAL DEFAULT 0"),
            ("created_by", "ALTER TABLE customers ADD COLUMN created_by INTEGER REFERENCES users(id)"),
            ("modified_by", "ALTER TABLE customers ADD COLUMN modified_by INTEGER"),
            ("modified_at", "ALTER TABLE customers ADD COLUMN modified_at TEXT"),
            ("ntn", "ALTER TABLE customers ADD COLUMN ntn TEXT"),
            ("strn", "ALTER TABLE customers ADD COLUMN strn TEXT"),
            ("province", "ALTER TABLE customers ADD COLUMN province TEXT"),
        ],
        "suppliers": [
            ("current_balance", "ALTER TABLE suppliers ADD COLUMN current_balance REAL DEFAULT 0"),
            ("created_by", "ALTER TABLE suppliers ADD COLUMN created_by INTEGER REFERENCES users(id)"),
            ("modified_by", "ALTER TABLE suppliers ADD COLUMN modified_by INTEGER"),
            ("modified_at", "ALTER TABLE suppliers ADD COLUMN modified_at TEXT"),
        ],
        "users": [
            ("created_by", "ALTER TABLE users ADD COLUMN created_by INTEGER REFERENCES users(id)"),
            ("modified_by", "ALTER TABLE users ADD COLUMN modified_by INTEGER"),
            ("modified_at", "ALTER TABLE users ADD COLUMN modified_at TEXT"),
        ],
    }
    for table, specs in alters.items():
        if not _table_exists(conn, table):
            continue
        for col, sql in specs:
            if not _column_exists(conn, table, col):
                conn.execute(sql)
        if table in ("customers", "suppliers") and _column_exists(conn, table, "balance"):
            conn.execute(
                f"UPDATE {table} SET current_balance = balance "
                f"WHERE current_balance IS NULL OR current_balance = 0"
            )


def _seed_system_defaults(conn):
    admin = conn.execute("SELECT id FROM users WHERE username=?", ("admin",)).fetchone()
    if not admin:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        import secrets
        from erp_core.password_v173 import hash_password_argon2id
        raw_bootstrap = secrets.token_urlsafe(16)
        bootstrap_pw = hash_password_argon2id(f"IFS!{raw_bootstrap[:8]}aZ9#")
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='schema_meta'").fetchone():
            conn.execute(
                "INSERT INTO schema_meta(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                ("bootstrap_admin_password", f"IFS!{raw_bootstrap[:8]}aZ9#"),
            )
        if "must_change_password" in cols:
            conn.execute(
                "INSERT INTO users (username, password_hash, full_name, role, must_change_password) VALUES (?, ?, ?, ?, 1)",
                ("admin", bootstrap_pw, "System Administrator", "admin"),
            )
        else:
            conn.execute(
                "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                ("admin", bootstrap_pw, "System Administrator", "admin"),
            )
        admin = conn.execute("SELECT id FROM users WHERE username=?", ("admin",)).fetchone()
    admin_id = admin[0]

    if conn.execute("SELECT COUNT(*) FROM warehouses").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO warehouses (code, name, is_default, created_by) VALUES (?, ?, 1, ?)",
            ("WH001", "Main Warehouse", admin_id),
        )

    if conn.execute("SELECT COUNT(*) FROM units_of_measure").fetchone()[0] == 0:
        units = [("U001", "Kilogram", "KG"), ("U002", "Liter", "L"), ("U003", "Bag", "Bag"),
                 ("U004", "Drum", "Drum"), ("U005", "Carton", "CTN"), ("U006", "Piece", "Pcs")]
        conn.executemany(
            "INSERT INTO units_of_measure (code, name, symbol, created_by) VALUES (?, ?, ?, ?)",
            [(c, n, s, admin_id) for c, n, s in units],
        )

    if conn.execute("SELECT COUNT(*) FROM product_categories").fetchone()[0] == 0:
        cats = [("CAT001", "Raw Material"), ("CAT002", "Finished Product"), ("CAT003", "Packaging"),
                ("CAT004", "Chemical"), ("CAT005", "Detergent"), ("CAT006", "Other")]
        conn.executemany(
            "INSERT INTO product_categories (code, name, created_by) VALUES (?, ?, ?)",
            [(c, n, admin_id) for c, n in cats],
        )

    if conn.execute("SELECT COUNT(*) FROM account_groups").fetchone()[0] == 0:
        groups = [
            ("AG1000", "Assets", "asset"), ("AG2000", "Liabilities", "liability"),
            ("AG3000", "Equity", "equity"), ("AG4000", "Income", "income"), ("AG5000", "Expenses", "expense"),
        ]
        conn.executemany(
            "INSERT INTO account_groups (code, name, group_type, created_by) VALUES (?, ?, ?, ?)",
            [(c, n, t, admin_id) for c, n, t in groups],
        )

    seq_defaults = [
        ("CUS", "CUS", 3), ("SUP", "SUP", 3), ("PRD", "ITM", 3), ("ACC", "ACC", 3),
        ("PO", "PO", 4), ("PI", "PUR", 4), ("PR", "PR", 4), ("SO", "SO", 4),
        ("SI", "SAL", 4), ("SR", "SR", 4), ("JV", "JV", 4), ("CR", "CR", 4),
        ("CP", "CP", 4), ("BR", "BR", 4), ("BP", "BP", 4),
        ("EB", "EB", 4),
    ]
    for doc_type, prefix, padding in seq_defaults:
        conn.execute(
            "INSERT OR IGNORE INTO document_sequences (doc_type, prefix, padding) VALUES (?, ?, ?)",
            (doc_type, prefix, padding),
        )


def _seed_defaults(conn):
    admin_id = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]

    if conn.execute("SELECT COUNT(*) FROM chart_of_accounts").fetchone()[0] == 0:
        group_map = {r["group_type"]: r["id"] for r in conn.execute("SELECT id, group_type FROM account_groups")}
        default_accounts = [
            ("1000", "Cash in Hand", "asset"), ("1100", "Bank Account", "asset"),
            ("1200", "Accounts Receivable", "asset"), ("1300", "Inventory", "asset"),
            ("2000", "Accounts Payable", "liability"), ("3000", "Owner's Equity", "equity"),
            ("4000", "Sales Revenue", "income"), ("4100", "Sales Returns", "income"),
            ("5000", "Cost of Goods Sold", "expense"), ("5100", "Purchase Expense", "expense"),
            ("5200", "Operating Expenses", "expense"),
        ]
        conn.executemany(
            """INSERT INTO chart_of_accounts (code, name, account_group_id, opening_balance, current_balance, created_by)
               VALUES (?, ?, ?, 0, 0, ?)""",
            [(c, n, group_map[t], admin_id) for c, n, t in default_accounts],
        )

    if conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO employees (code, full_name, department, designation, user_id, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("EMP001", "System Administrator", "Administration", "Admin", admin_id, admin_id),
        )


def _migrate_legacy_data(conn):
    admin_id = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
    wh_id = conn.execute("SELECT id FROM warehouses WHERE is_default=1").fetchone()[0]

    if _table_exists(conn, "_legacy_accounts"):
        group_map = {r["group_type"]: r["id"] for r in conn.execute("SELECT id, group_type FROM account_groups")}
        for row in conn.execute("SELECT * FROM _legacy_accounts").fetchall():
            gid = group_map.get(row["account_type"], group_map["asset"])
            conn.execute(
                """INSERT OR IGNORE INTO chart_of_accounts
                   (id, code, name, account_group_id, parent_id, opening_balance, current_balance, is_active, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (row["id"], row["code"], row["name"], gid, row["parent_id"],
                 row["opening_balance"], row["balance"], row["is_active"], row["created_at"]),
            )

    cat_cache, unit_cache = {}, {}
    if _table_exists(conn, "_legacy_items"):
        for row in conn.execute("SELECT DISTINCT category FROM _legacy_items WHERE category IS NOT NULL AND category != ''"):
            name = row[0]
            code = f"CAT{len(cat_cache)+1:03d}"
            cur = conn.execute(
                "INSERT OR IGNORE INTO product_categories (code, name, created_by) VALUES (?, ?, ?)",
                (code, name, admin_id),
            )
            cid = conn.execute("SELECT id FROM product_categories WHERE name=?", (name,)).fetchone()[0]
            cat_cache[name] = cid
        for row in conn.execute("SELECT DISTINCT unit FROM _legacy_items WHERE unit IS NOT NULL"):
            sym = row[0] or "KG"
            uid = conn.execute("SELECT id FROM units_of_measure WHERE symbol=?", (sym,)).fetchone()
            if not uid:
                code = f"U{len(unit_cache)+100:03d}"
                conn.execute(
                    "INSERT INTO units_of_measure (code, name, symbol, created_by) VALUES (?, ?, ?, ?)",
                    (code, sym, sym, admin_id),
                )
                uid = conn.execute("SELECT id FROM units_of_measure WHERE symbol=?", (sym,)).fetchone()
            unit_cache[sym] = uid[0]

        for row in conn.execute("SELECT * FROM _legacy_items").fetchall():
            cat_id = cat_cache.get(row["category"])
            unit_id = unit_cache.get(row["unit"], conn.execute("SELECT id FROM units_of_measure WHERE symbol='KG'").fetchone()[0])
            conn.execute(
                """INSERT INTO products (id, code, name, category_id, unit_id, product_type,
                   purchase_price, sale_price, reorder_level, default_warehouse_id, is_active, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (row["id"], row["code"], row["name"], cat_id, unit_id, row["item_type"],
                 row["purchase_price"], row["sale_price"], row["reorder_level"], wh_id,
                 row["is_active"], row["created_at"]),
            )
            if row["stock_qty"]:
                conn.execute(
                    "INSERT INTO warehouse_stock (warehouse_id, product_id, quantity) VALUES (?, ?, ?)",
                    (wh_id, row["id"], row["stock_qty"]),
                )

    if _table_exists(conn, "_legacy_purchases"):
        for p in conn.execute("SELECT * FROM _legacy_purchases").fetchall():
            conn.execute(
                """INSERT INTO purchase_invoices (id, document_no, invoice_date, supplier_id, subtotal, discount, tax,
                   total, paid_amount, payment_mode, notes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (p["id"], p["invoice_no"], p["purchase_date"], p["supplier_id"], p["subtotal"],
                 p["discount"], p["tax"], p["total"], p["paid_amount"], p["payment_mode"],
                 p["notes"], p["created_at"]),
            )
            _sync_doc_sequence(conn, "PI", p["invoice_no"])
        for li in conn.execute("SELECT * FROM _legacy_purchase_items").fetchall():
            conn.execute(
                "INSERT INTO purchase_invoice_items (id, invoice_id, product_id, quantity, rate, amount) VALUES (?, ?, ?, ?, ?, ?)",
                (li["id"], li["purchase_id"], li["item_id"], li["quantity"], li["rate"], li["amount"]),
            )

    if _table_exists(conn, "_legacy_sales"):
        for s in conn.execute("SELECT * FROM _legacy_sales").fetchall():
            conn.execute(
                """INSERT INTO sales_invoices (id, document_no, invoice_date, customer_id, subtotal, discount, tax,
                   total, paid_amount, payment_mode, notes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (s["id"], s["invoice_no"], s["sale_date"], s["customer_id"], s["subtotal"],
                 s["discount"], s["tax"], s["total"], s["paid_amount"], s["payment_mode"],
                 s["notes"], s["created_at"]),
            )
            _sync_doc_sequence(conn, "SI", s["invoice_no"])
        for li in conn.execute("SELECT * FROM _legacy_sale_items").fetchall():
            conn.execute(
                "INSERT INTO sales_invoice_items (id, invoice_id, product_id, quantity, rate, amount) VALUES (?, ?, ?, ?, ?, ?)",
                (li["id"], li["sale_id"], li["item_id"], li["quantity"], li["rate"], li["amount"]),
            )

    if _table_exists(conn, "_legacy_purchase_returns"):
        for r in conn.execute("SELECT * FROM _legacy_purchase_returns").fetchall():
            conn.execute(
                """INSERT INTO purchase_returns (id, document_no, return_date, supplier_id, invoice_id,
                   subtotal, total, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (r["id"], r["return_no"], r["return_date"], r["supplier_id"], r["purchase_id"],
                 r["subtotal"], r["total"], r["notes"], r["created_at"]),
            )
            _sync_doc_sequence(conn, "PR", r["return_no"])
        for li in conn.execute("SELECT * FROM _legacy_purchase_return_items").fetchall():
            conn.execute(
                "INSERT INTO purchase_return_items (id, return_id, product_id, quantity, rate, amount) VALUES (?, ?, ?, ?, ?, ?)",
                (li["id"], li["return_id"], li["item_id"], li["quantity"], li["rate"], li["amount"]),
            )

    if _table_exists(conn, "_legacy_sale_returns"):
        for r in conn.execute("SELECT * FROM _legacy_sale_returns").fetchall():
            conn.execute(
                """INSERT INTO sales_returns (id, document_no, return_date, customer_id, invoice_id,
                   subtotal, total, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (r["id"], r["return_no"], r["return_date"], r["customer_id"], r["sale_id"],
                 r["subtotal"], r["total"], r["notes"], r["created_at"]),
            )
            _sync_doc_sequence(conn, "SR", r["return_no"])
        for li in conn.execute("SELECT * FROM _legacy_sale_return_items").fetchall():
            conn.execute(
                "INSERT INTO sales_return_items (id, return_id, product_id, quantity, rate, amount) VALUES (?, ?, ?, ?, ?, ?)",
                (li["id"], li["return_id"], li["item_id"], li["quantity"], li["rate"], li["amount"]),
            )

    if _table_exists(conn, "_legacy_cash_book"):
        n = 0
        for e in conn.execute("SELECT * FROM _legacy_cash_book ORDER BY id").fetchall():
            n += 1
            doc = f"CR-{n:04d}" if e["entry_type"] == "credit" else f"CP-{n:04d}"
            if e["entry_type"] == "credit":
                conn.execute(
                    """INSERT INTO cash_receipts (receipt_date, document_no, account_id, description, reference_no, amount, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (e["entry_date"], doc, e["account_id"], e["description"], e["reference_no"], e["amount"], e["created_at"]),
                )
            else:
                conn.execute(
                    """INSERT INTO cash_payments (payment_date, document_no, account_id, description, reference_no, amount, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (e["entry_date"], doc, e["account_id"], e["description"], e["reference_no"], e["amount"], e["created_at"]),
                )

    if _table_exists(conn, "_legacy_bank_book"):
        n = 0
        for e in conn.execute("SELECT * FROM _legacy_bank_book ORDER BY id").fetchall():
            n += 1
            doc = f"BR-{n:04d}" if e["entry_type"] == "credit" else f"BP-{n:04d}"
            if e["entry_type"] == "credit":
                conn.execute(
                    """INSERT INTO bank_receipts (receipt_date, document_no, account_id, description, reference_no, amount, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (e["entry_date"], doc, e["account_id"], e["description"], e["reference_no"], e["amount"], e["created_at"]),
                )
            else:
                conn.execute(
                    """INSERT INTO bank_payments (payment_date, document_no, account_id, description, reference_no, amount, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (e["entry_date"], doc, e["account_id"], e["description"], e["reference_no"], e["amount"], e["created_at"]),
                )

    if _table_exists(conn, "_legacy_inventory_adjustments"):
        for a in conn.execute("SELECT * FROM _legacy_inventory_adjustments").fetchall():
            conn.execute(
                """INSERT INTO inventory_movements (movement_date, product_id, warehouse_id, movement_type,
                   quantity, reference_type, reference_id, reason, created_at)
                   VALUES (?, ?, ?, ?, ?, 'adjustment', ?, ?, ?)""",
                (a["adjustment_date"], a["item_id"], wh_id, a["adjustment_type"],
                 a["quantity"], a["id"], a["reason"], a["created_at"]),
            )


def _parse_doc_number(document_no):
    if not document_no:
        return None
    try:
        return int(str(document_no).strip().split("-")[-1])
    except (ValueError, IndexError, TypeError):
        digits = "".join(c for c in str(document_no) if c.isdigit())
        return int(digits) if digits else None


def _sync_doc_sequence(conn, doc_type: str, document_no: str):
    num = _parse_doc_number(document_no)
    if num is None:
        return
    row = conn.execute("SELECT last_number FROM document_sequences WHERE doc_type=?", (doc_type,)).fetchone()
    if row and num > row[0]:
        conn.execute(
            "UPDATE document_sequences SET last_number=?, modified_at=? WHERE doc_type=?",
            (num, _now(), doc_type),
        )


DOC_NUMBER_SOURCES = {
    "PI": [("purchase_invoices", "document_no")],
    "SI": [("sales_invoices", "document_no")],
    "PR": [("purchase_returns", "document_no")],
    "SR": [("sales_returns", "document_no")],
    "PO": [("purchase_orders", "document_no")],
    "SO": [("sales_orders", "document_no")],
    "QT": [("quotations", "document_no")],
    "DN": [("delivery_notes", "document_no")],
    "PRQ": [("purchase_requisitions", "document_no")],
    "GRN": [("goods_receipt_notes", "document_no")],
    "WS": [("weight_slips", "document_no")],
    "BOM": [("bom_formulas", "document_no")],
    "PRO": [("production_orders", "document_no")],
    "BAT": [("production_orders", "batch_no")],
    "JV": [("journal_vouchers", "document_no")],
    "CR": [("cash_receipts", "document_no")],
    "CP": [("cash_payments", "document_no")],
    "BR": [("bank_receipts", "document_no")],
    "BP": [("bank_payments", "document_no")],
    "GP": [("gate_passes", "document_no")],
    "JCG": [("job_cards", "document_no")],
    "JCC": [("job_cards", "document_no")],
    "PT": [("party_transfers", "document_no")],
    "LVR": [("leave_requests", "document_no")],
    "PAY": [("payroll_runs", "document_no")],
    "ADV": [("employee_advances", "document_no")],
    "LON": [("employee_loans", "document_no")],
    "EXP": [("expense_claims", "document_no")],
    "SRV": [("stock_revaluations", "document_no")],
    "EB": [("expense_bills", "document_no")],
    "CA": [("cash_advances", "document_no")],
    "CAS": [("cash_advance_settlements", "document_no")],
}


def _max_doc_suffix_from_table(conn, table, col):
    """Highest numeric suffix in a document_no column (handles SAL-26080140 and FMYE 26080139)."""
    if not _table_exists(conn, table):
        return 0
    max_n = 0
    # Prefixed docs: take the part after the last hyphen when it is all digits
    row = conn.execute(
        f"""SELECT MAX(
                CAST(substr({col}, instr({col}, '-') + 1) AS INTEGER)
            ) FROM {table}
            WHERE {col} IS NOT NULL AND TRIM({col}) != '' AND {col} LIKE '%-%'
              AND substr({col}, instr({col}, '-') + 1) GLOB '[0-9]*'""",
    ).fetchone()
    if row and row[0] is not None:
        max_n = max(max_n, int(row[0] or 0))
    # Bare numeric docs (FMYE import style) — must scan all rows, not a LIMIT sample
    for r in conn.execute(
        f"""SELECT {col} FROM {table}
            WHERE {col} IS NOT NULL AND TRIM({col}) != ''
              AND ({col} GLOB '[0-9]*' OR {col} LIKE '%-%')"""
    ):
        n = _parse_doc_number(r[0])
        if n is not None and n > max_n:
            max_n = n
    return max_n


def sync_document_sequences(conn=None):
    """Align sequence counters with the highest document numbers already in the database."""
    def _run(c):
        for doc_type, sources in DOC_NUMBER_SOURCES.items():
            max_n = 0
            for table, col in sources:
                max_n = max(max_n, _max_doc_suffix_from_table(c, table, col))
            if max_n <= 0:
                continue
            row = c.execute("SELECT last_number FROM document_sequences WHERE doc_type=?", (doc_type,)).fetchone()
            if row and max_n > row[0]:
                c.execute(
                    "UPDATE document_sequences SET last_number=?, modified_at=? WHERE doc_type=?",
                    (max_n, _now(), doc_type),
                )
    if conn:
        _run(conn)
    else:
        with get_connection() as c:
            _run(c)


def _peek_document_conn(conn, doc_type: str) -> str:
    row = conn.execute(
        "SELECT prefix, last_number, padding FROM document_sequences WHERE doc_type=?",
        (doc_type,),
    ).fetchone()
    if not row:
        return f"{doc_type}-0001"
    table_max = 0
    for table, col in DOC_NUMBER_SOURCES.get(doc_type, []):
        table_max = max(table_max, _max_doc_suffix_from_table(conn, table, col))
    num = max(int(row["last_number"] or 0), table_max) + 1
    return f"{row['prefix']}-{num:0{row['padding']}d}"


def _document_no_in_use(conn, doc_type: str, document_no: str) -> bool:
    """True if this document number already exists in any source table for the type."""
    doc = (document_no or "").strip()
    if not doc:
        return False
    for table, col in DOC_NUMBER_SOURCES.get(doc_type, []):
        if not _table_exists(conn, table):
            continue
        try:
            hit = conn.execute(
                f"SELECT 1 FROM {table} WHERE TRIM(COALESCE({col},''))=? LIMIT 1",
                (doc,),
            ).fetchone()
        except sqlite3.Error:
            continue
        if hit:
            return True
    return False


def _reserve_document_conn(conn, doc_type: str) -> str:
    """Atomically reserve the next free document number (safe for concurrent users)."""
    for _ in range(40):
        row = conn.execute(
            "SELECT prefix, last_number, padding FROM document_sequences WHERE doc_type=?",
            (doc_type,),
        ).fetchone()
        if not row:
            prefix = {"SI": "SAL", "PI": "PUR"}.get(doc_type, doc_type)
            conn.execute(
                "INSERT OR IGNORE INTO document_sequences(doc_type, prefix, padding, last_number) "
                "VALUES(?,?,?,0)",
                (doc_type, prefix, 4),
            )
            continue

        table_max = 0
        for table, col in DOC_NUMBER_SOURCES.get(doc_type, []):
            table_max = max(table_max, _max_doc_suffix_from_table(conn, table, col))
        current = int(row["last_number"] or 0)
        num = max(current, table_max) + 1
        cur = conn.execute(
            """UPDATE document_sequences
               SET last_number=?, modified_at=?
               WHERE doc_type=? AND last_number=?""",
            (num, _now(), doc_type, current),
        )
        if cur.rowcount == 0:
            # Another session reserved the same counter — retry
            continue

        pad = int(row["padding"] or 4)
        prefix = row["prefix"]
        # Skip any numbers already present (gaps / concurrent insert / imports)
        while True:
            doc = f"{prefix}-{num:0{pad}d}"
            if not _document_no_in_use(conn, doc_type, doc):
                if num != current + 1 and num != max(current, table_max) + 1:
                    conn.execute(
                        "UPDATE document_sequences SET last_number=?, modified_at=? WHERE doc_type=?",
                        (num, _now(), doc_type),
                    )
                return doc
            num += 1
            if num > max(current, table_max) + 5000:
                break
            conn.execute(
                "UPDATE document_sequences SET last_number=?, modified_at=? WHERE doc_type=?",
                (num, _now(), doc_type),
            )
    raise ValueError(
        f"Could not allocate a unique {doc_type} document number. Please try saving again."
    )


# --- Document numbers ---
def peek_document(doc_type: str) -> str:
    """Preview next document number without consuming it (safe for form display)."""
    with get_connection() as conn:
        return _peek_document_conn(conn, doc_type)


def next_document(doc_type: str) -> str:
    """Reserve and return the next document number (use only at save/post time)."""
    with get_connection() as conn:
        return _reserve_document_conn(conn, doc_type)


def ensure_document_no(doc_type: str, document_no=None, conn=None):
    """Confirm or reserve a document number when saving. Updates sequence to match.

    If multiple users prepare invoices with the same peeked number, the first save
    keeps it; later saves automatically get the next free number (no sequence error).
    """
    doc = (document_no or "").strip() if document_no is not None else ""
    auto_vals = {"", "AUTO", "auto"}

    def _run(c):
        if doc and doc.upper() not in auto_vals:
            if _document_no_in_use(c, doc_type, doc):
                # Peeked/stale number already taken by another user — take next free
                return _reserve_document_conn(c, doc_type)
            _sync_doc_sequence(c, doc_type, doc)
            return doc
        return _reserve_document_conn(c, doc_type)

    if conn is not None:
        return _run(conn)
    with get_connection() as c:
        return _run(c)


def next_code(prefix, table, code_col="code"):
    table_map = {"items": "products", "accounts": "chart_of_accounts"}
    return _next_master_code(prefix, table_map.get(table, table), code_col)


def _next_master_code(prefix, table, code_col="code"):
    with get_connection() as conn:
        row = conn.execute(f"SELECT {code_col} FROM {table} ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return f"{prefix}001"
        num = int("".join(c for c in row[0] if c.isdigit()) or "0") + 1
        return f"{prefix}{num:03d}"


def next_invoice(prefix, table, col="document_no"):
    mapping = {
        "purchases": "PI", "purchase_invoices": "PI", "purchase_returns": "PR",
        "sales": "SI", "sales_invoices": "SI", "sale_returns": "SR", "sales_returns": "SR",
    }
    doc_type = mapping.get(table, prefix)
    return next_document(doc_type)


def peek_invoice(prefix, table, col="document_no"):
    mapping = {
        "purchases": "PI", "purchase_invoices": "PI", "purchase_returns": "PR",
        "sales": "SI", "sales_invoices": "SI", "sale_returns": "SR", "sales_returns": "SR",
    }
    doc_type = mapping.get(table, prefix)
    return peek_document(doc_type)


def _default_warehouse_id(conn):
    row = conn.execute("SELECT id FROM warehouses WHERE is_default=1 LIMIT 1").fetchone()
    return row[0] if row else None


def _product_stock_join(alias="p"):
    return f"""LEFT JOIN (
        SELECT product_id, COALESCE(SUM(quantity), 0) AS _stock_qty
        FROM warehouse_stock
        GROUP BY product_id
    ) _pstk ON _pstk.product_id = {alias}.id"""


def _product_stock_sql(alias="p"):
    """Requires {_product_stock_join(alias)} on the same query FROM clause."""
    return "COALESCE(_pstk._stock_qty, 0)"


PRODUCT_SELECT = f"""
    SELECT p.*, pc.name AS category, u.symbol AS unit,
           {_product_stock_sql('p')} AS stock_qty,
           p.product_type AS item_type,
           mg.name AS group_name, mg.code AS group_code
    FROM products p
    {_product_stock_join('p')}
    LEFT JOIN product_categories pc ON p.category_id = pc.id
    LEFT JOIN units_of_measure u ON p.unit_id = u.id
    LEFT JOIN master_groups mg ON p.group_id = mg.id AND mg.entity_type = 'product'
"""

_CUSTOMER_SELECT = """
    SELECT c.*, c.current_balance AS balance,
           mg.name AS group_name, mg.code AS group_code
    FROM customers c
    LEFT JOIN master_groups mg ON c.group_id = mg.id AND mg.entity_type = 'customer'
"""

_SUPPLIER_SELECT = """
    SELECT s.*, s.current_balance AS balance,
           mg.name AS group_name, mg.code AS group_code
    FROM suppliers s
    LEFT JOIN master_groups mg ON s.group_id = mg.id AND mg.entity_type = 'supplier'
"""


# --- Auth ---
def _normalize_username(username: str) -> str:
    return (username or "").strip()


def _find_user_row(conn, username: str, *, active_only: bool = False):
    un = _normalize_username(username)
    if not un:
        return None
    sql = "SELECT * FROM users WHERE LOWER(username) = LOWER(?)"
    if active_only:
        sql += " AND is_active=1"
    return conn.execute(sql, (un,)).fetchone()


def authenticate(username: str, password: str, *, ip: str | None = None, user_agent: str | None = None):
    from erp_core.v15_security import (
        is_account_locked,
        record_login_attempt,
        verify_password,
    )
    from erp_core.password_v173 import needs_rehash, hash_password_argon2id, record_password_history

    deferred: list[tuple] = []
    result = None

    with get_connection() as conn:
        row = _find_user_row(conn, username, active_only=True)
        login_name = _normalize_username(username)
        if not row:
            deferred.append(("login_attempt", login_name, False, None, ip, user_agent, "unknown_user"))
            try:
                from db_audit import log_event
                log_event("users", None, "login_failed", user_id=None, module="Admin",
                          summary=f"Failed sign-in: {login_name}")
            except Exception:
                pass
            result = None
        else:
            u = row_to_dict(row)
            locked, lock_msg = is_account_locked(u)
            if locked:
                deferred.append(("login_attempt", login_name, False, u["id"], ip, user_agent, "locked"))
                result = {"_error": lock_msg}
            elif not verify_password(password, u.get("password_hash") or ""):
                row = conn.execute(
                    "SELECT failed_login_count FROM users WHERE id=?", (u["id"],)
                ).fetchone()
                count = (row[0] or 0) + 1 if row else 1
                locked_until = None
                from erp_core.v15_security import lockout_minutes, max_failed_logins
                if count >= max_failed_logins():
                    from datetime import timedelta
                    locked_until = (
                        datetime.now() + timedelta(minutes=lockout_minutes())
                    ).strftime("%Y-%m-%d %H:%M:%S")
                conn.execute(
                    "UPDATE users SET failed_login_count=?, locked_until=? WHERE id=?",
                    (count, locked_until, u["id"]),
                )
                deferred.append(("login_attempt", login_name, False, u["id"], ip, user_agent, "bad_password"))
                try:
                    from db_audit import log_event
                    log_event("users", u["id"], "login_failed", user_id=u["id"], module="Admin",
                              summary=f"Failed sign-in: {login_name}")
                except Exception:
                    pass
                result = None
            else:
                conn.execute(
                    "UPDATE users SET failed_login_count=0, locked_until=NULL WHERE id=?",
                    (u["id"],),
                )
                conn.execute(
                    "UPDATE users SET last_login_at=?, last_login_ip=?, last_login_device=? WHERE id=?",
                    (_now(), ip, (user_agent or "")[:500], u["id"]),
                )
                if needs_rehash(u.get("password_hash") or ""):
                    new_h = hash_password_argon2id(password)
                    conn.execute(
                        "UPDATE users SET password_hash=?, password_changed_at=? WHERE id=?",
                        (new_h, _now(), u["id"]),
                    )
                    record_password_history(u["id"], new_h, conn=conn)
                deferred.append(("login_attempt", login_name, True, u["id"], ip, user_agent, None))
                deferred.append(("audit", u["id"], u["username"], ip, user_agent))
                result = u

    for item in deferred:
        if item[0] == "login_attempt":
            _, un, ok, uid, lip, ua, reason = item
            record_login_attempt(un, ok, user_id=uid, ip=lip, user_agent=ua, reason=reason)
        elif item[0] == "audit":
            _, uid, un, lip, ua = item
            try:
                from db_audit import log_event
                log_event("users", uid, "login", user_id=uid, module="Admin", summary=f"Signed in as {un}")
                from erp_core.v15_security import log_access
                log_access(uid, "login", "Auth", lip, ua)
            except Exception:
                pass
    return result


def create_user_session(user_id: int, days: int = 30, *, ip: str | None = None, user_agent: str | None = None) -> str:
    """Create a session token. Only one active session per user (previous logins revoked)."""
    import secrets
    from datetime import timedelta

    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(days=max(1, int(days)))).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute("DELETE FROM user_sessions WHERE expires_at < ?", (_now(),))
        # Single concurrent login: sign out every other device for this user
        conn.execute("DELETE FROM user_sessions WHERE user_id=?", (user_id,))
        conn.execute(
            """INSERT INTO user_sessions(token, user_id, expires_at, last_activity_at, ip_address, user_agent)
               VALUES(?,?,?,?,?,?)""",
            (token, user_id, expires, _now(), ip, (user_agent or "")[:500]),
        )
    return token


def get_user_by_session_token(token: str, *, ip: str | None = None, user_agent: str | None = None):
    if not token:
        return None
    try:
        from erp_core.v15_security import touch_session
        if not touch_session(token, ip, user_agent):
            return None
    except Exception:
        pass
    with get_connection() as conn:
        row = conn.execute(
            """SELECT u.* FROM users u
               JOIN user_sessions s ON s.user_id = u.id
               WHERE s.token=? AND s.expires_at > ? AND u.is_active=1""",
            (token.strip(), _now()),
        ).fetchone()
        return row_to_dict(row) if row else None


def delete_user_session(token: str) -> None:
    if not token:
        return
    with get_connection() as conn:
        conn.execute("DELETE FROM user_sessions WHERE token=?", (token.strip(),))


def verify_user_password(user_id, password):
    """Confirm the user's login password (e.g. before sensitive admin actions)."""
    if not user_id or not password:
        return False
    from erp_core.v15_security import verify_password
    with get_connection() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id=? AND is_active=1", (user_id,),
        ).fetchone()
        if not row:
            return False
        return verify_password(password, row[0])


def change_user_password(user_id: int, new_password: str, *, clear_must_change: bool = True) -> None:
    from erp_core.v15_security import hash_password_secure, validate_password_strength
    ok, msg = validate_password_strength(new_password)
    if not ok:
        raise ValueError(msg)
    pwd_hash = hash_password_secure(new_password)
    with get_connection() as conn:
        if clear_must_change:
            conn.execute(
                "UPDATE users SET password_hash=?, must_change_password=0, modified_at=? WHERE id=?",
                (pwd_hash, _now(), user_id),
            )
        else:
            conn.execute(
                "UPDATE users SET password_hash=?, modified_at=? WHERE id=?",
                (pwd_hash, _now(), user_id),
            )


def get_users():
    with get_connection() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        base = "id, username, full_name, role, is_active, created_at, modified_at"
        extra = [c for c in ("user_type", "linked_customer_id", "last_login_at", "role_id") if c in cols]
        select = base + (", " + ", ".join(extra) if extra else "")
        return rows_to_list(conn.execute(
            f"SELECT {select} FROM users ORDER BY username"
        ).fetchall())


def get_user_by_id(user_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return row_to_dict(row)


def add_user(username, password, full_name, role="user", created_by=None, **extra):
    from erp_core.v15_security import hash_password_secure, validate_password_strength
    username = _normalize_username(username)
    if not username:
        raise ValueError("Username is required.")
    ok, msg = validate_password_strength(password)
    if not ok:
        raise ValueError(msg)
    pwd_hash = hash_password_secure(password)
    cols = ["username", "password_hash", "full_name", "role", "created_by"]
    vals = [username, pwd_hash, full_name, role, created_by]
    for k in ("user_type", "linked_customer_id", "role_id", "must_change_password"):
        if k in extra and extra[k] is not None:
            cols.append(k)
            vals.append(extra[k])
    placeholders = ", ".join("?" * len(cols))
    col_sql = ", ".join(cols)
    with get_connection() as conn:
        if _find_user_row(conn, username):
            raise ValueError("Username already exists (not case sensitive).")
        cur = conn.execute(
            f"INSERT INTO users ({col_sql}) VALUES ({placeholders})",
            vals,
        )
        rid = cur.lastrowid
        try:
            from db_audit import log_event
            log_event(
                "users", rid, "create", user_id=created_by, module="Admin",
                summary=f"User created: {username}",
            )
        except Exception:
            pass


def update_user(user_id, full_name, role, is_active, password=None, modified_by=None, **extra):
    from erp_core.v15_security import hash_password_secure, validate_password_strength
    with get_connection() as conn:
        ts = _now()
        sets = ["full_name=?", "role=?", "is_active=?", "modified_by=?", "modified_at=?"]
        params: list = [full_name, role, is_active, modified_by, ts]
        if password:
            ok, msg = validate_password_strength(password)
            if not ok:
                raise ValueError(msg)
            sets.append("password_hash=?")
            params.append(hash_password_secure(password))
        for k in ("user_type", "linked_customer_id", "role_id"):
            if k in extra:
                sets.append(f"{k}=?")
                params.append(extra[k])
        params.append(user_id)
        conn.execute(
            f"UPDATE users SET {', '.join(sets)} WHERE id=?",
            params,
        )
        try:
            from db_audit import log_event
            log_event(
                "users", user_id, "update", user_id=modified_by, module="Admin",
                summary=f"User updated: {full_name} ({role})",
            )
        except Exception:
            pass


def delete_user(user_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT username, full_name FROM users WHERE id=? AND LOWER(username)!='admin'", (user_id,)
        ).fetchone()
        conn.execute("DELETE FROM users WHERE id=? AND LOWER(username)!='admin'", (user_id,))
        try:
            from db_audit import log_event
            if row:
                log_event(
                    "users", user_id, "delete", module="Admin",
                    summary=f"User deleted: {row['username']}",
                )
        except Exception:
            pass


# --- Customers ---
def get_distinct_cities():
    """Unique city names from customers and suppliers (for location pickers)."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT TRIM(city) AS city FROM customers
            WHERE city IS NOT NULL AND TRIM(city) != ''
            UNION
            SELECT DISTINCT TRIM(city) AS city FROM suppliers
            WHERE city IS NOT NULL AND TRIM(city) != ''
            ORDER BY 1
            """
        ).fetchall()
    return [r["city"] for r in rows if r["city"]]


def get_customers(active_only=False, group_id=None):
    key = f"customers:{int(bool(active_only))}:{group_id or 0}"

    def _load():
        q = _CUSTOMER_SELECT + " WHERE 1=1"
        p = []
        if active_only:
            q += " AND c.is_active=1"
        if group_id:
            q += " AND c.group_id=?"
            p.append(group_id)
        q += " ORDER BY c.name"
        with get_connection() as conn:
            return rows_to_list(conn.execute(q, p).fetchall())

    return cached_read(key, _load)


def get_customer(customer_id):
    with get_connection() as conn:
        return row_to_dict(conn.execute(
            _CUSTOMER_SELECT + " WHERE c.id=?", (customer_id,)
        ).fetchone())


def add_customer(data, created_by=None):
    with get_connection() as conn:
        ob = data.get("opening_balance", 0)
        cur = conn.execute(
            """INSERT INTO customers (code, name, contact_person, phone, email, address, city, province,
               ntn, strn, credit_limit, opening_balance, current_balance, group_id, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (data["code"], data["name"], data.get("contact_person"), data.get("phone"),
             data.get("email"), data.get("address"), data.get("city"), data.get("province"),
             data.get("ntn"), data.get("strn"),
             data.get("credit_limit", 0), ob, ob, data.get("group_id"), created_by),
        )
        rid = cur.lastrowid
        try:
            from db_audit import log_event
            log_event(
                "customers", rid, "create", user_id=created_by, module="Masters",
                document_no=data.get("code"), summary=f"Customer {data.get('name')}",
            )
        except Exception:
            pass
        invalidate("customers")
        return rid


def update_customer(customer_id, data, modified_by=None):
    with get_connection() as conn:
        # Ensure portal contact columns exist (idempotent)
        try:
            from db_v15 import ensure_distributor_catalog_schema
            ensure_distributor_catalog_schema(conn)
        except Exception:
            pass
        old = conn.execute("SELECT opening_balance, current_balance FROM customers WHERE id=?", (customer_id,)).fetchone()
        diff = data.get("opening_balance", 0) - (old["opening_balance"] if old else 0)
        new_balance = (old["current_balance"] if old else 0) + diff
        conn.execute(
            """UPDATE customers SET code=?, name=?, contact_person=?, phone=?, email=?, address=?, city=?,
               province=?, ntn=?, strn=?,
               dispatch_phone=?, accounts_phone=?, owner_phone=?,
               credit_limit=?, opening_balance=?, current_balance=?, group_id=?,
               is_active=?, modified_by=?, modified_at=? WHERE id=?""",
            (data["code"], data["name"], data.get("contact_person"), data.get("phone"),
             data.get("email"), data.get("address"), data.get("city"), data.get("province"),
             data.get("ntn"), data.get("strn"),
             data.get("dispatch_phone"), data.get("accounts_phone"), data.get("owner_phone"),
             data.get("credit_limit", 0), data.get("opening_balance", 0), new_balance,
             data.get("group_id"), data.get("is_active", 1), modified_by, _now(), customer_id),
        )
        try:
            from db_audit import log_event
            log_event(
                "customers", customer_id, "update", user_id=modified_by, module="Masters",
                document_no=data.get("code"), summary=f"Customer {data.get('name')}",
            )
        except Exception:
            pass
    invalidate("customers")


def delete_customer(customer_id):
    with get_connection() as conn:
        row = conn.execute("SELECT code, name FROM customers WHERE id=?", (customer_id,)).fetchone()
        conn.execute("DELETE FROM customers WHERE id=?", (customer_id,))
        try:
            from db_audit import log_event
            if row:
                log_event(
                    "customers", customer_id, "delete", module="Masters",
                    document_no=row["code"], summary=f"Deleted customer {row['name']}",
                )
        except Exception:
            pass
    invalidate("customers")


# --- Suppliers ---
def get_suppliers(active_only=False, group_id=None):
    key = f"suppliers:{int(bool(active_only))}:{group_id or 0}"

    def _load():
        q = _SUPPLIER_SELECT + " WHERE 1=1"
        p = []
        if active_only:
            q += " AND s.is_active=1"
        if group_id:
            q += " AND s.group_id=?"
            p.append(group_id)
        q += " ORDER BY s.name"
        with get_connection() as conn:
            return rows_to_list(conn.execute(q, p).fetchall())

    return cached_read(key, _load)


def get_supplier(supplier_id):
    with get_connection() as conn:
        return row_to_dict(conn.execute(
            _SUPPLIER_SELECT + " WHERE s.id=?", (supplier_id,)
        ).fetchone())


def add_supplier(data, created_by=None):
    with get_connection() as conn:
        ob = data.get("opening_balance", 0)
        cur = conn.execute(
            """INSERT INTO suppliers (code, name, contact_person, phone, email, address, city,
               opening_balance, current_balance, group_id, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (data["code"], data["name"], data.get("contact_person"), data.get("phone"),
             data.get("email"), data.get("address"), data.get("city"), ob, ob,
             data.get("group_id"), created_by),
        )
        rid = cur.lastrowid
        try:
            from db_audit import log_event
            log_event(
                "suppliers", rid, "create", user_id=created_by, module="Masters",
                document_no=data.get("code"), summary=f"Supplier {data.get('name')}",
            )
        except Exception:
            pass
        invalidate("suppliers")
        return rid


def update_supplier(supplier_id, data, modified_by=None):
    with get_connection() as conn:
        old = conn.execute("SELECT opening_balance, current_balance FROM suppliers WHERE id=?", (supplier_id,)).fetchone()
        diff = data.get("opening_balance", 0) - (old["opening_balance"] if old else 0)
        new_balance = (old["current_balance"] if old else 0) + diff
        conn.execute(
            """UPDATE suppliers SET code=?, name=?, contact_person=?, phone=?, email=?, address=?, city=?,
               opening_balance=?, current_balance=?, group_id=?, is_active=?, modified_by=?, modified_at=? WHERE id=?""",
            (data["code"], data["name"], data.get("contact_person"), data.get("phone"),
             data.get("email"), data.get("address"), data.get("city"),
             data.get("opening_balance", 0), new_balance, data.get("group_id"),
             data.get("is_active", 1), modified_by, _now(), supplier_id),
        )
        try:
            from db_audit import log_event
            log_event(
                "suppliers", supplier_id, "update", user_id=modified_by, module="Masters",
                document_no=data.get("code"), summary=f"Supplier {data.get('name')}",
            )
        except Exception:
            pass
    invalidate("suppliers")


def delete_supplier(supplier_id):
    with get_connection() as conn:
        row = conn.execute("SELECT code, name FROM suppliers WHERE id=?", (supplier_id,)).fetchone()
        conn.execute("DELETE FROM suppliers WHERE id=?", (supplier_id,))
        try:
            from db_audit import log_event
            if row:
                log_event(
                    "suppliers", supplier_id, "delete", module="Masters",
                    document_no=row["code"], summary=f"Deleted supplier {row['name']}",
                )
        except Exception:
            pass
    invalidate("suppliers")


# --- Products (Items API compat) ---
def get_items(active_only=False, group_id=None):
    key = f"items:{int(bool(active_only))}:{group_id or 0}"

    def _load():
        q = PRODUCT_SELECT + " WHERE 1=1"
        p = []
        if active_only:
            q += " AND p.is_active=1"
        if group_id:
            q += " AND p.group_id=?"
            p.append(group_id)
        q += " ORDER BY p.name"
        with get_connection() as conn:
            return rows_to_list(conn.execute(q, p).fetchall())

    return cached_read(key, _load)


def get_item(item_id):
    with get_connection() as conn:
        return row_to_dict(conn.execute(f"{PRODUCT_SELECT} WHERE p.id=?", (item_id,)).fetchone())


def add_item(data, created_by=None):
    with get_connection() as conn:
        wh = _default_warehouse_id(conn)
        cat_id = data.get("category_id")
        if not cat_id and data.get("category"):
            row = conn.execute("SELECT id FROM product_categories WHERE name=?", (data["category"],)).fetchone()
            if row:
                cat_id = row[0]
            else:
                conn.execute("INSERT INTO product_categories (code, name, created_by) VALUES (?, ?, ?)",
                             (f"CAT{data['category'][:3].upper()}", data["category"], created_by))
                cat_id = conn.execute("SELECT id FROM product_categories WHERE name=?", (data["category"],)).fetchone()[0]
        unit_id = data.get("unit_id")
        if not unit_id:
            sym = data.get("unit", "KG")
            row = conn.execute("SELECT id FROM units_of_measure WHERE symbol=?", (sym,)).fetchone()
            unit_id = row[0] if row else conn.execute("SELECT id FROM units_of_measure LIMIT 1").fetchone()[0]
        cur = conn.execute(
            """INSERT INTO products (code, name, category_id, unit_id, product_type, purchase_price,
               sale_price, reorder_level, default_warehouse_id, weight_unit, standard_weight,
               packing_size, tax_rate_id, min_stock, group_id, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (data["code"], data["name"], cat_id, unit_id, data.get("item_type", "finished"),
             data.get("purchase_price", 0), data.get("sale_price", 0), data.get("reorder_level", 0), wh,
             data.get("weight_unit", "kg"), data.get("standard_weight", 0), data.get("packing_size"),
             data.get("tax_rate_id"), data.get("min_stock", 0), data.get("group_id"), created_by),
        )
        pid = cur.lastrowid
        stock = data.get("stock_qty", 0)
        if stock and wh:
            conn.execute(
                "INSERT INTO warehouse_stock (warehouse_id, product_id, quantity) VALUES (?, ?, ?)",
                (wh, pid, stock),
            )
            _record_movement(conn, pid, wh, "in", stock, "opening", None, "Opening stock", created_by)
        invalidate("items")
        return pid


def update_item(item_id, data, modified_by=None):
    with get_connection() as conn:
        cat_id = data.get("category_id")
        if not cat_id and data.get("category"):
            row = conn.execute("SELECT id FROM product_categories WHERE name=?", (data["category"],)).fetchone()
            cat_id = row[0] if row else None
        unit_id = data.get("unit_id")
        if not unit_id and data.get("unit"):
            row = conn.execute("SELECT id FROM units_of_measure WHERE symbol=?", (data["unit"],)).fetchone()
            unit_id = row[0] if row else None
        conn.execute(
            """UPDATE products SET code=?, name=?, category_id=COALESCE(?, category_id),
               unit_id=COALESCE(?, unit_id), product_type=?, purchase_price=?, sale_price=?,
               reorder_level=?, weight_unit=COALESCE(?, weight_unit), standard_weight=COALESCE(?, standard_weight),
               packing_size=COALESCE(?, packing_size), tax_rate_id=COALESCE(?, tax_rate_id),
               min_stock=COALESCE(?, min_stock), group_id=?, is_active=?, modified_by=?, modified_at=? WHERE id=?""",
            (data["code"], data["name"], cat_id, unit_id, data.get("item_type", "finished"),
             data.get("purchase_price", 0), data.get("sale_price", 0), data.get("reorder_level", 0),
             data.get("weight_unit"), data.get("standard_weight"), data.get("packing_size"),
             data.get("tax_rate_id"), data.get("min_stock"), data.get("group_id"),
             data.get("is_active", 1), modified_by, _now(), item_id),
        )
    invalidate("items")


def get_product_delete_blockers(item_id):
    """Return human-readable list of reasons a product cannot be permanently deleted."""
    checks = [
        ("sales invoices", "sales_invoice_items", "product_id"),
        ("purchase invoices", "purchase_invoice_items", "product_id"),
        ("sales orders", "sales_order_items", "product_id"),
        ("purchase orders", "purchase_order_items", "product_id"),
        ("sales returns", "sales_return_items", "product_id"),
        ("purchase returns", "purchase_return_items", "product_id"),
        ("quotations", "quotation_items", "product_id"),
        ("delivery notes", "delivery_note_items", "product_id"),
        ("GRN lines", "grn_items", "product_id"),
        ("BOM formulas", "bom_formulas", "finished_product_id"),
        ("BOM raw materials", "bom_formula_lines", "raw_product_id"),
        ("production orders", "production_orders", "finished_product_id"),
        ("production material issues", "production_material_issues", "product_id"),
        ("production receipts", "production_finished_receipts", "product_id"),
        ("weight slips", "weight_slips", "product_id"),
        ("gate passes", "gate_passes", "product_id"),
    ]
    blockers = []
    with get_connection() as conn:
        for label, table, col in checks:
            if not _table_exists(conn, table):
                continue
            n = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col}=?", (item_id,)).fetchone()[0]
            if n:
                blockers.append(f"{label} ({n})")
    return blockers


def deactivate_item(item_id, modified_by=None):
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM products WHERE id=?", (item_id,)).fetchone()
        if not row:
            raise ValueError("Product not found.")
        conn.execute(
            "UPDATE products SET is_active=0, modified_by=?, modified_at=? WHERE id=?",
            (modified_by, _now(), item_id),
        )
    invalidate("items")


def delete_item(item_id, modified_by=None):
    blockers = get_product_delete_blockers(item_id)
    if blockers:
        raise ValueError(
            "Cannot delete this product because it is used in: "
            + ", ".join(blockers)
            + ". Deactivate it instead to hide from new transactions."
        )
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM products WHERE id=?", (item_id,)).fetchone()
        if not row:
            raise ValueError("Product not found.")
        if _table_exists(conn, "inventory_movements"):
            conn.execute("DELETE FROM inventory_movements WHERE product_id=?", (item_id,))
        if _table_exists(conn, "product_batches"):
            conn.execute("DELETE FROM product_batches WHERE product_id=?", (item_id,))
        conn.execute("DELETE FROM warehouse_stock WHERE product_id=?", (item_id,))
        conn.execute("DELETE FROM products WHERE id=?", (item_id,))
    invalidate("items")


def _record_movement(conn, product_id, warehouse_id, movement_type, quantity, ref_type, ref_id, reason, user_id):
    conn.execute(
        """INSERT INTO inventory_movements (movement_date, product_id, warehouse_id, movement_type,
           quantity, reference_type, reference_id, reason, created_by)
           VALUES (date('now'), ?, ?, ?, ?, ?, ?, ?, ?)""",
        (product_id, warehouse_id, movement_type, quantity, ref_type, ref_id, reason, user_id),
    )


def _adjust_warehouse_stock(conn, product_id, warehouse_id, qty_change, user_id=None):
    if qty_change < 0:
        try:
            from erp_core.inventory_guards import validate_stock_movement
            validate_stock_movement(conn, product_id, warehouse_id, qty_change, user_id=user_id)
        except ValueError:
            raise
        except Exception:
            pass
    row = conn.execute(
        "SELECT quantity FROM warehouse_stock WHERE warehouse_id=? AND product_id=?",
        (warehouse_id, product_id),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE warehouse_stock SET quantity=quantity+?, modified_at=? WHERE warehouse_id=? AND product_id=?",
            (qty_change, _now(), warehouse_id, product_id),
        )
    else:
        conn.execute(
            "INSERT INTO warehouse_stock (warehouse_id, product_id, quantity, modified_at) VALUES (?, ?, ?, ?)",
            (warehouse_id, product_id, qty_change, _now()),
        )


# --- Chart of Accounts (Accounts API compat) ---
def get_accounts(active_only=False):
    q = """SELECT a.id, a.code, a.name, g.group_type AS account_type, a.parent_id,
                  a.opening_balance, a.current_balance AS balance, a.is_active,
                  a.created_at, a.modified_at, a.account_group_id
           FROM chart_of_accounts a
           JOIN account_groups g ON a.account_group_id = g.id"""
    if active_only:
        q += " WHERE a.is_active=1"
    q += " ORDER BY a.code"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q).fetchall())


def get_account(account_id):
    with get_connection() as conn:
        return row_to_dict(conn.execute(
            """SELECT a.id, a.code, a.name, g.group_type AS account_type, a.parent_id,
                      a.opening_balance, a.current_balance AS balance, a.is_active, a.account_group_id
               FROM chart_of_accounts a JOIN account_groups g ON a.account_group_id = g.id WHERE a.id=?""",
            (account_id,),
        ).fetchone())


def add_account(data, created_by=None):
    with get_connection() as conn:
        gid = data.get("account_group_id")
        if not gid and data.get("account_type"):
            gid = conn.execute(
                "SELECT id FROM account_groups WHERE group_type=? LIMIT 1", (data["account_type"],)
            ).fetchone()[0]
        ob = data.get("opening_balance", 0)
        cur = conn.execute(
            """INSERT INTO chart_of_accounts (code, name, account_group_id, parent_id,
               opening_balance, current_balance, created_by) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (data["code"], data["name"], gid, data.get("parent_id"), ob, ob, created_by),
        )
        return cur.lastrowid


def update_account(account_id, data, modified_by=None):
    with get_connection() as conn:
        old = conn.execute("SELECT opening_balance, current_balance FROM chart_of_accounts WHERE id=?", (account_id,)).fetchone()
        diff = data.get("opening_balance", 0) - (old["opening_balance"] if old else 0)
        new_balance = (old["current_balance"] if old else 0) + diff
        gid = data.get("account_group_id")
        if not gid and data.get("account_type"):
            gid = conn.execute("SELECT id FROM account_groups WHERE group_type=? LIMIT 1", (data["account_type"],)).fetchone()[0]
        conn.execute(
            """UPDATE chart_of_accounts SET code=?, name=?, account_group_id=COALESCE(?, account_group_id),
               parent_id=?, opening_balance=?, current_balance=?, is_active=?, modified_by=?, modified_at=? WHERE id=?""",
            (data["code"], data["name"], gid, data.get("parent_id"), data.get("opening_balance", 0),
             new_balance, data.get("is_active", 1), modified_by, _now(), account_id),
        )


def delete_account(account_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM chart_of_accounts WHERE id=?", (account_id,))


def get_accounts_by_type(account_type):
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            """SELECT a.id, a.code, a.name, g.group_type AS account_type, a.current_balance AS balance
               FROM chart_of_accounts a JOIN account_groups g ON a.account_group_id = g.id
               WHERE g.group_type=? AND a.is_active=1 ORDER BY a.name""",
            (account_type,),
        ).fetchall())


# --- Purchases -> purchase_invoices ---
def get_purchases():
    from db_cache import _LIST_TTL

    def _load():
        with get_connection() as conn:
            return rows_to_list(conn.execute(
                """SELECT p.id, p.document_no AS invoice_no, p.invoice_date AS purchase_date, p.supplier_id,
                          p.subtotal, p.discount, p.tax, p.total, p.paid_amount, p.payment_mode, p.notes,
                          p.created_at, s.name AS supplier_name
                   FROM purchase_invoices p JOIN suppliers s ON p.supplier_id=s.id
                   ORDER BY p.invoice_date DESC, p.id DESC"""
            ).fetchall())

    return cached_read("purchases", _load, ttl=_LIST_TTL)


def search_purchases(
    q=None,
    from_date=None,
    to_date=None,
    supplier_id=None,
    status=None,
    payment_mode=None,
    page=1,
    page_size=50,
    export_all=False,
    sort=None,
):
    """Paginated purchase register — server-side filters for large datasets."""
    page = max(1, int(page or 1))
    page_size = min(500, max(10, int(page_size or 50)))
    where = ["1=1"]
    params = []
    if q:
        like = f"%{q.strip()}%"
        where.append(
            "(p.document_no LIKE ? OR s.name LIKE ? OR s.code LIKE ? OR COALESCE(p.notes,'') LIKE ?)"
        )
        params.extend([like, like, like, like])
    if from_date:
        where.append("p.invoice_date >= ?")
        params.append(from_date)
    if to_date:
        where.append("p.invoice_date <= ?")
        params.append(to_date)
    if supplier_id:
        where.append("p.supplier_id = ?")
        params.append(supplier_id)
    if status and status != "All":
        where.append("COALESCE(p.status,'draft') = ?")
        params.append(status)
    if payment_mode and payment_mode != "All":
        where.append("p.payment_mode = ?")
        params.append(payment_mode)
    clause = " AND ".join(where)
    cols = """p.id, p.document_no AS invoice_no, p.invoice_date AS purchase_date, p.supplier_id,
              p.subtotal, p.discount, p.tax, p.total, p.paid_amount, p.payment_mode,
              COALESCE(p.status,'draft') AS status, p.notes, p.created_at,
              p.total_net_weight, p.physical_weight_kg, p.weight_variance_kg, p.weight_variance_pct,
              p.weight_match_status,
              s.name AS supplier_name, s.code AS supplier_code,
              ws.document_no AS weight_slip_no, gp.document_no AS gate_pass_no"""
    base = f"""FROM purchase_invoices p
               JOIN suppliers s ON p.supplier_id=s.id
               LEFT JOIN weight_slips ws ON p.weight_slip_id=ws.id
               LEFT JOIN gate_passes gp ON p.gate_pass_id=gp.id
               WHERE {clause}"""
    with get_connection() as conn:
        total = conn.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0]
        agg = conn.execute(
            f"SELECT COALESCE(SUM(p.total),0), COALESCE(SUM(p.paid_amount),0) {base}", params
        ).fetchone()
        order_by = _invoice_register_order_by(
            sort,
            date_col="p.invoice_date",
            party_col="s.name",
            status_col="p.status",
            id_col="p.id",
        )
        if export_all:
            rows = conn.execute(
                f"SELECT {cols} {base} ORDER BY {order_by}", params
            ).fetchall()
            pages = 1
            page = 1
        else:
            offset = (page - 1) * page_size
            rows = conn.execute(
                f"SELECT {cols} {base} ORDER BY {order_by} LIMIT ? OFFSET ?",
                params + [page_size, offset],
            ).fetchall()
            pages = max(1, (total + page_size - 1) // page_size)
            if page > pages:
                page = pages
    return {
        "items": rows_to_list(rows),
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "sum_total": float(agg[0] or 0),
        "sum_paid": float(agg[1] or 0),
    }


def get_purchase(purchase_id):
    with get_connection() as conn:
        header = row_to_dict(conn.execute(
            """SELECT p.id, p.document_no AS invoice_no, p.invoice_date AS purchase_date, p.supplier_id,
                      p.subtotal, p.discount, p.discount_pct, p.tax, p.tax_rate_id, p.tax_inclusive,
                      p.total, p.paid_amount, p.payment_mode, p.notes, p.status, p.weight_slip_id,
                      p.order_id, p.grn_id, p.weighbridge_required,
                      p.total_net_weight, p.physical_weight_kg, p.weight_variance_kg, p.weight_variance_pct,
                      p.weight_match_status, p.gate_pass_id, p.approved_by, p.approved_at,
                      p.created_by, p.created_at, p.posted_at, p.updated_at,
                      s.name AS supplier_name
               FROM purchase_invoices p JOIN suppliers s ON p.supplier_id=s.id WHERE p.id=?""",
            (purchase_id,),
        ).fetchone())
        if not header:
            return None
        header["items"] = rows_to_list(conn.execute(
            """SELECT pi.id, pi.invoice_id AS purchase_id, pi.product_id AS item_id,
                      pi.quantity, pi.rate, pi.amount, pi.net_weight,
                      COALESCE(pi.line_discount, 0) AS line_discount,
                      pr.name AS item_name, u.symbol AS unit
               FROM purchase_invoice_items pi
               JOIN products pr ON pi.product_id=pr.id
               LEFT JOIN units_of_measure u ON pr.unit_id=u.id
               WHERE pi.invoice_id=?""",
            (purchase_id,),
        ).fetchall())
        for li in header["items"]:
            qty = float(li.get("quantity") or 0)
            rate = float(li.get("rate") or 0)
            disc_amt = float(li.get("line_discount") or 0)
            # Only expose Disc % from stored line_discount — never invent discount from amount gaps
            # (that caused Submit for Approval to re-save an unintended 5% etc.)
            gross = qty * rate
            if disc_amt > 0.0001 and gross > 0.0001:
                li["discount_pct"] = round(min(100.0, disc_amt / gross * 100.0), 2)
            else:
                li["discount_pct"] = 0.0
        wi = conn.execute(
            """SELECT ws.document_no, p.weight_slip_id, p.total_net_weight
               FROM purchase_invoices p LEFT JOIN weight_slips ws ON p.weight_slip_id=ws.id WHERE p.id=?""",
            (purchase_id,),
        ).fetchone()
        if wi:
            header["weight_slip_no"] = wi[0]
            header["weight_slip_id"] = wi[1]
            header["total_net_weight"] = float(wi[2] or 0)
        from db_commercial import get_invoice_weight_info
        header.update(get_invoice_weight_info(purchase_id, "purchase"))
        return header


def save_purchase(data, line_items, purchase_id=None, user_id=None):
    from db_commercial import apply_invoice_totals_to_data, enrich_line_weights, link_weight_slip_to_invoice
    from db_invoice_workflow import EDITABLE_STATUSES, refresh_invoice_weight_match, _validate_weight_slip_unique
    from erp_core.transaction_validation import validate_purchase_invoice
    data, totals = apply_invoice_totals_to_data(data, line_items)
    vr = validate_purchase_invoice(
        data, totals.get("lines") or line_items, totals, stage="draft",
    )
    vr.raise_if_invalid("Purchase invoice")
    line_items = totals["lines"]
    with get_connection() as conn:
        if purchase_id:
            old = conn.execute("SELECT status FROM purchase_invoices WHERE id=?", (purchase_id,)).fetchone()
            if old and old["status"] not in EDITABLE_STATUSES:
                raise ValueError(f"Cannot edit invoice with status '{old['status']}'.")
        line_items = enrich_line_weights(conn, line_items)
        total_net_weight = round(sum(float(li.get("net_weight") or 0) for li in line_items), 3)
        wh = _default_warehouse_id(conn)
        subtotal = totals["subtotal"]
        discount = totals["discount_amt"]
        tax = totals["total_tax"]
        total = totals["total"]
        taxable = totals["taxable"]
        paid = data.get("paid_amount", 0)
        ts = _now()
        status = data.get("status", "draft")
        weighbridge = 0 if data.get("weighbridge_required") in (0, False, "0") else (
            1 if data.get("weighbridge_required") or data.get("weight_slip_id") else 0
        )
        if not weighbridge:
            data["weight_slip_id"] = None
        if weighbridge and not data.get("weight_slip_id"):
            raise ValueError(
                "Weight slip required: complete 1st and 2nd weight on Weight Scale, then create the purchase invoice."
            )
        if weighbridge and data.get("weight_slip_id"):
            ws = conn.execute(
                "SELECT status, net_weight FROM weight_slips WHERE id=?", (data["weight_slip_id"],),
            ).fetchone()
            if not ws or ws["status"] != "completed" or float(ws["net_weight"] or 0) <= 0:
                raise ValueError("Linked weight slip must be completed with net weight.")
        grn_id = data.get("grn_id")
        _validate_weight_slip_unique(conn, data.get("weight_slip_id"), purchase_id, "purchase_invoices")

        if not purchase_id:
            data["invoice_no"] = ensure_document_no("PI", data.get("invoice_no"), conn)
        elif data.get("invoice_no"):
            _sync_doc_sequence(conn, "PI", data["invoice_no"])

        old_order_id = None
        if purchase_id:
            old_row = conn.execute("SELECT order_id FROM purchase_invoices WHERE id=?", (purchase_id,)).fetchone()
            old_order_id = old_row["order_id"] if old_row else None
            # Edit forms sometimes omit order_id; keep the existing PO link
            if not data.get("order_id") and old_order_id:
                data["order_id"] = old_order_id
            if old_order_id:
                from db_v3 import reverse_purchase_order_delivery
                reverse_purchase_order_delivery(conn, old_order_id, purchase_id)

        if purchase_id:
            conn.execute("DELETE FROM purchase_invoice_items WHERE invoice_id=?", (purchase_id,))
            conn.execute(
                """UPDATE purchase_invoices SET document_no=?, supplier_id=?, invoice_date=?, subtotal=?,
                   discount=?, discount_pct=?, tax=?, sales_tax=?, further_tax=?, extra_tax=?, fed_tax=?,
                   wht_tax=?, taxable_amount=?, tax_inclusive=?, tax_rate_id=?, total=?, paid_amount=?,
                   payment_mode=?, notes=?, grn_id=COALESCE(?, grn_id), order_id=?,
                   weighbridge_required=?,
                   weight_slip_id=COALESCE(?, weight_slip_id), total_net_weight=?, status=?,
                   modified_by=?, modified_at=? WHERE id=?""",
                (data["invoice_no"], data["supplier_id"], data["purchase_date"], subtotal,
                 discount, totals["discount_pct"], tax, totals["sales_tax"], totals["further_tax"],
                 totals["extra_tax"], totals["fed_tax"], totals["wht_tax"], taxable,
                 totals["tax_inclusive"], data.get("tax_rate_id"), total, paid,
                 data.get("payment_mode", "credit"), data.get("notes"), grn_id,
                 data.get("order_id"), weighbridge,
                 data.get("weight_slip_id"), total_net_weight, status, user_id, ts, purchase_id),
            )
        else:
            purchase_id = None
            for _attempt in range(8):
                try:
                    cur = conn.execute(
                        """INSERT INTO purchase_invoices (document_no, supplier_id, invoice_date, warehouse_id,
                           subtotal, discount, discount_pct, tax, sales_tax, further_tax, extra_tax, fed_tax,
                           wht_tax, taxable_amount, tax_inclusive, tax_rate_id, total, paid_amount, payment_mode,
                           notes, grn_id, order_id, weighbridge_required, weight_slip_id,
                           total_net_weight, status, created_by, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (data["invoice_no"], data["supplier_id"], data["purchase_date"], wh,
                         subtotal, discount, totals["discount_pct"], tax, totals["sales_tax"], totals["further_tax"],
                         totals["extra_tax"], totals["fed_tax"], totals["wht_tax"], taxable,
                         totals["tax_inclusive"], data.get("tax_rate_id"), total, paid,
                         data.get("payment_mode", "credit"), data.get("notes"), grn_id,
                         data.get("order_id"), weighbridge, data.get("weight_slip_id"),
                         total_net_weight, status, user_id, ts),
                    )
                    purchase_id = cur.lastrowid
                    break
                except sqlite3.IntegrityError as ex:
                    msg = str(ex).lower()
                    if "document_no" not in msg and "unique" not in msg:
                        raise
                    data["invoice_no"] = ensure_document_no("PI", None, conn)
            if not purchase_id:
                raise ValueError(
                    "Could not save invoice — document number conflict. Please try again."
                )

        for li in line_items:
            pid = li["item_id"]
            conn.execute(
                """INSERT INTO purchase_invoice_items (invoice_id, product_id, quantity, rate, amount, net_weight, tax_amount, line_discount)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (purchase_id, pid, li["quantity"], li["rate"], li["line_amount"],
                 float(li.get("net_weight") or 0), li.get("tax_amount", 0), li.get("line_discount", 0)),
            )
            conn.execute("UPDATE products SET purchase_price=?, modified_at=? WHERE id=?", (li["rate"], ts, pid))

        from db_v3 import apply_purchase_order_delivery
        if data.get("order_id"):
            apply_purchase_order_delivery(conn, data["order_id"], purchase_id)

        refresh_invoice_weight_match(conn, purchase_id, "purchase")
        try:
            from db_v13_13 import persist_invoice_v13_extras, sync_draft_registry_row
            persist_invoice_v13_extras(conn, "purchase_invoices", purchase_id, data)
            row = conn.execute(
                """SELECT pi.*, s.name AS party_name FROM purchase_invoices pi
                   LEFT JOIN suppliers s ON s.id = pi.supplier_id WHERE pi.id=?""",
                (purchase_id,),
            ).fetchone()
            if row:
                sync_draft_registry_row(
                    conn,
                    doc_type="Purchase Invoice",
                    doc_table="purchase_invoices",
                    record_id=purchase_id,
                    document_no=row["document_no"],
                    doc_date=row["invoice_date"],
                    party_name=row["party_name"] or "",
                    amount=row["total"],
                    status=row["status"],
                    approval_status=row["approval_status"] if "approval_status" in row.keys() else row["status"],
                    created_by=row["created_by"],
                    created_at=row["created_at"] or "",
                    updated_by=user_id,
                    updated_at=ts,
                )
        except Exception:
            pass
    if data.get("weight_slip_id"):
        link_weight_slip_to_invoice(
            data["weight_slip_id"], "purchase_invoice", purchase_id, user_id,
            as_primary=data.get("weight_slip_as_primary", None),
        )
        from db_invoice_workflow import generate_gate_pass_from_purchase
        generate_gate_pass_from_purchase(purchase_id, user_id, require_approved=False)
    invalidate_invoices()
    invalidate_stock()
    invalidate("suppliers")
    try:
        from product_rates_legacy import clear_rate_cache
        clear_rate_cache()
    except Exception:
        pass
    return purchase_id


def delete_purchase(purchase_id):
    with get_connection() as conn:
        p = conn.execute("SELECT * FROM purchase_invoices WHERE id=?", (purchase_id,)).fetchone()
        if not p:
            return
        status = p["status"] or "draft"
        if status == "approved":
            raise ValueError("Cannot delete approved invoice. Use Cancel from approval workflow.")
        if status == "pending_approval":
            raise ValueError("Cannot delete pending invoice. Reject it first.")
        if p["order_id"]:
            from db_v3 import reverse_purchase_order_delivery
            reverse_purchase_order_delivery(conn, p["order_id"], purchase_id)
        if p["weight_slip_id"]:
            conn.execute(
                "UPDATE weight_slips SET reference_type=NULL, reference_id=NULL, weight_difference=0 WHERE id=?",
                (p["weight_slip_id"],),
            )
        if p.get("gate_pass_id"):
            conn.execute("DELETE FROM gate_passes WHERE id=?", (p["gate_pass_id"],))
        conn.execute("DELETE FROM purchase_invoice_items WHERE invoice_id=?", (purchase_id,))
        conn.execute("DELETE FROM purchase_invoices WHERE id=?", (purchase_id,))
    try:
        from db_audit import log_event
        log_event(
            "purchase_invoices", purchase_id, "delete", module="Purchase",
            document_no=p["document_no"], summary=f"Deleted purchase invoice {p['document_no']}",
        )
    except Exception:
        pass
    invalidate_invoices()
    invalidate_stock()
    invalidate("suppliers")


# --- Sales -> sales_invoices ---
def get_sales():
    from db_cache import _LIST_TTL

    def _load():
        with get_connection() as conn:
            return rows_to_list(conn.execute(
                """SELECT s.id, s.document_no AS invoice_no, s.invoice_date AS sale_date, s.customer_id,
                          s.subtotal, s.discount, s.tax, s.total, s.paid_amount, s.payment_mode, s.notes,
                          s.created_at, c.name AS customer_name
                   FROM sales_invoices s JOIN customers c ON s.customer_id=c.id
                   ORDER BY s.invoice_date DESC, s.id DESC"""
            ).fetchall())

    return cached_read("sales", _load, ttl=_LIST_TTL)


def _invoice_register_order_by(
    sort: str | None,
    *,
    date_col: str,
    party_col: str,
    status_col: str,
    id_col: str,
) -> str:
    """SQL ORDER BY for sales/purchase registers."""
    key = (sort or "workflow").strip().lower()
    if key == "date_asc":
        return f"{date_col} ASC, {id_col} ASC"
    if key == "amount_desc":
        return f"total DESC, {id_col} DESC"
    if key == "amount_asc":
        return f"total ASC, {id_col} ASC"
    if key == "party":
        return f"{party_col} ASC, {date_col} DESC, {id_col} DESC"
    if key == "status":
        return f"{status_col} ASC, {date_col} DESC, {id_col} DESC"
    if key == "date_desc":
        return f"{date_col} DESC, {id_col} DESC"
    # workflow — pending/draft first (sales/purchase approval queues)
    return (
        f"CASE COALESCE({status_col},'draft') "
        "WHEN 'pending_approval' THEN 0 "
        "WHEN 'draft' THEN 1 "
        "WHEN 'rejected' THEN 2 "
        "ELSE 3 END, "
        f"{date_col} DESC, {id_col} DESC"
    )


def search_sales_invoices(
    q=None,
    from_date=None,
    to_date=None,
    customer_id=None,
    status=None,
    payment_mode=None,
    page=1,
    page_size=50,
    export_all=False,
    sort=None,
):
    page = max(1, int(page or 1))
    page_size = min(500, max(10, int(page_size or 50)))
    where = ["1=1"]
    params = []
    if q:
        like = f"%{q.strip()}%"
        where.append(
            "(s.document_no LIKE ? OR c.name LIKE ? OR c.code LIKE ? OR COALESCE(s.notes,'') LIKE ?)"
        )
        params.extend([like, like, like, like])
    if from_date:
        where.append("s.invoice_date >= ?")
        params.append(from_date)
    if to_date:
        where.append("s.invoice_date <= ?")
        params.append(to_date)
    if customer_id:
        where.append("s.customer_id = ?")
        params.append(customer_id)
    if status and status != "All":
        where.append("COALESCE(s.status,'draft') = ?")
        params.append(status)
    if payment_mode and payment_mode != "All":
        where.append("s.payment_mode = ?")
        params.append(payment_mode)
    clause = " AND ".join(where)
    cols = """s.id, s.document_no AS invoice_no, s.invoice_date AS sale_date, s.customer_id,
              s.subtotal, s.discount, s.tax, s.total, s.paid_amount, s.payment_mode,
              COALESCE(s.status,'draft') AS status, s.notes, s.created_at,
              s.total_net_weight, s.physical_weight_kg, s.weight_variance_kg, s.weight_variance_pct,
              s.weight_match_status,
              c.name AS customer_name, c.code AS customer_code,
              ws.document_no AS weight_slip_no, gp.document_no AS gate_pass_no"""
    base = f"""FROM sales_invoices s
               JOIN customers c ON s.customer_id=c.id
               LEFT JOIN weight_slips ws ON s.weight_slip_id=ws.id
               LEFT JOIN gate_passes gp ON s.gate_pass_id=gp.id
               WHERE {clause}"""
    with get_connection() as conn:
        total = conn.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0]
        agg = conn.execute(
            f"SELECT COALESCE(SUM(s.total),0), COALESCE(SUM(s.paid_amount),0) {base}", params
        ).fetchone()
        order_by = _invoice_register_order_by(
            sort,
            date_col="s.invoice_date",
            party_col="c.name",
            status_col="s.status",
            id_col="s.id",
        )
        if export_all:
            rows = conn.execute(
                f"SELECT {cols} {base} ORDER BY {order_by}", params
            ).fetchall()
            pages = 1
            page = 1
        else:
            offset = (page - 1) * page_size
            rows = conn.execute(
                f"SELECT {cols} {base} ORDER BY {order_by} LIMIT ? OFFSET ?",
                params + [page_size, offset],
            ).fetchall()
            pages = max(1, (total + page_size - 1) // page_size)
            if page > pages:
                page = pages
    return {
        "items": rows_to_list(rows),
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "sum_total": float(agg[0] or 0),
        "sum_paid": float(agg[1] or 0),
    }


def get_sale(sale_id):
    with get_connection() as conn:
        header = row_to_dict(conn.execute(
            """SELECT s.id, s.document_no AS invoice_no, s.invoice_date AS sale_date, s.customer_id,
                      s.subtotal, s.discount, s.discount_pct, s.tax, s.tax_rate_id, s.tax_inclusive,
                      s.total, s.paid_amount, s.payment_mode, s.notes, s.status, s.weight_slip_id,
                      s.order_id, s.quotation_id, s.weighbridge_required,
                      s.vehicle_no, s.driver_name, s.driver_contact, s.dispatch_remarks,
                      s.total_net_weight, s.physical_weight_kg, s.weight_variance_kg, s.weight_variance_pct,
                      s.weight_match_status, s.gate_pass_id, s.override_reason, s.approved_by, s.approved_at,
                      s.created_by, s.created_at, s.posted_at, s.updated_at,
                      c.name AS customer_name
               FROM sales_invoices s JOIN customers c ON s.customer_id=c.id WHERE s.id=?""",
            (sale_id,),
        ).fetchone())
        if not header:
            return None
        header["items"] = rows_to_list(conn.execute(
            """SELECT si.id, si.invoice_id AS sale_id, si.product_id AS item_id,
                      si.quantity, si.rate, si.amount, si.net_weight,
                      COALESCE(si.line_discount, 0) AS line_discount,
                      pr.name AS item_name, u.symbol AS unit
               FROM sales_invoice_items si
               JOIN products pr ON si.product_id=pr.id
               LEFT JOIN units_of_measure u ON pr.unit_id=u.id WHERE si.invoice_id=?""",
            (sale_id,),
        ).fetchall())
        for li in header["items"]:
            qty = float(li.get("quantity") or 0)
            rate = float(li.get("rate") or 0)
            disc_amt = float(li.get("line_discount") or 0)
            # Only expose Disc % from stored line_discount — never invent discount from amount gaps
            # (that caused Submit for Approval to re-save an unintended 5% etc.)
            gross = qty * rate
            if disc_amt > 0.0001 and gross > 0.0001:
                li["discount_pct"] = round(min(100.0, disc_amt / gross * 100.0), 2)
            else:
                li["discount_pct"] = 0.0
        wi = conn.execute(
            """SELECT ws.document_no, s.weight_slip_id, s.total_net_weight
               FROM sales_invoices s LEFT JOIN weight_slips ws ON s.weight_slip_id=ws.id WHERE s.id=?""",
            (sale_id,),
        ).fetchone()
        if wi:
            header["weight_slip_no"] = wi[0]
            header["weight_slip_id"] = wi[1]
            header["total_net_weight"] = float(wi[2] or 0)
        from db_commercial import get_invoice_weight_info
        header.update(get_invoice_weight_info(sale_id, "sales"))
        return header


def save_sale(data, line_items, sale_id=None, user_id=None):
    from db_commercial import apply_invoice_totals_to_data, enrich_line_weights, link_weight_slip_to_invoice
    from db_invoice_workflow import EDITABLE_STATUSES, refresh_invoice_weight_match, _validate_weight_slip_unique
    from erp_core.transaction_validation import validate_sale_invoice
    data, totals = apply_invoice_totals_to_data(data, line_items)
    vr = validate_sale_invoice(
        data, totals.get("lines") or line_items, totals, stage="draft",
    )
    vr.raise_if_invalid("Sales invoice")
    line_items = totals["lines"]
    with get_connection() as conn:
        if sale_id:
            old = conn.execute("SELECT status FROM sales_invoices WHERE id=?", (sale_id,)).fetchone()
            if old and old["status"] not in EDITABLE_STATUSES:
                raise ValueError(f"Cannot edit invoice with status '{old['status']}'. Cancel or reject first.")
        line_items = enrich_line_weights(conn, line_items)
        total_net_weight = round(sum(float(li.get("net_weight") or 0) for li in line_items), 3)
        wh = _default_warehouse_id(conn)
        subtotal = totals["subtotal"]
        discount = totals["discount_amt"]
        tax = totals["total_tax"]
        total = totals["total"]
        taxable = totals["taxable"]
        paid = data.get("paid_amount", 0)
        from db_invoice_workflow import validate_sale_cash_payment
        paid = validate_sale_cash_payment(data.get("payment_mode"), paid, total)
        data["paid_amount"] = paid
        ts = _now()
        status = data.get("status", "draft")
        weighbridge = 0 if data.get("weighbridge_required") in (0, False, "0") else (
            1 if data.get("weighbridge_required") or data.get("weight_slip_id") else 0
        )
        if not weighbridge:
            data["weight_slip_id"] = None
        if weighbridge and not data.get("weight_slip_id"):
            raise ValueError(
                "Weight slip required: complete 1st and 2nd weight on Weight Scale, then create the sales invoice."
            )
        if weighbridge and data.get("weight_slip_id"):
            ws = conn.execute(
                "SELECT status, net_weight FROM weight_slips WHERE id=?", (data["weight_slip_id"],),
            ).fetchone()
            if not ws or ws["status"] != "completed" or float(ws["net_weight"] or 0) <= 0:
                raise ValueError("Linked weight slip must be completed with net weight.")
        if data.get("quotation_id"):
            from db_v3 import mark_quotation_converted
            mark_quotation_converted(conn, data["quotation_id"])
        _validate_weight_slip_unique(conn, data.get("weight_slip_id"), sale_id, "sales_invoices")

        if not sale_id:
            data["invoice_no"] = ensure_document_no("SI", data.get("invoice_no"), conn)
        elif data.get("invoice_no"):
            _sync_doc_sequence(conn, "SI", data["invoice_no"])

        old_order_id = None
        if sale_id:
            old_row = conn.execute("SELECT order_id FROM sales_invoices WHERE id=?", (sale_id,)).fetchone()
            old_order_id = old_row["order_id"] if old_row else None
            # Edit forms sometimes omit order_id; keep the existing SO link so delivery/status stay correct
            if not data.get("order_id") and old_order_id:
                data["order_id"] = old_order_id
            if old_order_id:
                from db_v3 import reverse_sales_order_delivery
                reverse_sales_order_delivery(conn, old_order_id, sale_id)

        vehicle_no = (data.get("vehicle_no") or "").strip() or None
        driver_name = (data.get("driver_name") or "").strip() or None
        driver_contact = (data.get("driver_contact") or "").strip() or None
        dispatch_remarks = (data.get("dispatch_remarks") or "").strip() or None
        if weighbridge:
            # Vehicle/driver come from the weight slip; keep dispatch town/remarks for multi-dispatch
            vehicle_no = driver_name = driver_contact = None

        if sale_id:
            old_doc_row = conn.execute(
                "SELECT document_no FROM sales_invoices WHERE id=?", (sale_id,),
            ).fetchone()
            old_doc = (old_doc_row["document_no"] if old_doc_row else "") or ""
            new_doc = data["invoice_no"]
            conn.execute("DELETE FROM sales_invoice_items WHERE invoice_id=?", (sale_id,))
            conn.execute(
                """UPDATE sales_invoices SET document_no=?, customer_id=?, invoice_date=?, subtotal=?,
                   discount=?, discount_pct=?, tax=?, sales_tax=?, further_tax=?, extra_tax=?, fed_tax=?,
                   wht_tax=?, taxable_amount=?, tax_inclusive=?, tax_rate_id=?, total=?, paid_amount=?,
                   payment_mode=?, notes=?, dn_id=COALESCE(?, dn_id),
                   order_id=?, quotation_id=COALESCE(?, quotation_id),
                   weighbridge_required=?,
                   vehicle_no=?, driver_name=?, driver_contact=?, dispatch_remarks=?,
                   weight_slip_id=?, total_net_weight=?, status=?,
                   modified_by=?, modified_at=? WHERE id=?""",
                (data["invoice_no"], data["customer_id"], data["sale_date"], subtotal,
                 discount, totals["discount_pct"], tax, totals["sales_tax"], totals["further_tax"],
                 totals["extra_tax"], totals["fed_tax"], totals["wht_tax"], taxable,
                 totals["tax_inclusive"], data.get("tax_rate_id"), total, paid,
                 data.get("payment_mode", "credit"), data.get("notes"), data.get("dn_id"),
                 data.get("order_id"), data.get("quotation_id"), weighbridge,
                 vehicle_no, driver_name, driver_contact, dispatch_remarks,
                 data.get("weight_slip_id"), total_net_weight, status, user_id, ts, sale_id),
            )
            if old_doc and new_doc and old_doc != new_doc:
                _sync_sale_linked_cash_bank_refs(conn, old_doc, new_doc)
        else:
            # Concurrent users may race between number check and insert — retry with next free no.
            sale_id = None
            for _attempt in range(8):
                try:
                    cur = conn.execute(
                        """INSERT INTO sales_invoices (document_no, customer_id, invoice_date, warehouse_id,
                           subtotal, discount, discount_pct, tax, sales_tax, further_tax, extra_tax, fed_tax,
                           wht_tax, taxable_amount, tax_inclusive, tax_rate_id, total, paid_amount, payment_mode,
                           notes, dn_id, order_id, quotation_id, weighbridge_required,
                           vehicle_no, driver_name, driver_contact, dispatch_remarks,
                           weight_slip_id, total_net_weight, status, created_by, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (data["invoice_no"], data["customer_id"], data["sale_date"], wh,
                         subtotal, discount, totals["discount_pct"], tax, totals["sales_tax"], totals["further_tax"],
                         totals["extra_tax"], totals["fed_tax"], totals["wht_tax"], taxable,
                         totals["tax_inclusive"], data.get("tax_rate_id"), total, paid,
                         data.get("payment_mode", "credit"), data.get("notes"), data.get("dn_id"),
                         data.get("order_id"), data.get("quotation_id"), weighbridge,
                         vehicle_no, driver_name, driver_contact, dispatch_remarks,
                         data.get("weight_slip_id"), total_net_weight, status, user_id, ts),
                    )
                    sale_id = cur.lastrowid
                    break
                except sqlite3.IntegrityError as ex:
                    msg = str(ex).lower()
                    if "document_no" not in msg and "unique" not in msg:
                        raise
                    data["invoice_no"] = ensure_document_no("SI", None, conn)
            if not sale_id:
                raise ValueError(
                    "Could not save invoice — document number conflict. Please try again."
                )

        for li in line_items:
            pid = li["item_id"]
            conn.execute(
                """INSERT INTO sales_invoice_items (invoice_id, product_id, quantity, rate, amount, net_weight, tax_amount, line_discount)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (sale_id, pid, li["quantity"], li["rate"], li["line_amount"],
                 float(li.get("net_weight") or 0), li.get("tax_amount", 0), li.get("line_discount", 0)),
            )

        from db_v3 import apply_sales_order_delivery, mark_quotation_converted
        if data.get("order_id"):
            apply_sales_order_delivery(conn, data["order_id"], sale_id)
            so_q = conn.execute(
                "SELECT quotation_id FROM sales_orders WHERE id=?", (data["order_id"],)
            ).fetchone()
            if so_q and so_q["quotation_id"]:
                mark_quotation_converted(conn, so_q["quotation_id"])
        elif data.get("quotation_id"):
            mark_quotation_converted(conn, data["quotation_id"])

        refresh_invoice_weight_match(conn, sale_id, "sales")
        gp_row = conn.execute(
            "SELECT gate_pass_id FROM sales_invoices WHERE id=?", (sale_id,),
        ).fetchone()
        has_gate_pass = bool(gp_row and gp_row["gate_pass_id"]) or bool(
            conn.execute(
                "SELECT 1 FROM gate_passes WHERE sales_invoice_id=? LIMIT 1", (sale_id,),
            ).fetchone()
        )
        try:
            from db_v13_13 import persist_invoice_v13_extras, sync_draft_registry_row
            persist_invoice_v13_extras(conn, "sales_invoices", sale_id, data)
            row = conn.execute(
                """SELECT si.*, c.name AS party_name FROM sales_invoices si
                   LEFT JOIN customers c ON c.id = si.customer_id WHERE si.id=?""",
                (sale_id,),
            ).fetchone()
            if row:
                sync_draft_registry_row(
                    conn,
                    doc_type="Sales Invoice",
                    doc_table="sales_invoices",
                    record_id=sale_id,
                    document_no=row["document_no"],
                    doc_date=row["invoice_date"],
                    party_name=row["party_name"] or "",
                    amount=row["total"],
                    status=row["status"],
                    approval_status=row["approval_status"] if "approval_status" in row.keys() else row["status"],
                    created_by=row["created_by"],
                    created_at=row["created_at"] or "",
                    updated_by=user_id,
                    updated_at=ts,
                )
        except Exception:
            pass
    if data.get("weight_slip_id"):
        link_weight_slip_to_invoice(
            data["weight_slip_id"], "sales_invoice", sale_id, user_id,
            as_primary=data.get("weight_slip_as_primary", None),
        )
    has_dispatch = bool(
        (data.get("vehicle_no") or data.get("driver_name") or data.get("driver_contact")
         or data.get("dispatch_remarks"))
        and not weighbridge
    )
    if sale_id and (data.get("weight_slip_id") or has_gate_pass or has_dispatch):
        from db_invoice_workflow import generate_gate_pass_from_sale
        generate_gate_pass_from_sale(sale_id, user_id, require_approved=False)
    invalidate_invoices()
    invalidate_stock()
    invalidate("customers")
    try:
        from product_rates_legacy import clear_rate_cache
        clear_rate_cache()
    except Exception:
        pass
    return sale_id


def delete_sale(sale_id):
    with get_connection() as conn:
        s = conn.execute("SELECT * FROM sales_invoices WHERE id=?", (sale_id,)).fetchone()
        if not s:
            return
        status = s["status"] or "draft"
        if status == "approved":
            raise ValueError("Cannot delete approved invoice. Use Cancel from approval workflow.")
        if status == "pending_approval":
            raise ValueError("Cannot delete pending invoice. Reject it first.")
        if s["order_id"]:
            from db_v3 import reverse_sales_order_delivery
            reverse_sales_order_delivery(conn, s["order_id"], sale_id)
        if s["weight_slip_id"]:
            conn.execute(
                "UPDATE weight_slips SET reference_type=NULL, reference_id=NULL, weight_difference=0 WHERE id=?",
                (s["weight_slip_id"],),
            )
        if s["gate_pass_id"]:
            conn.execute("DELETE FROM gate_passes WHERE id=?", (s["gate_pass_id"],))
        conn.execute("DELETE FROM sales_invoice_items WHERE invoice_id=?", (sale_id,))
        conn.execute("DELETE FROM sales_invoices WHERE id=?", (sale_id,))
    try:
        from db_audit import log_event
        log_event(
            "sales_invoices", sale_id, "delete", module="Sales",
            document_no=s["document_no"], summary=f"Deleted sales invoice {s['document_no']}",
        )
    except Exception:
        pass
    invalidate_invoices()
    invalidate_stock()
    invalidate("customers")


# --- Purchase Returns ---
def get_purchase_returns():
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            """SELECT pr.id, pr.document_no AS return_no, pr.return_date, pr.invoice_id AS purchase_id,
                      pr.supplier_id, pr.subtotal, pr.total, pr.notes, s.name AS supplier_name
               FROM purchase_returns pr JOIN suppliers s ON pr.supplier_id=s.id
               ORDER BY pr.return_date DESC"""
        ).fetchall())


def search_purchase_returns(
    q=None,
    from_date=None,
    to_date=None,
    supplier_id=None,
    page=1,
    page_size=50,
    export_all=False,
    **_ignored,
):
    where, params = ["1=1"], []
    if q:
        like = f"%{q.strip()}%"
        where.append(
            "(pr.document_no LIKE ? OR s.name LIKE ? OR s.code LIKE ? OR COALESCE(pr.notes,'') LIKE ? "
            "OR COALESCE(pi.document_no,'') LIKE ?)"
        )
        params.extend([like, like, like, like, like])
    if from_date:
        where.append("pr.return_date >= ?")
        params.append(from_date)
    if to_date:
        where.append("pr.return_date <= ?")
        params.append(to_date)
    if supplier_id:
        where.append("pr.supplier_id = ?")
        params.append(supplier_id)
    return run_paginated_list(
        """purchase_returns pr
           JOIN suppliers s ON pr.supplier_id=s.id
           LEFT JOIN purchase_invoices pi ON pr.invoice_id=pi.id""",
        """pr.id, pr.document_no AS return_no, pr.return_date, pr.invoice_id AS purchase_id,
           pr.supplier_id, pr.subtotal, pr.total, pr.notes, pr.created_at,
           s.name AS supplier_name, s.code AS supplier_code,
           pi.document_no AS invoice_no""",
        where, params, "pr.return_date DESC, pr.id DESC", page, page_size, export_all,
        sum_exprs=["COALESCE(SUM(pr.total),0)"],
    )


def get_purchase_return(return_id):
    with get_connection() as conn:
        header = row_to_dict(conn.execute(
            """SELECT pr.id, pr.document_no AS return_no, pr.return_date, pr.invoice_id AS purchase_id,
                      pr.supplier_id, pr.subtotal, pr.total, pr.notes, pr.created_at, pr.modified_at,
                      s.name AS supplier_name, s.code AS supplier_code,
                      pi.document_no AS invoice_no
               FROM purchase_returns pr
               JOIN suppliers s ON pr.supplier_id=s.id
               LEFT JOIN purchase_invoices pi ON pr.invoice_id=pi.id
               WHERE pr.id=?""",
            (return_id,),
        ).fetchone())
        if header:
            header["items"] = rows_to_list(conn.execute(
                """SELECT pri.id, pri.return_id, pri.product_id AS item_id, pri.quantity, pri.rate, pri.amount,
                          p.name AS item_name FROM purchase_return_items pri
                   JOIN products p ON pri.product_id=p.id WHERE pri.return_id=?""",
                (return_id,),
            ).fetchall())
        return header


def save_purchase_return(data, line_items, return_id=None, user_id=None):
    from db_commercial import apply_invoice_totals_to_data
    from erp_core.transaction_validation import validate_purchase_invoice
    data, totals = apply_invoice_totals_to_data(data, line_items)
    vr = validate_purchase_invoice(data, totals.get("lines") or line_items, totals, stage="draft")
    vr.raise_if_invalid("Purchase return")
    line_items = totals["lines"]
    with get_connection() as conn:
        wh = _default_warehouse_id(conn)
        subtotal = totals["subtotal"]
        total = totals["total"]
        ts = _now()
        if not return_id:
            data["return_no"] = ensure_document_no("PR", data.get("return_no"), conn)
        elif data.get("return_no"):
            _sync_doc_sequence(conn, "PR", data["return_no"])
        if return_id:
            for o in conn.execute("SELECT * FROM purchase_return_items WHERE return_id=?", (return_id,)).fetchall():
                _adjust_warehouse_stock(conn, o["product_id"], wh, o["quantity"])
            old_r = conn.execute("SELECT * FROM purchase_returns WHERE id=?", (return_id,)).fetchone()
            conn.execute("UPDATE suppliers SET current_balance=current_balance-? WHERE id=?", (old_r["total"], old_r["supplier_id"]))
            conn.execute("DELETE FROM purchase_return_items WHERE return_id=?", (return_id,))
            conn.execute(
                """UPDATE purchase_returns SET document_no=?, invoice_id=?, supplier_id=?, return_date=?,
                   subtotal=?, total=?, notes=?, modified_by=?, modified_at=? WHERE id=?""",
                (data["return_no"], data.get("purchase_id"), data["supplier_id"], data["return_date"],
                 subtotal, total, data.get("notes"), user_id, ts, return_id),
            )
        else:
            cur = conn.execute(
                """INSERT INTO purchase_returns (document_no, invoice_id, supplier_id, return_date,
                   warehouse_id, subtotal, total, notes, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (data["return_no"], data.get("purchase_id"), data["supplier_id"], data["return_date"],
                 wh, subtotal, total, data.get("notes"), user_id),
            )
            return_id = cur.lastrowid

        allow_neg = get_setting("allow_negative_stock", "0") == "1"
        for li in line_items:
            pid = li["item_id"]
            stock = conn.execute("SELECT COALESCE(quantity,0) FROM warehouse_stock WHERE warehouse_id=? AND product_id=?", (wh, pid)).fetchone()
            if (stock[0] if stock else 0) < li["quantity"] and not allow_neg:
                raise ValueError(f"Insufficient stock for return item ID {pid}")
            conn.execute(
                "INSERT INTO purchase_return_items (return_id, product_id, quantity, rate, amount) VALUES (?, ?, ?, ?, ?)",
                (return_id, pid, li["quantity"], li["rate"], li["line_amount"]),
            )
            _adjust_warehouse_stock(conn, pid, wh, -li["quantity"])
            _record_movement(conn, pid, wh, "out", li["quantity"], "purchase_return", return_id, data["return_no"], user_id)

        conn.execute("UPDATE suppliers SET current_balance=current_balance+? WHERE id=?", (total, data["supplier_id"]))
        return return_id


def delete_purchase_return(return_id):
    with get_connection() as conn:
        wh = _default_warehouse_id(conn)
        r = conn.execute("SELECT * FROM purchase_returns WHERE id=?", (return_id,)).fetchone()
        if not r:
            return
        for o in conn.execute("SELECT * FROM purchase_return_items WHERE return_id=?", (return_id,)).fetchall():
            _adjust_warehouse_stock(conn, o["product_id"], wh, o["quantity"])
        conn.execute("UPDATE suppliers SET current_balance=current_balance+? WHERE id=?", (r["total"], r["supplier_id"]))
        conn.execute("DELETE FROM purchase_return_items WHERE return_id=?", (return_id,))
        conn.execute("DELETE FROM purchase_returns WHERE id=?", (return_id,))


# --- Sale Returns ---
def get_sale_returns():
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            """SELECT sr.id, sr.document_no AS return_no, sr.return_date, sr.invoice_id AS sale_id,
                      sr.customer_id, sr.subtotal, sr.total, sr.notes, c.name AS customer_name
               FROM sales_returns sr JOIN customers c ON sr.customer_id=c.id ORDER BY sr.return_date DESC"""
        ).fetchall())


def search_sale_returns(
    q=None,
    from_date=None,
    to_date=None,
    customer_id=None,
    page=1,
    page_size=50,
    export_all=False,
    **_ignored,
):
    where, params = ["1=1"], []
    if q:
        like = f"%{q.strip()}%"
        where.append(
            "(sr.document_no LIKE ? OR c.name LIKE ? OR c.code LIKE ? OR COALESCE(sr.notes,'') LIKE ? "
            "OR COALESCE(si.document_no,'') LIKE ?)"
        )
        params.extend([like, like, like, like, like])
    if from_date:
        where.append("sr.return_date >= ?")
        params.append(from_date)
    if to_date:
        where.append("sr.return_date <= ?")
        params.append(to_date)
    if customer_id:
        where.append("sr.customer_id = ?")
        params.append(customer_id)
    return run_paginated_list(
        """sales_returns sr
           JOIN customers c ON sr.customer_id=c.id
           LEFT JOIN sales_invoices si ON sr.invoice_id=si.id""",
        """sr.id, sr.document_no AS return_no, sr.return_date, sr.invoice_id AS sale_id,
           sr.customer_id, sr.subtotal, sr.total, sr.notes, sr.created_at,
           c.name AS customer_name, c.code AS customer_code,
           si.document_no AS invoice_no""",
        where, params, "sr.return_date DESC, sr.id DESC", page, page_size, export_all,
        sum_exprs=["COALESCE(SUM(sr.total),0)"],
    )


def get_sale_return(return_id):
    with get_connection() as conn:
        header = row_to_dict(conn.execute(
            """SELECT sr.id, sr.document_no AS return_no, sr.return_date, sr.invoice_id AS sale_id,
                      sr.customer_id, sr.subtotal, sr.total, sr.notes, sr.created_at, sr.modified_at,
                      c.name AS customer_name, c.code AS customer_code,
                      si.document_no AS invoice_no
               FROM sales_returns sr
               JOIN customers c ON sr.customer_id=c.id
               LEFT JOIN sales_invoices si ON sr.invoice_id=si.id
               WHERE sr.id=?""",
            (return_id,),
        ).fetchone())
        if header:
            header["items"] = rows_to_list(conn.execute(
                """SELECT sri.id, sri.return_id, sri.product_id AS item_id, sri.quantity, sri.rate, sri.amount,
                          p.name AS item_name FROM sales_return_items sri
                   JOIN products p ON sri.product_id=p.id WHERE sri.return_id=?""",
                (return_id,),
            ).fetchall())
        return header


def save_sale_return(data, line_items, return_id=None, user_id=None):
    from db_commercial import apply_invoice_totals_to_data
    from erp_core.transaction_validation import validate_sale_invoice
    data, totals = apply_invoice_totals_to_data(data, line_items)
    vr = validate_sale_invoice(data, totals.get("lines") or line_items, totals, stage="draft")
    vr.raise_if_invalid("Sales return")
    line_items = totals["lines"]
    with get_connection() as conn:
        wh = _default_warehouse_id(conn)
        subtotal = totals["subtotal"]
        total = totals["total"]
        ts = _now()
        if not return_id:
            data["return_no"] = ensure_document_no("SR", data.get("return_no"), conn)
        elif data.get("return_no"):
            _sync_doc_sequence(conn, "SR", data["return_no"])
        if return_id:
            for o in conn.execute("SELECT * FROM sales_return_items WHERE return_id=?", (return_id,)).fetchall():
                _adjust_warehouse_stock(conn, o["product_id"], wh, -o["quantity"])
            old_r = conn.execute("SELECT * FROM sales_returns WHERE id=?", (return_id,)).fetchone()
            conn.execute("UPDATE customers SET current_balance=current_balance-? WHERE id=?", (old_r["total"], old_r["customer_id"]))
            conn.execute("DELETE FROM sales_return_items WHERE return_id=?", (return_id,))
            conn.execute(
                """UPDATE sales_returns SET document_no=?, invoice_id=?, customer_id=?, return_date=?,
                   subtotal=?, total=?, notes=?, modified_by=?, modified_at=? WHERE id=?""",
                (data["return_no"], data.get("sale_id"), data["customer_id"], data["return_date"],
                 subtotal, total, data.get("notes"), user_id, ts, return_id),
            )
        else:
            cur = conn.execute(
                """INSERT INTO sales_returns (document_no, invoice_id, customer_id, return_date,
                   warehouse_id, subtotal, total, notes, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (data["return_no"], data.get("sale_id"), data["customer_id"], data["return_date"],
                 wh, subtotal, total, data.get("notes"), user_id),
            )
            return_id = cur.lastrowid

        for li in line_items:
            pid = li["item_id"]
            conn.execute(
                "INSERT INTO sales_return_items (return_id, product_id, quantity, rate, amount) VALUES (?, ?, ?, ?, ?)",
                (return_id, pid, li["quantity"], li["rate"], li.get("line_amount", li.get("amount", 0))),
            )
            _adjust_warehouse_stock(conn, pid, wh, li["quantity"])
            _record_movement(conn, pid, wh, "in", li["quantity"], "sales_return", return_id, data["return_no"], user_id)

        conn.execute("UPDATE customers SET current_balance=current_balance-? WHERE id=?", (total, data["customer_id"]))
        return return_id


def delete_sale_return(return_id):
    with get_connection() as conn:
        wh = _default_warehouse_id(conn)
        r = conn.execute("SELECT * FROM sales_returns WHERE id=?", (return_id,)).fetchone()
        if not r:
            return
        for o in conn.execute("SELECT * FROM sales_return_items WHERE return_id=?", (return_id,)).fetchall():
            _adjust_warehouse_stock(conn, o["product_id"], wh, -o["quantity"])
        conn.execute("UPDATE customers SET current_balance=current_balance+? WHERE id=?", (r["total"], r["customer_id"]))
        conn.execute("DELETE FROM sales_return_items WHERE return_id=?", (return_id,))
        conn.execute("DELETE FROM sales_returns WHERE id=?", (return_id,))


# --- Cash / Bank (compat with cash_book / bank_book API) ---
def _next_doc_no(conn, doc_type: str) -> str:
    return _reserve_document_conn(conn, doc_type)


def _sync_sale_linked_cash_bank_refs(conn, old_doc: str, new_doc: str):
    """Keep cash/bank receipt description + reference_no aligned when a sale doc no changes."""
    old_doc = (old_doc or "").strip()
    new_doc = (new_doc or "").strip()
    if not old_doc or not new_doc or old_doc == new_doc:
        return
    new_desc = f"Sale {new_doc}"
    for table in ("cash_receipts", "bank_receipts"):
        try:
            conn.execute(
                f"""UPDATE {table}
                   SET reference_no=?, description=?
                   WHERE reference_no=? OR description=? OR description=?""",
                (new_doc, new_desc, old_doc, f"Sale {old_doc}", old_doc),
            )
        except Exception:
            pass


def _add_cash_receipt(conn, entry_date, description, reference_no, amount, user_id=None, account_id=None,
                      party_type=None, party_id=None):
    from db_cash_day import assert_cash_day_open
    assert_cash_day_open(entry_date, "post")
    doc = _next_doc_no(conn, "CR")
    # Prefer Sale <invoice> when reference is a sales invoice — keeps Daily Activity in sync
    ref = (reference_no or "").strip()
    desc = (description or "").strip()
    if ref.upper().startswith("SAL") and (not desc or desc.upper().startswith("SALE ")):
        desc = f"Sale {ref}"
    ts = _now()
    cur = conn.execute(
        """INSERT INTO cash_receipts (document_no, receipt_date, account_id, party_type, party_id,
           description, reference_no, amount, created_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (doc, entry_date, account_id, party_type, party_id, desc, reference_no, amount, user_id, ts),
    )
    return cur.lastrowid, doc


def _add_cash_payment(conn, entry_date, description, reference_no, amount, user_id=None, account_id=None,
                      party_type=None, party_id=None):
    from db_cash_day import assert_cash_day_open
    assert_cash_day_open(entry_date, "post")
    doc = _next_doc_no(conn, "CP")
    ts = _now()
    cur = conn.execute(
        """INSERT INTO cash_payments (document_no, payment_date, account_id, party_type, party_id,
           description, reference_no, amount, created_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (doc, entry_date, account_id, party_type, party_id, description, reference_no, amount, user_id, ts),
    )
    return cur.lastrowid, doc


def _add_bank_receipt(conn, entry_date, description, reference_no, amount, account_id=None, user_id=None,
                      party_type=None, party_id=None):
    doc = _next_doc_no(conn, "BR")
    ts = _now()
    cur = conn.execute(
        """INSERT INTO bank_receipts (document_no, receipt_date, account_id, party_type, party_id,
           description, reference_no, amount, created_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (doc, entry_date, account_id, party_type, party_id, description, reference_no, amount, user_id, ts),
    )
    return cur.lastrowid, doc


def _add_bank_payment(conn, entry_date, description, reference_no, amount, account_id=None, user_id=None,
                      party_type=None, party_id=None):
    doc = _next_doc_no(conn, "BP")
    ts = _now()
    cur = conn.execute(
        """INSERT INTO bank_payments (document_no, payment_date, account_id, party_type, party_id,
           description, reference_no, amount, created_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (doc, entry_date, account_id, party_type, party_id, description, reference_no, amount, user_id, ts),
    )
    return cur.lastrowid, doc


def _cash_advance_return_receipt_exclude_sql():
    """Cash-advance settlement returns are GL/advance-only — never in Cash Book."""
    return (
        " AND reference_no NOT GLOB 'CAS-*' "
        " AND id NOT IN ("
        "SELECT cash_entry_id FROM cash_advance_settlements WHERE cash_entry_id IS NOT NULL"
        ")"
    )


def _cash_advance_issue_payment_exclude_sql():
    """Cash-advance issue payments are shadow-only — never in Cash Book."""
    return (
        " AND id NOT IN ("
        "SELECT issue_entry_id FROM cash_advances WHERE issue_entry_id IS NOT NULL"
        ") "
        "AND document_no NOT IN ("
        "SELECT issue_doc_no FROM cash_advances "
        "WHERE issue_doc_no IS NOT NULL AND issue_doc_no != ''"
        ") "
        "AND NOT ("
        "COALESCE(reference_no,'') GLOB 'CA-*' "
        "AND COALESCE(description,'') LIKE 'Advance to%'"
        ")"
    )


def cash_book_payments_sum(conn, *, before_date=None, from_date=None, to_date=None):
    """Sum cash payments included in Cash Book (excludes cash-advance issue vouchers)."""
    q = "SELECT COALESCE(SUM(amount),0) FROM cash_payments WHERE 1=1"
    params = []
    q += _cash_advance_issue_payment_exclude_sql()
    if before_date:
        q += " AND payment_date<?"; params.append(before_date)
    if from_date:
        q += " AND payment_date>=?"; params.append(from_date)
    if to_date:
        q += " AND payment_date<=?"; params.append(to_date)
    return float(conn.execute(q, params).fetchone()[0] or 0)


def cash_advance_outstanding_summary(conn=None):
    """Totals for open/partial cash advances (Cash Book physical-cash adjustment).

    Returns:
        total_outstanding: sum of outstanding_amount on open/partial advances.
        outside_cash_book: same as total_outstanding — issue is shadow-only; only
            unsettled float is excluded from physical cash in hand.
    """
    from db_v3 import _ensure_cash_advances_schema

    def _run(c):
        _ensure_cash_advances_schema(c)
        row = c.execute(
            """SELECT COALESCE(SUM(outstanding_amount), 0)
               FROM cash_advances
               WHERE status IN ('open','partial')
                 AND COALESCE(outstanding_amount, 0) > 0"""
        ).fetchone()
        total = round(float(row[0] or 0), 2)
        return {"total_outstanding": total, "outside_cash_book": total}

    if conn is not None:
        return _run(conn)
    with get_connection() as c:
        return _run(c)


def cash_book_receipts_sum(conn, *, before_date=None, from_date=None, to_date=None):
    """Sum cash receipts included in Cash Book (excludes advance settlement returns)."""
    q = "SELECT COALESCE(SUM(amount),0) FROM cash_receipts WHERE 1=1"
    params = []
    q += _cash_advance_return_receipt_exclude_sql()
    if before_date:
        q += " AND receipt_date<?"; params.append(before_date)
    if from_date:
        q += " AND receipt_date>=?"; params.append(from_date)
    if to_date:
        q += " AND receipt_date<=?"; params.append(to_date)
    return float(conn.execute(q, params).fetchone()[0] or 0)


def _cash_book_rows(conn, from_date=None, to_date=None):
    q = """SELECT id, receipt_date AS entry_date, description, reference_no, 'credit' AS entry_type,
                  amount, document_no, account_id, party_type, party_id, created_at
           FROM cash_receipts WHERE 1=1"""
    params = []
    q += _cash_advance_return_receipt_exclude_sql()
    if from_date:
        q += " AND receipt_date>=?"; params.append(from_date)
    if to_date:
        q += " AND receipt_date<=?"; params.append(to_date)
    receipts = rows_to_list(conn.execute(q, params).fetchall())
    for r in receipts:
        r["entry_source"] = "cash_receipt"
    q2 = """SELECT id, payment_date AS entry_date, description, reference_no, 'debit' AS entry_type,
                   amount, document_no, account_id, party_type, party_id, created_at
            FROM cash_payments WHERE 1=1"""
    params2 = []
    q2 += _cash_advance_issue_payment_exclude_sql()
    if from_date:
        q2 += " AND payment_date>=?"; params2.append(from_date)
    if to_date:
        q2 += " AND payment_date<=?"; params2.append(to_date)
    payments = rows_to_list(conn.execute(q2, params2).fetchall())
    for r in payments:
        r["entry_source"] = "cash_payment"
    rows = sorted(receipts + payments, key=lambda r: (r["entry_date"], r["id"]))
    bal = 0
    for r in rows:
        bal = bal + r["amount"] if r["entry_type"] == "credit" else bal - r["amount"]
        r["balance_after"] = bal
        title = _cash_bank_account_title(conn, r.get("party_type"), r.get("party_id"))
        if not title and r.get("account_id"):
            title = _cash_bank_account_title(conn, "account", r.get("account_id"))
        r["account_title"] = title
    return rows


def _cash_bank_account_title(conn, party_type, party_id) -> str:
    """Human-readable account title for cash/bank vouchers."""
    if not party_type or not party_id:
        return ""
    try:
        pid = int(party_id)
    except (TypeError, ValueError):
        return ""
    pt = str(party_type).lower()
    if pt == "customer":
        row = conn.execute("SELECT code, name FROM customers WHERE id=?", (pid,)).fetchone()
    elif pt == "supplier":
        row = conn.execute("SELECT code, name FROM suppliers WHERE id=?", (pid,)).fetchone()
    elif pt in ("account", "expense"):
        row = conn.execute("SELECT code, name FROM chart_of_accounts WHERE id=?", (pid,)).fetchone()
    else:
        return ""
    if not row:
        return ""
    return f"{row['code']} - {row['name']}"


def get_cash_book(from_date=None, to_date=None):
    with get_connection() as conn:
        return _cash_book_rows(conn, from_date, to_date)


def get_provisional_cash_sale_invoices(from_date=None, to_date=None):
    """Draft / pending-approval cash sales not yet posted as cash receipts.

    Shown in Cash Book Daily Book for visibility; they do not affect cash balance
    until the invoice is approved and a cash_receipts row is created.
    """
    q = """
        SELECT s.id, s.document_no, s.invoice_date AS entry_date, s.status,
               COALESCE(s.total, 0) AS amount, s.created_at,
               c.name AS customer_name
        FROM sales_invoices s
        LEFT JOIN customers c ON c.id = s.customer_id
        WHERE LOWER(COALESCE(s.payment_mode, '')) = 'cash'
          AND LOWER(COALESCE(s.status, '')) IN ('draft', 'pending_approval')
          AND NOT EXISTS (
              SELECT 1 FROM cash_receipts cr
              WHERE cr.reference_no = s.document_no
          )
    """
    params = []
    if from_date:
        q += " AND s.invoice_date >= ?"
        params.append(from_date)
    if to_date:
        q += " AND s.invoice_date <= ?"
        params.append(to_date)
    q += " ORDER BY s.invoice_date, s.id"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, params).fetchall())


def add_cash_entry(entry_date, description, reference_no, entry_type, amount, account_id=None, user_id=None):
    from db_v3 import validate_fiscal_open
    validate_fiscal_open(entry_date)
    with get_connection() as conn:
        if entry_type == "credit":
            eid, doc = _add_cash_receipt(conn, entry_date, description, reference_no, amount, user_id, account_id)
            tbl = "cash_receipts"
        else:
            eid, doc = _add_cash_payment(conn, entry_date, description, reference_no, amount, user_id, account_id)
            tbl = "cash_payments"
    try:
        from db_audit import log_event
        log_event(
            tbl, eid, "create", user_id=user_id, module="Finance",
            document_no=doc, summary=f"Cash {entry_type} {amount:,.2f} — {description or reference_no or ''}",
        )
    except Exception:
        pass


def _cash_entry_date(entry_id):
    """Return entry_date string for a cash receipt or payment id."""
    with get_connection() as conn:
        for tbl, col in (("cash_receipts", "receipt_date"), ("cash_payments", "payment_date")):
            row = conn.execute(f"SELECT {col} FROM {tbl} WHERE id=?", (entry_id,)).fetchone()
            if row:
                return row[0]
    return None


def update_cash_entry(entry_id, entry_date, description, reference_no, entry_type, amount, account_id=None, user_id=None):
    from db_cash_day import assert_cash_day_open
    old_date = _cash_entry_date(entry_id)
    if old_date:
        assert_cash_day_open(old_date, "edit or delete")
    assert_cash_day_open(entry_date, "post")
    delete_cash_entry(entry_id, entry_type, _skip_close_check=True)
    add_cash_entry(entry_date, description, reference_no, entry_type, amount, account_id, user_id)


def delete_cash_entry(entry_id, entry_type=None, _skip_close_check=False):
    from db_cash_day import assert_cash_day_open
    if not _skip_close_check:
        old_date = _cash_entry_date(entry_id)
        if old_date:
            assert_cash_day_open(old_date, "delete")
    with get_connection() as conn:
        for tbl in ("cash_receipts", "cash_payments"):
            row = conn.execute(
                f"SELECT document_no, amount FROM {tbl} WHERE id=?", (entry_id,)
            ).fetchone()
            if row:
                conn.execute(f"DELETE FROM {tbl} WHERE id=?", (entry_id,))
                try:
                    from db_audit import log_event
                    log_event(
                        tbl, entry_id, "delete", module="Finance",
                        document_no=row["document_no"],
                        summary=f"Deleted cash entry {row['document_no']}",
                    )
                except Exception:
                    pass
                return


def _bank_book_rows(conn, from_date=None, to_date=None):
    q = """SELECT id, receipt_date AS entry_date, description, reference_no, 'credit' AS entry_type,
                  amount, document_no, account_id, party_type, party_id, created_at
           FROM bank_receipts WHERE 1=1"""
    params = []
    if from_date:
        q += " AND receipt_date>=?"; params.append(from_date)
    if to_date:
        q += " AND receipt_date<=?"; params.append(to_date)
    receipts = rows_to_list(conn.execute(q, params).fetchall())
    for r in receipts:
        r["entry_source"] = "bank_receipt"
    q2 = """SELECT id, payment_date AS entry_date, description, reference_no, 'debit' AS entry_type,
                   amount, document_no, account_id, party_type, party_id, created_at
            FROM bank_payments WHERE 1=1"""
    params2 = []
    if from_date:
        q2 += " AND payment_date>=?"; params2.append(from_date)
    if to_date:
        q2 += " AND payment_date<=?"; params2.append(to_date)
    payments = rows_to_list(conn.execute(q2, params2).fetchall())
    for r in payments:
        r["entry_source"] = "bank_payment"
    rows = sorted(receipts + payments, key=lambda r: (r["entry_date"], r["id"]))
    bal = 0
    for r in rows:
        bal = bal + r["amount"] if r["entry_type"] == "credit" else bal - r["amount"]
        r["balance_after"] = bal
        title = _cash_bank_account_title(conn, r.get("party_type"), r.get("party_id"))
        # GL-linked vouchers store the ledger on party_type=account; do not
        # fall back to account_id here (that is often the bank account itself).
        r["account_title"] = title
    return rows


def get_bank_book(from_date=None, to_date=None):
    with get_connection() as conn:
        return _bank_book_rows(conn, from_date, to_date)


def add_bank_entry(entry_date, description, reference_no, entry_type, amount, account_id=None, user_id=None):
    from db_v3 import validate_fiscal_open
    validate_fiscal_open(entry_date)
    with get_connection() as conn:
        if entry_type == "credit":
            entry_id, doc_no = _add_bank_receipt(conn, entry_date, description, reference_no, amount, account_id, user_id)
            return {"id": entry_id, "document_no": doc_no, "vch_source": "bank_receipt"}
        entry_id, doc_no = _add_bank_payment(conn, entry_date, description, reference_no, amount, account_id, user_id)
        return {"id": entry_id, "document_no": doc_no, "vch_source": "bank_payment"}


def update_bank_entry(entry_id, entry_date, description, reference_no, entry_type, amount, account_id=None, user_id=None):
    delete_bank_entry(entry_id, entry_type)
    add_bank_entry(entry_date, description, reference_no, entry_type, amount, account_id, user_id)


def delete_bank_entry(entry_id, entry_type=None):
    from db_v3 import delete_attachments_for_source
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM bank_receipts WHERE id=?", (entry_id,)).fetchone():
            delete_attachments_for_source("bank_receipt", entry_id)
        elif conn.execute("SELECT 1 FROM bank_payments WHERE id=?", (entry_id,)).fetchone():
            delete_attachments_for_source("bank_payment", entry_id)
        conn.execute("DELETE FROM bank_receipts WHERE id=?", (entry_id,))
        conn.execute("DELETE FROM bank_payments WHERE id=?", (entry_id,))


# --- Inventory ---
def get_inventory():
    q = PRODUCT_SELECT + " ORDER BY p.name"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q).fetchall())


def add_inventory_adjustment(item_id, adjustment_date, adjustment_type, quantity, reason, user_id=None):
    with get_connection() as conn:
        wh = _default_warehouse_id(conn)
        qty_change = quantity if adjustment_type == "in" else -quantity
        if adjustment_type == "in" and quantity > 0:
            pp = conn.execute(
                "SELECT COALESCE(purchase_price,0) FROM products WHERE id=?", (item_id,)
            ).fetchone()
            unit_cost = float(pp[0] if pp else 0)
            from erp_core.inventory_valuation import apply_inbound_cost
            apply_inbound_cost(conn, wh, item_id, quantity, unit_cost)
        _adjust_warehouse_stock(conn, item_id, wh, qty_change)
        _record_movement(conn, item_id, wh, adjustment_type, quantity, "adjustment", None, reason, user_id)
    invalidate_stock()


def get_inventory_adjustments():
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            """SELECT im.id, im.movement_date AS adjustment_date, im.movement_type AS adjustment_type,
                      im.quantity, im.reason, p.code AS item_code, p.name AS item_name
               FROM inventory_movements im
               JOIN products p ON im.product_id=p.id
               WHERE im.reference_type='adjustment' OR im.reference_type IS NULL
               ORDER BY im.movement_date DESC"""
        ).fetchall())


def delete_inventory_adjustment(adj_id):
    with get_connection() as conn:
        adj = conn.execute("SELECT * FROM inventory_movements WHERE id=?", (adj_id,)).fetchone()
        if adj:
            qty_change = adj["quantity"] if adj["movement_type"] == "out" else -adj["quantity"]
            _adjust_warehouse_stock(conn, adj["product_id"], adj["warehouse_id"], qty_change)
            conn.execute("DELETE FROM inventory_movements WHERE id=?", (adj_id,))
    invalidate_stock()


# --- Reports ---
def get_dashboard_stats():
    try:
        return get_dashboard_stats_v2()
    except Exception:
        pass
    with get_connection() as conn:
        stats = {}
        stats["customers"] = conn.execute("SELECT COUNT(*) FROM customers WHERE is_active=1").fetchone()[0]
        stats["suppliers"] = conn.execute("SELECT COUNT(*) FROM suppliers WHERE is_active=1").fetchone()[0]
        stats["items"] = conn.execute("SELECT COUNT(*) FROM products WHERE is_active=1").fetchone()[0]
        stats["sales_total"] = conn.execute("SELECT COALESCE(SUM(total),0) FROM sales_invoices").fetchone()[0]
        stats["purchases_total"] = conn.execute("SELECT COALESCE(SUM(total),0) FROM purchase_invoices").fetchone()[0]
        stats["receivables"] = conn.execute("SELECT COALESCE(SUM(current_balance),0) FROM customers WHERE current_balance>0").fetchone()[0]
        stats["payables"] = conn.execute("SELECT COALESCE(SUM(-current_balance),0) FROM suppliers WHERE current_balance<0").fetchone()[0]
        stk = _product_stock_join("p")
        stock_col = _product_stock_sql("p")
        unit_cost = """COALESCE((
            SELECT wac.avg_cost FROM warehouse_product_avg_cost wac
            WHERE wac.product_id = p.id ORDER BY wac.warehouse_id LIMIT 1
        ), p.purchase_price, 0)"""
        stats["stock_value"] = conn.execute(
            f"SELECT COALESCE(SUM({stock_col} * ({unit_cost})),0) FROM products p {stk}"
        ).fetchone()[0]
        low_stock = conn.execute(
            f"""SELECT p.name, {stock_col} AS stock_qty, p.reorder_level FROM products p {stk}
                WHERE {stock_col} <= p.reorder_level AND p.is_active=1 AND p.reorder_level > 0"""
        ).fetchall()
        stats["low_stock"] = rows_to_list(low_stock)
        recent_sales = conn.execute(
            """SELECT s.document_no AS invoice_no, s.invoice_date AS sale_date, s.total, c.name AS customer_name
               FROM sales_invoices s JOIN customers c ON s.customer_id=c.id ORDER BY s.id DESC LIMIT 5"""
        ).fetchall()
        stats["recent_sales"] = rows_to_list(recent_sales)
        return stats


def _party_display(conn, party_type, party_id):
    """Return 'CODE - Name' for a customer or supplier."""
    if party_type == "customer":
        r = conn.execute("SELECT code, name FROM customers WHERE id=?", (party_id,)).fetchone()
    elif party_type == "supplier":
        r = conn.execute("SELECT code, name FROM suppliers WHERE id=?", (party_id,)).fetchone()
    else:
        return "Unknown"
    if not r:
        return "Unknown"
    return f"{r['code']} - {r['name']}"


def _counter_party(r, party_type, party_id):
    if r["from_party_type"] == party_type and r["from_party_id"] == party_id:
        return r["to_party_type"], r["to_party_id"]
    return r["from_party_type"], r["from_party_id"]


def _party_transfer_ledger_rows(conn, party_type, party_id, from_date=None, to_date=None):
    """Ledger lines from party_transfers for customer or supplier sub-ledger."""
    q = """SELECT transfer_date, document_no, amount, description, transfer_type,
                  from_party_type, from_party_id, to_party_type, to_party_id
           FROM party_transfers
           WHERE ((from_party_type=? AND from_party_id=?) OR (to_party_type=? AND to_party_id=?))"""
    params = [party_type, party_id, party_type, party_id]
    if from_date:
        q += " AND transfer_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND transfer_date<=?"
        params.append(to_date)
    rows = []
    fd = str(from_date)[:10] if from_date else None
    td = str(to_date)[:10] if to_date else None
    for raw in conn.execute(q, params).fetchall():
        r = row_to_dict(raw)
        # Defensive: SQL OR/AND precedence historically leaked out-of-range rows
        dt = str(r.get("transfer_date") or "")[:10]
        if fd and dt and dt < fd:
            continue
        if td and dt and dt > td:
            continue
        tt = r["transfer_type"]
        amt = float(r["amount"])
        is_from = r["from_party_type"] == party_type and r["from_party_id"] == party_id
        is_to = r["to_party_type"] == party_type and r["to_party_id"] == party_id
        cp_type, cp_id = _counter_party(r, party_type, party_id)
        cp_label = _party_display(conn, cp_type, cp_id)
        if tt == "customer_to_supplier":
            if party_type == "customer":
                debit, credit = 0, amt
            else:
                debit, credit = amt, 0
            desc = f"Party Set-off with {cp_label}"
        elif party_type == "customer":
            if is_from:
                debit, credit = 0, amt
                desc = f"Party Transfer to {cp_label}"
            elif is_to:
                debit, credit = amt, 0
                desc = f"Party Transfer from {cp_label}"
            else:
                continue
        else:
            if is_from:
                debit, credit = amt, 0
                desc = f"Party Transfer to {cp_label}"
            elif is_to:
                debit, credit = 0, amt
                desc = f"Party Transfer from {cp_label}"
            else:
                continue
        extra = (r.get("description") or "").strip()
        if extra and cp_label not in extra:
            desc = f"{desc} — {extra}"
        rows.append({
            "date": r["transfer_date"],
            "ref": r["document_no"],
            "description": desc,
            "debit": debit,
            "credit": credit,
        })
    return rows


def _ledger_dates_match(entry_date, txn_date) -> bool:
    if not txn_date:
        return True
    a = str(entry_date or "")[:10]
    b = str(txn_date or "")[:10]
    if not a or not b:
        return True
    return a == b


def _running_balance_before_ref(entries, ref, txn_date=None) -> float:
    """Previous running balance from a ledger (opening row + movements)."""
    if not entries:
        return 0.0
    prev = float(entries[0].get("balance") or 0)
    ref_s = str(ref or "").strip()
    if not ref_s:
        return float(entries[-1].get("balance") or prev)
    for e in entries[1:]:
        if str(e.get("ref") or "").strip() == ref_s and _ledger_dates_match(e.get("date"), txn_date):
            return prev
        prev = float(e.get("balance", prev))
    # Draft / pending invoices are not on the approved ledger yet — previous = current closing.
    return float(entries[-1].get("balance") or prev)


def get_customer_balance_before_ref(customer_id, ref, txn_date=None):
    """Previous balance printed on a sales invoice — same figure as Customer Ledger.

    Dual-role parties (same code as customer and supplier) use the combined ledger.
    Draft invoices are not posted yet, so this returns the current ledger closing.
    """
    _, entries = get_customer_ledger(customer_id, include_linked=True)
    return _running_balance_before_ref(entries, ref, txn_date)


def get_supplier_balance_before_ref(supplier_id, ref, txn_date=None):
    """Previous balance printed on a purchase invoice — same figure as Supplier Ledger."""
    _, entries = get_supplier_ledger(supplier_id, include_linked=True)
    return _running_balance_before_ref(entries, ref, txn_date)


def _ensure_fmye_party_entries_table(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS fmye_party_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            party_type TEXT NOT NULL,
            party_id INTEGER NOT NULL,
            entry_date TEXT NOT NULL,
            document_no TEXT,
            description TEXT,
            debit REAL DEFAULT 0,
            credit REAL DEFAULT 0,
            voucher_type TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_fmye_party ON fmye_party_entries(party_type, party_id, entry_date)"
    )


def _fmye_party_ledger_rows(conn, party_type, party_id, from_date=None, to_date=None):
    try:
        _ensure_fmye_party_entries_table(conn)
    except Exception:
        return []
    q = """SELECT entry_date AS dt, document_no AS ref, description, debit, credit, voucher_type
           FROM fmye_party_entries WHERE party_type=? AND party_id=?"""
    params = [party_type, party_id]
    if from_date:
        q += " AND entry_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND entry_date<=?"
        params.append(to_date)
    rows = []
    for r in conn.execute(q, params).fetchall():
        vt = r["voucher_type"] or ""
        desc = r["description"] or f"{vt} Voucher".strip()
        rows.append({
            "date": r["dt"],
            "ref": r["ref"] or "",
            "description": desc,
            "voucher_type": (vt or "JVR").strip(),
            "debit": float(r["debit"] or 0),
            "credit": float(r["credit"] or 0),
        })
    return rows


def _coa_journal_party_ledger_rows(conn, party_type, party_id, from_date=None, to_date=None):
    """Journal vouchers posted to a COA account whose code matches this party.

    ERP journals hit ``general_ledger`` / Account Ledger; party Customer/Supplier
    ledgers must also show them when the chart account code = party code.
    """
    table = "customers" if party_type == "customer" else "suppliers"
    prow = conn.execute(f"SELECT code FROM {table} WHERE id=?", (party_id,)).fetchone()
    if not prow or not (prow["code"] or "").strip():
        return []
    code = str(prow["code"]).strip()
    acct = conn.execute(
        "SELECT id FROM chart_of_accounts WHERE code=?", (code,),
    ).fetchone()
    if not acct:
        return []
    q = """SELECT gl.entry_date AS dt, gl.reference_no AS ref, gl.description,
                  gl.debit, gl.credit
           FROM general_ledger gl
           WHERE gl.account_id=?
             AND LOWER(COALESCE(gl.reference_type,'')) IN ('journal', 'journal_voucher', 'jv')
             AND COALESCE(gl.reference_no,'') LIKE 'JV%'"""
    params: list = [acct["id"]]
    if from_date:
        q += " AND gl.entry_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND gl.entry_date<=?"
        params.append(to_date)
    q += " ORDER BY gl.entry_date, gl.id"
    out = []
    for r in conn.execute(q, params).fetchall():
        out.append({
            "date": r["dt"],
            "ref": r["ref"] or "",
            "description": r["description"] or "Journal Voucher",
            "voucher_type": "JV",
            "debit": float(r["debit"] or 0),
            "credit": float(r["credit"] or 0),
        })
    return out


def restore_party_openings_from_fmye(*, period_id: str = "2026") -> dict:
    """Restore customer/supplier opening_balance from FMYE OpeningBalances (OpeningDr − OpeningCr).

    Sign convention (Finance Manager): **positive = Debit, negative = Credit**.
    Applies to both customers and suppliers — never force supplier OB to credit.
    Dual-code parties: put the opening on the Chart category side (V→supplier, else customer).
    """
    report = {
        "customers_restored": 0,
        "suppliers_restored": 0,
        "dual_assigned": 0,
        "missing_in_erp": 0,
        "errors": [],
    }
    try:
        from import_fmye_from_dat import FMYEExport, EXPORT_DIR, _opening_map
    except Exception as e:
        report["errors"].append(f"FMYE import module unavailable: {e}")
        return report
    if not EXPORT_DIR.exists():
        report["errors"].append(f"FMYE export not found: {EXPORT_DIR}")
        return report

    exp = FMYEExport(EXPORT_DIR)
    open_bal = _opening_map(exp.rows("OpeningBalances"), period_id=period_id)
    chart_cat = {}
    for r in exp.rows("Chart"):
        code = (r.get("AccountCode") or "").strip()
        if code:
            chart_cat[code] = (r.get("AccountCategory") or "").strip().upper()

    with get_connection() as conn:
        cust_by = {
            (r["code"] or "").strip(): r
            for r in conn.execute("SELECT id, code, opening_balance FROM customers").fetchall()
        }
        supp_by = {
            (r["code"] or "").strip(): r
            for r in conn.execute("SELECT id, code, opening_balance FROM suppliers").fetchall()
        }
        for code, ob in open_bal.items():
            code = (code or "").strip()
            if not code:
                continue
            ob = round(float(ob or 0), 2)
            c_row = cust_by.get(code)
            s_row = supp_by.get(code)
            if not c_row and not s_row:
                report["missing_in_erp"] += 1
                continue

            if c_row and s_row:
                cat = chart_cat.get(code, "")
                # V = vendor/supplier in FMYE; C/A often customer/asset receivable
                if cat == "V" or (not cat and code.startswith("2")):
                    target_c, target_s = 0.0, ob
                    primary = "supplier"
                else:
                    target_c, target_s = ob, 0.0
                    primary = "customer"
                if abs(float(c_row["opening_balance"] or 0) - target_c) > 0.005:
                    conn.execute(
                        "UPDATE customers SET opening_balance=?, modified_at=? WHERE id=?",
                        (target_c, _now(), c_row["id"]),
                    )
                    report["customers_restored"] += 1
                if abs(float(s_row["opening_balance"] or 0) - target_s) > 0.005:
                    conn.execute(
                        "UPDATE suppliers SET opening_balance=?, modified_at=? WHERE id=?",
                        (target_s, _now(), s_row["id"]),
                    )
                    report["suppliers_restored"] += 1
                report["dual_assigned"] += 1
            elif s_row:
                if abs(float(s_row["opening_balance"] or 0) - ob) > 0.005:
                    conn.execute(
                        "UPDATE suppliers SET opening_balance=?, modified_at=? WHERE id=?",
                        (ob, _now(), s_row["id"]),
                    )
                    report["suppliers_restored"] += 1
            else:
                if abs(float(c_row["opening_balance"] or 0) - ob) > 0.005:
                    conn.execute(
                        "UPDATE customers SET opening_balance=?, modified_at=? WHERE id=?",
                        (ob, _now(), c_row["id"]),
                    )
                    report["customers_restored"] += 1
    return report


def repair_dual_role_opening_balances(conn=None) -> dict:
    """
    Same party code on customers AND suppliers with mirrored/duplicated openings.
    Keep signed opening (+Dr / −Cr) on the primary trading side; clear the stub side.
    Never force supplier openings through abs() — Credit openings stay negative.
    """
    own = conn is None
    if own:
        ctx = get_connection()
        conn = ctx.__enter__()
    cleared_c = cleared_s = moved = 0
    details = []
    try:
        rows = conn.execute(
            """
            SELECT c.code, c.name, c.id AS cid, s.id AS sid,
                   COALESCE(c.opening_balance,0) AS cob,
                   COALESCE(s.opening_balance,0) AS sob,
                   (SELECT COUNT(*) FROM sales_invoices
                    WHERE customer_id=c.id AND status='approved') AS scnt,
                   (SELECT COUNT(*) FROM purchase_invoices
                    WHERE supplier_id=s.id AND status='approved') AS pcnt
            FROM customers c
            JOIN suppliers s ON s.code = c.code
            WHERE ABS(COALESCE(c.opening_balance,0)) + ABS(COALESCE(s.opening_balance,0)) > 0.01
            """
        ).fetchall()
        for r in rows:
            r = row_to_dict(r)
            cob, sob = float(r["cob"]), float(r["sob"])
            mag = max(abs(cob), abs(sob))
            if mag < 0.01:
                continue
            # Same-magnitude duplicate/mirror only (ignore unrelated dual traders)
            if abs(cob) > 0.01 and abs(sob) > 0.01 and abs(abs(cob) - abs(sob)) > 0.05:
                continue

            scnt = int(r["scnt"] or 0)
            pcnt = int(r["pcnt"] or 0)
            code = str(r["code"] or "")
            if pcnt > scnt:
                primary = "supplier"
            elif scnt > pcnt:
                primary = "customer"
            elif code.startswith("2"):
                primary = "supplier"
            else:
                primary = "customer"

            # Preserve FMYE signed amount (prefer the side that already has the value)
            signed = cob if abs(cob) >= 0.01 else sob
            if primary == "supplier":
                new_sob, new_cob = signed, 0.0
            else:
                new_cob, new_sob = signed, 0.0

            if abs(new_cob - cob) > 0.01 or abs(new_sob - sob) > 0.01:
                conn.execute(
                    "UPDATE customers SET opening_balance=?, modified_at=? WHERE id=?",
                    (new_cob, _now(), r["cid"]),
                )
                conn.execute(
                    "UPDATE suppliers SET opening_balance=?, modified_at=? WHERE id=?",
                    (new_sob, _now(), r["sid"]),
                )
                moved += 1
                if abs(cob) > 0.01 and abs(new_cob) < 0.01:
                    cleared_c += 1
                if abs(sob) > 0.01 and abs(new_sob) < 0.01:
                    cleared_s += 1
                details.append({
                    "code": r["code"],
                    "primary": primary,
                    "sales": scnt,
                    "purchases": pcnt,
                    "customer_ob": new_cob,
                    "supplier_ob": new_sob,
                })
        return {
            "dual_pairs": len(rows),
            "adjusted": moved,
            "cleared_customer_ob": cleared_c,
            "cleared_supplier_ob": cleared_s,
            "details": details,
        }
    finally:
        if own:
            ctx.__exit__(None, None, None)


def audit_fix_party_ledgers(*, apply_dual_role_repair: bool = True, restore_fmye_openings: bool = True) -> dict:
    """
    Full party-ledger repair:
      1) Restore openings from FMYE (OpeningDr − OpeningCr → +Dr / −Cr)
      2) De-duplicate openings on dual-role codes (keep signed value)
      3) Recalculate every customer/supplier current_balance from ledger
    """
    report = {
        "supplier_ob_flipped": 0,
        "fmye_openings": {},
        "dual_role": {},
        "customers_updated": 0,
        "suppliers_updated": 0,
        "mismatches_before": 0,
        "mismatches_after": 0,
        "samples": [],
    }

    if restore_fmye_openings:
        report["fmye_openings"] = restore_party_openings_from_fmye()

    with get_connection() as conn:
        _ensure_fmye_party_entries_table(conn)
        report["supplier_ob_flipped"] = 0
        if apply_dual_role_repair:
            report["dual_role"] = repair_dual_role_opening_balances(conn)

    # Spot mismatches before full write (uses repaired openings)
    bad = []
    for row in get_customers(active_only=False):
        _, entries = get_customer_ledger(row["id"])
        closing = float(entries[-1]["balance"]) if entries else float(row.get("opening_balance") or 0)
        stored = float(row.get("current_balance") or 0)
        if abs(closing - stored) > 0.05:
            bad.append(("customer", row.get("code"), stored, closing))
    for row in get_suppliers(active_only=False):
        _, entries = get_supplier_ledger(row["id"])
        closing = float(entries[-1]["balance"]) if entries else _normalize_supplier_opening(
            float(row.get("opening_balance") or 0)
        )
        stored = float(row.get("current_balance") or 0)
        if abs(closing - stored) > 0.05:
            bad.append(("supplier", row.get("code"), stored, closing))
    report["mismatches_before"] = len(bad)
    report["samples"] = bad[:25]

    bal = recalculate_party_balances()
    report["customers_updated"] = bal.get("customers", 0)
    report["suppliers_updated"] = bal.get("suppliers", 0)

    # Verify after
    bad2 = 0
    for row in get_customers(active_only=False):
        _, entries = get_customer_ledger(row["id"])
        closing = float(entries[-1]["balance"]) if entries else 0.0
        stored = float(row.get("current_balance") or 0)
        if abs(closing - stored) > 0.05:
            bad2 += 1
    for row in get_suppliers(active_only=False):
        _, entries = get_supplier_ledger(row["id"])
        closing = float(entries[-1]["balance"]) if entries else 0.0
        stored = float(row.get("current_balance") or 0)
        if abs(closing - stored) > 0.05:
            bad2 += 1
    report["mismatches_after"] = bad2

    # Known sample: ASIF KHAN MARBLE period check
    try:
        with get_connection() as conn:
            s = conn.execute(
                "SELECT id FROM suppliers WHERE code=?", ("200345",)
            ).fetchone()
        if s:
            p, _ = get_supplier_ledger(s[0], None, "2026-08-07")
            report["asif_khan_closing_to_2026_08_07"] = (p.get("ledger_summary") or {}).get("closing")
    except Exception:
        pass

    return report


def recalculate_party_balances():
    """Sync party current_balance fields from full ledger (invoices, receipts, FMYE vouchers)."""
    with get_connection() as conn:
        _ensure_fmye_party_entries_table(conn)
    updated_c, updated_s = 0, 0
    for row in get_customers(active_only=False):
        _, entries = get_customer_ledger(row["id"])
        closing = float(entries[-1]["balance"]) if entries else float(row.get("opening_balance") or 0)
        with get_connection() as conn:
            conn.execute(
                "UPDATE customers SET current_balance=?, modified_at=? WHERE id=?",
                (closing, _now(), row["id"]),
            )
        updated_c += 1
    for row in get_suppliers(active_only=False):
        _, entries = get_supplier_ledger(row["id"])
        closing = float(entries[-1]["balance"]) if entries else float(row.get("opening_balance") or 0)
        with get_connection() as conn:
            conn.execute(
                "UPDATE suppliers SET current_balance=?, modified_at=? WHERE id=?",
                (closing, _now(), row["id"]),
            )
        updated_s += 1
    return {"customers": updated_c, "suppliers": updated_s}


def _filter_union_ledger_dates(union_sql, params, from_date, to_date):
    """Wrap UNION ledger subquery with optional dt range (avoids broken nested AND)."""
    params = list(params)
    clauses = []
    if from_date:
        clauses.append("dt>=?")
        params.append(from_date)
    if to_date:
        clauses.append("dt<=?")
        params.append(to_date)
    if clauses:
        union_sql = f"SELECT * FROM ({union_sql}) WHERE {' AND '.join(clauses)}"
    return union_sql, params


def _day_before(iso_date) -> str:
    from datetime import date, timedelta
    d = date.fromisoformat(str(iso_date)[:10])
    return (d - timedelta(days=1)).isoformat()


def _extract_cheque_no(text) -> str:
    s = str(text or "").strip()
    if not s:
        return ""
    m = re.search(r"CHQ(?:\.?\s*NO\.?)?[:#\s-]*([0-9]{5,})", s, re.I)
    return (m.group(1) if m else "").strip()


def _supplier_withholding_ledger_rows(conn, supplier_id, from_date=None, to_date=None):
    """Supplier-side WHT bank vouchers keyed to the same cheque number.

    These vouchers are often posted as plain GL/account bank payments instead of
    party-linked supplier payments, but they still settle the supplier balance.
    """
    q = """
        SELECT bp.payment_date AS dt, bp.document_no AS ref, bp.amount, bp.description
        FROM bank_payments bp
        JOIN bank_payments sp
          ON sp.party_type='supplier'
         AND sp.party_id=?
         AND bp.id != sp.id
        WHERE COALESCE(bp.party_type, '') != 'supplier'
          AND UPPER(COALESCE(bp.description, '')) LIKE '%HOLDING TAX ON CHQ%'
    """
    params = [supplier_id]
    if from_date:
        q += " AND bp.payment_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND bp.payment_date<=?"
        params.append(to_date)
    rows = []
    seen = set()
    for r in conn.execute(q, params).fetchall():
        row = row_to_dict(r)
        wht_chq = _extract_cheque_no(row.get("description"))
        if not wht_chq:
            continue
        linked = conn.execute(
            """SELECT 1
               FROM bank_payments sp
               WHERE sp.party_type='supplier' AND sp.party_id=?
                 AND (
                     COALESCE(sp.reference_no, '') LIKE ?
                     OR COALESCE(sp.description, '') LIKE ?
                 )
               LIMIT 1""",
            (supplier_id, f"%{wht_chq}%", f"%{wht_chq}%"),
        ).fetchone()
        if not linked:
            continue
        key = (row.get("dt") or "", row.get("ref") or "")
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "date": row["dt"],
            "ref": row["ref"],
            "description": f"{row.get('description') or 'Supplier W/H Tax'} (Bank)",
            "debit": float(row.get("amount") or 0),
            "credit": 0,
        })
    return rows


def _resolve_cash_bank_party(conn, account_id, account_code, group_type):
    """Map a selected GL head to a customer/supplier master when possible."""
    try:
        aid = int(account_id)
    except (TypeError, ValueError):
        return None, None
    code = str(account_code or "").strip()
    if not code:
        return None, None
    cust = conn.execute(
        "SELECT id FROM customers WHERE TRIM(COALESCE(code,''))=? LIMIT 1", (code,)
    ).fetchone()
    sup = conn.execute(
        "SELECT id FROM suppliers WHERE TRIM(COALESCE(code,''))=? LIMIT 1", (code,)
    ).fetchone()
    if cust and not sup:
        return "customer", int(cust["id"])
    if sup and not cust:
        return "supplier", int(sup["id"])
    gt = str(group_type or "").strip().lower()
    if cust and sup:
        if gt == "asset":
            return "customer", int(cust["id"])
        if gt == "liability":
            return "supplier", int(sup["id"])
    return None, None


def sync_party_current_balance(party_type, party_id):
    """Recompute one party's current_balance from its live ledger."""
    if not party_type or not party_id:
        return
    party_type = str(party_type).strip().lower()
    if party_type == "customer":
        party, entries = get_customer_ledger(int(party_id), include_linked=True)
        if not party:
            return
        closing = float(entries[-1]["balance"]) if entries else float(party.get("opening_balance") or 0)
        with get_connection() as conn:
            conn.execute(
                "UPDATE customers SET current_balance=?, modified_at=? WHERE id=?",
                (closing, _now(), int(party_id)),
            )
    elif party_type == "supplier":
        party, entries = get_supplier_ledger(int(party_id), include_linked=True)
        if not party:
            return
        closing = float(entries[-1]["balance"]) if entries else float(party.get("opening_balance") or 0)
        with get_connection() as conn:
            conn.execute(
                "UPDATE suppliers SET current_balance=?, modified_at=? WHERE id=?",
                (closing, _now(), int(party_id)),
            )


def _is_withholding_tax_voucher(description) -> bool:
    return "HOLDING TAX ON CHQ" in str(description or "").upper()


def _party_cash_bank_receipt_rows(conn, party_kind, party_id, from_date=None, to_date=None):
    """Receipts on customer/supplier ledger — party link or matching GL account code."""
    master = "customers" if party_kind == "customer" else "suppliers"
    seen = set()
    rows = []
    for mode, tbl, date_col in (
        ("Cash", "cash_receipts", "receipt_date"),
        ("Bank", "bank_receipts", "receipt_date"),
    ):
        q = f"""
            SELECT {date_col} AS dt, document_no AS ref, amount, description, ? AS mode
            FROM {tbl}
            WHERE party_type=? AND party_id=?
        """
        params = [mode, party_kind, party_id]
        if from_date:
            q += f" AND {date_col}>=?"
            params.append(from_date)
        if to_date:
            q += f" AND {date_col}<=?"
            params.append(to_date)
        for r in conn.execute(q, params).fetchall():
            key = (r["dt"], r["ref"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(row_to_dict(r))
        q2 = f"""
            SELECT t.{date_col} AS dt, t.document_no AS ref, t.amount, t.description, ? AS mode
            FROM {tbl} t
            JOIN chart_of_accounts a ON a.id = t.party_id
            JOIN {master} p ON p.id=? AND TRIM(COALESCE(p.code,''))=TRIM(COALESCE(a.code,''))
            WHERE t.party_type='account'
        """
        params2 = [mode, party_id]
        if from_date:
            q2 += f" AND t.{date_col}>=?"
            params2.append(from_date)
        if to_date:
            q2 += f" AND t.{date_col}<=?"
            params2.append(to_date)
        for r in conn.execute(q2, params2).fetchall():
            key = (r["dt"], r["ref"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(row_to_dict(r))
    return rows


def _party_cash_bank_payment_rows(conn, party_kind, party_id, from_date=None, to_date=None):
    """Payments on customer/supplier ledger — party link or matching GL account code."""
    master = "customers" if party_kind == "customer" else "suppliers"
    seen = set()
    rows = []
    for mode, tbl, date_col in (
        ("Cash", "cash_payments", "payment_date"),
        ("Bank", "bank_payments", "payment_date"),
    ):
        q = f"""
            SELECT {date_col} AS dt, document_no AS ref, amount, description, ? AS mode
            FROM {tbl}
            WHERE party_type=? AND party_id=?
        """
        params = [mode, party_kind, party_id]
        if from_date:
            q += f" AND {date_col}>=?"
            params.append(from_date)
        if to_date:
            q += f" AND {date_col}<=?"
            params.append(to_date)
        for r in conn.execute(q, params).fetchall():
            key = (r["dt"], r["ref"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(row_to_dict(r))
        q2 = f"""
            SELECT t.{date_col} AS dt, t.document_no AS ref, t.amount, t.description, ? AS mode
            FROM {tbl} t
            JOIN chart_of_accounts a ON a.id = t.party_id
            JOIN {master} p ON p.id=? AND TRIM(COALESCE(p.code,''))=TRIM(COALESCE(a.code,''))
            WHERE t.party_type='account'
        """
        if party_kind == "supplier":
            q2 += " AND UPPER(COALESCE(t.description,'')) NOT LIKE '%HOLDING TAX ON CHQ%'"
        params2 = [mode, party_id]
        if from_date:
            q2 += f" AND t.{date_col}>=?"
            params2.append(from_date)
        if to_date:
            q2 += f" AND t.{date_col}<=?"
            params2.append(to_date)
        for r in conn.execute(q2, params2).fetchall():
            key = (r["dt"], r["ref"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(row_to_dict(r))
    return rows


def repair_party_linked_cash_bank_vouchers(conn=None):
    """Retag cash/bank vouchers posted against party GL heads as customer/supplier rows."""
    stats = {"payments": 0, "receipts": 0, "parties": set()}

    def _run(c):
        for tbl, direction in (
            ("cash_payments", "payment"),
            ("bank_payments", "payment"),
            ("cash_receipts", "receipt"),
            ("bank_receipts", "receipt"),
        ):
            rows = c.execute(
                f"""SELECT id, document_no, description, party_type, party_id
                    FROM {tbl}
                    WHERE COALESCE(party_type,'') IN ('account','')
                      AND party_id IS NOT NULL""",
            ).fetchall()
            for row in rows:
                if _is_withholding_tax_voucher(row["description"]):
                    continue
                acc = c.execute(
                    """SELECT a.id, a.code, g.group_type
                       FROM chart_of_accounts a
                       JOIN account_groups g ON g.id=a.account_group_id
                       WHERE a.id=?""",
                    (row["party_id"],),
                ).fetchone()
                if not acc:
                    continue
                pt, pid = _resolve_cash_bank_party(c, acc["id"], acc["code"], acc["group_type"])
                if not pt or not pid:
                    continue
                c.execute(
                    f"UPDATE {tbl} SET party_type=?, party_id=?, modified_at=? WHERE id=?",
                    (pt, pid, _now(), row["id"]),
                )
                key = "payments" if direction == "payment" else "receipts"
                stats[key] += 1
                stats["parties"].add((pt, int(pid)))

    if conn is None:
        with get_connection() as c:
            _run(c)
    else:
        _run(conn)
    stats["parties"] = len(stats["parties"])
    return stats


def _party_subledger_account_id(conn, party_type, party_id):
    """Chart account id when party code matches an active COA row."""
    party_type = str(party_type or "").strip().lower()
    try:
        pid = int(party_id)
    except (TypeError, ValueError):
        return None
    table = "suppliers" if party_type == "supplier" else "customers"
    row = conn.execute(f"SELECT code FROM {table} WHERE id=?", (pid,)).fetchone()
    code = str(row["code"] or "").strip() if row else ""
    if not code:
        return None
    acc = conn.execute(
        "SELECT id FROM chart_of_accounts WHERE TRIM(code)=TRIM(?) AND is_active=1",
        (code,),
    ).fetchone()
    return int(acc["id"]) if acc else None


def repair_party_subledger_gl(conn=None):
    """Move invoice/receipt GL from AR/AP control accounts to party sub-ledger heads."""
    from db_v3 import gl_account_code

    stats = {
        "purchase_invoices": 0,
        "sales_invoices": 0,
        "supplier_payments": 0,
        "customer_receipts": 0,
    }

    def _control_id(c, role):
        code = gl_account_code(role)
        row = c.execute("SELECT id FROM chart_of_accounts WHERE code=?", (code,)).fetchone()
        return int(row["id"]) if row else None

    def _run(c):
        ap_id = _control_id(c, "ap")
        ar_id = _control_id(c, "ar")
        if ap_id:
            for row in c.execute(
                "SELECT id, supplier_id FROM purchase_invoices WHERE status='approved'",
            ).fetchall():
                sub_id = _party_subledger_account_id(c, "supplier", row["supplier_id"])
                if not sub_id or sub_id == ap_id:
                    continue
                cur = c.execute(
                    """UPDATE general_ledger SET account_id=?
                       WHERE reference_type='purchase_invoice' AND reference_id=?
                         AND account_id=? AND credit > 0""",
                    (sub_id, row["id"], ap_id),
                )
                stats["purchase_invoices"] += cur.rowcount
            for row in c.execute(
                """SELECT id, reference_id AS supplier_id
                   FROM general_ledger
                   WHERE reference_type='supplier_payment' AND account_id=? AND debit > 0""",
                (ap_id,),
            ).fetchall():
                sub_id = _party_subledger_account_id(c, "supplier", row["supplier_id"])
                if not sub_id or sub_id == ap_id:
                    continue
                c.execute("UPDATE general_ledger SET account_id=? WHERE id=?", (sub_id, row["id"]))
                stats["supplier_payments"] += 1
        if ar_id:
            for row in c.execute(
                "SELECT id, customer_id FROM sales_invoices WHERE status='approved'",
            ).fetchall():
                sub_id = _party_subledger_account_id(c, "customer", row["customer_id"])
                if not sub_id or sub_id == ar_id:
                    continue
                cur = c.execute(
                    """UPDATE general_ledger SET account_id=?
                       WHERE reference_type='sales_invoice' AND reference_id=?
                         AND account_id=? AND debit > 0""",
                    (sub_id, row["id"], ar_id),
                )
                stats["sales_invoices"] += cur.rowcount
            for row in c.execute(
                """SELECT id, reference_id AS customer_id
                   FROM general_ledger
                   WHERE reference_type='customer_receipt' AND account_id=? AND credit > 0""",
                (ar_id,),
            ).fetchall():
                sub_id = _party_subledger_account_id(c, "customer", row["customer_id"])
                if not sub_id or sub_id == ar_id:
                    continue
                c.execute("UPDATE general_ledger SET account_id=? WHERE id=?", (sub_id, row["id"]))
                stats["customer_receipts"] += 1

    if conn is None:
        with get_connection() as c:
            _run(c)
    else:
        _run(conn)
    return stats


def _collect_customer_summary_movements(
    conn, customer_id, from_date=None, to_date=None, *, skip_shared_coa_jv=False,
):
    """Voucher lines for customer summary ledger (no opening row)."""
    entries = []
    q = "SELECT invoice_date AS dt, document_no AS ref, total, paid_amount FROM sales_invoices WHERE customer_id=? AND status='approved'"
    params = [customer_id]
    if from_date:
        q += " AND invoice_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND invoice_date<=?"
        params.append(to_date)
    for r in conn.execute(q, params).fetchall():
        entries.append({
            "date": r["dt"], "ref": r["ref"], "description": "Sale Invoice",
            "debit": float(r["total"] or 0), "credit": float(r["paid_amount"] or 0),
        })
    q2 = "SELECT return_date AS dt, document_no AS ref, total FROM sales_returns WHERE customer_id=?"
    params2 = [customer_id]
    if from_date:
        q2 += " AND return_date>=?"
        params2.append(from_date)
    if to_date:
        q2 += " AND return_date<=?"
        params2.append(to_date)
    for r in conn.execute(q2, params2).fetchall():
        entries.append({
            "date": r["dt"], "ref": r["ref"], "description": "Sale Return",
            "debit": 0, "credit": float(r["total"] or 0),
        })
    for r in _party_cash_bank_receipt_rows(conn, "customer", customer_id, from_date, to_date):
        desc = r["description"] or "Customer Receipt"
        if r.get("mode"):
            desc = f"{desc} ({r['mode']})"
        entries.append({
            "date": r["dt"], "ref": r["ref"], "description": desc,
            "debit": 0, "credit": float(r["amount"] or 0),
        })
    for r in _party_cash_bank_payment_rows(conn, "customer", customer_id, from_date, to_date):
        desc = r["description"] or "Customer Payment"
        if r.get("mode"):
            desc = f"{desc} ({r['mode']})"
        entries.append({
            "date": r["dt"], "ref": r["ref"], "description": desc,
            "debit": float(r["amount"] or 0), "credit": 0,
        })
    entries.extend(_fmye_party_ledger_rows(conn, "customer", customer_id, from_date, to_date))
    if not skip_shared_coa_jv:
        entries.extend(_coa_journal_party_ledger_rows(conn, "customer", customer_id, from_date, to_date))
    entries.extend(_party_transfer_ledger_rows(conn, "customer", customer_id, from_date, to_date))
    entries.extend(_expense_bill_ledger_rows(conn, "customer", customer_id, from_date, to_date))
    return entries


def _collect_supplier_summary_movements(
    conn, supplier_id, from_date=None, to_date=None, *, skip_shared_coa_jv=False,
):
    """Voucher lines for supplier summary ledger (no opening row)."""
    entries = []
    q = "SELECT invoice_date AS dt, document_no AS ref, total, paid_amount FROM purchase_invoices WHERE supplier_id=? AND status='approved'"
    params = [supplier_id]
    if from_date:
        q += " AND invoice_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND invoice_date<=?"
        params.append(to_date)
    for r in conn.execute(q, params).fetchall():
        entries.append({
            "date": r["dt"], "ref": r["ref"], "description": "Purchase Invoice",
            "debit": float(r["paid_amount"] or 0), "credit": float(r["total"] or 0),
        })
    q2 = "SELECT return_date AS dt, document_no AS ref, total FROM purchase_returns WHERE supplier_id=?"
    params2 = [supplier_id]
    if from_date:
        q2 += " AND return_date>=?"
        params2.append(from_date)
    if to_date:
        q2 += " AND return_date<=?"
        params2.append(to_date)
    for r in conn.execute(q2, params2).fetchall():
        entries.append({
            "date": r["dt"], "ref": r["ref"], "description": "Purchase Return",
            "debit": float(r["total"] or 0), "credit": 0,
        })
    for r in _party_cash_bank_payment_rows(conn, "supplier", supplier_id, from_date, to_date):
        desc = r["description"] or "Supplier Payment"
        if r.get("mode"):
            desc = f"{desc} ({r['mode']})"
        entries.append({
            "date": r["dt"], "ref": r["ref"], "description": desc,
            "debit": float(r["amount"] or 0), "credit": 0,
        })
    for r in _party_cash_bank_receipt_rows(conn, "supplier", supplier_id, from_date, to_date):
        desc = r["description"] or "Supplier Receipt"
        if r.get("mode"):
            desc = f"{desc} ({r['mode']})"
        entries.append({
            "date": r["dt"], "ref": r["ref"], "description": desc,
            "debit": 0, "credit": float(r["amount"] or 0),
        })
    entries.extend(_supplier_withholding_ledger_rows(conn, supplier_id, from_date, to_date))
    entries.extend(_fmye_party_ledger_rows(conn, "supplier", supplier_id, from_date, to_date))
    if not skip_shared_coa_jv:
        entries.extend(_coa_journal_party_ledger_rows(conn, "supplier", supplier_id, from_date, to_date))
    entries.extend(_party_transfer_ledger_rows(conn, "supplier", supplier_id, from_date, to_date))
    entries.extend(_expense_bill_ledger_rows(conn, "supplier", supplier_id, from_date, to_date))
    return entries


def _expense_bill_ledger_rows(conn, party_type, party_id, from_date=None, to_date=None):
    """Credit expense bills on party ledger (cash/bank already appear via cash/bank vouchers)."""
    if not _table_exists(conn, "expense_bills"):
        return []
    q = """SELECT bill_date AS dt, document_no AS ref, total_amount AS amount, description
           FROM expense_bills
           WHERE party_type=? AND party_id=? AND settlement='credit' AND status='posted'"""
    params = [party_type, party_id]
    if from_date:
        q += " AND bill_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND bill_date<=?"
        params.append(to_date)
    out = []
    for r in conn.execute(q, params).fetchall():
        r = row_to_dict(r)
        amt = float(r.get("amount") or 0)
        desc = r.get("description") or "Expense Bill"
        if party_type == "supplier":
            # We owe supplier — credit
            out.append({
                "date": r["dt"], "ref": r["ref"], "description": desc,
                "debit": 0, "credit": amt, "voucher_type": "EB",
            })
        else:
            # Customer credit (we owe them / reduce receivable) — credit on customer ledger
            out.append({
                "date": r["dt"], "ref": r["ref"], "description": desc,
                "debit": 0, "credit": amt, "voucher_type": "EB",
            })
    return out


def _apply_summary_movements(balance, movements, kind: str) -> float:
    """Apply sorted movements to a signed opening balance (+Dr / −Cr for customer and supplier)."""
    bal = float(balance or 0)
    rest = sorted(
        movements,
        key=lambda e: (e.get("date") or "", _summary_ledger_group(e), e.get("ref") or ""),
    )
    for e in rest:
        d = float(e.get("debit") or 0)
        c = float(e.get("credit") or 0)
        # Same as Finance Manager party ledgers: running bal += Debit − Credit
        bal += d - c
    return bal


def _party_ledger_opening_as_of(
    conn, kind: str, party_id, from_date, master_ob: float, *, skip_shared_coa_jv=False,
) -> float:
    """
    Balance brought forward as of From date.
    = master opening + all movements with date < From.
    If From is empty, returns master opening only.

    Signed convention (FMYE OpeningDr − OpeningCr): positive = Debit, negative = Credit.
    Same for customers and suppliers.
    """
    master = float(master_ob or 0)
    if not from_date:
        return master
    prior_to = _day_before(from_date)
    if kind == "supplier":
        prior = _drop_duplicate_opening_jvr(
            _collect_supplier_summary_movements(
                conn, party_id, None, prior_to, skip_shared_coa_jv=skip_shared_coa_jv,
            ),
            master,
            kind="supplier",
        )
    else:
        prior = _drop_duplicate_opening_jvr(
            _collect_customer_summary_movements(
                conn, party_id, None, prior_to, skip_shared_coa_jv=skip_shared_coa_jv,
            ),
            master,
            kind="customer",
        )
    return _apply_summary_movements(master, prior, kind)


def _ledger_period_summary(entries, opening: float, kind: str, *, balance_rows_only: bool = False) -> dict:
    """Opening, period debit/credit (exclude opening row), and closing (+Dr − Cr)."""
    opening = float(opening or 0)
    body = (entries or [])[1:] if entries else []
    if balance_rows_only:
        body = [e for e in body if e.get("balance") not in (None, "")]
    period_debit = round(sum(float(e.get("debit") or 0) for e in body), 2)
    period_credit = round(sum(float(e.get("credit") or 0) for e in body), 2)
    closing = round(opening + period_debit - period_credit, 2)
    return {
        "opening": round(opening, 2),
        "period_debit": period_debit,
        "period_credit": period_credit,
        "closing": closing,
    }


def _normalize_supplier_opening(master_ob: float) -> float:
    """Identity — supplier OB uses the same +Dr/−Cr sign as FMYE (OpeningDr − OpeningCr).

    Kept as a named helper so call sites stay readable; do not flip signs here.
    """
    return float(master_ob or 0)


def _drop_duplicate_opening_jvr(movements, master_ob: float, kind: str = "supplier"):
    """
    Some imports posted the same opening both on party.opening_balance and as a JVR.
    Keep master OB; drop one matching JVR so the opening is not doubled.
    Match on signed +Dr contribution (debit − credit ≈ master OB).
    """
    target = float(master_ob or 0)
    if abs(target) < 0.005:
        return list(movements or [])
    out = []
    dropped = False
    for e in movements or []:
        ref = (e.get("ref") or "").upper()
        vt = (e.get("voucher_type") or "").upper()
        is_jvr = vt == "JVR" or ref.startswith("JVR")
        net_dr = float(e.get("debit") or 0) - float(e.get("credit") or 0)
        match = abs(net_dr - target) < 0.02
        if not dropped and is_jvr and match:
            dropped = True
            continue
        out.append(e)
    return out


def _opening_summary_row(opening: float, from_date=None, kind: str = "customer") -> dict:
    """Opening / B/F row — positive → Debit, negative → Credit (customer and supplier)."""
    opening = float(opening or 0)
    debit = opening if opening > 0 else 0.0
    credit = abs(opening) if opening < 0 else 0.0
    return {
        "date": str(from_date)[:10] if from_date else "",
        "ref": "Opening",
        "description": "Balance B/F" if from_date else "Opening Balance",
        "debit": debit,
        "credit": credit,
    }


def net_dual_role_party_balances(conn=None):
    """Net Customer↔Supplier exposure when the same party code exists in both masters.

    Both books use signed balances (+Dr / −Cr). Dual-role net = customer + supplier.
    Returns dict:
      receivables: [{code, name, balance, credit_limit, phone, dual_role}]  # net Dr only
      payables: [{code, name, balance, phone, dual_role}]  # positive payable amount (net Cr)
      total_receivables, total_payables
    """
    EPS = 0.005

    def _run(c):
        customers = rows_to_list(c.execute(
            """SELECT id, code, name, phone, credit_limit, current_balance
               FROM customers WHERE is_active=1"""
        ).fetchall())
        suppliers = rows_to_list(c.execute(
            """SELECT id, code, name, phone, current_balance
               FROM suppliers WHERE is_active=1"""
        ).fetchall())
        sup_by_code = {}
        for s in suppliers:
            key = (s.get("code") or "").strip().upper()
            if key and key not in sup_by_code:
                sup_by_code[key] = s
        used_sup_codes = set()
        receivables = []
        payables = []

        for cust in customers:
            key = (cust.get("code") or "").strip().upper()
            cbal = float(cust.get("current_balance") or 0)
            linked = sup_by_code.get(key) if key else None
            if linked:
                used_sup_codes.add(key)
                net = cbal + float(linked.get("current_balance") or 0)
                dual = True
                name = cust.get("name") or linked.get("name")
                phone = cust.get("phone") or linked.get("phone")
            else:
                net = cbal
                dual = False
                name = cust.get("name")
                phone = cust.get("phone")
            if net > EPS:
                receivables.append({
                    "code": cust.get("code"),
                    "name": name,
                    "balance": round(net, 2),
                    "credit_limit": cust.get("credit_limit"),
                    "phone": phone or "",
                    "dual_role": dual,
                })
            elif net < -EPS:
                payables.append({
                    "code": cust.get("code") or (linked.get("code") if linked else ""),
                    "name": name,
                    "balance": round(abs(net), 2),
                    "phone": phone or "",
                    "dual_role": dual,
                })

        for sup in suppliers:
            key = (sup.get("code") or "").strip().upper()
            if key and key in used_sup_codes:
                continue
            sbal = float(sup.get("current_balance") or 0)
            if sbal < -EPS:
                payables.append({
                    "code": sup.get("code"),
                    "name": sup.get("name"),
                    "balance": round(abs(sbal), 2),
                    "phone": sup.get("phone") or "",
                    "dual_role": False,
                })

        receivables.sort(key=lambda r: r["balance"], reverse=True)
        payables.sort(key=lambda r: r["balance"], reverse=True)
        return {
            "receivables": receivables,
            "payables": payables,
            "total_receivables": round(sum(r["balance"] for r in receivables), 2),
            "total_payables": round(sum(r["balance"] for r in payables), 2),
        }

    if conn is not None:
        return _run(conn)
    with get_connection() as c:
        return _run(c)


def _linked_parties_same_code(conn, party_type, party_id) -> bool:
    """True when this party and its linked counterparty share the same account code."""
    linked = find_linked_counterparty(party_type, party_id, conn)
    if not linked:
        return False
    table = "customers" if (party_type or "").lower() == "customer" else "suppliers"
    row = conn.execute(f"SELECT code FROM {table} WHERE id=?", (party_id,)).fetchone()
    if not row:
        return False
    code = (row["code"] or "").strip().upper()
    linked_code = (linked.get("code") or linked.get("primary_code") or "").strip().upper()
    return bool(code) and code == linked_code


def find_linked_counterparty(party_type, party_id, conn=None):
    """If the same party code exists in the other master (Customer↔Supplier), return it.

    Returns dict: {party_type, id, code, name, opening_balance, current_balance} or None.
    """
    party_type = (party_type or "").lower()
    if party_type not in ("customer", "supplier") or not party_id:
        return None

    def _run(c):
        if party_type == "customer":
            row = c.execute(
                "SELECT id, code, name, opening_balance, current_balance FROM customers WHERE id=?",
                (party_id,),
            ).fetchone()
            if not row or not (row["code"] or "").strip():
                return None
            other = c.execute(
                """SELECT id, code, name, opening_balance, current_balance
                   FROM suppliers WHERE UPPER(TRIM(code))=UPPER(TRIM(?)) AND is_active=1
                   ORDER BY id LIMIT 1""",
                (row["code"],),
            ).fetchone()
            if not other:
                return None
            return {
                "party_type": "supplier",
                "id": other["id"],
                "code": other["code"],
                "name": other["name"],
                "opening_balance": float(other["opening_balance"] or 0),
                "current_balance": float(other["current_balance"] or 0),
                "primary_code": row["code"],
                "primary_name": row["name"],
            }
        row = c.execute(
            "SELECT id, code, name, opening_balance, current_balance FROM suppliers WHERE id=?",
            (party_id,),
        ).fetchone()
        if not row or not (row["code"] or "").strip():
            return None
        other = c.execute(
            """SELECT id, code, name, opening_balance, current_balance
               FROM customers WHERE UPPER(TRIM(code))=UPPER(TRIM(?)) AND is_active=1
               ORDER BY id LIMIT 1""",
            (row["code"],),
        ).fetchone()
        if not other:
            return None
        return {
            "party_type": "customer",
            "id": other["id"],
            "code": other["code"],
            "name": other["name"],
            "opening_balance": float(other["opening_balance"] or 0),
            "current_balance": float(other["current_balance"] or 0),
            "primary_code": row["code"],
            "primary_name": row["name"],
        }

    if conn is not None:
        return _run(conn)
    with get_connection() as c:
        return _run(c)


def ensure_linked_counterparty(party_type, party_id, created_by=None):
    """Ensure a matching Customer↔Supplier exists with the same party code.

    Used when purchasing from a customer or selling to a supplier: invoices still
    post to the correct master (supplier_id / customer_id). Same code means one
    **combined** party ledger (Customer + Supplier books netted).

    Returns dict: {party_type, id, code, name, created: bool, reactivated: bool}
    Raises ValueError if the source party is missing or has no code.
    """
    party_type = (party_type or "").lower()
    if party_type not in ("customer", "supplier") or not party_id:
        raise ValueError("Select a party first.")

    def _run(c):
        if party_type == "customer":
            src = c.execute(
                """SELECT id, code, name, contact_person, phone, email, address, city, group_id, is_active
                   FROM customers WHERE id=?""",
                (party_id,),
            ).fetchone()
            if not src:
                raise ValueError("Customer not found.")
            code = (src["code"] or "").strip()
            if not code:
                raise ValueError("Customer has no code — set a party code before using on Purchase.")
            other = c.execute(
                """SELECT id, code, name, is_active FROM suppliers
                   WHERE UPPER(TRIM(code))=UPPER(TRIM(?))
                   ORDER BY CASE WHEN is_active=1 THEN 0 ELSE 1 END, id LIMIT 1""",
                (code,),
            ).fetchone()
            if other:
                reactivated = False
                if not int(other["is_active"] or 0):
                    c.execute(
                        "UPDATE suppliers SET is_active=1, modified_by=?, modified_at=? WHERE id=?",
                        (created_by, _now(), other["id"]),
                    )
                    reactivated = True
                    invalidate("suppliers")
                return {
                    "party_type": "supplier",
                    "id": other["id"],
                    "code": other["code"],
                    "name": other["name"],
                    "created": False,
                    "reactivated": reactivated,
                }
            cur = c.execute(
                """INSERT INTO suppliers (code, name, contact_person, phone, email, address, city,
                   opening_balance, current_balance, group_id, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)""",
                (
                    code, src["name"], src["contact_person"], src["phone"], src["email"],
                    src["address"], src["city"], src["group_id"], created_by,
                ),
            )
            rid = cur.lastrowid
            try:
                from db_audit import log_event
                log_event(
                    "suppliers", rid, "create", user_id=created_by, module="Masters",
                    document_no=code,
                    summary=f"Auto-created supplier from customer {src['name']} (dual-role)",
                )
            except Exception:
                pass
            invalidate("suppliers")
            return {
                "party_type": "supplier",
                "id": rid,
                "code": code,
                "name": src["name"],
                "created": True,
                "reactivated": False,
            }

        src = c.execute(
            """SELECT id, code, name, contact_person, phone, email, address, city, group_id, is_active
               FROM suppliers WHERE id=?""",
            (party_id,),
        ).fetchone()
        if not src:
            raise ValueError("Supplier not found.")
        code = (src["code"] or "").strip()
        if not code:
            raise ValueError("Supplier has no code — set a party code before using on Sale.")
        other = c.execute(
            """SELECT id, code, name, is_active FROM customers
               WHERE UPPER(TRIM(code))=UPPER(TRIM(?))
               ORDER BY CASE WHEN is_active=1 THEN 0 ELSE 1 END, id LIMIT 1""",
            (code,),
        ).fetchone()
        if other:
            reactivated = False
            if not int(other["is_active"] or 0):
                c.execute(
                    "UPDATE customers SET is_active=1, modified_by=?, modified_at=? WHERE id=?",
                    (created_by, _now(), other["id"]),
                )
                reactivated = True
                invalidate("customers")
            return {
                "party_type": "customer",
                "id": other["id"],
                "code": other["code"],
                "name": other["name"],
                "created": False,
                "reactivated": reactivated,
            }
        cur = c.execute(
            """INSERT INTO customers (code, name, contact_person, phone, email, address, city, province,
               ntn, strn, credit_limit, opening_balance, current_balance, group_id, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, 0, 0, 0, ?, ?)""",
            (
                code, src["name"], src["contact_person"], src["phone"], src["email"],
                src["address"], src["city"], src["group_id"], created_by,
            ),
        )
        rid = cur.lastrowid
        try:
            from db_audit import log_event
            log_event(
                "customers", rid, "create", user_id=created_by, module="Masters",
                document_no=code,
                summary=f"Auto-created customer from supplier {src['name']} (dual-role)",
            )
        except Exception:
            pass
        invalidate("customers")
        return {
            "party_type": "customer",
            "id": rid,
            "code": code,
            "name": src["name"],
            "created": True,
            "reactivated": False,
        }

    with get_connection() as c:
        return _run(c)


def _strip_ledger_book_prefix(text: str) -> str:
    """Remove [Customer]/[Supplier] tag from combined-ledger descriptions."""
    return re.sub(r"^\[(Customer|Supplier)\]\s*", "", (text or "").strip())


def _dedupe_combined_ledger_movements(movements):
    """Drop mirror rows when the same voucher was posted to both Customer and Supplier books."""
    seen: set[tuple] = set()
    out = []
    for e in movements or []:
        key = (
            str(e.get("date") or "")[:10],
            (e.get("ref") or "").upper(),
            round(float(e.get("debit") or 0), 2),
            round(float(e.get("credit") or 0), 2),
            _strip_ledger_book_prefix(e.get("description")),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def _dedupe_combined_detailed_events(events):
    """Detailed ledger: same voucher on both books counts once."""
    out = []
    seen: set[tuple] = set()
    for e in events or []:
        if (e.get("type") or "").upper() == "OB":
            out.append(e)
            continue
        amt = e.get("amount")
        amt_key = round(float(amt), 2) if amt not in (None, "") else None
        key = (
            str(e.get("_iso") or e.get("date") or "")[:10],
            (e.get("vr_no") or "").upper(),
            round(float(e.get("debit") or 0), 2),
            round(float(e.get("credit") or 0), 2),
            _strip_ledger_book_prefix(e.get("narration")),
            amt_key,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def _tag_ledger_book(movements, book_label: str):
    """Prefix description so dual-party combined ledger shows source book."""
    out = []
    for e in movements or []:
        e = dict(e)
        desc = (e.get("description") or "").strip()
        prefix = f"[{book_label}] "
        if not desc.startswith(prefix):
            e["description"] = prefix + (desc or "—")
        e["ledger_book"] = book_label
        out.append(e)
    return out


def get_customer_ledger(customer_id, from_date=None, to_date=None, include_linked=True):
    with get_connection() as conn:
        customer = row_to_dict(conn.execute(
            "SELECT *, current_balance AS balance FROM customers WHERE id=?", (customer_id,)
        ).fetchone())
        if not customer:
            return None, []
        master_ob = float(customer.get("opening_balance") or 0)
        opening = _party_ledger_opening_as_of(conn, "customer", customer_id, from_date, master_ob)
        movements = _drop_duplicate_opening_jvr(
            _collect_customer_summary_movements(conn, customer_id, from_date, to_date),
            master_ob,
            kind="customer",
        )
        linked = find_linked_counterparty("customer", customer_id, conn) if include_linked else None
        if linked:
            same_code = _linked_parties_same_code(conn, "customer", customer_id)
            movements = _tag_ledger_book(movements, "Customer")
            supp_ob = float(linked["opening_balance"] or 0)
            supp_open = _party_ledger_opening_as_of(
                conn, "supplier", linked["id"], from_date, supp_ob,
                skip_shared_coa_jv=same_code,
            )
            # Both books use +Dr/−Cr — net party position = customer + supplier
            opening = float(opening or 0) + float(supp_open or 0)
            smov = _drop_duplicate_opening_jvr(
                _collect_supplier_summary_movements(
                    conn, linked["id"], from_date, to_date, skip_shared_coa_jv=same_code,
                ),
                supp_ob,
                kind="supplier",
            )
            movements = movements + _tag_ledger_book(smov, "Supplier")
            movements = _dedupe_combined_ledger_movements(movements)
            customer["linked_party"] = linked
            customer["ledger_mode"] = "combined"
        else:
            customer["linked_party"] = None
            customer["ledger_mode"] = "customer"

        entries = [_opening_summary_row(opening, from_date, kind="customer")]
        rest = sorted(
            movements,
            key=lambda e: (e.get("date") or "", _summary_ledger_group(e), e.get("ref") or ""),
        )
        entries = [entries[0]] + rest
        balance = opening
        entries[0]["balance"] = opening
        for e in entries[1:]:
            balance += float(e["debit"] or 0) - float(e["credit"] or 0)
            e["balance"] = balance
        customer["ledger_summary"] = _ledger_period_summary(entries, opening, "customer")
        if linked:
            customer["ledger_summary"]["note"] = (
                f"Combined with Supplier {linked['code']} — {linked['name']} "
                f"(same party code). Closing = net signed balance (+Dr / -Cr)."
            )
        return customer, entries


def get_supplier_ledger(supplier_id, from_date=None, to_date=None, include_linked=True):
    with get_connection() as conn:
        supplier = row_to_dict(conn.execute(
            "SELECT *, current_balance AS balance FROM suppliers WHERE id=?", (supplier_id,)
        ).fetchone())
        if not supplier:
            return None, []
        master_ob = float(supplier.get("opening_balance") or 0)
        opening = _party_ledger_opening_as_of(conn, "supplier", supplier_id, from_date, master_ob)
        movements = _drop_duplicate_opening_jvr(
            _collect_supplier_summary_movements(conn, supplier_id, from_date, to_date),
            master_ob,
            kind="supplier",
        )
        linked = find_linked_counterparty("supplier", supplier_id, conn) if include_linked else None
        if linked:
            same_code = _linked_parties_same_code(conn, "supplier", supplier_id)
            movements = _tag_ledger_book(movements, "Supplier")
            cust_ob = float(linked["opening_balance"] or 0)
            cust_open = _party_ledger_opening_as_of(
                conn, "customer", linked["id"], from_date, cust_ob,
                skip_shared_coa_jv=same_code,
            )
            # Both books use +Dr/−Cr — net party position = supplier + customer
            opening = float(opening or 0) + float(cust_open or 0)
            cmov = _drop_duplicate_opening_jvr(
                _collect_customer_summary_movements(
                    conn, linked["id"], from_date, to_date, skip_shared_coa_jv=same_code,
                ),
                cust_ob,
                kind="customer",
            )
            movements = movements + _tag_ledger_book(cmov, "Customer")
            movements = _dedupe_combined_ledger_movements(movements)
            supplier["linked_party"] = linked
            supplier["ledger_mode"] = "combined"
        else:
            supplier["linked_party"] = None
            supplier["ledger_mode"] = "supplier"

        entries = [_opening_summary_row(opening, from_date, kind="supplier")]
        rest = sorted(
            movements,
            key=lambda e: (e.get("date") or "", _summary_ledger_group(e), e.get("ref") or ""),
        )
        entries = [entries[0]] + rest
        balance = opening
        entries[0]["balance"] = opening
        for e in entries[1:]:
            balance += float(e["debit"] or 0) - float(e["credit"] or 0)
            e["balance"] = balance
        supplier["opening_balance"] = master_ob
        supplier["ledger_summary"] = _ledger_period_summary(entries, opening, "supplier")
        if linked:
            supplier["ledger_summary"]["note"] = (
                f"Combined with Customer {linked['code']} — {linked['name']} "
                f"(same party code). Closing = net signed balance (+Dr / -Cr)."
            )
        return supplier, entries

def _summary_ledger_group(entry) -> int:
    """0 = invoices (sales/purchases), 1 = returns, 2 = receipts/payments/JV/transfers."""
    desc = (entry.get("description") or "").strip().lower()
    ref = (entry.get("ref") or "").strip().upper()
    vt = (entry.get("voucher_type") or "").strip().upper()
    if desc in ("sale invoice", "purchase invoice") or vt in ("SAL", "PUR", "SI", "PI"):
        return 0
    if desc in ("sale return", "purchase return") or vt in ("SR", "PR"):
        return 1
    if ref.startswith(("SAL", "SI-", "PUR", "PI-")) and "return" not in desc:
        return 0
    return 2


def _detailed_ledger_group(entry) -> int:
    """0 = sale/purchase (+ lines), 1 = returns (+ lines), 2 = other vouchers."""
    if "_group" in entry:
        return int(entry["_group"])
    t = (entry.get("type") or "").strip().upper()
    if t in ("SAL", "PUR"):
        return 0
    if t in ("SR", "PR"):
        return 1
    if t in ("OB",):
        return -1
    # Invoice/return detail lines keep empty type — group stamped at append time.
    return 2


def _fmt_ledger_date(dt) -> str:
    if not dt:
        return ""
    s = str(dt)[:10]
    parts = s.split("-")
    if len(parts) == 3:
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return s


def _fmt_ledger_balance(balance, kind: str = "customer") -> str:
    if balance is None or balance == "":
        return ""
    b = float(balance)
    # Same for customer and supplier (FMYE): + = Dr, − = Cr
    side = "Dr" if b >= 0 else "Cr"
    return f"{abs(b):,.2f} {side}"


def parse_ledger_balance_display(balance, kind: str = "customer") -> float:
    """Signed balance from formatted ledger text (+Dr / −Cr for customer and supplier)."""
    if balance is None or balance == "":
        return 0.0
    if isinstance(balance, (int, float)):
        return float(balance)
    s = str(balance).strip()
    if not s:
        return 0.0
    cr = s.endswith("Cr")
    dr = s.endswith("Dr")
    num = s.replace(" Dr", "").replace(" Cr", "").replace(",", "").strip()
    val = float(num)
    if cr:
        return -val
    if dr:
        return val
    return val


def last_detailed_ledger_balance(entries, kind: str = "customer") -> float:
    for e in reversed(entries or []):
        b = e.get("balance")
        if b:
            return parse_ledger_balance_display(b, kind=kind)
    return 0.0


def _dledger_row(
    dt,
    typ,
    vr_no,
    narration,
    *,
    qty=None,
    rate=None,
    amount=None,
    debit=0,
    credit=0,
    balance_line=True,
    sort_seq=0,
    group=None,
):
    iso = str(dt or "")[:10]
    t = (typ or "").strip().upper()
    if group is None:
        if t in ("SAL", "PUR"):
            group = 0
        elif t in ("SR", "PR"):
            group = 1
        elif t in ("OB",):
            group = -1
        else:
            group = 2
    return {
        "date": _fmt_ledger_date(dt),
        "type": typ or "",
        "vr_no": vr_no or "",
        "narration": narration or "",
        "qty": qty,
        "rate": rate,
        "amount": amount,
        "debit": float(debit or 0),
        "credit": float(credit or 0),
        "balance": None,
        "_balance_line": balance_line,
        "_sort": sort_seq,
        "_iso": iso,
        "_group": group,
    }


def _detailed_ledger_finalize(party, entries, opening_balance, balance_fn, kind="customer"):
    """Sort by date; on the same day: invoices, then returns, then other vouchers."""
    opening = entries[0]
    rest = sorted(
        entries[1:],
        key=lambda e: (
            e.get("_iso") or "",
            _detailed_ledger_group(e),
            e.get("vr_no") or "",
            e.get("_sort", 0),
        ),
    )
    out = [opening]
    balance = float(opening_balance or 0)
    opening["balance"] = _fmt_ledger_balance(balance, kind=kind)
    for e in rest:
        if e.pop("_balance_line", True):
            balance = balance_fn(balance, e)
            e["balance"] = _fmt_ledger_balance(balance, kind=kind)
        else:
            e["balance"] = ""
        e.pop("_sort", None)
        e.pop("_iso", None)
        e.pop("_group", None)
        out.append(e)
    party["ledger_summary"] = _ledger_period_summary(out, opening_balance, kind, balance_rows_only=True)
    return party, out


def _tag_detailed_book(events, book_label: str, skip_ob: bool = True):
    prefix = f"[{book_label}] "
    for e in events or []:
        if skip_ob and (e.get("type") or "").upper() == "OB":
            continue
        narr = (e.get("narration") or "").strip()
        if not narr.startswith(prefix):
            e["narration"] = prefix + (narr or "—")
        e["ledger_book"] = book_label
    return events


def get_customer_ledger_detailed(customer_id, from_date=None, to_date=None, include_linked=True):
    """Customer detailed ledger — Finance Manager style columns only."""
    with get_connection() as conn:
        customer = row_to_dict(conn.execute(
            "SELECT code, name, opening_balance, current_balance AS balance FROM customers WHERE id=?",
            (customer_id,),
        ).fetchone())
        if not customer:
            return None, []
        master_ob = float(customer.get("opening_balance") or 0)
        opening = _party_ledger_opening_as_of(conn, "customer", customer_id, from_date, master_ob)
        linked = find_linked_counterparty("customer", customer_id, conn) if include_linked else None
        if linked:
            same_code = _linked_parties_same_code(conn, "customer", customer_id)
            supp_ob = float(linked["opening_balance"] or 0)
            supp_open = _party_ledger_opening_as_of(
                conn, "supplier", linked["id"], from_date, supp_ob,
                skip_shared_coa_jv=same_code,
            )
            opening = float(opening or 0) + float(supp_open or 0)
            customer["linked_party"] = linked
            customer["ledger_mode"] = "combined"
        else:
            same_code = False
            customer["linked_party"] = None
            customer["ledger_mode"] = "customer"

        events = [_dledger_row(
            from_date or "", "OB", "", "Balance B/F" if from_date else "Previous Balance",
            debit=opening if opening > 0 else 0, credit=abs(opening) if opening < 0 else 0,
            balance_line=True, sort_seq=0,
        )]
        before = len(events)
        _append_customer_invoice_detail(conn, events, customer_id, from_date, to_date)
        _append_customer_other_ledger(conn, events, customer_id, from_date, to_date, len(events))
        if linked:
            _tag_detailed_book(events[before:], "Customer")
            before_s = len(events)
            _append_supplier_invoice_detail(conn, events, linked["id"], from_date, to_date)
            _append_supplier_other_ledger(
                conn, events, linked["id"], from_date, to_date, len(events),
                skip_shared_coa_jv=same_code,
            )
            _tag_detailed_book(events[before_s:], "Supplier")
            if len(events) > 1:
                events = [events[0]] + _dedupe_combined_detailed_events(events[1:])

        if abs(master_ob) >= 0.005 and not linked:
            kept = [events[0]]
            dropped = False
            for e in events[1:]:
                ref = (e.get("vr_no") or "").upper()
                typ = (e.get("type") or "").upper()
                net_dr = float(e.get("debit") or 0) - float(e.get("credit") or 0)
                is_jvr = typ == "JVR" or ref.startswith("JVR")
                if not dropped and is_jvr and abs(net_dr - master_ob) < 0.02 and e.get("_balance_line", True):
                    dropped = True
                    continue
                kept.append(e)
            events = kept

        party, out = _detailed_ledger_finalize(
            customer, events, opening,
            lambda b, e: b + float(e.get("debit") or 0) - float(e.get("credit") or 0),
            kind="customer",
        )
        if linked:
            party["ledger_summary"]["note"] = (
                f"Combined with Supplier {linked['code']} — {linked['name']} (same party code)."
            )
        return party, out


def get_supplier_ledger_detailed(supplier_id, from_date=None, to_date=None, include_linked=True):
    """Supplier detailed ledger — Finance Manager style columns only."""
    with get_connection() as conn:
        supplier = row_to_dict(conn.execute(
            "SELECT code, name, opening_balance, current_balance AS balance FROM suppliers WHERE id=?",
            (supplier_id,),
        ).fetchone())
        if not supplier:
            return None, []
        master_ob = float(supplier.get("opening_balance") or 0)
        opening = _party_ledger_opening_as_of(conn, "supplier", supplier_id, from_date, master_ob)
        linked = find_linked_counterparty("supplier", supplier_id, conn) if include_linked else None
        if linked:
            same_code = _linked_parties_same_code(conn, "supplier", supplier_id)
            cust_ob = float(linked["opening_balance"] or 0)
            cust_open = _party_ledger_opening_as_of(
                conn, "customer", linked["id"], from_date, cust_ob,
                skip_shared_coa_jv=same_code,
            )
            opening = float(opening or 0) + float(cust_open or 0)
            supplier["linked_party"] = linked
            supplier["ledger_mode"] = "combined"
        else:
            same_code = False
            supplier["linked_party"] = None
            supplier["ledger_mode"] = "supplier"

        events = [_dledger_row(
            from_date or "", "OB", "", "Balance B/F" if from_date else "Previous Balance",
            debit=opening if opening > 0 else 0,
            credit=abs(opening) if opening < 0 else 0,
            balance_line=True, sort_seq=0,
        )]
        before = len(events)
        _append_supplier_invoice_detail(conn, events, supplier_id, from_date, to_date)
        _append_supplier_other_ledger(conn, events, supplier_id, from_date, to_date, len(events))
        if linked:
            _tag_detailed_book(events[before:], "Supplier")
            before_c = len(events)
            _append_customer_invoice_detail(conn, events, linked["id"], from_date, to_date)
            _append_customer_other_ledger(
                conn, events, linked["id"], from_date, to_date, len(events),
                skip_shared_coa_jv=same_code,
            )
            _tag_detailed_book(events[before_c:], "Customer")
            if len(events) > 1:
                events = [events[0]] + _dedupe_combined_detailed_events(events[1:])

        if abs(master_ob) >= 0.005 and not linked:
            kept = [events[0]]
            dropped = False
            for e in events[1:]:
                ref = (e.get("vr_no") or "").upper()
                typ = (e.get("type") or "").upper()
                net_dr = float(e.get("debit") or 0) - float(e.get("credit") or 0)
                is_jvr = typ == "JVR" or ref.startswith("JVR")
                if not dropped and is_jvr and abs(net_dr - master_ob) < 0.02 and e.get("_balance_line", True):
                    dropped = True
                    continue
                kept.append(e)
            events = kept
        party, out = _detailed_ledger_finalize(
            supplier, events, opening,
            lambda b, e: b + float(e.get("debit") or 0) - float(e.get("credit") or 0),
            kind="supplier",
        )
        party["opening_balance"] = master_ob
        if linked:
            party["ledger_summary"]["note"] = (
                f"Combined with Customer {linked['code']} — {linked['name']} (same party code)."
            )
        return party, out


def _append_customer_invoice_detail(conn, events, customer_id, from_date, to_date):
    seq = len(events)
    q = """SELECT id, invoice_date, document_no, subtotal, discount, tax, total, paid_amount
           FROM sales_invoices WHERE customer_id=? AND status='approved'"""
    params = [customer_id]
    if from_date:
        q += " AND invoice_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND invoice_date<=?"
        params.append(to_date)
    q += " ORDER BY invoice_date, document_no"
    for inv in conn.execute(q, params).fetchall():
        inv = row_to_dict(inv)
        doc = inv["document_no"]
        disc = float(inv.get("discount") or 0)
        tax = float(inv.get("tax") or 0)
        net = float(inv.get("total") or 0)
        paid = float(inv.get("paid_amount") or 0)
        # Short header only — Amount/Discount/Tax/Net are not merged into narration
        events.append(_dledger_row(
            inv["invoice_date"], "SAL", doc, f"Credit Sale Vide Invoice No {doc}",
            debit=net, credit=paid, balance_line=True, sort_seq=seq, group=0,
        ))
        seq += 1
        for it in conn.execute(
            """SELECT p.name AS product_name, COALESCE(u.symbol,'') AS unit,
                      si.quantity, si.rate, si.amount
               FROM sales_invoice_items si
               JOIN products p ON si.product_id=p.id
               LEFT JOIN units_of_measure u ON p.unit_id=u.id
               WHERE si.invoice_id=? ORDER BY si.id""",
            (inv["id"],),
        ).fetchall():
            it = row_to_dict(it)
            unit = (it.get("unit") or "").strip()
            item_narr = it["product_name"]
            if unit:
                item_narr = f"{item_narr} ({unit})"
            events.append(_dledger_row(
                inv["invoice_date"], "", doc, item_narr,
                qty=float(it["quantity"] or 0), rate=float(it["rate"] or 0),
                amount=float(it["amount"] or 0), balance_line=False, sort_seq=seq, group=0,
            ))
            seq += 1
        if abs(disc) >= 0.005:
            events.append(_dledger_row(
                inv["invoice_date"], "", doc, "Discount",
                amount=abs(disc), balance_line=False, sort_seq=seq, group=0,
            ))
            seq += 1
        if abs(tax) >= 0.005:
            events.append(_dledger_row(
                inv["invoice_date"], "", doc, "Sales Tax",
                amount=abs(tax), balance_line=False, sort_seq=seq, group=0,
            ))
            seq += 1

    q2 = """SELECT id, return_date, document_no, total FROM sales_returns WHERE customer_id=?"""
    params2 = [customer_id]
    if from_date:
        q2 += " AND return_date>=?"
        params2.append(from_date)
    if to_date:
        q2 += " AND return_date<=?"
        params2.append(to_date)
    q2 += " ORDER BY return_date, document_no"
    for ret in conn.execute(q2, params2).fetchall():
        ret = row_to_dict(ret)
        doc = ret["document_no"]
        net = float(ret.get("total") or 0)
        events.append(_dledger_row(
            ret["return_date"], "SR", doc,
            f"Sale Return Vide No {doc}",
            credit=net, balance_line=True, sort_seq=seq, group=1,
        ))
        seq += 1
        for it in conn.execute(
            """SELECT p.name AS product_name, COALESCE(u.symbol,'') AS unit,
                      ri.quantity, ri.rate, ri.amount
               FROM sales_return_items ri
               JOIN products p ON ri.product_id=p.id
               LEFT JOIN units_of_measure u ON p.unit_id=u.id
               WHERE ri.return_id=? ORDER BY ri.id""",
            (ret["id"],),
        ).fetchall():
            it = row_to_dict(it)
            unit = (it.get("unit") or "").strip()
            item_narr = it["product_name"]
            if unit:
                item_narr = f"{item_narr} ({unit})"
            events.append(_dledger_row(
                ret["return_date"], "", doc, item_narr,
                qty=float(it["quantity"] or 0), rate=float(it["rate"] or 0),
                amount=float(it["amount"] or 0), balance_line=False, sort_seq=seq, group=1,
            ))
            seq += 1


def _append_supplier_invoice_detail(conn, events, supplier_id, from_date, to_date):
    seq = len(events)
    q = """SELECT id, invoice_date, document_no, subtotal, discount, tax, total, paid_amount
           FROM purchase_invoices WHERE supplier_id=? AND status='approved'"""
    params = [supplier_id]
    if from_date:
        q += " AND invoice_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND invoice_date<=?"
        params.append(to_date)
    q += " ORDER BY invoice_date, document_no"
    for inv in conn.execute(q, params).fetchall():
        inv = row_to_dict(inv)
        doc = inv["document_no"]
        disc = float(inv.get("discount") or 0)
        tax = float(inv.get("tax") or 0)
        net = float(inv.get("total") or 0)
        paid = float(inv.get("paid_amount") or 0)
        events.append(_dledger_row(
            inv["invoice_date"], "PUR", doc, f"Credit Purchase Vide Invoice No {doc}",
            credit=net, debit=paid, balance_line=True, sort_seq=seq, group=0,
        ))
        seq += 1
        for it in conn.execute(
            """SELECT p.name AS product_name, COALESCE(u.symbol,'') AS unit,
                      pi.quantity, pi.rate, pi.amount
               FROM purchase_invoice_items pi
               JOIN products p ON pi.product_id=p.id
               LEFT JOIN units_of_measure u ON p.unit_id=u.id
               WHERE pi.invoice_id=? ORDER BY pi.id""",
            (inv["id"],),
        ).fetchall():
            it = row_to_dict(it)
            unit = (it.get("unit") or "").strip()
            item_narr = it["product_name"]
            if unit:
                item_narr = f"{item_narr} ({unit})"
            events.append(_dledger_row(
                inv["invoice_date"], "", doc, item_narr,
                qty=float(it["quantity"] or 0), rate=float(it["rate"] or 0),
                amount=float(it["amount"] or 0), balance_line=False, sort_seq=seq, group=0,
            ))
            seq += 1
        if abs(disc) >= 0.005:
            events.append(_dledger_row(
                inv["invoice_date"], "", doc, "Discount",
                amount=abs(disc), balance_line=False, sort_seq=seq, group=0,
            ))
            seq += 1
        if abs(tax) >= 0.005:
            events.append(_dledger_row(
                inv["invoice_date"], "", doc, "Sales Tax",
                amount=abs(tax), balance_line=False, sort_seq=seq, group=0,
            ))
            seq += 1

    q2 = """SELECT id, return_date, document_no, total FROM purchase_returns WHERE supplier_id=?"""
    params2 = [supplier_id]
    if from_date:
        q2 += " AND return_date>=?"
        params2.append(from_date)
    if to_date:
        q2 += " AND return_date<=?"
        params2.append(to_date)
    q2 += " ORDER BY return_date, document_no"
    for ret in conn.execute(q2, params2).fetchall():
        ret = row_to_dict(ret)
        doc = ret["document_no"]
        net = float(ret.get("total") or 0)
        events.append(_dledger_row(
            ret["return_date"], "PR", doc,
            f"Purchase Return Vide No {doc}",
            debit=net, balance_line=True, sort_seq=seq, group=1,
        ))
        seq += 1
        for it in conn.execute(
            """SELECT p.name AS product_name, COALESCE(u.symbol,'') AS unit,
                      ri.quantity, ri.rate, ri.amount
               FROM purchase_return_items ri
               JOIN products p ON ri.product_id=p.id
               LEFT JOIN units_of_measure u ON p.unit_id=u.id
               WHERE ri.return_id=? ORDER BY ri.id""",
            (ret["id"],),
        ).fetchall():
            it = row_to_dict(it)
            unit = (it.get("unit") or "").strip()
            item_narr = it["product_name"]
            if unit:
                item_narr = f"{item_narr} ({unit})"
            events.append(_dledger_row(
                ret["return_date"], "", doc, item_narr,
                qty=float(it["quantity"] or 0), rate=float(it["rate"] or 0),
                amount=float(it["amount"] or 0), balance_line=False, sort_seq=seq, group=1,
            ))
            seq += 1


def _append_customer_other_ledger(
    conn, events, customer_id, from_date, to_date, seq_start, *, skip_shared_coa_jv=False,
):
    seq = seq_start
    for r in _party_cash_bank_receipt_rows(conn, "customer", customer_id, from_date, to_date):
        desc = r.get("description") or "Customer Receipt"
        if r.get("mode"):
            desc = f"{desc} ({r['mode']})"
        typ = "BRV" if (r.get("mode") or "").strip().lower() == "bank" else "CRV"
        events.append(_dledger_row(
            r["dt"], typ, r["ref"], desc,
            credit=float(r.get("amount") or 0), balance_line=True, sort_seq=seq, group=2,
        ))
        seq += 1
    for r in _party_cash_bank_payment_rows(conn, "customer", customer_id, from_date, to_date):
        desc = r.get("description") or "Customer Payment"
        if r.get("mode"):
            desc = f"{desc} ({r['mode']})"
        typ = "BPV" if (r.get("mode") or "").strip().lower() == "bank" else "CPV"
        events.append(_dledger_row(
            r["dt"], typ, r["ref"], desc,
            debit=float(r.get("amount") or 0), balance_line=True, sort_seq=seq, group=2,
        ))
        seq += 1
    # SALE IN CASH (100013): cash hits Cash+Sale; FMYE party JV leftovers must not inflate AR.
    _cc = conn.execute(
        "SELECT code, name FROM customers WHERE id=?", (customer_id,)
    ).fetchone()
    _cc_code = str((_cc["code"] if _cc else "") or "").strip()
    _cc_name = str((_cc["name"] if _cc else "") or "").strip().upper()
    _skip_fmye_party = _cc_code == "100013" or _cc_name in (
        "SALE IN CASH", "CASH SALE", "CASH SALES",
    )
    if not _skip_fmye_party:
        for e in _fmye_party_ledger_rows(conn, "customer", customer_id, from_date, to_date):
            events.append(_dledger_row(
                e["date"], e.get("voucher_type") or "JVR", e.get("ref") or "", e.get("description") or "",
                debit=float(e.get("debit") or 0), credit=float(e.get("credit") or 0),
                balance_line=True, sort_seq=seq, group=2,
            ))
            seq += 1
        if not skip_shared_coa_jv:
            for e in _coa_journal_party_ledger_rows(conn, "customer", customer_id, from_date, to_date):
                events.append(_dledger_row(
                    e["date"], e.get("voucher_type") or "JV", e.get("ref") or "", e.get("description") or "",
                    debit=float(e.get("debit") or 0), credit=float(e.get("credit") or 0),
                    balance_line=True, sort_seq=seq, group=2,
                ))
                seq += 1
    for e in _party_transfer_ledger_rows(conn, "customer", customer_id, from_date, to_date):
        events.append(_dledger_row(
            e["date"], "TRF", e.get("ref") or "", e.get("description") or "",
            debit=float(e.get("debit") or 0), credit=float(e.get("credit") or 0),
            balance_line=True, sort_seq=seq, group=2,
        ))
        seq += 1
    seq = _append_expense_bill_detail(conn, events, "customer", customer_id, from_date, to_date, seq)
    return seq


def _append_supplier_other_ledger(
    conn, events, supplier_id, from_date, to_date, seq_start, *, skip_shared_coa_jv=False,
):
    seq = seq_start
    for r in _party_cash_bank_payment_rows(conn, "supplier", supplier_id, from_date, to_date):
        desc = r.get("description") or "Supplier Payment"
        if r.get("mode"):
            desc = f"{desc} ({r['mode']})"
        typ = "BPV" if (r.get("mode") or "").strip().lower() == "bank" else "CPV"
        events.append(_dledger_row(
            r["dt"], typ, r["ref"], desc,
            debit=float(r.get("amount") or 0), balance_line=True, sort_seq=seq, group=2,
        ))
        seq += 1
    for r in _party_cash_bank_receipt_rows(conn, "supplier", supplier_id, from_date, to_date):
        desc = r.get("description") or "Supplier Receipt"
        if r.get("mode"):
            desc = f"{desc} ({r['mode']})"
        typ = "BRV" if (r.get("mode") or "").strip().lower() == "bank" else "CRV"
        events.append(_dledger_row(
            r["dt"], typ, r["ref"], desc,
            credit=float(r.get("amount") or 0), balance_line=True, sort_seq=seq, group=2,
        ))
        seq += 1
    for e in _supplier_withholding_ledger_rows(conn, supplier_id, from_date, to_date):
        events.append(_dledger_row(
            e["date"], "BPV", e.get("ref") or "", e.get("description") or "Supplier W/H Tax",
            debit=float(e.get("debit") or 0), credit=float(e.get("credit") or 0),
            balance_line=True, sort_seq=seq, group=2,
        ))
        seq += 1
    for e in _fmye_party_ledger_rows(conn, "supplier", supplier_id, from_date, to_date):
        events.append(_dledger_row(
            e["date"], e.get("voucher_type") or "JVR", e.get("ref") or "", e.get("description") or "",
            debit=float(e.get("debit") or 0), credit=float(e.get("credit") or 0),
            balance_line=True, sort_seq=seq, group=2,
        ))
        seq += 1
    if not skip_shared_coa_jv:
        for e in _coa_journal_party_ledger_rows(conn, "supplier", supplier_id, from_date, to_date):
            events.append(_dledger_row(
                e["date"], e.get("voucher_type") or "JV", e.get("ref") or "", e.get("description") or "",
                debit=float(e.get("debit") or 0), credit=float(e.get("credit") or 0),
                balance_line=True, sort_seq=seq, group=2,
            ))
            seq += 1
    for e in _party_transfer_ledger_rows(conn, "supplier", supplier_id, from_date, to_date):
        events.append(_dledger_row(
            e["date"], "TRF", e.get("ref") or "", e.get("description") or "",
            debit=float(e.get("debit") or 0), credit=float(e.get("credit") or 0),
            balance_line=True, sort_seq=seq, group=2,
        ))
        seq += 1
    seq = _append_expense_bill_detail(conn, events, "supplier", supplier_id, from_date, to_date, seq)
    return seq


def _append_expense_bill_detail(conn, events, party_type, party_id, from_date, to_date, seq_start):
    """Credit expense bills: header + one line per expense head (no merged narration)."""
    if not _table_exists(conn, "expense_bills"):
        return seq_start
    seq = seq_start
    q = """SELECT id, bill_date, document_no, total_amount, description
           FROM expense_bills
           WHERE party_type=? AND party_id=? AND settlement='credit' AND status='posted'"""
    params = [party_type, party_id]
    if from_date:
        q += " AND bill_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND bill_date<=?"
        params.append(to_date)
    q += " ORDER BY bill_date, document_no"
    for bill in conn.execute(q, params).fetchall():
        bill = row_to_dict(bill)
        doc = bill["document_no"]
        amt = float(bill.get("total_amount") or 0)
        hdr = (bill.get("description") or "").strip() or f"Expense Bill {doc}"
        if party_type == "supplier":
            events.append(_dledger_row(
                bill["bill_date"], "EB", doc, hdr,
                credit=amt, balance_line=True, sort_seq=seq, group=2,
            ))
        else:
            events.append(_dledger_row(
                bill["bill_date"], "EB", doc, hdr,
                credit=amt, balance_line=True, sort_seq=seq, group=2,
            ))
        seq += 1
        for ln in conn.execute(
            """SELECT l.narration, l.amount, a.code, a.name
               FROM expense_bill_lines l
               JOIN chart_of_accounts a ON l.expense_account_id=a.id
               WHERE l.bill_id=? ORDER BY l.line_no, l.id""",
            (bill["id"],),
        ).fetchall():
            ln = row_to_dict(ln)
            narr = (ln.get("narration") or "").strip() or f"{ln.get('code')} — {ln.get('name')}"
            events.append(_dledger_row(
                bill["bill_date"], "", doc, narr,
                amount=float(ln.get("amount") or 0), balance_line=False, sort_seq=seq, group=2,
            ))
            seq += 1
    return seq


def get_stock_report(product_group_id=None, view_mode="detail"):
    from db_report_groups import summarize_product_sales, PARTY_VIEW_MASTER_GROUP

    stk = _product_stock_join("p")
    stock_col = _product_stock_sql("p")
    # Prefer warehouse weighted-average cost when present (Main WH); else purchase_price
    unit_cost = """COALESCE((
        SELECT wac.avg_cost FROM warehouse_product_avg_cost wac
        WHERE wac.product_id = p.id
        ORDER BY wac.warehouse_id LIMIT 1
    ), p.purchase_price, 0)"""
    q = f"""SELECT p.id AS product_id, p.code, p.name, pc.name AS category, u.symbol AS unit,
                   p.product_type AS item_type,
                   p.group_id, mg.code AS group_code, mg.name AS group_name,
                   {stock_col} AS stock_qty, p.purchase_price, p.sale_price,
                   ({unit_cost}) AS unit_cost,
                   ({stock_col} * ({unit_cost})) AS stock_value, p.reorder_level,
                   CASE WHEN {stock_col} <= p.reorder_level AND p.reorder_level > 0
                        THEN 'Low' ELSE 'OK' END AS status
            FROM products p
            {stk}
            LEFT JOIN product_categories pc ON p.category_id=pc.id
            LEFT JOIN units_of_measure u ON p.unit_id=u.id
            LEFT JOIN master_groups mg ON p.group_id=mg.id AND mg.entity_type='product'
            WHERE p.is_active=1"""
    p = []
    if product_group_id:
        q += " AND p.group_id=?"
        p.append(product_group_id)
    q += " ORDER BY p.code, p.name"
    with get_connection() as conn:
        rows = rows_to_list(conn.execute(q, p).fetchall())
    if view_mode != PARTY_VIEW_MASTER_GROUP:
        return rows
    return summarize_product_sales(
        [{"code": r["code"], "name": r["name"], "group_id": r.get("group_id"),
          "group_code": r.get("group_code"), "group_name": r.get("group_name"),
          "qty": r.get("stock_qty"), "amount": r.get("stock_value")} for r in rows],
        view_mode,
    )


def get_stock_report_group_wise(product_group_id=None):
    """Stock totals rolled up by product master group."""
    rows = get_stock_report(product_group_id=product_group_id, view_mode="detail")
    buckets: dict[str, dict] = {}
    for r in rows:
        gid = r.get("group_id")
        key = f"g{gid}" if gid else "_none"
        if key not in buckets:
            buckets[key] = {
                "group_code": r.get("group_code") or "—",
                "group_name": r.get("group_name") or "Unassigned",
                "items": 0,
                "stock_qty": 0.0,
                "stock_value": 0.0,
                "low_items": 0,
            }
        b = buckets[key]
        b["items"] += 1
        b["stock_qty"] = round(b["stock_qty"] + float(r.get("stock_qty") or 0), 4)
        b["stock_value"] = round(b["stock_value"] + float(r.get("stock_value") or 0), 2)
        if (r.get("status") or "") == "Low":
            b["low_items"] += 1
    out = list(buckets.values())
    out.sort(key=lambda x: (x["group_code"] == "—", x["group_code"] or "", x["group_name"] or ""))
    return out


def get_stock_report_bom_wise(*, composition_type=None, status: str = "approved"):
    """Stock for finished goods and their BOM components, grouped by composition.

    One row per finished product + each raw/component line on the latest matching BOM.
    """
    stk = _product_stock_join("p")
    stock_col = _product_stock_sql("p")
    unit_cost = """COALESCE((
        SELECT wac.avg_cost FROM warehouse_product_avg_cost wac
        WHERE wac.product_id = p.id
        ORDER BY wac.warehouse_id LIMIT 1
    ), p.purchase_price, 0)"""

    with get_connection() as conn:
        bom_q = """
            SELECT b.id AS bom_id, b.document_no AS bom_no, b.version_no, b.status,
                   COALESCE(b.composition_type, 'other') AS composition_type,
                   b.finished_product_id,
                   fp.code AS finished_code, fp.name AS finished_name
            FROM bom_formulas b
            JOIN products fp ON fp.id = b.finished_product_id
            WHERE fp.is_active=1
        """
        params: list = []
        if status and status != "All":
            bom_q += " AND b.status=?"
            params.append(status)
        if composition_type and composition_type not in ("All", "", None):
            bom_q += " AND COALESCE(b.composition_type,'other')=?"
            params.append(composition_type)
        bom_q += " ORDER BY fp.code, b.version_no DESC, b.id DESC"
        boms = rows_to_list(conn.execute(bom_q, params).fetchall())

        # Keep latest BOM per finished product
        seen_fp = set()
        selected = []
        for b in boms:
            fpid = int(b["finished_product_id"])
            if fpid in seen_fp:
                continue
            seen_fp.add(fpid)
            selected.append(b)

        out = []
        for b in selected:
            # Finished product stock
            fg = row_to_dict(conn.execute(
                f"""SELECT p.code, p.name, u.symbol AS unit,
                           {stock_col} AS stock_qty,
                           ({unit_cost}) AS unit_cost,
                           ({stock_col} * ({unit_cost})) AS stock_value
                    FROM products p
                    {stk}
                    LEFT JOIN units_of_measure u ON p.unit_id=u.id
                    WHERE p.id=?""",
                (b["finished_product_id"],),
            ).fetchone()) or {}
            out.append({
                "bom_no": b.get("bom_no") or "",
                "version": b.get("version_no") or "",
                "composition_type": b.get("composition_type") or "other",
                "finished_code": b.get("finished_code") or "",
                "finished_name": b.get("finished_name") or "",
                "role": "Finished",
                "code": fg.get("code") or b.get("finished_code") or "",
                "name": fg.get("name") or b.get("finished_name") or "",
                "bom_qty": 1.0,
                "unit": fg.get("unit") or "",
                "stock_qty": float(fg.get("stock_qty") or 0),
                "unit_cost": float(fg.get("unit_cost") or 0),
                "stock_value": float(fg.get("stock_value") or 0),
            })
            lines = rows_to_list(conn.execute(
                f"""SELECT bl.quantity AS bom_qty, p.code, p.name, u.symbol AS unit,
                           {stock_col} AS stock_qty,
                           ({unit_cost}) AS unit_cost,
                           ({stock_col} * ({unit_cost})) AS stock_value
                    FROM bom_formula_lines bl
                    JOIN products p ON p.id = bl.raw_product_id
                    {stk}
                    LEFT JOIN units_of_measure u ON COALESCE(bl.unit_id, p.unit_id)=u.id
                    WHERE bl.bom_id=?
                    ORDER BY bl.id""",
                (b["bom_id"],),
            ).fetchall())
            for ln in lines:
                out.append({
                    "bom_no": b.get("bom_no") or "",
                    "version": b.get("version_no") or "",
                    "composition_type": b.get("composition_type") or "other",
                    "finished_code": b.get("finished_code") or "",
                    "finished_name": b.get("finished_name") or "",
                    "role": "Component",
                    "code": ln.get("code") or "",
                    "name": ln.get("name") or "",
                    "bom_qty": float(ln.get("bom_qty") or 0),
                    "unit": ln.get("unit") or "",
                    "stock_qty": float(ln.get("stock_qty") or 0),
                    "unit_cost": float(ln.get("unit_cost") or 0),
                    "stock_value": float(ln.get("stock_value") or 0),
                })
        return out


def get_profit_loss(from_date=None, to_date=None):
    with get_connection() as conn:
        def _sum(table, date_col):
            q = f"SELECT COALESCE(SUM(total),0) FROM {table} WHERE 1=1"
            p = []
            if from_date:
                q += f" AND {date_col}>=?"; p.append(from_date)
            if to_date:
                q += f" AND {date_col}<=?"; p.append(to_date)
            return conn.execute(q, p).fetchone()[0]

        gross_sales = _sum("sales_invoices", "invoice_date")
        sale_returns = _sum("sales_returns", "return_date")
        net_sales = gross_sales - sale_returns
        gross_purchases = _sum("purchase_invoices", "invoice_date")
        purchase_returns = _sum("purchase_returns", "return_date")
        net_purchases = gross_purchases - purchase_returns

        def _gl_debit(code_prefix):
            q = """SELECT COALESCE(SUM(gl.debit),0) FROM general_ledger gl
                   JOIN chart_of_accounts a ON gl.account_id=a.id WHERE a.code LIKE ?"""
            p = [f"{code_prefix}%"]
            if from_date:
                q += " AND gl.entry_date>=?"; p.append(from_date)
            if to_date:
                q += " AND gl.entry_date<=?"; p.append(to_date)
            row = conn.execute(q, p).fetchone()
            return row[0] if row else 0

        cogs = _gl_debit("5000")
        if cogs == 0:
            cogs = net_purchases

        operating_expenses = _gl_debit("6100") + _gl_debit("5200") + _gl_debit("5300")

        gross_profit = net_sales - cogs
        net_profit = gross_profit - operating_expenses

        return {
            "gross_sales": gross_sales, "sale_returns": sale_returns, "net_sales": net_sales,
            "gross_purchases": gross_purchases, "purchase_returns": purchase_returns,
            "net_purchases": net_purchases, "cogs": cogs,
            "operating_expenses": operating_expenses,
            "gross_profit": gross_profit, "net_profit": net_profit,
        }


# --- Master data accessors (new tables) ---
def get_product_categories(active_only=True):
    q = "SELECT * FROM product_categories"
    if active_only:
        q += " WHERE is_active=1"
    q += " ORDER BY name"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q).fetchall())


def get_units_of_measure(active_only=True):
    q = "SELECT * FROM units_of_measure"
    if active_only:
        q += " WHERE is_active=1"
    q += " ORDER BY name"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q).fetchall())


def get_warehouses(active_only=True):
    q = "SELECT * FROM warehouses"
    if active_only:
        q += " WHERE is_active=1"
    q += " ORDER BY name"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q).fetchall())


def get_employees(active_only=True):
    q = "SELECT * FROM employees"
    if active_only:
        q += " WHERE is_active=1"
    q += " ORDER BY full_name"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q).fetchall())


def get_account_groups():
    with get_connection() as conn:
        return rows_to_list(conn.execute("SELECT * FROM account_groups ORDER BY code").fetchall())


def get_schema_info():
    with get_connection() as conn:
        version = _get_schema_version(conn)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()]
        return {"schema_version": version, "tables": tables}


# Re-export v3 API
from db_v3 import *  # noqa: F401,F403,E402
from db_holidays import *  # noqa: F401,F403,E402
from db_invoice_workflow import *  # noqa: F401,F403,E402
from db_hr import *  # noqa: F401,F403,E402
from db_commercial import *  # noqa: F401,F403,E402
from db_job_cards import *  # noqa: F401,F403,E402
from db_stock_costing import (  # noqa: F401,E402
    apply_stock_costing,
    cancel_stock_revaluation,
    classify_product_types,
    find_same_day_production_duplicates,
    get_stock_revaluation,
    get_stock_revaluations,
    post_daily_production,
    post_stock_revaluation,
    preview_revaluation_lines,
    refresh_bom_costs,
    save_stock_revaluation,
)
from db_audit import log_event, search_audit_log  # noqa: F401,F403,E402
from product_rates_legacy import (  # noqa: F401,E402
    clear_rate_cache,
    resolve_product_rate,
    sync_missing_product_rates,
)
from db_cash_day import (  # noqa: F401,E402
    assert_cash_day_open,
    assert_cash_day_open_for_invoice,
    close_cash_day,
    get_cash_day_close,
    is_cash_day_closed,
    list_closed_cash_days,
    reopen_cash_day,
)
from db_groups import (  # noqa: F401,E402
    add_master_group,
    assign_entities_to_group,
    assign_entity_to_group,
    delete_master_group,
    get_entities_for_group_add,
    get_group_members,
    get_master_group,
    get_master_groups,
    group_options,
    remove_entities_from_group,
    remove_entity_from_group,
    resolve_entity_ids_by_codes,
    update_master_group,
)
