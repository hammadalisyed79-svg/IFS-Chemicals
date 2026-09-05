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
        CREATE TABLE IF NOT EXISTS contract_labour_month_runs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contractor_id   INTEGER NOT NULL REFERENCES contract_labourers(id) ON DELETE CASCADE,
            year_month      TEXT NOT NULL,
            from_date       TEXT NOT NULL,
            to_date         TEXT NOT NULL,
            gross_amount    REAL DEFAULT 0,
            closing_qty     REAL DEFAULT 0,
            notes           TEXT,
            created_by      INTEGER REFERENCES users(id),
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            modified_by     INTEGER REFERENCES users(id),
            modified_at     TEXT,
            UNIQUE(contractor_id, year_month)
        );
        CREATE TABLE IF NOT EXISTS contract_labour_month_lines (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id          INTEGER NOT NULL
                REFERENCES contract_labour_month_runs(id) ON DELETE CASCADE,
            product_id      INTEGER NOT NULL REFERENCES products(id),
            product_code    TEXT,
            product_name    TEXT,
            sold_qty        REAL DEFAULT 0,
            stock_qty       REAL DEFAULT 0,
            sale_return_qty REAL DEFAULT 0,
            manual_qty      REAL DEFAULT 0,
            closing_stock   REAL DEFAULT 0,
            rate            REAL DEFAULT 0,
            amount          REAL DEFAULT 0,
            sort_order      INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_cl_supplier ON contract_labourers(supplier_id);
        CREATE INDEX IF NOT EXISTS idx_cl_type ON contract_labourers(payment_type);
        CREATE INDEX IF NOT EXISTS idx_cl_products_c ON contract_labour_products(contractor_id);
        CREATE INDEX IF NOT EXISTS idx_cl_products_p ON contract_labour_products(product_id);
        CREATE INDEX IF NOT EXISTS idx_cl_month_run ON contract_labour_month_runs(contractor_id, year_month);
        CREATE INDEX IF NOT EXISTS idx_cl_month_lines ON contract_labour_month_lines(run_id);
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
        new_id = int(cur.lastrowid)
    try:
        from db_audit import log_event
        log_event(
            "contract_labourers", new_id, "create", user_id=user_id,
            module="Contract Labour",
            summary=f"Contractor created supplier_id={supplier_id}",
        )
    except Exception:
        pass
    return new_id


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
    try:
        from db_audit import log_event
        log_event(
            "contract_labourers", contractor_id, "update", user_id=user_id,
            module="Contract Labour",
            summary=f"Contractor updated active={int(data.get('is_active', 1))}",
        )
    except Exception:
        pass


def deactivate_contractor(contractor_id: int, user_id=None):
    """Soft-delete: keep products/rates, hide from active lists."""
    from database import get_connection, _now

    with get_connection() as conn:
        apply_contract_labour(conn)
        row = conn.execute(
            "SELECT id FROM contract_labourers WHERE id=?", (contractor_id,),
        ).fetchone()
        if not row:
            raise ValueError("Contractor not found.")
        conn.execute(
            """UPDATE contract_labourers SET is_active=0, modified_by=?, modified_at=?
               WHERE id=?""",
            (user_id, _now(), contractor_id),
        )
    try:
        from db_audit import log_event
        log_event(
            "contract_labourers", contractor_id, "deactivate", user_id=user_id,
            module="Contract Labour",
            summary="Contractor deactivated (soft delete)",
        )
    except Exception:
        pass


def delete_contractor(contractor_id: int, user_id=None):
    """Permanently remove contractor and product assignments."""
    from database import get_connection

    with get_connection() as conn:
        apply_contract_labour(conn)
        row = conn.execute(
            "SELECT id, supplier_id FROM contract_labourers WHERE id=?",
            (contractor_id,),
        ).fetchone()
        if not row:
            raise ValueError("Contractor not found.")
        supplier_id = row["supplier_id"]
        conn.execute(
            "DELETE FROM contract_labour_products WHERE contractor_id=?",
            (contractor_id,),
        )
        conn.execute(
            "DELETE FROM contract_labourers WHERE id=?", (contractor_id,),
        )
    try:
        from db_audit import log_event
        log_event(
            "contract_labourers", contractor_id, "delete", user_id=user_id,
            module="Contract Labour",
            summary=f"Contractor permanently deleted supplier_id={supplier_id}",
        )
    except Exception:
        pass

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
    """Monthly payment worksheet lines.

    Sold Qty = approved sales in month
    Stock in hand = opening qty as of month start
    Sale return = returns in month
    Physical Manual Added Stock = user-entered manual qty
    Closing Stock (billable) = Sold - Opening - Sale return + Physical Manual
    Amount = Closing Stock x Rate
    Gross = sum of amounts
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
    total_sold = total_stock = total_return = total_manual = total_closing = 0.0
    for p in products:
        pid = int(p["product_id"])
        sold = round(float(sold_map.get(pid) or 0), 4)
        stock = round(float(stock_map.get(pid) or 0), 4)
        ret = round(float(return_map.get(pid) or 0), 4)
        man = round(float(manual.get(pid) or 0), 4)
        closing = round(sold - stock - ret + man, 4)
        rate = float(p["rate"] if p.get("rate") is not None else default_rate)
        amount = round(closing * rate, 2)
        qinfo = prod_map.get(pid) or {}
        total += amount
        total_sold += sold
        total_stock += stock
        total_return += ret
        total_manual += man
        total_closing += closing
        lines.append({
            "product_id": pid,
            "product_code": p.get("product_code"),
            "product_name": p.get("product_name"),
            "sold_qty": sold,
            "stock_qty": stock,
            "sale_return_qty": ret,
            "manual_qty": man,
            "closing_stock": closing,
            "batch_count": int(qinfo.get("batch_count") or 0),
            "production_qty": float(qinfo.get("quantity") or 0),
            "quantity": closing,  # billable
            "rate": rate,
            "amount": amount,
        })
    ym = str(from_date)[:7]
    return {
        "contractor": c,
        "year_month": ym,
        "from_date": from_date,
        "to_date": to_date,
        "payment_type": c.get("payment_type"),
        "payment_type_label": PAYMENT_TYPES.get(c.get("payment_type"), c.get("payment_type")),
        "formula": (
            "Closing (billable) = Sold - Opening - Sale return + Physical Manual; "
            "Amount = Closing x Rate"
        ),
        "lines": lines,
        "total": round(total, 2),
        "totals": {
            "sold_qty": round(total_sold, 4),
            "stock_qty": round(total_stock, 4),
            "sale_return_qty": round(total_return, 4),
            "manual_qty": round(total_manual, 4),
            "closing_stock": round(total_closing, 4),
            "gross_amount": round(total, 2),
            "item_count": len(lines),
        },
    }


def month_bounds(year: int, month: int) -> tuple[str, str]:
    """Return (from_date, to_date) for a calendar month."""
    import calendar
    from datetime import date as _date

    y, m = int(year), int(month)
    if m < 1 or m > 12:
        raise ValueError("Month must be 1–12.")
    last = calendar.monthrange(y, m)[1]
    return (
        _date(y, m, 1).isoformat(),
        _date(y, m, last).isoformat(),
    )


def get_contractor_month_run(contractor_id: int, year_month: str):
    """Load saved monthly worksheet header + lines, or None."""
    from database import get_connection, row_to_dict, rows_to_list

    ym = str(year_month)[:7]
    with get_connection() as conn:
        apply_contract_labour(conn)
        h = conn.execute(
            """SELECT * FROM contract_labour_month_runs
               WHERE contractor_id=? AND year_month=?""",
            (int(contractor_id), ym),
        ).fetchone()
        if not h:
            return None
        header = row_to_dict(h)
        lines = rows_to_list(conn.execute(
            """SELECT * FROM contract_labour_month_lines
               WHERE run_id=? ORDER BY sort_order, id""",
            (header["id"],),
        ).fetchall())
        header["lines"] = lines
        return header


def list_contractor_month_runs(contractor_id: int, limit: int = 24):
    from database import get_connection, rows_to_list

    with get_connection() as conn:
        apply_contract_labour(conn)
        return rows_to_list(conn.execute(
            """SELECT id, year_month, from_date, to_date, gross_amount, closing_qty,
                      modified_at, created_at
               FROM contract_labour_month_runs
               WHERE contractor_id=?
               ORDER BY year_month DESC
               LIMIT ?""",
            (int(contractor_id), int(limit)),
        ).fetchall())


def save_contractor_month_run(
    contractor_id: int,
    year_month: str,
    lines: list[dict],
    *,
    notes: str | None = None,
    user_id=None,
) -> int:
    """Upsert monthly worksheet record (one per contractor per month)."""
    from database import get_connection, _now

    ym = str(year_month)[:7]
    try:
        y, m = int(ym[:4]), int(ym[5:7])
    except (TypeError, ValueError):
        raise ValueError("year_month must be YYYY-MM.")
    from_date, to_date = month_bounds(y, m)
    gross = 0.0
    closing_sum = 0.0
    clean = []
    for i, ln in enumerate(lines or []):
        try:
            pid = int(ln.get("product_id") or 0)
        except (TypeError, ValueError):
            continue
        if not pid:
            continue
        sold = round(float(ln.get("sold_qty") or 0), 4)
        stock = round(float(ln.get("stock_qty") or 0), 4)
        ret = round(float(ln.get("sale_return_qty") or 0), 4)
        man = round(float(ln.get("manual_qty") or 0), 4)
        closing = round(float(ln.get("closing_stock") if ln.get("closing_stock") is not None
                              else (sold - stock - ret + man)), 4)
        rate = round(float(ln.get("rate") or 0), 4)
        amount = round(float(ln.get("amount") if ln.get("amount") is not None
                             else (closing * rate)), 2)
        gross += amount
        closing_sum += closing
        clean.append({
            "product_id": pid,
            "product_code": ln.get("product_code"),
            "product_name": ln.get("product_name"),
            "sold_qty": sold,
            "stock_qty": stock,
            "sale_return_qty": ret,
            "manual_qty": man,
            "closing_stock": closing,
            "rate": rate,
            "amount": amount,
            "sort_order": i,
        })

    ts = _now()
    with get_connection() as conn:
        apply_contract_labour(conn)
        if not conn.execute(
            "SELECT id FROM contract_labourers WHERE id=?", (int(contractor_id),),
        ).fetchone():
            raise ValueError("Contractor not found.")
        existing = conn.execute(
            """SELECT id FROM contract_labour_month_runs
               WHERE contractor_id=? AND year_month=?""",
            (int(contractor_id), ym),
        ).fetchone()
        note_val = (notes or "").strip() or None
        if existing:
            run_id = int(existing["id"])
            conn.execute(
                """UPDATE contract_labour_month_runs
                   SET from_date=?, to_date=?, gross_amount=?, closing_qty=?, notes=?,
                       modified_by=?, modified_at=?
                   WHERE id=?""",
                (from_date, to_date, round(gross, 2), round(closing_sum, 4),
                 note_val, user_id, ts, run_id),
            )
            conn.execute(
                "DELETE FROM contract_labour_month_lines WHERE run_id=?", (run_id,),
            )
        else:
            cur = conn.execute(
                """INSERT INTO contract_labour_month_runs(
                       contractor_id, year_month, from_date, to_date,
                       gross_amount, closing_qty, notes, created_by, created_at
                   ) VALUES (?,?,?,?,?,?,?,?,?)""",
                (int(contractor_id), ym, from_date, to_date,
                 round(gross, 2), round(closing_sum, 4), note_val, user_id, ts),
            )
            run_id = int(cur.lastrowid)
        for ln in clean:
            conn.execute(
                """INSERT INTO contract_labour_month_lines(
                       run_id, product_id, product_code, product_name,
                       sold_qty, stock_qty, sale_return_qty, manual_qty,
                       closing_stock, rate, amount, sort_order
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id, ln["product_id"], ln["product_code"], ln["product_name"],
                    ln["sold_qty"], ln["stock_qty"], ln["sale_return_qty"], ln["manual_qty"],
                    ln["closing_stock"], ln["rate"], ln["amount"], ln["sort_order"],
                ),
            )
    try:
        from db_audit import log_event
        log_event(
            "contract_labour_month_runs", run_id, "save", user_id=user_id,
            module="Contract Labour",
            summary=f"Month worksheet saved {ym} gross={round(gross, 2)}",
        )
    except Exception:
        pass
    return run_id
