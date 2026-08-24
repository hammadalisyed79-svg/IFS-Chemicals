"""Stock costing, weighted average, revaluation, BOM cost refresh, daily production post.

Standard practice:
  - Last purchase rate → products.purchase_price (master / default rate)
  - Weighted average → warehouse_product_avg_cost (on-hand valuation)
  - Stock value reports → qty × COALESCE(avg_cost, purchase_price)
  - Revaluation document → reset remaining stock to a rate + GL delta
"""

from __future__ import annotations

from datetime import datetime

SCHEMA_KEY = "stock_costing_version"
SCHEMA_VER = 1


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def apply_stock_costing(conn, db_module) -> None:
    """Idempotent schema + COA + one-time master fixes."""
    ver = _meta_ver(conn)
    if ver < 1:
        _ensure_schema(conn)
        _ensure_reval_account(conn)
        classify_product_types(conn)
        refresh_bom_costs(conn)
        seed_avg_cost_from_purchase_price(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (SCHEMA_KEY, str(SCHEMA_VER)),
        )
    else:
        _ensure_schema(conn)
        _ensure_reval_account(conn)
    db_module.DOC_NUMBER_SOURCES.setdefault(
        "SRV", [("stock_revaluations", "document_no")]
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
        CREATE TABLE IF NOT EXISTS warehouse_product_avg_cost (
            warehouse_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            avg_cost REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (warehouse_id, product_id)
        );

        CREATE TABLE IF NOT EXISTS stock_revaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_no TEXT NOT NULL UNIQUE,
            reval_date TEXT NOT NULL,
            warehouse_id INTEGER,
            status TEXT DEFAULT 'draft',
            rate_mode TEXT DEFAULT 'manual',
            notes TEXT,
            total_delta REAL DEFAULT 0,
            posted_by INTEGER,
            posted_at TEXT,
            created_by INTEGER,
            created_at TEXT,
            modified_by INTEGER,
            modified_at TEXT
        );

        CREATE TABLE IF NOT EXISTS stock_revaluation_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reval_id INTEGER NOT NULL REFERENCES stock_revaluations(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL,
            qty REAL NOT NULL DEFAULT 0,
            old_rate REAL NOT NULL DEFAULT 0,
            new_rate REAL NOT NULL DEFAULT 0,
            delta_value REAL NOT NULL DEFAULT 0,
            rate_source TEXT DEFAULT 'manual'
        );
        """
    )


def _ensure_reval_account(conn) -> None:
    if conn.execute(
        "SELECT 1 FROM chart_of_accounts WHERE code='5180'"
    ).fetchone():
        return
    groups = {
        r["group_type"]: r["id"]
        for r in conn.execute("SELECT id, group_type FROM account_groups").fetchall()
    }
    admin = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    aid = admin[0] if admin else 1
    gid = groups.get("expense") or (next(iter(groups.values())) if groups else None)
    if gid:
        conn.execute(
            "INSERT INTO chart_of_accounts(code,name,account_group_id,created_by) VALUES(?,?,?,?)",
            ("5180", "Inventory Revaluation", gid, aid),
        )


def inventory_role_for_product(product_type: str | None) -> str:
    t = (product_type or "finished").lower()
    if t == "raw":
        return "raw_inv"
    if t == "packaging":
        return "pack_inv"
    return "fg_inv"


def get_unit_cost(conn, warehouse_id: int | None, product_id: int, fallback: float = 0.0) -> float:
    from erp_core.inventory_valuation import get_weighted_average_cost

    pp = conn.execute(
        "SELECT COALESCE(purchase_price,0) FROM products WHERE id=?", (product_id,)
    ).fetchone()
    master = float(pp[0] if pp else 0) or float(fallback or 0)
    if not warehouse_id:
        return master
    return float(get_weighted_average_cost(conn, warehouse_id, product_id, master))


def set_unit_cost(conn, warehouse_id: int, product_id: int, unit_cost: float, *, update_master: bool = True) -> None:
    from erp_core.inventory_valuation import _ensure_table

    unit_cost = float(unit_cost or 0)
    _ensure_table(conn)
    conn.execute(
        """INSERT INTO warehouse_product_avg_cost(warehouse_id, product_id, avg_cost)
           VALUES(?,?,?)
           ON CONFLICT(warehouse_id, product_id) DO UPDATE SET avg_cost=excluded.avg_cost""",
        (warehouse_id, product_id, unit_cost),
    )
    if update_master:
        conn.execute(
            "UPDATE products SET purchase_price=?, modified_at=? WHERE id=?",
            (unit_cost, now(), product_id),
        )


def apply_purchase_inbound_cost(
    conn,
    warehouse_id: int,
    product_id: int,
    qty: float,
    unit_cost: float,
    *,
    update_last_rate: bool = True,
) -> float:
    """Last purchase rate on master + weighted average on warehouse stock."""
    from erp_core.inventory_valuation import apply_inbound_cost

    qty = float(qty or 0)
    unit_cost = float(unit_cost or 0)
    if update_last_rate and unit_cost > 0:
        conn.execute(
            "UPDATE products SET purchase_price=?, modified_at=? WHERE id=?",
            (unit_cost, now(), product_id),
        )
    if qty > 0 and unit_cost >= 0:
        return apply_inbound_cost(conn, warehouse_id, product_id, qty, unit_cost)
    return get_unit_cost(conn, warehouse_id, product_id, unit_cost)


def last_purchase_rate(conn, product_id: int) -> float | None:
    row = conn.execute(
        """SELECT pii.rate
           FROM purchase_invoice_items pii
           JOIN purchase_invoices pi ON pi.id = pii.invoice_id
           WHERE pii.product_id=? AND pi.status='approved' AND COALESCE(pii.rate,0)>0
           ORDER BY pi.invoice_date DESC, pi.id DESC LIMIT 1""",
        (product_id,),
    ).fetchone()
    return float(row[0]) if row else None


def classify_product_types(conn) -> dict:
    stats = {"raw": 0, "packaging": 0}
    rows = conn.execute("SELECT id, code, product_type FROM products").fetchall()
    for r in rows:
        code = (r["code"] or "").strip().upper()
        cur = (r["product_type"] or "finished").lower()
        new = None
        if code.startswith("RM"):
            new = "raw"
        elif code.startswith("PKG") or code.startswith("PK"):
            new = "packaging"
        if new and cur != new:
            conn.execute("UPDATE products SET product_type=? WHERE id=?", (new, r["id"]))
            stats[new] += 1
    return stats


def refresh_bom_costs(conn) -> int:
    n = 0
    boms = conn.execute("SELECT id FROM bom_formulas").fetchall()
    for b in boms:
        bid = b[0]
        lines = conn.execute(
            "SELECT id, raw_product_id, quantity FROM bom_formula_lines WHERE bom_id=?",
            (bid,),
        ).fetchall()
        total = 0.0
        for ln in lines:
            pp = conn.execute(
                "SELECT COALESCE(purchase_price,0) FROM products WHERE id=?",
                (ln["raw_product_id"],),
            ).fetchone()
            rate = float(pp[0] if pp else 0)
            qty = float(ln["quantity"] or 0)
            line_cost = round(qty * rate, 4)
            conn.execute(
                "UPDATE bom_formula_lines SET standard_cost=?, line_cost=? WHERE id=?",
                (rate, line_cost, ln["id"]),
            )
            total += line_cost
            n += 1
        conn.execute(
            "UPDATE bom_formulas SET standard_cost=? WHERE id=?", (total, bid)
        )
    return n


def seed_avg_cost_from_purchase_price(conn) -> int:
    from erp_core.inventory_valuation import _ensure_table

    _ensure_table(conn)
    rows = conn.execute(
        """SELECT ws.warehouse_id, ws.product_id, COALESCE(p.purchase_price,0) AS pp
           FROM warehouse_stock ws
           JOIN products p ON p.id = ws.product_id
           WHERE ABS(COALESCE(ws.quantity,0)) > 0.0001"""
    ).fetchall()
    n = 0
    for r in rows:
        existing = conn.execute(
            "SELECT 1 FROM warehouse_product_avg_cost WHERE warehouse_id=? AND product_id=?",
            (r["warehouse_id"], r["product_id"]),
        ).fetchone()
        if existing:
            continue
        conn.execute(
            "INSERT INTO warehouse_product_avg_cost(warehouse_id, product_id, avg_cost) VALUES(?,?,?)",
            (r["warehouse_id"], r["product_id"], float(r["pp"] or 0)),
        )
        n += 1
    return n


def preview_revaluation_lines(warehouse_id: int, rate_mode: str = "last_purchase", product_ids: list | None = None):
    from database import get_connection, rows_to_list

    with get_connection() as conn:
        q = """SELECT ws.product_id, ws.quantity AS qty, p.code, p.name, p.product_type,
                      p.purchase_price, wac.avg_cost
               FROM warehouse_stock ws
               JOIN products p ON p.id = ws.product_id
               LEFT JOIN warehouse_product_avg_cost wac
                 ON wac.warehouse_id = ws.warehouse_id AND wac.product_id = ws.product_id
               WHERE ws.warehouse_id=? AND ABS(COALESCE(ws.quantity,0)) > 0.0001 AND p.is_active=1"""
        params: list = [warehouse_id]
        if product_ids:
            placeholders = ",".join("?" * len(product_ids))
            q += f" AND ws.product_id IN ({placeholders})"
            params.extend(product_ids)
        q += " ORDER BY p.name"
        rows = rows_to_list(conn.execute(q, params).fetchall())
        out = []
        for r in rows:
            qty = float(r["qty"] or 0)
            old = float(r["avg_cost"] if r.get("avg_cost") is not None else (r["purchase_price"] or 0))
            if rate_mode == "last_purchase":
                lp = last_purchase_rate(conn, r["product_id"])
                new = float(lp) if lp is not None else old
                src = "last_purchase" if lp is not None else "master"
            else:
                new = old
                src = "manual"
            delta = round(qty * (new - old), 2)
            out.append({
                "product_id": r["product_id"],
                "code": r["code"],
                "name": r["name"],
                "product_type": r.get("product_type"),
                "qty": qty,
                "old_rate": old,
                "new_rate": new,
                "delta_value": delta,
                "rate_source": src,
            })
        return out


def save_stock_revaluation(data: dict, lines: list, reval_id: int | None = None, user_id=None) -> int:
    from database import get_connection, ensure_document_no

    if not lines:
        raise ValueError("Add at least one revaluation line.")
    total = round(sum(float(l.get("delta_value") or 0) for l in lines), 2)
    ts = now()
    with get_connection() as conn:
        _ensure_schema(conn)
        if reval_id:
            row = conn.execute(
                "SELECT status FROM stock_revaluations WHERE id=?", (reval_id,)
            ).fetchone()
            if not row or row[0] != "draft":
                raise ValueError("Only draft revaluations can be edited.")
            conn.execute(
                """UPDATE stock_revaluations SET reval_date=?, warehouse_id=?, rate_mode=?, notes=?,
                   total_delta=?, modified_by=?, modified_at=? WHERE id=?""",
                (
                    data["reval_date"], data.get("warehouse_id"), data.get("rate_mode", "manual"),
                    data.get("notes"), total, user_id, ts, reval_id,
                ),
            )
            conn.execute("DELETE FROM stock_revaluation_lines WHERE reval_id=?", (reval_id,))
            rid = reval_id
        else:
            doc = ensure_document_no("SRV", data.get("document_no"), conn)
            cur = conn.execute(
                """INSERT INTO stock_revaluations(
                       document_no, reval_date, warehouse_id, status, rate_mode, notes,
                       total_delta, created_by, created_at)
                   VALUES(?,?,?,'draft',?,?,?,?,?)""",
                (
                    doc, data["reval_date"], data.get("warehouse_id"),
                    data.get("rate_mode", "manual"), data.get("notes"), total, user_id, ts,
                ),
            )
            rid = cur.lastrowid
        for ln in lines:
            conn.execute(
                """INSERT INTO stock_revaluation_lines(
                       reval_id, product_id, qty, old_rate, new_rate, delta_value, rate_source)
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    rid, ln["product_id"], float(ln.get("qty") or 0),
                    float(ln.get("old_rate") or 0), float(ln.get("new_rate") or 0),
                    float(ln.get("delta_value") or 0), ln.get("rate_source") or "manual",
                ),
            )
        return rid


def get_stock_revaluations(status=None):
    from database import get_connection, rows_to_list

    with get_connection() as conn:
        _ensure_schema(conn)
        q = """SELECT sr.*, w.code AS warehouse_code, w.name AS warehouse_name
               FROM stock_revaluations sr
               LEFT JOIN warehouses w ON w.id = sr.warehouse_id WHERE 1=1"""
        p = []
        if status:
            q += " AND sr.status=?"; p.append(status)
        q += " ORDER BY sr.reval_date DESC, sr.id DESC"
        return rows_to_list(conn.execute(q, p).fetchall())


def get_stock_revaluation(reval_id: int):
    from database import get_connection, row_to_dict, rows_to_list

    with get_connection() as conn:
        h = row_to_dict(
            conn.execute("SELECT * FROM stock_revaluations WHERE id=?", (reval_id,)).fetchone()
        )
        if not h:
            return None
        h["lines"] = rows_to_list(
            conn.execute(
                """SELECT l.*, p.code, p.name, p.product_type
                   FROM stock_revaluation_lines l
                   JOIN products p ON p.id = l.product_id
                   WHERE l.reval_id=? ORDER BY p.name""",
                (reval_id,),
            ).fetchall()
        )
        return h


def post_stock_revaluation(reval_id: int, user_id=None) -> float:
    from database import get_connection
    from db_v3 import gl_account_code, post_gl
    from db_cache import invalidate_stock

    ts = now()
    with get_connection() as conn:
        _ensure_schema(conn)
        _ensure_reval_account(conn)
        h = conn.execute("SELECT * FROM stock_revaluations WHERE id=?", (reval_id,)).fetchone()
        if not h:
            raise ValueError("Revaluation not found.")
        if (h["status"] or "") != "draft":
            raise ValueError("Only draft revaluations can be posted.")
        wh = h["warehouse_id"]
        if not wh:
            from database import _default_warehouse_id
            wh = _default_warehouse_id(conn)
        lines = conn.execute(
            "SELECT * FROM stock_revaluation_lines WHERE reval_id=?", (reval_id,)
        ).fetchall()
        total_delta = 0.0
        inv_deltas: dict[str, float] = {}
        for ln in lines:
            old = float(ln["old_rate"] or 0)
            new = float(ln["new_rate"] or 0)
            live = conn.execute(
                "SELECT COALESCE(quantity,0) FROM warehouse_stock WHERE warehouse_id=? AND product_id=?",
                (wh, ln["product_id"]),
            ).fetchone()
            qty = float(live[0] if live else (ln["qty"] or 0))
            # Skip near-zero qty — no value change / no cost write
            if abs(qty) < 0.0001:
                conn.execute(
                    "UPDATE stock_revaluation_lines SET qty=?, delta_value=0 WHERE id=?",
                    (qty, ln["id"]),
                )
                continue
            delta = round(qty * (new - old), 2)
            total_delta += delta
            set_unit_cost(conn, wh, ln["product_id"], new, update_master=True)
            conn.execute(
                "UPDATE stock_revaluation_lines SET qty=?, delta_value=? WHERE id=?",
                (qty, delta, ln["id"]),
            )
            pt = conn.execute(
                "SELECT product_type FROM products WHERE id=?", (ln["product_id"],)
            ).fetchone()
            role = inventory_role_for_product(pt[0] if pt else None)
            inv_deltas[role] = inv_deltas.get(role, 0.0) + delta

        doc = h["document_no"]
        dt = h["reval_date"]
        reval_ac = gl_account_code("inv_reval") or "5180"
        for role, delta in inv_deltas.items():
            if abs(delta) < 0.01:
                continue
            inv_ac = gl_account_code(role) or "1310"
            if delta > 0:
                post_gl(conn, dt, inv_ac, delta, 0, "Stock revaluation", "stock_reval", reval_id, doc, user_id)
                post_gl(conn, dt, reval_ac, 0, delta, "Stock revaluation", "stock_reval", reval_id, doc, user_id)
            else:
                amt = abs(delta)
                post_gl(conn, dt, reval_ac, amt, 0, "Stock revaluation", "stock_reval", reval_id, doc, user_id)
                post_gl(conn, dt, inv_ac, 0, amt, "Stock revaluation", "stock_reval", reval_id, doc, user_id)

        conn.execute(
            """UPDATE stock_revaluations SET status='posted', total_delta=?, posted_by=?, posted_at=?,
               modified_by=?, modified_at=? WHERE id=?""",
            (total_delta, user_id, ts, user_id, ts, reval_id),
        )
    try:
        invalidate_stock()
    except Exception:
        pass
    return total_delta


def cancel_stock_revaluation(reval_id: int, user_id=None) -> None:
    """Cancel draft (no GL) or reverse a posted revaluation (restore old rates + reverse GL)."""
    from database import get_connection
    from db_cache import invalidate_stock

    ts = now()
    with get_connection() as conn:
        _ensure_schema(conn)
        h = conn.execute("SELECT * FROM stock_revaluations WHERE id=?", (reval_id,)).fetchone()
        if not h:
            raise ValueError("Revaluation not found.")
        status = (h["status"] or "").lower()
        if status == "cancelled":
            raise ValueError("Revaluation is already cancelled.")
        if status == "draft":
            conn.execute(
                """UPDATE stock_revaluations SET status='cancelled', modified_by=?, modified_at=? WHERE id=?""",
                (user_id, ts, reval_id),
            )
            return
        if status != "posted":
            raise ValueError(f"Cannot cancel revaluation in status '{status}'.")

        wh = h["warehouse_id"]
        if not wh:
            from database import _default_warehouse_id
            wh = _default_warehouse_id(conn)

        # Restore pre-revaluation rates from document lines
        lines = conn.execute(
            "SELECT * FROM stock_revaluation_lines WHERE reval_id=?", (reval_id,)
        ).fetchall()
        for ln in lines:
            set_unit_cost(conn, wh, ln["product_id"], float(ln["old_rate"] or 0), update_master=True)

        # Reverse GL (mirror post_gl balance updates)
        gl_rows = conn.execute(
            """SELECT account_id, debit, credit FROM general_ledger
               WHERE reference_type='stock_reval' AND reference_id=?""",
            (reval_id,),
        ).fetchall()
        for row in gl_rows:
            aid, dr, cr = row[0], float(row[1] or 0), float(row[2] or 0)
            if dr:
                conn.execute(
                    "UPDATE chart_of_accounts SET current_balance=current_balance-? WHERE id=?",
                    (dr, aid),
                )
            if cr:
                conn.execute(
                    "UPDATE chart_of_accounts SET current_balance=current_balance+? WHERE id=?",
                    (cr, aid),
                )
        conn.execute(
            "DELETE FROM general_ledger WHERE reference_type='stock_reval' AND reference_id=?",
            (reval_id,),
        )
        conn.execute(
            """UPDATE stock_revaluations SET status='cancelled', modified_by=?, modified_at=? WHERE id=?""",
            (user_id, ts, reval_id),
        )
    try:
        invalidate_stock()
    except Exception:
        pass


def find_same_day_production_duplicates(bom_id, order_date, qty, *, qty_tol: float = 0.0005):
    """Orders already posted for the same BOM + date + output qty (accidental double-post guard)."""
    from database import get_connection, rows_to_list

    if not bom_id or not order_date:
        return []
    try:
        q = float(qty or 0)
    except (TypeError, ValueError):
        return []
    with get_connection() as conn:
        return rows_to_list(
            conn.execute(
                """
                SELECT id, document_no, batch_no, order_date, status,
                       COALESCE(actual_qty, planned_qty, 0) AS qty
                FROM production_orders
                WHERE bom_id = ?
                  AND order_date = ?
                  AND LOWER(COALESCE(status, '')) NOT IN ('cancelled', 'deleted')
                  AND ABS(COALESCE(actual_qty, planned_qty, 0) - ?) < ?
                ORDER BY id DESC
                """,
                (int(bom_id), str(order_date), q, float(qty_tol)),
            ).fetchall()
        )


def post_daily_production(
    data: dict,
    user_id=None,
    allow_insufficient: bool = False,
    allow_duplicate: bool = False,
) -> int:
    """Create production order, issue BOM materials, receive FG — updates warehouse_stock."""
    from db_v3 import (
        save_production_order,
        issue_production_materials,
        complete_production,
        get_bom,
    )

    bom_id = data.get("bom_id")
    bom = get_bom(bom_id)
    if not bom or bom.get("status") != "approved":
        raise ValueError("Select an approved BOM / composition.")
    qty = float(data.get("actual_qty") or data.get("planned_qty") or 0)
    if qty <= 0:
        raise ValueError("Quantity must be greater than zero.")
    order_date = data.get("order_date") or data.get("production_date")
    dups = find_same_day_production_duplicates(bom_id, order_date, qty)
    if dups and not allow_duplicate:
        docs = ", ".join(
            f"{d.get('document_no')} ({d.get('batch_no') or '—'})" for d in dups[:5]
        )
        extra = f" +{len(dups) - 5} more" if len(dups) > 5 else ""
        raise ValueError(
            f"Same BOM and qty already posted on {order_date}: {docs}{extra}. "
            "Tick **Allow duplicate (same BOM + qty on this date)** if this is intentional."
        )
    payload = {
        "document_no": data.get("document_no"),
        "batch_no": data.get("batch_no"),
        "order_date": order_date,
        "bom_id": bom_id,
        "finished_product_id": data.get("finished_product_id") or bom["finished_product_id"],
        "warehouse_id": data.get("warehouse_id"),
        "machine_id": data.get("machine_id"),
        "planned_qty": qty,
        "labour_cost": data.get("labour_cost", 0),
        "utility_cost": data.get("utility_cost", 0),
        "packing_cost": data.get("packing_cost", 0),
        "overhead_cost": data.get("overhead_cost", 0),
        "production_type": data.get("production_type") or bom.get("composition_type"),
        "notes": data.get("notes") or "Daily production entry",
    }
    po_id = save_production_order(payload, user_id)
    issue_production_materials(po_id, user_id, allow_insufficient=allow_insufficient)
    wastage = float(data.get("wastage_qty") or 0)
    complete_production(
        po_id, qty, wastage, data.get("qc_status") or "Passed", user_id
    )
    return po_id
