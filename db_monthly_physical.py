"""Shared month-end physical stock — single source of truth.

Contractor labour \"Physical Manual\" and Sale & Production \"Phy\" both
read/write this table so either screen keeps reports in sync.

physical_qty = month-end physical count (not an adjustment delta).
"""

from __future__ import annotations

from datetime import datetime

SCHEMA_KEY = "monthly_physical_stock_version"
SCHEMA_VER = 1
DEFAULT_WAREHOUSE_ID = 1


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _meta_ver(conn) -> int:
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_meta'"
    ).fetchone():
        return 0
    r = conn.execute(
        "SELECT value FROM schema_meta WHERE key=?", (SCHEMA_KEY,)
    ).fetchone()
    return int(r[0]) if r else 0


def apply_monthly_physical(conn) -> None:
    """Idempotent schema + one-time backfill from contractor / production drafts."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS monthly_physical_stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year_month TEXT NOT NULL,
            warehouse_id INTEGER NOT NULL DEFAULT 1,
            product_id INTEGER NOT NULL,
            physical_qty REAL NOT NULL DEFAULT 0,
            source TEXT,
            updated_by INTEGER,
            updated_at TEXT,
            UNIQUE(year_month, warehouse_id, product_id)
        );
        CREATE INDEX IF NOT EXISTS idx_mps_ym_wh
            ON monthly_physical_stock(year_month, warehouse_id);
        CREATE INDEX IF NOT EXISTS idx_mps_product
            ON monthly_physical_stock(product_id);
        """
    )
    ver = _meta_ver(conn)
    if ver < SCHEMA_VER:
        _backfill_from_existing(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (SCHEMA_KEY, str(SCHEMA_VER)),
        )


def _backfill_from_existing(conn) -> None:
    """Seed shared table from contractor manual_qty, then production phy (later wins)."""
    ts = now()
    # Contractor: manual_qty is used as month-end physical in closing formula
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='contract_labour_month_lines'"
    ).fetchone():
        rows = conn.execute(
            """
            SELECT r.year_month, l.product_id, l.manual_qty
            FROM contract_labour_month_lines l
            JOIN contract_labour_month_runs r ON r.id = l.run_id
            WHERE l.product_id IS NOT NULL
              AND ABS(COALESCE(l.manual_qty, 0)) > 0.00005
            """
        ).fetchall()
        for r in rows:
            _upsert_conn(
                conn,
                str(r["year_month"])[:7],
                DEFAULT_WAREHOUSE_ID,
                int(r["product_id"]),
                float(r["manual_qty"] or 0),
                source="backfill_contractor",
                user_id=None,
                ts=ts,
            )
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='production_month_lines'"
    ).fetchone():
        rows = conn.execute(
            """
            SELECT r.year_month, r.warehouse_id, l.product_id, l.physical_qty
            FROM production_month_lines l
            JOIN production_month_runs r ON r.id = l.run_id
            WHERE l.product_id IS NOT NULL
              AND ABS(COALESCE(l.physical_qty, 0)) > 0.00005
            """
        ).fetchall()
        for r in rows:
            _upsert_conn(
                conn,
                str(r["year_month"])[:7],
                int(r["warehouse_id"] or DEFAULT_WAREHOUSE_ID),
                int(r["product_id"]),
                float(r["physical_qty"] or 0),
                source="backfill_production",
                user_id=None,
                ts=ts,
            )


def _upsert_conn(
    conn,
    year_month: str,
    warehouse_id: int,
    product_id: int,
    physical_qty: float,
    *,
    source: str | None,
    user_id,
    ts: str,
) -> None:
    ym = str(year_month)[:7]
    wh = int(warehouse_id or DEFAULT_WAREHOUSE_ID)
    pid = int(product_id)
    qty = round(float(physical_qty or 0), 4)
    conn.execute(
        """
        INSERT INTO monthly_physical_stock(
            year_month, warehouse_id, product_id, physical_qty, source, updated_by, updated_at
        ) VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(year_month, warehouse_id, product_id) DO UPDATE SET
            physical_qty = excluded.physical_qty,
            source = excluded.source,
            updated_by = excluded.updated_by,
            updated_at = excluded.updated_at
        """,
        (ym, wh, pid, qty, source, user_id, ts),
    )


def get_physical_map(
    year_month: str,
    *,
    warehouse_id: int | None = None,
    product_ids: list[int] | None = None,
) -> dict[int, float]:
    """Return {product_id: physical_qty} for a month."""
    from database import get_connection

    ym = str(year_month)[:7]
    wh = int(warehouse_id or DEFAULT_WAREHOUSE_ID)
    with get_connection() as conn:
        apply_monthly_physical(conn)
        if product_ids:
            ids = sorted({int(p) for p in product_ids if p})
            if not ids:
                return {}
            ph = ",".join("?" * len(ids))
            rows = conn.execute(
                f"""
                SELECT product_id, physical_qty FROM monthly_physical_stock
                WHERE year_month=? AND warehouse_id=? AND product_id IN ({ph})
                """,
                [ym, wh, *ids],
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT product_id, physical_qty FROM monthly_physical_stock
                WHERE year_month=? AND warehouse_id=?
                """,
                (ym, wh),
            ).fetchall()
    return {int(r["product_id"]): float(r["physical_qty"] or 0) for r in rows}


def upsert_physical_map(
    year_month: str,
    physical_map: dict,
    *,
    warehouse_id: int | None = None,
    source: str = "manual",
    user_id=None,
    sync_worksheets: bool = True,
) -> int:
    """Upsert physical counts. Optionally mirror into contractor + production drafts.

    Returns number of product rows written.
    """
    from database import get_connection

    ym = str(year_month)[:7]
    wh = int(warehouse_id or DEFAULT_WAREHOUSE_ID)
    cleaned: dict[int, float] = {}
    for k, v in (physical_map or {}).items():
        try:
            pid = int(k)
        except (TypeError, ValueError):
            continue
        if not pid:
            continue
        try:
            cleaned[pid] = round(float(v or 0), 4)
        except (TypeError, ValueError):
            continue
    if not cleaned:
        return 0

    # Freeze Physical once Sale & Production is posted for this month
    try:
        from db_production_stock import is_production_month_posted

        posted = is_production_month_posted(ym, warehouse_id=wh)
        if posted is None:
            posted = is_production_month_posted(ym)
        if posted:
            raise ValueError(
                f"Month {ym} production is already posted"
                + (
                    f" ({posted.get('batch_ref')})"
                    if posted.get("batch_ref")
                    else ""
                )
                + ". Reverse production first before changing Physical."
            )
    except ValueError:
        raise
    except Exception:
        pass

    ts = now()
    with get_connection() as conn:
        apply_monthly_physical(conn)
        for pid, qty in cleaned.items():
            _upsert_conn(
                conn, ym, wh, pid, qty, source=source, user_id=user_id, ts=ts,
            )
        if sync_worksheets:
            _mirror_into_worksheets(conn, ym, wh, cleaned, user_id=user_id, ts=ts)
    return len(cleaned)


def merge_physical_defaults(
    year_month: str,
    product_ids: list[int],
    existing: dict | None = None,
    *,
    warehouse_id: int | None = None,
) -> dict[int, float]:
    """Fill physical from shared store.

    Existing non-zero values win. Missing or zero values are filled from shared
    so contractor and Sale & Production stay aligned after either side saves.
    """
    out: dict[int, float] = {}
    for k, v in (existing or {}).items():
        try:
            out[int(k)] = round(float(v or 0), 4)
        except (TypeError, ValueError):
            continue
    ids = [int(p) for p in (product_ids or []) if p]
    if not ids:
        return out
    shared = get_physical_map(
        year_month, warehouse_id=warehouse_id, product_ids=ids,
    )
    for pid in ids:
        cur = out.get(pid)
        if cur is None or abs(float(cur or 0)) < 0.00005:
            if pid in shared:
                out[pid] = shared[pid]
        elif pid not in out and pid in shared:
            out[pid] = shared[pid]
    return out


def _mirror_into_worksheets(
    conn,
    ym: str,
    warehouse_id: int,
    phy_map: dict[int, float],
    *,
    user_id=None,
    ts: str,
) -> None:
    """Keep draft worksheets aligned with shared physical."""
    if not phy_map:
        return
    ids = sorted(phy_map.keys())
    ph = ",".join("?" * len(ids))

    # --- Production month draft lines ---
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='production_month_runs'"
    ).fetchone():
        run = conn.execute(
            """
            SELECT id, status FROM production_month_runs
            WHERE warehouse_id=? AND year_month=?
            """,
            (int(warehouse_id), ym),
        ).fetchone()
        if run and (run["status"] or "draft") != "posted":
            run_id = int(run["id"])
            lines = conn.execute(
                f"""
                SELECT id, product_id, opening_qty, sold_qty, return_qty, adj_qty
                FROM production_month_lines
                WHERE run_id=? AND product_id IN ({ph})
                """,
                [run_id, *ids],
            ).fetchall()
            total_phy = 0.0
            total_prod = 0.0
            # Recompute affected lines
            for ln in lines:
                pid = int(ln["product_id"])
                phy = float(phy_map.get(pid, 0) or 0)
                os_ = float(ln["opening_qty"] or 0)
                sale = float(ln["sold_qty"] or 0)
                ret = float(ln["return_qty"] or 0)
                adj = float(ln["adj_qty"] or 0)
                prod = round(phy - os_ - ret + sale - adj, 4)
                conn.execute(
                    """
                    UPDATE production_month_lines
                    SET physical_qty=?, production_qty=?, closing_qty=?
                    WHERE id=?
                    """,
                    (phy, prod, phy, int(ln["id"])),
                )
            # Refresh run totals from all lines
            sums = conn.execute(
                """
                SELECT COALESCE(SUM(physical_qty),0), COALESCE(SUM(production_qty),0)
                FROM production_month_lines WHERE run_id=?
                """,
                (run_id,),
            ).fetchone()
            total_phy = float(sums[0] or 0)
            total_prod = float(sums[1] or 0)
            conn.execute(
                """
                UPDATE production_month_runs
                SET total_physical=?, total_production=?, modified_by=?, modified_at=?
                WHERE id=?
                """,
                (round(total_phy, 4), round(total_prod, 4), user_id, ts, run_id),
            )

    # --- Contractor month lines (closing-basis only; leave prod/sold billable intact) ---
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='contract_labour_month_lines'"
    ).fetchone():
        lines = conn.execute(
            f"""
            SELECT l.id, l.run_id, l.product_id, l.sold_qty, l.stock_qty,
                   l.sale_return_qty, l.rate, l.manual_qty, l.closing_stock, l.amount,
                   cl.payment_type
            FROM contract_labour_month_lines l
            JOIN contract_labour_month_runs r ON r.id = l.run_id
            JOIN contract_labourers cl ON cl.id = r.contractor_id
            WHERE r.year_month=? AND l.product_id IN ({ph})
              AND cl.payment_type = 'sku_carton'
            """,
            [ym, *ids],
        ).fetchall()
        touched_runs: set[int] = set()
        for ln in lines:
            pid = int(ln["product_id"])
            man = float(phy_map.get(pid, 0) or 0)
            sold = float(ln["sold_qty"] or 0)
            stock = float(ln["stock_qty"] or 0)
            ret = float(ln["sale_return_qty"] or 0)
            rate = float(ln["rate"] or 0)
            old_man = float(ln["manual_qty"] or 0)
            stored_closing = float(ln["closing_stock"] or 0)
            implied_old = round(sold - stock - ret + old_man, 4)
            # Closing-basis: closing ≈ sold − opening − return + manual
            if abs(stored_closing - implied_old) <= 0.051:
                closing = round(sold - stock - ret + man, 4)
                amount = round(closing * rate, 2)
                conn.execute(
                    """
                    UPDATE contract_labour_month_lines
                    SET manual_qty=?, closing_stock=?, amount=?
                    WHERE id=?
                    """,
                    (man, closing, amount, int(ln["id"])),
                )
                touched_runs.add(int(ln["run_id"]))
            else:
                # Sold/production-basis line on sku contractor — keep billable, sync phy only
                conn.execute(
                    "UPDATE contract_labour_month_lines SET manual_qty=? WHERE id=?",
                    (man, int(ln["id"])),
                )
        for run_id in touched_runs:
            sums = conn.execute(
                """
                SELECT COALESCE(SUM(amount),0), COALESCE(SUM(closing_stock),0)
                FROM contract_labour_month_lines WHERE run_id=?
                """,
                (run_id,),
            ).fetchone()
            conn.execute(
                """
                UPDATE contract_labour_month_runs
                SET gross_amount=?, closing_qty=?, modified_by=?, modified_at=?
                WHERE id=?
                """,
                (round(float(sums[0] or 0), 2), round(float(sums[1] or 0), 4),
                 user_id, ts, run_id),
            )
