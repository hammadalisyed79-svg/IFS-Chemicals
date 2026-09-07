"""Contract labour — payment types and product assignments for contractors."""

from __future__ import annotations

PAYMENT_PRODUCTION_QTY = "production_qty"
PAYMENT_SKU_CARTON = "sku_carton"
PAYMENT_LOADING_UNLOADING = "loading_unloading"

PAYMENT_TYPES = {
    PAYMENT_PRODUCTION_QTY: "Production quantity (qty x rate per SKU)",
    PAYMENT_SKU_CARTON: "SKU / cartons x rate per SKU",
    PAYMENT_LOADING_UNLOADING: "Loading & unloading (sale/purchase kg × rate)",
}

LINE_CODE_LOADING = "LOADING"
LINE_CODE_UNLOADING = "UNLOADING"

# Per-SKU billing on monthly worksheet
BILLING_PRODUCTION = "production"
BILLING_SOLD = "sold"
BILLING_CLOSING = "closing"
BILLING_BASES = {
    BILLING_PRODUCTION: "Production qty × rate",
    BILLING_SOLD: "Sold qty × rate",
    BILLING_CLOSING: "Closing stock × rate",
}


def default_billing_basis(product_code: str | None, contractor_payment_type: str | None) -> str:
    """SF* (semi-finished / base powder) bills on sold qty; else follow contractor type."""
    code = (product_code or "").strip().upper()
    if code.startswith("SF"):
        return BILLING_SOLD
    if (contractor_payment_type or "").strip() == PAYMENT_PRODUCTION_QTY:
        return BILLING_PRODUCTION
    return BILLING_CLOSING


def _ensure_billing_basis_column(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(contract_labour_products)")}
    if "billing_basis" not in cols:
        conn.execute(
            "ALTER TABLE contract_labour_products ADD COLUMN billing_basis TEXT "
            "DEFAULT 'closing'"
        )
        # SF* → sold; production contractors' non-SF → production
        conn.execute(
            """UPDATE contract_labour_products
               SET billing_basis='sold'
               WHERE product_id IN (
                 SELECT id FROM products WHERE UPPER(TRIM(code)) LIKE 'SF%'
               )"""
        )
        conn.execute(
            """UPDATE contract_labour_products
               SET billing_basis='production'
               WHERE COALESCE(billing_basis,'') IN ('', 'closing')
                 AND contractor_id IN (
                   SELECT id FROM contract_labourers WHERE payment_type='production_qty'
                 )
                 AND product_id NOT IN (
                   SELECT id FROM products WHERE UPPER(TRIM(code)) LIKE 'SF%'
                 )"""
        )
        conn.execute(
            """UPDATE contract_labour_products
               SET billing_basis='closing'
               WHERE COALESCE(billing_basis,'')=''
                 AND contractor_id IN (
                   SELECT id FROM contract_labourers WHERE payment_type='sku_carton'
                 )"""
        )


def _ensure_loading_unloading_schema(conn):
    """Rates columns + allow loading_unloading payment_type + nullable month-line product_id."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(contract_labourers)")}
    if "loading_rate" not in cols:
        conn.execute(
            "ALTER TABLE contract_labourers ADD COLUMN loading_rate REAL DEFAULT 0"
        )
    if "unloading_rate" not in cols:
        conn.execute(
            "ALTER TABLE contract_labourers ADD COLUMN unloading_rate REAL DEFAULT 0"
        )

    create_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='contract_labourers'"
    ).fetchone()
    create_sql = (create_sql[0] or "") if create_sql else ""
    if create_sql and "loading_unloading" not in create_sql:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.executescript(
            """
            CREATE TABLE contract_labourers__lu (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_id     INTEGER NOT NULL UNIQUE REFERENCES suppliers(id),
                payment_type    TEXT NOT NULL,
                default_rate    REAL DEFAULT 0,
                loading_rate    REAL DEFAULT 0,
                unloading_rate  REAL DEFAULT 0,
                notes           TEXT,
                is_active       INTEGER DEFAULT 1,
                created_by      INTEGER REFERENCES users(id),
                created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
                modified_by     INTEGER REFERENCES users(id),
                modified_at     TEXT
            );
            INSERT INTO contract_labourers__lu(
                id, supplier_id, payment_type, default_rate, loading_rate, unloading_rate,
                notes, is_active, created_by, created_at, modified_by, modified_at
            )
            SELECT id, supplier_id, payment_type, default_rate,
                   COALESCE(loading_rate, 0), COALESCE(unloading_rate, 0),
                   notes, is_active, created_by, created_at, modified_by, modified_at
            FROM contract_labourers;
            DROP TABLE contract_labourers;
            ALTER TABLE contract_labourers__lu RENAME TO contract_labourers;
            CREATE INDEX IF NOT EXISTS idx_cl_supplier ON contract_labourers(supplier_id);
            CREATE INDEX IF NOT EXISTS idx_cl_type ON contract_labourers(payment_type);
            """
        )
        conn.execute("PRAGMA foreign_keys=ON")

    # Month lines: allow NULL product_id for Loading / Unloading synthetic rows
    ml_cols = {r[1]: r for r in conn.execute("PRAGMA table_info(contract_labour_month_lines)")}
    prod_col = ml_cols.get("product_id")
    if prod_col is not None and int(prod_col[3] or 0) == 1:  # notnull
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.executescript(
            """
            CREATE TABLE contract_labour_month_lines__lu (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id          INTEGER NOT NULL
                    REFERENCES contract_labour_month_runs(id) ON DELETE CASCADE,
                product_id      INTEGER REFERENCES products(id),
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
            INSERT INTO contract_labour_month_lines__lu
            SELECT id, run_id, product_id, product_code, product_name,
                   sold_qty, stock_qty, sale_return_qty, manual_qty,
                   closing_stock, rate, amount, sort_order
            FROM contract_labour_month_lines;
            DROP TABLE contract_labour_month_lines;
            ALTER TABLE contract_labour_month_lines__lu RENAME TO contract_labour_month_lines;
            CREATE INDEX IF NOT EXISTS idx_cl_month_lines ON contract_labour_month_lines(run_id);
            """
        )
        conn.execute("PRAGMA foreign_keys=ON")

    # Persist unselected weighbridge slips for L/U monthly bills
    run_cols = {r[1] for r in conn.execute("PRAGMA table_info(contract_labour_month_runs)")}
    if "excluded_slip_ids" not in run_cols:
        conn.execute(
            "ALTER TABLE contract_labour_month_runs ADD COLUMN excluded_slip_ids TEXT"
        )

    # Permanent product excludes for L/U (carry across months; slips hidden + not billed)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS contract_labour_lu_exclude_products (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contractor_id   INTEGER NOT NULL
                REFERENCES contract_labourers(id) ON DELETE CASCADE,
            product_code    TEXT NOT NULL,
            product_name    TEXT,
            product_id      INTEGER REFERENCES products(id),
            created_by      INTEGER REFERENCES users(id),
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(contractor_id, product_code)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cl_lu_excl_c "
        "ON contract_labour_lu_exclude_products(contractor_id)"
    )


def normalize_lu_exclude_code(code) -> str:
    """Canonical product code for L/U permanent excludes. Blank / none → (NONE)."""
    c = str(code or "").strip().upper()
    if not c or c in ("(NONE)", "NONE", "N/A", "-"):
        return "(NONE)"
    return c


def list_lu_excluded_products(contractor_id: int) -> list[dict]:
    from database import get_connection, rows_to_list

    with get_connection() as conn:
        apply_contract_labour(conn)
        return rows_to_list(
            conn.execute(
                """
                SELECT id, contractor_id, product_code, product_name, product_id,
                       created_at, created_by
                FROM contract_labour_lu_exclude_products
                WHERE contractor_id=?
                ORDER BY product_code
                """,
                (int(contractor_id),),
            ).fetchall()
        )


def get_lu_excluded_product_codes(contractor_id: int) -> set[str]:
    return {
        normalize_lu_exclude_code(r.get("product_code"))
        for r in list_lu_excluded_products(contractor_id)
    }


def add_lu_excluded_product(
    contractor_id: int,
    product_code: str,
    *,
    product_name: str | None = None,
    product_id: int | None = None,
    user_id=None,
) -> dict:
    """Add a product code to the contractor's permanent L/U exclude list."""
    from database import get_connection, row_to_dict

    code = normalize_lu_exclude_code(product_code)
    name = (product_name or "").strip() or (
        "(no product)" if code == "(NONE)" else code
    )
    pid = int(product_id) if product_id else None
    with get_connection() as conn:
        apply_contract_labour(conn)
        c = conn.execute(
            "SELECT id, payment_type FROM contract_labourers WHERE id=?",
            (int(contractor_id),),
        ).fetchone()
        if not c:
            raise ValueError("Contractor not found.")
        if (c["payment_type"] or "").strip() != PAYMENT_LOADING_UNLOADING:
            raise ValueError(
                "Permanent product excludes apply only to Loading & Unloading contractors."
            )
        conn.execute(
            """
            INSERT INTO contract_labour_lu_exclude_products(
                contractor_id, product_code, product_name, product_id, created_by
            ) VALUES (?,?,?,?,?)
            ON CONFLICT(contractor_id, product_code) DO UPDATE SET
                product_name=excluded.product_name,
                product_id=COALESCE(excluded.product_id, product_id)
            """,
            (int(contractor_id), code, name, pid, user_id),
        )
        row = conn.execute(
            """
            SELECT id, contractor_id, product_code, product_name, product_id,
                   created_at, created_by
            FROM contract_labour_lu_exclude_products
            WHERE contractor_id=? AND product_code=?
            """,
            (int(contractor_id), code),
        ).fetchone()
        return row_to_dict(row) or {"product_code": code, "product_name": name}


def remove_lu_excluded_product(contractor_id: int, product_code: str) -> bool:
    """Remove one code from the permanent L/U exclude list. Returns True if deleted."""
    from database import get_connection

    code = normalize_lu_exclude_code(product_code)
    with get_connection() as conn:
        apply_contract_labour(conn)
        cur = conn.execute(
            """
            DELETE FROM contract_labour_lu_exclude_products
            WHERE contractor_id=? AND product_code=?
            """,
            (int(contractor_id), code),
        )
        return cur.rowcount > 0


def add_lu_excluded_products_bulk(
    contractor_id: int,
    items: list[dict],
    *,
    user_id=None,
) -> int:
    """Add many {product_code, product_name?, product_id?} rows. Returns count added/updated."""
    n = 0
    for it in items or []:
        code = (it.get("product_code") if isinstance(it, dict) else it) or ""
        if not str(code).strip() and not isinstance(it, dict):
            continue
        add_lu_excluded_product(
            contractor_id,
            code if not isinstance(it, dict) else (it.get("product_code") or ""),
            product_name=(it.get("product_name") if isinstance(it, dict) else None),
            product_id=(it.get("product_id") if isinstance(it, dict) else None),
            user_id=user_id,
        )
        n += 1
    return n


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
            payment_type    TEXT NOT NULL,
            default_rate    REAL DEFAULT 0,
            loading_rate    REAL DEFAULT 0,
            unloading_rate  REAL DEFAULT 0,
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
            product_id      INTEGER REFERENCES products(id),
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
    _ensure_billing_basis_column(conn)
    _ensure_loading_unloading_schema(conn)


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
                   supplier_id, payment_type, default_rate, loading_rate, unloading_rate,
                   notes, is_active, created_by, created_at
               ) VALUES(?,?,?,?,?,?,1,?,?)""",
            (
                supplier_id, payment_type,
                float(data.get("default_rate") or 0),
                float(data.get("loading_rate") or 0),
                float(data.get("unloading_rate") or 0),
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
            """UPDATE contract_labourers SET payment_type=?, default_rate=?,
                   loading_rate=?, unloading_rate=?, notes=?,
                   is_active=?, modified_by=?, modified_at=? WHERE id=?""",
            (
                payment_type,
                float(data.get("default_rate") or 0),
                float(data.get("loading_rate") or 0),
                float(data.get("unloading_rate") or 0),
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


def get_contractor_product_billing(contractor_id: int) -> dict[int, str]:
    """product_id → billing_basis for saved assignments."""
    c = get_contractor(contractor_id)
    if not c:
        return {}
    pay = c.get("payment_type")
    out = {}
    for p in c.get("products") or []:
        pid = int(p["product_id"])
        basis = (p.get("billing_basis") or "").strip().lower()
        if basis not in BILLING_BASES:
            basis = default_billing_basis(p.get("product_code"), pay)
        out[pid] = basis
    return out


def save_contractor_products(
    contractor_id: int,
    product_ids: list[int],
    *,
    rates: dict | None = None,
    billing_basis: dict | None = None,
    user_id=None,
) -> int:
    """Replace product assignment for a contractor (remember selection)."""
    from database import get_connection, _now

    rates = rates or {}
    billing_basis = billing_basis or {}
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
            "SELECT id, default_rate, payment_type FROM contract_labourers WHERE id=?",
            (contractor_id,),
        ).fetchone()
        if not cl:
            raise ValueError("Contractor not found.")
        default_rate = float(cl["default_rate"] or 0)
        pay_type = cl["payment_type"]
        codes = {
            int(r["id"]): str(r["code"] or "")
            for r in conn.execute(
                f"SELECT id, code FROM products WHERE id IN ({','.join('?' * len(ids))})",
                ids,
            ).fetchall()
        } if ids else {}
        for pid in ids:
            if pid not in codes:
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
            basis = (billing_basis.get(pid) or billing_basis.get(str(pid)) or "").strip().lower()
            if basis not in BILLING_BASES:
                basis = default_billing_basis(codes.get(pid), pay_type)
            conn.execute(
                """INSERT INTO contract_labour_products(
                       contractor_id, product_id, rate, billing_basis, sort_order
                   ) VALUES(?,?,?,?,?)""",
                (contractor_id, pid, float(rate or 0), basis, i),
            )
        conn.execute(
            "UPDATE contract_labourers SET modified_by=?, modified_at=? WHERE id=?",
            (user_id, _now(), contractor_id),
        )
    return len(ids)


def clear_contractor_products(contractor_id: int, user_id=None) -> int:
    """Discard all product assignments for a contractor."""
    return save_contractor_products(contractor_id, [], user_id=user_id)


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
    ("DT1", "Lashkara / DT1*"),
    ("DT2", "Train detergent (DT2*)"),
    ("DT3", "Detergent AD (DT3*)"),
    ("DT4", "DT4*"),
    ("DT5", "Lashkara NO.19 (DT5*)"),
    ("DT9", "Jagmag (DT9*)"),
    ("DT0", "Brillo (DT0*)"),
    ("DTT", "Tower detergent (DTT*)"),
    ("SF", "Base powder / SF* (sold × rate)"),
    ("DP", "Detergent Powder (DP*)"),
    ("LQ", "Liquid (LQ*)"),
)


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
    loading_rate: float | None = None,
    unloading_rate: float | None = None,
    exclude_slip_ids: list[int] | set[int] | None = None,
) -> dict:
    """Monthly payment worksheet lines (per-SKU billing_basis or loading/unloading kg).

    Bases:
      production — completed production qty × rate
      sold       — sale qty × rate (default for SF* base powder)
      closing    — (Sold − Opening − Sale return + Physical Manual) × rate
      loading_unloading — sale kg × loading rate + purchase kg × unloading rate
    """
    c = get_contractor(contractor_id)
    if not c:
        raise ValueError("Contractor not found.")
    pay_type = (c.get("payment_type") or PAYMENT_SKU_CARTON).strip()
    if pay_type == PAYMENT_LOADING_UNLOADING:
        return calculate_loading_unloading_month(
            contractor_id,
            from_date,
            to_date,
            loading_rate=loading_rate,
            unloading_rate=unloading_rate,
            exclude_slip_ids=exclude_slip_ids,
        )

    products = c.get("products") or []
    pids = [int(p["product_id"]) for p in products]
    is_prod = pay_type == PAYMENT_PRODUCTION_QTY

    bases = {}
    needs_prod = needs_sold = needs_closing = False
    for p in products:
        pid = int(p["product_id"])
        basis = (p.get("billing_basis") or "").strip().lower()
        if basis not in BILLING_BASES:
            basis = default_billing_basis(p.get("product_code"), pay_type)
        bases[pid] = basis
        if basis == BILLING_PRODUCTION:
            needs_prod = True
        elif basis == BILLING_SOLD:
            needs_sold = True
        else:
            needs_closing = True

    prod_map = {}
    if needs_prod or is_prod:
        prod_map = {
            int(r["product_id"]): r
            for r in production_qty_for_products(pids, from_date, to_date)
        }
    sold_map = return_map = stock_map = {}
    if needs_sold or needs_closing:
        sold_map = sold_qty_for_products(pids, from_date, to_date)
        return_map = sale_return_qty_for_products(pids, from_date, to_date)
    if needs_closing:
        stock_map = stock_on_hand_for_products(pids, as_of_date=from_date)

    manual = {}
    if needs_closing:
        for k, v in (manual_qty or {}).items():
            try:
                manual[int(k)] = float(v or 0)
            except (TypeError, ValueError):
                continue

    default_rate = float(c.get("default_rate") or 0)
    lines = []
    total = 0.0
    total_sold = total_stock = total_return = total_manual = 0.0
    total_billable = total_prod = total_closing = 0.0
    for p in products:
        pid = int(p["product_id"])
        basis = bases[pid]
        qinfo = prod_map.get(pid) or {}
        prod_qty = round(float(qinfo.get("quantity") or 0), 4)
        sold = round(float(sold_map.get(pid) or 0), 4)
        stock = round(float(stock_map.get(pid) or 0), 4)
        ret = round(float(return_map.get(pid) or 0), 4)
        man = round(float(manual.get(pid) or 0), 4)
        closing = round(sold - stock - ret + man, 4)
        if basis == BILLING_PRODUCTION:
            billable = prod_qty
        elif basis == BILLING_SOLD:
            billable = sold
        else:
            billable = closing
        rate = float(p["rate"] if p.get("rate") is not None else default_rate)
        amount = round(billable * rate, 2)
        total += amount
        total_sold += sold
        total_stock += stock
        total_return += ret
        total_manual += man
        total_billable += billable
        total_prod += prod_qty
        total_closing += closing if basis == BILLING_CLOSING else 0.0
        lines.append({
            "product_id": pid,
            "product_code": p.get("product_code"),
            "product_name": p.get("product_name"),
            "billing_basis": basis,
            "billing_basis_label": BILLING_BASES.get(basis, basis),
            "sold_qty": sold,
            "stock_qty": stock,
            "sale_return_qty": ret,
            "manual_qty": man,
            "closing_stock": closing if basis == BILLING_CLOSING else 0.0,
            "batch_count": int(qinfo.get("batch_count") or 0),
            "production_qty": prod_qty,
            "quantity": billable,
            "rate": rate,
            "amount": amount,
        })
    ym = str(from_date)[:7]
    hybrid = len({b for b in bases.values()}) > 1
    if hybrid:
        formula = (
            "Per SKU: production × rate, sold × rate (SF*), "
            "or closing stock × rate"
        )
    elif needs_prod and not needs_sold and not needs_closing:
        formula = "Billable = Production qty (month); Amount = Production × Rate"
    elif needs_sold and not needs_prod and not needs_closing:
        formula = "Billable = Sold qty (month); Amount = Sold × Rate"
    else:
        formula = (
            "Closing (billable) = Sold − Opening − Sale return + Physical Manual; "
            "Amount = Closing × Rate"
        )
    return {
        "contractor": c,
        "year_month": ym,
        "from_date": from_date,
        "to_date": to_date,
        "payment_type": pay_type,
        "payment_type_label": PAYMENT_TYPES.get(pay_type, pay_type),
        "is_production_qty": is_prod,
        "is_loading_unloading": False,
        "has_sold_basis": needs_sold,
        "has_closing_basis": needs_closing,
        "has_production_basis": needs_prod,
        "hybrid_billing": hybrid,
        "formula": formula,
        "lines": lines,
        "total": round(total, 2),
        "totals": {
            "sold_qty": round(total_sold, 4),
            "stock_qty": round(total_stock, 4),
            "sale_return_qty": round(total_return, 4),
            "manual_qty": round(total_manual, 4),
            "production_qty": round(total_prod, 4),
            "closing_stock": round(total_closing, 4),
            "billable_qty": round(total_billable, 4),
            "gross_amount": round(total, 2),
            "item_count": len(lines),
        },
    }


def _parse_excluded_slip_ids(raw) -> list[int]:
    """Normalize JSON / CSV / list of excluded weight_slip ids."""
    import json

    if raw is None or raw == "":
        return []
    if isinstance(raw, (list, tuple, set)):
        out = []
        for x in raw:
            try:
                out.append(int(x))
            except (TypeError, ValueError):
                continue
        return sorted(set(out))
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            return _parse_excluded_slip_ids(parsed)
        except Exception:
            parts = [p.strip() for p in s.replace(";", ",").split(",") if p.strip()]
            return _parse_excluded_slip_ids(parts)
    try:
        return [int(raw)]
    except (TypeError, ValueError):
        return []


def _slip_side(party_type, customer_id, supplier_id) -> str | None:
    """Return 'sale' (loading) or 'purchase' (unloading), or None if unclassified."""
    pt = (party_type or "").strip().lower()
    if pt == "customer":
        return "sale"
    if pt == "supplier":
        return "purchase"
    if customer_id is not None and pt != "supplier":
        return "sale"
    if supplier_id is not None and pt != "customer":
        return "purchase"
    return None


def list_weighbridge_slips_for_month(from_date: str, to_date: str) -> list[dict]:
    """Completed weighbridge slips for a date range with product / party / vehicle."""
    from database import get_connection, rows_to_list

    fd, td = str(from_date)[:10], str(to_date)[:10]
    with get_connection() as conn:
        if not _table_exists(conn, "weight_slips"):
            return []
        rows = rows_to_list(conn.execute(
            """SELECT ws.id, ws.document_no, ws.slip_date, ws.party_type,
                      ws.net_weight, ws.vehicle_no, ws.product_id,
                      ws.customer_id, ws.supplier_id,
                      p.code AS product_code, p.name AS product_name,
                      c.name AS customer_name, s.name AS supplier_name
               FROM weight_slips ws
               LEFT JOIN products p ON p.id = ws.product_id
               LEFT JOIN customers c ON c.id = ws.customer_id
               LEFT JOIN suppliers s ON s.id = ws.supplier_id
               WHERE ws.status='completed'
                 AND ws.slip_date>=? AND ws.slip_date<=?
               ORDER BY ws.slip_date, ws.id""",
            (fd, td),
        ).fetchall())
    out = []
    for r in rows:
        side = _slip_side(r.get("party_type"), r.get("customer_id"), r.get("supplier_id"))
        if not side:
            continue
        party = r.get("customer_name") if side == "sale" else r.get("supplier_name")
        out.append({
            "id": int(r["id"]),
            "document_no": r.get("document_no") or "",
            "slip_date": str(r.get("slip_date") or "")[:10],
            "side": side,
            "side_label": "Loading (sale)" if side == "sale" else "Unloading (purchase)",
            "product_id": int(r["product_id"]) if r.get("product_id") else None,
            "product_code": (r.get("product_code") or "").strip() or "(none)",
            "product_name": (r.get("product_name") or "").strip() or "(no product)",
            "party_name": (party or "").strip() or "—",
            "vehicle_no": (r.get("vehicle_no") or "").strip() or "—",
            "net_weight": round(float(r.get("net_weight") or 0), 4),
        })
    return out


def weighbridge_kg_for_month(
    from_date: str,
    to_date: str,
    *,
    exclude_slip_ids: list[int] | set[int] | None = None,
    exclude_product_codes: list[str] | set[str] | None = None,
    hide_excluded_products: bool = True,
) -> dict:
    """Completed weighbridge net kg split by sale (loading) vs purchase (unloading).

    ``exclude_product_codes`` — permanent / filter excludes by product code
    (``(NONE)`` for slips with no product). Those slips are never billed; when
    ``hide_excluded_products`` is True they are omitted from ``slips``.
    """
    excl = set(_parse_excluded_slip_ids(exclude_slip_ids))
    excl_codes = {
        normalize_lu_exclude_code(c) for c in (exclude_product_codes or []) if c is not None
    }
    all_slips = list_weighbridge_slips_for_month(from_date, to_date)
    # Auto-exclude slip ids that match permanent product codes
    for s in all_slips:
        if normalize_lu_exclude_code(s.get("product_code")) in excl_codes:
            excl.add(int(s["id"]))

    sale_kg = purch_kg = 0.0
    sale_n = purch_n = 0
    sale_excl = purch_excl = 0
    products: dict[tuple, dict] = {}
    visible_slips = []
    for s in all_slips:
        code_n = normalize_lu_exclude_code(s.get("product_code"))
        product_blocked = code_n in excl_codes
        pid_key = s.get("product_id") or 0
        pkey = (s["side"], pid_key, s["product_code"], s["product_name"])
        if pkey not in products:
            products[pkey] = {
                "side": s["side"],
                "side_label": s["side_label"],
                "product_id": s.get("product_id"),
                "product_code": s["product_code"],
                "product_name": s["product_name"],
                "slip_count": 0,
                "net_kg": 0.0,
                "excluded_count": 0,
                "excluded_kg": 0.0,
                "slip_ids": [],
                "permanently_excluded": product_blocked,
            }
        products[pkey]["slip_count"] += 1
        products[pkey]["net_kg"] = round(products[pkey]["net_kg"] + s["net_weight"], 4)
        products[pkey]["slip_ids"].append(s["id"])
        if s["id"] in excl or product_blocked:
            products[pkey]["excluded_count"] += 1
            products[pkey]["excluded_kg"] = round(
                products[pkey]["excluded_kg"] + s["net_weight"], 4,
            )
            if s["side"] == "sale":
                sale_excl += 1
            else:
                purch_excl += 1
            if not (hide_excluded_products and product_blocked):
                visible_slips.append(s)
            continue
        visible_slips.append(s)
        if s["side"] == "sale":
            sale_kg += s["net_weight"]
            sale_n += 1
        else:
            purch_kg += s["net_weight"]
            purch_n += 1
    product_rows = sorted(
        products.values(),
        key=lambda r: (0 if r["side"] == "sale" else 1, -float(r["net_kg"]), r["product_code"]),
    )
    for pr in product_rows:
        pr["included_kg"] = round(float(pr["net_kg"]) - float(pr["excluded_kg"]), 4)
        pr["included_count"] = int(pr["slip_count"]) - int(pr["excluded_count"])
    fd, td = str(from_date)[:10], str(to_date)[:10]
    return {
        "sale_kg": round(sale_kg, 4),
        "purchase_kg": round(purch_kg, 4),
        "sale_slip_count": sale_n,
        "purchase_slip_count": purch_n,
        "sale_excluded_count": sale_excl,
        "purchase_excluded_count": purch_excl,
        "excluded_slip_ids": sorted(excl),
        "exclude_product_codes": sorted(excl_codes),
        "from_date": fd,
        "to_date": td,
        "slips": visible_slips,
        "slips_all": all_slips,
        "products": product_rows,
    }


def calculate_loading_unloading_month(
    contractor_id: int,
    from_date: str,
    to_date: str,
    *,
    loading_rate: float | None = None,
    unloading_rate: float | None = None,
    exclude_slip_ids: list[int] | set[int] | None = None,
    exclude_product_codes: list[str] | set[str] | None = None,
) -> dict:
    """Month bill = sale kg × loading rate + purchase kg × unloading rate."""
    c = get_contractor(contractor_id)
    if not c:
        raise ValueError("Contractor not found.")
    if (c.get("payment_type") or "").strip() != PAYMENT_LOADING_UNLOADING:
        raise ValueError("Contractor is not a Loading & Unloading type.")

    perm = get_lu_excluded_product_codes(contractor_id)
    if exclude_product_codes:
        perm |= {normalize_lu_exclude_code(x) for x in exclude_product_codes}
    kg = weighbridge_kg_for_month(
        from_date,
        to_date,
        exclude_slip_ids=exclude_slip_ids,
        exclude_product_codes=perm,
        # Keep permanently blocked slips visible so users can move them back to Include
        hide_excluded_products=False,
    )
    load_rate = float(
        loading_rate if loading_rate is not None else (c.get("loading_rate") or 0)
    )
    unload_rate = float(
        unloading_rate if unloading_rate is not None else (c.get("unloading_rate") or 0)
    )
    sale_kg = float(kg["sale_kg"])
    purch_kg = float(kg["purchase_kg"])
    load_amt = round(sale_kg * load_rate, 2)
    unload_amt = round(purch_kg * unload_rate, 2)
    total = round(load_amt + unload_amt, 2)
    lines = [
        {
            "product_id": None,
            "product_code": LINE_CODE_LOADING,
            "product_name": "Loading (sale / outward kg)",
            "billing_basis": "loading",
            "billing_basis_label": "Sale kg × loading rate",
            "sold_qty": sale_kg,
            "stock_qty": 0.0,
            "sale_return_qty": 0.0,
            "manual_qty": 0.0,
            "closing_stock": sale_kg,
            "production_qty": 0.0,
            "quantity": sale_kg,
            "rate": load_rate,
            "amount": load_amt,
            "slip_count": int(kg["sale_slip_count"]),
        },
        {
            "product_id": None,
            "product_code": LINE_CODE_UNLOADING,
            "product_name": "Unloading (purchase / inward kg)",
            "billing_basis": "unloading",
            "billing_basis_label": "Purchase kg × unloading rate",
            "sold_qty": purch_kg,
            "stock_qty": 0.0,
            "sale_return_qty": 0.0,
            "manual_qty": 0.0,
            "closing_stock": purch_kg,
            "production_qty": 0.0,
            "quantity": purch_kg,
            "rate": unload_rate,
            "amount": unload_amt,
            "slip_count": int(kg["purchase_slip_count"]),
        },
    ]
    ym = str(from_date)[:7]
    return {
        "contractor": c,
        "year_month": ym,
        "from_date": from_date,
        "to_date": to_date,
        "payment_type": PAYMENT_LOADING_UNLOADING,
        "payment_type_label": PAYMENT_TYPES[PAYMENT_LOADING_UNLOADING],
        "is_production_qty": False,
        "is_loading_unloading": True,
        "has_sold_basis": False,
        "has_closing_basis": False,
        "has_production_basis": False,
        "hybrid_billing": False,
        "formula": (
            "Loading = Sale net kg × Loading rate; "
            "Unloading = Purchase net kg × Unloading rate "
            "(completed weighbridge slips; unchecked slips excluded)"
        ),
        "lines": lines,
        "total": total,
        "weighbridge": kg,
        "slips": kg.get("slips") or [],
        "products": kg.get("products") or [],
        "excluded_slip_ids": list(kg.get("excluded_slip_ids") or []),
        "exclude_product_codes": list(kg.get("exclude_product_codes") or []),
        "totals": {
            "sale_kg": sale_kg,
            "purchase_kg": purch_kg,
            "sale_slip_count": int(kg["sale_slip_count"]),
            "purchase_slip_count": int(kg["purchase_slip_count"]),
            "loading_amount": load_amt,
            "unloading_amount": unload_amt,
            "billable_qty": round(sale_kg + purch_kg, 4),
            "gross_amount": total,
            "item_count": 2,
            "excluded_slip_count": int(kg.get("sale_excluded_count") or 0)
            + int(kg.get("purchase_excluded_count") or 0),
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
        header["excluded_slip_ids"] = _parse_excluded_slip_ids(
            header.get("excluded_slip_ids")
        )
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
    excluded_slip_ids: list[int] | set[int] | None = None,
) -> int:
    """Upsert monthly worksheet record (one per contractor per month)."""
    import json
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
        code = (ln.get("product_code") or "").strip().upper()
        is_lu = code in (LINE_CODE_LOADING, LINE_CODE_UNLOADING)
        try:
            pid_raw = ln.get("product_id")
            pid = int(pid_raw) if pid_raw not in (None, "") else 0
        except (TypeError, ValueError):
            pid = 0
        if not pid and not is_lu:
            continue
        sold = round(float(ln.get("sold_qty") or 0), 4)
        stock = round(float(ln.get("stock_qty") or 0), 4)
        ret = round(float(ln.get("sale_return_qty") or 0), 4)
        man = round(float(ln.get("manual_qty") or 0), 4)
        if ln.get("quantity") is not None:
            closing = round(float(ln.get("quantity") or 0), 4)
        elif ln.get("production_qty") is not None and float(ln.get("production_qty") or 0) and not (
            ln.get("closing_stock") is not None and float(ln.get("closing_stock") or 0)
        ):
            closing = round(float(ln.get("production_qty") or 0), 4)
        elif ln.get("closing_stock") is not None:
            closing = round(float(ln.get("closing_stock") or 0), 4)
        else:
            closing = round(sold - stock - ret + man, 4)
        rate = round(float(ln.get("rate") or 0), 4)
        amount = round(float(ln.get("amount") if ln.get("amount") is not None
                             else (closing * rate)), 2)
        gross += amount
        closing_sum += closing
        clean.append({
            "product_id": pid if pid else None,
            "product_code": ln.get("product_code") or (code if is_lu else None),
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

    excl_list = _parse_excluded_slip_ids(excluded_slip_ids)
    excl_json = json.dumps(excl_list) if excl_list else None

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
                       excluded_slip_ids=?, modified_by=?, modified_at=?
                   WHERE id=?""",
                (from_date, to_date, round(gross, 2), round(closing_sum, 4),
                 note_val, excl_json, user_id, ts, run_id),
            )
            conn.execute(
                "DELETE FROM contract_labour_month_lines WHERE run_id=?", (run_id,),
            )
        else:
            cur = conn.execute(
                """INSERT INTO contract_labour_month_runs(
                       contractor_id, year_month, from_date, to_date,
                       gross_amount, closing_qty, notes, excluded_slip_ids,
                       created_by, created_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (int(contractor_id), ym, from_date, to_date,
                 round(gross, 2), round(closing_sum, 4), note_val, excl_json,
                 user_id, ts),
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
            summary=(
                f"Month worksheet saved {ym} gross={round(gross, 2)}"
                + (f" excluded_slips={len(excl_list)}" if excl_list else "")
            ),
        )
    except Exception:
        pass
    return run_id
