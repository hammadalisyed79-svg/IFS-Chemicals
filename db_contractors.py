"""Contract labour — payment types and product assignments for contractors."""

from __future__ import annotations

PAYMENT_PRODUCTION_QTY = "production_qty"
PAYMENT_SKU_CARTON = "sku_carton"

PAYMENT_TYPES = {
    PAYMENT_PRODUCTION_QTY: "Production quantity (qty x rate per SKU)",
    PAYMENT_SKU_CARTON: "SKU / cartons x rate per SKU",
}


def _table_exists(conn, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,),
        ).fetchone()
    )


def apply_contract_labour(conn, db_module=None):
    """Create contractor tables (idempotent)."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS contract_labourers (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id     INTEGER NOT NULL UNIQUE REFERENCES suppliers(id),
            payment_type    TEXT NOT NULL
                CHECK(payment_type IN ('production_qty','sku_carton')),
            default_rate    REAL DEFAULT 0,
            notes           TEXT,
            is_active       INTEGER DEFAULT 1,
            created_by      INTEGER REFERENCES users(id),
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            modified_by     INTEGER REFERENCES users(id),
            modified_at     TEXT
        );
        CREATE TABLE IF NOT EXISTS contract_labour_products (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contractor_id   INTEGER NOT NULL REFERENCES contract_labourers(id) ON DELETE CASCADE,
            product_id      INTEGER NOT NULL REFERENCES products(id),
            rate            REAL,
            sort_order      INTEGER DEFAULT 0,
            UNIQUE(contractor_id, product_id)
        );
        CREATE INDEX IF NOT EXISTS idx_cl_supplier ON contract_labourers(supplier_id);
        CREATE INDEX IF NOT EXISTS idx_cl_type ON contract_labourers(payment_type);
        CREATE INDEX IF NOT EXISTS idx_cl_products_c ON contract_labour_products(contractor_id);
        CREATE INDEX IF NOT EXISTS idx_cl_products_p ON contract_labour_products(product_id);
        """
    )


def list_contractors(active_only: bool = True, payment_type: str | None = None):
    from database import get_connection, rows_to_list

    q = """SELECT cl.*, s.code AS supplier_code, s.name AS supplier_name,
                  (SELECT COUNT(*) FROM contract_labour_products cp WHERE cp.contractor_id=cl.id) AS product_count
           FROM contract_labourers cl
           JOIN suppliers s ON s.id=cl.supplier_id
           WHERE 1=1"""
    p: list = []
    if active_only:
        q += " AND cl.is_active=1"
    if payment_type:
        q += " AND cl.payment_type=?"
        p.append(payment_type)
    q += " ORDER BY s.name"
    with get_connection() as conn:
        apply_contract_labour(conn)
        return rows_to_list(conn.execute(q, p).fetchall())


def get_contractor(contractor_id: int):
    from database import get_connection, row_to_dict, rows_to_list

    with get_connection() as conn:
        apply_contract_labour(conn)
        h = row_to_dict(conn.execute(
            """SELECT cl.*, s.code AS supplier_code, s.name AS supplier_name
               FROM contract_labourers cl
               JOIN suppliers s ON s.id=cl.supplier_id
               WHERE cl.id=?""",
            (contractor_id,),
        ).fetchone())
        if not h:
            return None
        h["products"] = rows_to_list(conn.execute(
            """SELECT cp.*, p.code AS product_code, p.name AS product_name
               FROM contract_labour_products cp
               JOIN products p ON p.id=cp.product_id
               WHERE cp.contractor_id=?
               ORDER BY cp.sort_order, p.code""",
            (contractor_id,),
        ).fetchall())
        return h


def add_contractor(data: dict, user_id=None) -> int:
    from database import get_connection, _now

    payment_type = (data.get("payment_type") or "").strip()
    if payment_type not in PAYMENT_TYPES:
        raise ValueError("Select a valid payment type.")
    supplier_id = int(data.get("supplier_id") or 0)
    if not supplier_id:
        raise ValueError("Select a contractor (supplier).")
    with get_connection() as conn:
        apply_contract_labour(conn)
        exists = conn.execute(
            "SELECT id FROM contract_labourers WHERE supplier_id=?", (supplier_id,),
        ).fetchone()
        if exists:
            raise ValueError("This supplier is already set up as a contract labourer.")
        cur = conn.execute(
            """INSERT INTO contract_labourers(
                   supplier_id, payment_type, default_rate, notes, is_active, created_by, created_at
               ) VALUES(?,?,?,?,1,?,?)""",
            (
                supplier_id, payment_type,
                float(data.get("default_rate") or 0),
                (data.get("notes") or "").strip() or None,
                user_id, _now(),
            ),
        )
        return int(cur.lastrowid)


def update_contractor(contractor_id: int, data: dict, user_id=None):
    from database import get_connection, _now

    payment_type = (data.get("payment_type") or "").strip()
    if payment_type not in PAYMENT_TYPES:
        raise ValueError("Select a valid payment type.")
    with get_connection() as conn:
        apply_contract_labour(conn)
        row = conn.execute(
            "SELECT id FROM contract_labourers WHERE id=?", (contractor_id,),
        ).fetchone()
        if not row:
            raise ValueError("Contractor not found.")
        conn.execute(
            """UPDATE contract_labourers SET payment_type=?, default_rate=?, notes=?,
                   is_active=?, modified_by=?, modified_at=? WHERE id=?""",
            (
                payment_type,
                float(data.get("default_rate") or 0),
                (data.get("notes") or "").strip() or None,
                int(data.get("is_active", 1)),
                user_id, _now(), contractor_id,
            ),
        )


def delete_contractor(contractor_id: int):
    from database import get_connection

    with get_connection() as conn:
        apply_contract_labour(conn)
        conn.execute("DELETE FROM contract_labour_products WHERE contractor_id=?", (contractor_id,))
        conn.execute("DELETE FROM contract_labourers WHERE id=?", (contractor_id,))


def get_contractor_product_ids(contractor_id: int) -> list[int]:
    c = get_contractor(contractor_id)
    if not c:
        return []
    return [int(p["product_id"]) for p in (c.get("products") or [])]


def get_contractor_product_rates(contractor_id: int) -> dict[int, float]:
    """product_id → rate for saved assignments."""
    c = get_contractor(contractor_id)
    if not c:
        return {}
    default_rate = float(c.get("default_rate") or 0)
    out = {}
    for p in c.get("products") or []:
        pid = int(p["product_id"])
        out[pid] = float(p["rate"] if p.get("rate") is not None else default_rate)
    return out


def product_ids_by_code_prefix(prefix: str, *, active_only: bool = True) -> list[dict]:
    """Active products whose code starts with prefix (case-insensitive), e.g. DW → Dish Wash."""
    from database import get_connection, rows_to_list

    pref = (prefix or "").strip().upper()
    if not pref:
        return []
    q = """SELECT id, code, name FROM products
           WHERE UPPER(TRIM(code)) LIKE ?
           {active}
           ORDER BY code""".format(
        active="AND COALESCE(is_active,1)=1" if active_only else "",
    )
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, (f"{pref}%",)).fetchall())


# Common finished-goods code families for bulk assign shortcuts
BULK_PREFIX_HINTS = (
    ("DW", "Dish Wash (DW*)"),
    ("DP", "Detergent Powder (DP*)"),
    ("LQ", "Liquid (LQ*)"),
)


def save_contractor_products(
    contractor_id: int,
    product_ids: list[int],
    *,
    rates: dict | None = None,
    user_id=None,
) -> int:
    """Replace product assignment for a contractor (remember selection)."""
    from database import get_connection, _now

    rates = rates or {}
    ids = []
    seen = set()
    for raw in product_ids or []:
        try:
            pid = int(raw)
        except (TypeError, ValueError):
            continue
        if pid and pid not in seen:
            seen.add(pid)
            ids.append(pid)

    with get_connection() as conn:
        apply_contract_labour(conn)
        cl = conn.execute(
            "SELECT id, default_rate FROM contract_labourers WHERE id=?", (contractor_id,),
        ).fetchone()
        if not cl:
            raise ValueError("Contractor not found.")
        default_rate = float(cl["default_rate"] or 0)
        for pid in ids:
            if not conn.execute("SELECT id FROM products WHERE id=?", (pid,)).fetchone():
                raise ValueError(f"Product id {pid} not found.")
        conn.execute(
            "DELETE FROM contract_labour_products WHERE contractor_id=?", (contractor_id,),
        )
        for i, pid in enumerate(ids):
            rate = rates.get(pid)
            if rate is None:
                rate = rates.get(str(pid))
            if rate is None or rate == "":
                rate = default_rate
            conn.execute(
                """INSERT INTO contract_labour_products(contractor_id, product_id, rate, sort_order)
                   VALUES(?,?,?,?)""",
                (contractor_id, pid, float(rate or 0), i),
            )
        conn.execute(
            "UPDATE contract_labourers SET modified_by=?, modified_at=? WHERE id=?",
            (user_id, _now(), contractor_id),
        )
    return len(ids)


def clear_contractor_products(contractor_id: int, user_id=None) -> int:
    """Discard all product assignments for a contractor."""
    return save_contractor_products(contractor_id, [], user_id=user_id)


def production_qty_for_products(product_ids: list[int], from_date: str, to_date: str) -> list[dict]:
    """Completed production qty by finished product in date range."""
    from database import get_connection, rows_to_list

    ids = [int(p) for p in (product_ids or []) if p]
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    q = f"""
        SELECT p.id AS product_id, p.code AS product_code, p.name AS product_name,
               COUNT(po.id) AS batch_count,
               COALESCE(SUM(po.actual_qty), 0) AS quantity
        FROM products p
        LEFT JOIN production_orders po
          ON po.finished_product_id=p.id
         AND LOWER(COALESCE(po.status,''))='completed'
         AND po.order_date >= ? AND po.order_date <= ?
        WHERE p.id IN ({placeholders})
        GROUP BY p.id
        ORDER BY p.code
    """
    params = [from_date, to_date, *ids]
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, params).fetchall())


def sold_qty_for_products(product_ids: list[int], from_date: str, to_date: str) -> dict[int, float]:
    """Approved sales invoice qty by product in date range."""
    from database import get_connection

    ids = [int(p) for p in (product_ids or []) if p]
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    q = f"""
        SELECT si.product_id, COALESCE(SUM(si.quantity), 0) AS sold_qty
        FROM sales_invoice_items si
        JOIN sales_invoices s ON si.invoice_id = s.id
        WHERE si.product_id IN ({placeholders})
          AND COALESCE(s.status, 'approved') = 'approved'
          AND s.invoice_date >= ? AND s.invoice_date <= ?
        GROUP BY si.product_id
    """
    with get_connection() as conn:
        rows = conn.execute(q, [*ids, from_date, to_date]).fetchall()
    return {int(r["product_id"]): float(r["sold_qty"] or 0) for r in rows}


def sale_return_qty_for_products(
    product_ids: list[int], from_date: str, to_date: str,
) -> dict[int, float]:
    """Sale return qty by product in date range (excludes pending/rejected)."""
    from database import get_connection

    ids = [int(p) for p in (product_ids or []) if p]
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    q = f"""
        SELECT sri.product_id, COALESCE(SUM(sri.quantity), 0) AS return_qty
        FROM sales_return_items sri
        JOIN sales_returns sr ON sri.return_id = sr.id
        WHERE sri.product_id IN ({placeholders})
          AND sr.return_date >= ? AND sr.return_date <= ?
          AND LOWER(COALESCE(sr.approval_status, '')) NOT IN
              ('pending', 'rejected', 'cancelled')
        GROUP BY sri.product_id
    """
    with get_connection() as conn:
        rows = conn.execute(q, [*ids, from_date, to_date]).fetchall()
    return {int(r["product_id"]): float(r["return_qty"] or 0) for r in rows}


def stock_on_hand_for_products(
    product_ids: list[int], *, as_of_date: str | None = None,
) -> dict[int, float]:
    """Stock in hand by product (all warehouses).

    When as_of_date is set, returns opening qty at the start of that date:
    current warehouse_stock minus net inventory movements on/after as_of_date.
    """
    from database import get_connection

    ids = [int(p) for p in (product_ids or []) if p]
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT product_id, COALESCE(SUM(quantity), 0) AS stock_qty
            FROM warehouse_stock
            WHERE product_id IN ({placeholders})
            GROUP BY product_id
            """,
            ids,
        ).fetchall()
        current = {int(r["product_id"]): float(r["stock_qty"] or 0) for r in rows}
        if not as_of_date or not _table_exists(conn, "inventory_movements"):
            return current
        mv_rows = conn.execute(
            f"""
            SELECT product_id,
                   COALESCE(SUM(
                       CASE
                         WHEN LOWER(COALESCE(movement_type, '')) = 'in'
                           THEN quantity
                         WHEN LOWER(COALESCE(movement_type, '')) = 'out'
                           THEN -quantity
                         ELSE 0
                       END
                   ), 0) AS net_since
            FROM inventory_movements
            WHERE product_id IN ({placeholders})
              AND movement_date >= ?
            GROUP BY product_id
            """,
            [*ids, as_of_date],
        ).fetchall()
        net_since = {
            int(r["product_id"]): float(r["net_since"] or 0) for r in mv_rows
        }
    all_pids = set(ids) | set(current) | set(net_since)
    return {
        pid: round(current.get(pid, 0.0) - net_since.get(pid, 0.0), 4)
        for pid in all_pids
    }


def calculate_contractor_month(
    contractor_id: int,
    from_date: str,
    to_date: str,
    *,
    manual_qty: dict | None = None,
) -> dict:
    """Payment worksheet lines for the period.

    Sold Qty = approved sales in period
    Stock in hand = opening qty as of From date
    Sale return = returns in period
    Physical Manual Added Stock = user-entered manual qty
    Closing Stock = Sold - Opening - Sale return + Physical Manual
    Billable (Answer) = Sold + Opening + Physical Manual
    Amount = Answer x Rate
    Gross = sum of amounts

    For production_qty contractors, production qty is also returned (info);
    billable still follows Sold + Opening + Manual so SKU payment is consistent.
    """
    c = get_contractor(contractor_id)
    if not c:
        raise ValueError("Contractor not found.")
    products = c.get("products") or []
    pids = [int(p["product_id"]) for p in products]
    sold_map = sold_qty_for_products(pids, from_date, to_date)
    return_map = sale_return_qty_for_products(pids, from_date, to_date)
    stock_map = stock_on_hand_for_products(pids, as_of_date=from_date)
    prod_map = {
        int(r["product_id"]): r
        for r in production_qty_for_products(pids, from_date, to_date)
    }
    manual = {}
    for k, v in (manual_qty or {}).items():
        try:
            manual[int(k)] = float(v or 0)
        except (TypeError, ValueError):
            continue

    default_rate = float(c.get("default_rate") or 0)
    lines = []
    total = 0.0
    total_sold = total_stock = total_return = total_manual = total_closing = total_answer = 0.0
    for p in products:
        pid = int(p["product_id"])
        sold = round(float(sold_map.get(pid) or 0), 4)
        stock = round(float(stock_map.get(pid) or 0), 4)
        ret = round(float(return_map.get(pid) or 0), 4)
        man = round(float(manual.get(pid) or 0), 4)
        closing = round(sold - stock - ret + man, 4)
        answer = round(sold + stock + man, 4)
        rate = float(p["rate"] if p.get("rate") is not None else default_rate)
        amount = round(answer * rate, 2)
        qinfo = prod_map.get(pid) or {}
        total += amount
        total_sold += sold
        total_stock += stock
        total_return += ret
        total_manual += man
        total_closing += closing
        total_answer += answer
        lines.append({
            "product_id": pid,
            "product_code": p.get("product_code"),
            "product_name": p.get("product_name"),
            "sold_qty": sold,
            "stock_qty": stock,
            "sale_return_qty": ret,
            "manual_qty": man,
            "closing_stock": closing,
            "answer_qty": answer,
            "batch_count": int(qinfo.get("batch_count") or 0),
            "production_qty": float(qinfo.get("quantity") or 0),
            "quantity": answer,  # billable
            "rate": rate,
            "amount": amount,
        })
    return {
        "contractor": c,
        "from_date": from_date,
        "to_date": to_date,
        "payment_type": c.get("payment_type"),
        "payment_type_label": PAYMENT_TYPES.get(c.get("payment_type"), c.get("payment_type")),
        "formula": (
            "Closing = Sold - Opening - Sale return + Physical Manual; "
            "Answer = Sold + Opening + Physical Manual; Amount = Answer x Rate"
        ),
        "lines": lines,
        "total": round(total, 2),
        "totals": {
            "sold_qty": round(total_sold, 4),
            "stock_qty": round(total_stock, 4),
            "sale_return_qty": round(total_return, 4),
            "manual_qty": round(total_manual, 4),
            "closing_stock": round(total_closing, 4),
            "answer_qty": round(total_answer, 4),
            "gross_amount": round(total, 2),
            "item_count": len(lines),
        },
    }
