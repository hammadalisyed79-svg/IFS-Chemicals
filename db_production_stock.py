"""Bulk production from physical stock worksheet.

Formula (Phy = month-end physical count):
  Closing    = Phy
  Production = Phy - OS - Return + Sale - Adj

Adj = net inventory adjustments already posted in the month
(reference_type='adjustment'), excluding production_physical posts.
"""

from __future__ import annotations

from datetime import datetime

SCHEMA_KEY = "production_stock_version"
SCHEMA_VER = 1
REF_TYPE_PRODUCTION = "production_physical"


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def apply_production_stock(conn, db_module=None) -> None:
    """Idempotent schema for production month worksheets."""
    _ensure_schema(conn)
    ver = _meta_ver(conn)
    if ver < SCHEMA_VER:
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (SCHEMA_KEY, str(SCHEMA_VER)),
        )


def _meta_ver(conn) -> int:
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_meta'"
    ).fetchone():
        return 0
    r = conn.execute(
        "SELECT value FROM schema_meta WHERE key=?", (SCHEMA_KEY,)
    ).fetchone()
    return int(r[0]) if r else 0


def _ensure_schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS production_month_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year_month TEXT NOT NULL,
            warehouse_id INTEGER NOT NULL,
            from_date TEXT NOT NULL,
            to_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            notes TEXT,
            batch_ref TEXT,
            total_production REAL DEFAULT 0,
            total_physical REAL DEFAULT 0,
            posted_at TEXT,
            posted_by INTEGER,
            created_by INTEGER,
            created_at TEXT,
            modified_by INTEGER,
            modified_at TEXT,
            UNIQUE(warehouse_id, year_month)
        );

        CREATE TABLE IF NOT EXISTS production_month_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL
                REFERENCES production_month_runs(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL,
            product_code TEXT,
            product_name TEXT,
            opening_qty REAL NOT NULL DEFAULT 0,
            sold_qty REAL NOT NULL DEFAULT 0,
            return_qty REAL NOT NULL DEFAULT 0,
            adj_qty REAL NOT NULL DEFAULT 0,
            physical_qty REAL NOT NULL DEFAULT 0,
            production_qty REAL NOT NULL DEFAULT 0,
            closing_qty REAL NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            UNIQUE(run_id, product_id)
        );

        CREATE INDEX IF NOT EXISTS idx_prod_month_run_ym
            ON production_month_runs(year_month, warehouse_id);
        CREATE INDEX IF NOT EXISTS idx_prod_month_lines_run
            ON production_month_lines(run_id);
        """
    )


def production_qty_formula(
    opening: float,
    sold: float,
    return_qty: float,
    adj: float,
    physical: float,
) -> tuple[float, float]:
    """Return (production, closing). Closing = physical."""
    os_ = round(float(opening or 0), 4)
    sale = round(float(sold or 0), 4)
    ret = round(float(return_qty or 0), 4)
    adj_n = round(float(adj or 0), 4)
    phy = round(float(physical or 0), 4)
    production = round(phy - os_ - ret + sale - adj_n, 4)
    return production, phy


def stock_on_hand_for_products_wh(
    product_ids: list[int],
    warehouse_id: int,
    *,
    as_of_date: str | None = None,
) -> dict[int, float]:
    """Warehouse stock; with as_of_date = opening at start of that date."""
    from database import get_connection

    ids = [int(p) for p in (product_ids or []) if p]
    wh = int(warehouse_id)
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT product_id, COALESCE(SUM(quantity), 0) AS stock_qty
            FROM warehouse_stock
            WHERE warehouse_id=? AND product_id IN ({placeholders})
            GROUP BY product_id
            """,
            [wh, *ids],
        ).fetchall()
        current = {int(r["product_id"]): float(r["stock_qty"] or 0) for r in rows}
        if not as_of_date:
            return {pid: round(current.get(pid, 0.0), 4) for pid in ids}
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
            WHERE warehouse_id=?
              AND product_id IN ({placeholders})
              AND movement_date >= ?
            GROUP BY product_id
            """,
            [wh, *ids, as_of_date],
        ).fetchall()
        net_since = {
            int(r["product_id"]): float(r["net_since"] or 0) for r in mv_rows
        }
    return {
        pid: round(current.get(pid, 0.0) - net_since.get(pid, 0.0), 4)
        for pid in ids
    }


def adjustment_qty_for_products_wh(
    product_ids: list[int],
    warehouse_id: int,
    from_date: str,
    to_date: str,
) -> dict[int, float]:
    """Net adjustment qty in period (in − out). Excludes production_physical posts."""
    from database import get_connection

    ids = [int(p) for p in (product_ids or []) if p]
    wh = int(warehouse_id)
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    with get_connection() as conn:
        rows = conn.execute(
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
                   ), 0) AS adj_qty
            FROM inventory_movements
            WHERE warehouse_id=?
              AND product_id IN ({placeholders})
              AND movement_date >= ? AND movement_date <= ?
              AND LOWER(COALESCE(reference_type, '')) = 'adjustment'
            GROUP BY product_id
            """,
            [wh, *ids, from_date, to_date],
        ).fetchall()
    return {int(r["product_id"]): float(r["adj_qty"] or 0) for r in rows}


def calculate_production_month(
    warehouse_id: int,
    from_date: str,
    to_date: str,
    product_ids: list[int],
    *,
    physical_map: dict | None = None,
) -> dict:
    """Build worksheet lines for selected products."""
    from database import get_connection, rows_to_list
    from db_contractors import sale_return_qty_for_products, sold_qty_for_products

    ids = sorted({int(p) for p in (product_ids or []) if p})
    if not ids:
        return {
            "warehouse_id": int(warehouse_id),
            "from_date": from_date,
            "to_date": to_date,
            "lines": [],
            "totals": {
                "items": 0,
                "opening_qty": 0.0,
                "sold_qty": 0.0,
                "return_qty": 0.0,
                "adj_qty": 0.0,
                "physical_qty": 0.0,
                "production_qty": 0.0,
                "closing_qty": 0.0,
            },
        }

    phy_in = physical_map or {}
    phy_map = {}
    for k, v in phy_in.items():
        try:
            phy_map[int(k)] = float(v or 0)
        except (TypeError, ValueError):
            continue

    placeholders = ",".join("?" * len(ids))
    with get_connection() as conn:
        products = rows_to_list(
            conn.execute(
                f"""
                SELECT id, code, name FROM products
                WHERE id IN ({placeholders})
                ORDER BY code
                """,
                ids,
            ).fetchall()
        )

    opening = stock_on_hand_for_products_wh(
        ids, int(warehouse_id), as_of_date=from_date
    )
    sold = sold_qty_for_products(ids, from_date, to_date)
    returns = sale_return_qty_for_products(ids, from_date, to_date)
    adjs = adjustment_qty_for_products_wh(
        ids, int(warehouse_id), from_date, to_date
    )

    lines = []
    tot = {
        "items": 0,
        "opening_qty": 0.0,
        "sold_qty": 0.0,
        "return_qty": 0.0,
        "adj_qty": 0.0,
        "physical_qty": 0.0,
        "production_qty": 0.0,
        "closing_qty": 0.0,
    }
    for i, p in enumerate(products):
        pid = int(p["id"])
        os_ = round(float(opening.get(pid, 0) or 0), 4)
        sale = round(float(sold.get(pid, 0) or 0), 4)
        ret = round(float(returns.get(pid, 0) or 0), 4)
        adj = round(float(adjs.get(pid, 0) or 0), 4)
        phy = round(float(phy_map.get(pid, 0) or 0), 4)
        prod, closing = production_qty_formula(os_, sale, ret, adj, phy)
        ln = {
            "product_id": pid,
            "product_code": p.get("code"),
            "product_name": p.get("name"),
            "opening_qty": os_,
            "sold_qty": sale,
            "return_qty": ret,
            "adj_qty": adj,
            "physical_qty": phy,
            "production_qty": prod,
            "closing_qty": closing,
            "sort_order": i,
        }
        lines.append(ln)
        tot["items"] += 1
        for k in (
            "opening_qty",
            "sold_qty",
            "return_qty",
            "adj_qty",
            "physical_qty",
            "production_qty",
            "closing_qty",
        ):
            tot[k] = round(tot[k] + float(ln[k]), 4)

    return {
        "warehouse_id": int(warehouse_id),
        "from_date": from_date,
        "to_date": to_date,
        "lines": lines,
        "totals": tot,
    }


def get_production_month_run(warehouse_id: int, year_month: str):
    """Load saved draft/posted run + lines, or None."""
    from database import get_connection, row_to_dict, rows_to_list

    ym = str(year_month)[:7]
    with get_connection() as conn:
        apply_production_stock(conn)
        h = conn.execute(
            """SELECT * FROM production_month_runs
               WHERE warehouse_id=? AND year_month=?""",
            (int(warehouse_id), ym),
        ).fetchone()
        if not h:
            return None
        header = row_to_dict(h)
        header["lines"] = rows_to_list(
            conn.execute(
                """SELECT * FROM production_month_lines
                   WHERE run_id=? ORDER BY sort_order, id""",
                (header["id"],),
            ).fetchall()
        )
        return header


def list_production_month_runs(warehouse_id: int | None = None, limit: int = 24):
    from database import get_connection, rows_to_list

    with get_connection() as conn:
        apply_production_stock(conn)
        if warehouse_id:
            return rows_to_list(
                conn.execute(
                    """SELECT r.*, w.code AS warehouse_code, w.name AS warehouse_name
                       FROM production_month_runs r
                       LEFT JOIN warehouses w ON w.id = r.warehouse_id
                       WHERE r.warehouse_id=?
                       ORDER BY r.year_month DESC
                       LIMIT ?""",
                    (int(warehouse_id), int(limit)),
                ).fetchall()
            )
        return rows_to_list(
            conn.execute(
                """SELECT r.*, w.code AS warehouse_code, w.name AS warehouse_name
                   FROM production_month_runs r
                   LEFT JOIN warehouses w ON w.id = r.warehouse_id
                   ORDER BY r.year_month DESC, r.id DESC
                   LIMIT ?""",
                (int(limit),),
            ).fetchall()
        )


def save_production_month_run(
    warehouse_id: int,
    year_month: str,
    lines: list[dict],
    *,
    notes: str | None = None,
    user_id=None,
) -> int:
    """Upsert draft worksheet (one per warehouse per month). Posted runs stay locked."""
    from database import get_connection
    from db_contractors import month_bounds

    ym = str(year_month)[:7]
    try:
        y, m = int(ym[:4]), int(ym[5:7])
    except (TypeError, ValueError):
        raise ValueError("year_month must be YYYY-MM.")
    from_date, to_date = month_bounds(y, m)
    clean = []
    total_prod = 0.0
    total_phy = 0.0
    for i, ln in enumerate(lines or []):
        try:
            pid = int(ln.get("product_id") or 0)
        except (TypeError, ValueError):
            pid = 0
        if not pid:
            continue
        os_ = round(float(ln.get("opening_qty") or 0), 4)
        sale = round(float(ln.get("sold_qty") or 0), 4)
        ret = round(float(ln.get("return_qty") or 0), 4)
        adj = round(float(ln.get("adj_qty") or 0), 4)
        phy = round(float(ln.get("physical_qty") or 0), 4)
        prod, closing = production_qty_formula(os_, sale, ret, adj, phy)
        total_prod += prod
        total_phy += phy
        clean.append({
            "product_id": pid,
            "product_code": ln.get("product_code"),
            "product_name": ln.get("product_name"),
            "opening_qty": os_,
            "sold_qty": sale,
            "return_qty": ret,
            "adj_qty": adj,
            "physical_qty": phy,
            "production_qty": prod,
            "closing_qty": closing,
            "sort_order": i,
        })
    if not clean:
        raise ValueError("No products to save.")

    ts = now()
    with get_connection() as conn:
        apply_production_stock(conn)
        existing = conn.execute(
            """SELECT id, status FROM production_month_runs
               WHERE warehouse_id=? AND year_month=?""",
            (int(warehouse_id), ym),
        ).fetchone()
        if existing and (existing["status"] or "") == "posted":
            raise ValueError(
                f"Month {ym} is already posted for this warehouse. Unlock or use a new month."
            )
        if existing:
            run_id = int(existing["id"])
            conn.execute(
                """UPDATE production_month_runs
                   SET from_date=?, to_date=?, notes=?, status='draft',
                       total_production=?, total_physical=?,
                       modified_by=?, modified_at=?
                   WHERE id=?""",
                (
                    from_date,
                    to_date,
                    notes,
                    round(total_prod, 4),
                    round(total_phy, 4),
                    user_id,
                    ts,
                    run_id,
                ),
            )
            conn.execute(
                "DELETE FROM production_month_lines WHERE run_id=?", (run_id,)
            )
        else:
            cur = conn.execute(
                """INSERT INTO production_month_runs
                   (year_month, warehouse_id, from_date, to_date, status, notes,
                    total_production, total_physical, created_by, created_at,
                    modified_by, modified_at)
                   VALUES (?,?,?,?, 'draft', ?,?,?,?,?,?,?)""",
                (
                    ym,
                    int(warehouse_id),
                    from_date,
                    to_date,
                    notes,
                    round(total_prod, 4),
                    round(total_phy, 4),
                    user_id,
                    ts,
                    user_id,
                    ts,
                ),
            )
            run_id = int(cur.lastrowid)

        for ln in clean:
            conn.execute(
                """INSERT INTO production_month_lines
                   (run_id, product_id, product_code, product_name,
                    opening_qty, sold_qty, return_qty, adj_qty,
                    physical_qty, production_qty, closing_qty, sort_order)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id,
                    ln["product_id"],
                    ln["product_code"],
                    ln["product_name"],
                    ln["opening_qty"],
                    ln["sold_qty"],
                    ln["return_qty"],
                    ln["adj_qty"],
                    ln["physical_qty"],
                    ln["production_qty"],
                    ln["closing_qty"],
                    ln["sort_order"],
                ),
            )
    return run_id


def post_production_month_run(
    run_id: int,
    *,
    user_id=None,
    allow_negative: bool = False,
) -> dict:
    """Post production_qty > 0 as warehouse stock-in movements.

    Movements use reference_type=production_physical so they are excluded from Adj.
    """
    from database import (
        get_connection,
        invalidate_stock,
        _adjust_warehouse_stock,
        row_to_dict,
        rows_to_list,
    )

    ts = now()
    with get_connection() as conn:
        apply_production_stock(conn)
        h = conn.execute(
            "SELECT * FROM production_month_runs WHERE id=?", (int(run_id),)
        ).fetchone()
        if not h:
            raise ValueError("Production month run not found.")
        header = row_to_dict(h)
        if (header.get("status") or "") == "posted":
            raise ValueError("This month is already posted.")

        lines = rows_to_list(
            conn.execute(
                """SELECT * FROM production_month_lines
                   WHERE run_id=? ORDER BY sort_order, id""",
                (int(run_id),),
            ).fetchall()
        )
        if not lines:
            raise ValueError("No lines to post.")

        negatives = [
            ln for ln in lines if float(ln.get("production_qty") or 0) < -0.0001
        ]
        if negatives and not allow_negative:
            codes = ", ".join(
                (ln.get("product_code") or str(ln.get("product_id")))
                for ln in negatives[:8]
            )
            raise ValueError(
                f"Negative production on {len(negatives)} item(s) "
                f"({codes}). Fix Phy or enable allow negative."
            )

        wh = int(header["warehouse_id"])
        ym = header["year_month"]
        post_date = header.get("to_date") or ts[:10]
        batch_ref = f"PROD {ym} physical count"
        posted_n = 0
        posted_qty = 0.0
        verify = []

        for ln in lines:
            prod = round(float(ln.get("production_qty") or 0), 4)
            if abs(prod) < 0.0001:
                continue
            if prod < 0 and not allow_negative:
                continue
            pid = int(ln["product_id"])
            phy = round(float(ln.get("physical_qty") or 0), 4)
            if prod > 0:
                pp = conn.execute(
                    "SELECT COALESCE(purchase_price,0) FROM products WHERE id=?",
                    (pid,),
                ).fetchone()
                unit_cost = float(pp[0] if pp else 0)
                try:
                    from erp_core.inventory_valuation import apply_inbound_cost

                    apply_inbound_cost(conn, wh, pid, prod, unit_cost)
                except Exception:
                    pass
                _adjust_warehouse_stock(conn, pid, wh, prod, user_id=user_id)
                mtype = "in"
                qty = prod
            else:
                _adjust_warehouse_stock(conn, pid, wh, prod, user_id=user_id)
                mtype = "out"
                qty = abs(prod)

            conn.execute(
                """INSERT INTO inventory_movements
                   (movement_date, product_id, warehouse_id, movement_type,
                    quantity, reference_type, reference_id, reason, created_by)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    post_date,
                    pid,
                    wh,
                    mtype,
                    qty,
                    REF_TYPE_PRODUCTION,
                    int(run_id),
                    batch_ref,
                    user_id,
                ),
            )
            posted_n += 1
            posted_qty += prod

            row = conn.execute(
                """SELECT COALESCE(quantity,0) AS qty FROM warehouse_stock
                   WHERE warehouse_id=? AND product_id=?""",
                (wh, pid),
            ).fetchone()
            live = float(row["qty"] if row else 0)
            verify.append({
                "product_id": pid,
                "product_code": ln.get("product_code"),
                "physical_qty": phy,
                "live_qty": round(live, 4),
                "match": abs(live - phy) < 0.051,
            })

        conn.execute(
            """UPDATE production_month_runs
               SET status='posted', batch_ref=?, posted_at=?, posted_by=?,
                   modified_at=?, modified_by=?
               WHERE id=?""",
            (batch_ref, ts, user_id, ts, user_id, int(run_id)),
        )

    invalidate_stock()
    mismatches = [v for v in verify if not v["match"]]
    return {
        "run_id": int(run_id),
        "posted_lines": posted_n,
        "posted_production_qty": round(posted_qty, 4),
        "batch_ref": batch_ref,
        "verify": verify,
        "mismatches": mismatches,
    }


def unlock_production_month_run(run_id: int, *, user_id=None) -> None:
    """Mark posted run as draft again (does not reverse stock movements)."""
    from database import get_connection

    ts = now()
    with get_connection() as conn:
        apply_production_stock(conn)
        h = conn.execute(
            "SELECT id, status FROM production_month_runs WHERE id=?",
            (int(run_id),),
        ).fetchone()
        if not h:
            raise ValueError("Run not found.")
        conn.execute(
            """UPDATE production_month_runs
               SET status='draft', posted_at=NULL, posted_by=NULL,
                   modified_at=?, modified_by=?
               WHERE id=?""",
            (ts, user_id, int(run_id)),
        )
