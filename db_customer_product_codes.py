"""Customer / toll / 3rd-party product codes for delivery challan (gate pass) print."""

from __future__ import annotations


def apply_customer_product_codes(conn, db_module=None):
    """Idempotent schema for per-customer item codes."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_product_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            customer_code TEXT NOT NULL,
            notes TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            modified_at TEXT,
            UNIQUE(customer_id, product_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cpc_customer
        ON customer_product_codes(customer_id, is_active)
        """
    )
    # Optional default: print their codes on gate pass / delivery challan
    cols = [r[1] for r in conn.execute("PRAGMA table_info(customers)").fetchall()]
    if "print_party_item_code" not in cols:
        conn.execute(
            "ALTER TABLE customers ADD COLUMN print_party_item_code INTEGER DEFAULT 0"
        )


def list_customer_product_codes(customer_id, active_only=True):
    from database import get_connection, rows_to_list

    q = """
        SELECT cpc.*, p.code AS ifs_code, p.name AS product_name
        FROM customer_product_codes cpc
        JOIN products p ON p.id = cpc.product_id
        WHERE cpc.customer_id=?
    """
    params = [int(customer_id)]
    if active_only:
        q += " AND COALESCE(cpc.is_active,1)=1"
    q += " ORDER BY p.code"
    with get_connection() as conn:
        apply_customer_product_codes(conn)
        return rows_to_list(conn.execute(q, params).fetchall())


def map_customer_product_codes(customer_id):
    """product_id → customer_code for print."""
    return {
        int(r["product_id"]): (r.get("customer_code") or "").strip()
        for r in list_customer_product_codes(customer_id, active_only=True)
        if r.get("product_id") and (r.get("customer_code") or "").strip()
    }


def upsert_customer_product_code(customer_id, product_id, customer_code, notes=None, user_id=None):
    from database import get_connection

    code = (customer_code or "").strip()
    if not code:
        raise ValueError("Customer product code is required.")
    with get_connection() as conn:
        apply_customer_product_codes(conn)
        conn.execute(
            """
            INSERT INTO customer_product_codes(
                customer_id, product_id, customer_code, notes, is_active, modified_at
            ) VALUES (?,?,?,?,1,datetime('now','localtime'))
            ON CONFLICT(customer_id, product_id) DO UPDATE SET
                customer_code=excluded.customer_code,
                notes=excluded.notes,
                is_active=1,
                modified_at=datetime('now','localtime')
            """,
            (int(customer_id), int(product_id), code, (notes or "").strip() or None),
        )
        return conn.execute(
            "SELECT id FROM customer_product_codes WHERE customer_id=? AND product_id=?",
            (int(customer_id), int(product_id)),
        ).fetchone()[0]


def delete_customer_product_code(row_id):
    from database import get_connection

    with get_connection() as conn:
        apply_customer_product_codes(conn)
        conn.execute("DELETE FROM customer_product_codes WHERE id=?", (int(row_id),))


def customer_wants_party_item_code_print(customer_id) -> bool:
    from database import get_connection, row_to_dict

    if not customer_id:
        return False
    with get_connection() as conn:
        apply_customer_product_codes(conn)
        row = row_to_dict(
            conn.execute(
                "SELECT print_party_item_code FROM customers WHERE id=?",
                (int(customer_id),),
            ).fetchone()
        )
    return bool(int((row or {}).get("print_party_item_code") or 0))
