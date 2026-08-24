"""Per-customer distributor catalogue — invoice rebuild + admin overrides."""

from __future__ import annotations

from datetime import date, datetime

DEFAULT_CUTOFF = "2026-05-01"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return str(date.today())


def ensure_schema() -> None:
    from database import get_connection
    from db_v15 import ensure_distributor_catalog_schema
    with get_connection() as conn:
        ensure_distributor_catalog_schema(conn)


def list_distributor_customers(*, active_only: bool = True) -> list[dict]:
    from database import get_connection, rows_to_list
    where = ["(COALESCE(c.is_distributor,0)=1 OR COALESCE(c.portal_enabled,0)=1)"]
    if active_only:
        where.append("COALESCE(c.is_active,1)=1")
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            f"""SELECT c.id, c.code, c.name, c.is_distributor, c.portal_enabled,
                       c.assigned_price_list_id, c.credit_limit,
                       (SELECT COUNT(*) FROM distributor_catalog_items d
                        WHERE d.customer_id=c.id AND COALESCE(d.is_active,1)=1) AS catalog_count
                FROM customers c
                WHERE {' AND '.join(where)}
                ORDER BY c.code, c.name""",
        ).fetchall())


def list_catalog(customer_id: int, *, include_inactive: bool = False) -> list[dict]:
    ensure_schema()
    from database import get_connection, rows_to_list
    where = ["d.customer_id=?"]
    params: list = [customer_id]
    if not include_inactive:
        where.append("COALESCE(d.is_active,1)=1")
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            f"""SELECT d.*, p.code AS product_code, p.name AS product_name,
                       u.code AS unit
                FROM distributor_catalog_items d
                JOIN products p ON p.id=d.product_id
                LEFT JOIN units_of_measure u ON u.id=p.unit_id
                WHERE {' AND '.join(where)}
                ORDER BY p.name""",
            params,
        ).fetchall())


def get_catalog_price(customer_id: int, product_id: int) -> dict | None:
    """Active catalog price effective today for order validation."""
    ensure_schema()
    from database import get_connection, row_to_dict
    with get_connection() as conn:
        row = conn.execute(
            """SELECT * FROM distributor_catalog_items
               WHERE customer_id=? AND product_id=?
                 AND COALESCE(is_active,1)=1
                 AND date(effective_from) <= date('now')
               LIMIT 1""",
            (customer_id, product_id),
        ).fetchone()
        return row_to_dict(row) if row else None


def _latest_invoice_lines(conn, customer_id: int, cutoff: str) -> list[dict]:
    """Latest approved invoice line per product on/after cutoff."""
    from database import rows_to_list
    rows = rows_to_list(conn.execute(
        """
        SELECT si.product_id, si.rate, si.quantity, si.line_discount, si.amount,
               s.id AS invoice_id, s.invoice_date, s.document_no
        FROM sales_invoice_items si
        JOIN sales_invoices s ON s.id = si.invoice_id
        WHERE s.customer_id = ?
          AND COALESCE(s.status, '') = 'approved'
          AND date(s.invoice_date) >= date(?)
          AND si.product_id IS NOT NULL
        ORDER BY s.invoice_date DESC, s.id DESC, si.id DESC
        """,
        (customer_id, cutoff),
    ).fetchall())
    seen: set[int] = set()
    out = []
    for r in rows:
        pid = int(r["product_id"])
        if pid in seen:
            continue
        seen.add(pid)
        out.append(r)
    return out


def _discount_pct_from_line(row: dict) -> float:
    """Prefer explicit line_discount; else imply % from amount vs qty*rate (FMYE-style invoices)."""
    qty = float(row.get("quantity") or 0)
    rate = float(row.get("rate") or 0)
    disc_amt = float(row.get("line_discount") or 0)
    amount = float(row.get("amount") or 0)
    gross = qty * rate
    if gross <= 0.0001:
        return 0.0
    if disc_amt > 0.0001:
        pct = disc_amt / gross * 100.0
    elif amount > 0 and amount + 0.01 < gross:
        pct = (1.0 - amount / gross) * 100.0
    else:
        return 0.0
    pct = min(100.0, max(0.0, pct))
    # Round to 2 dp; snap near-integers (e.g. 7.001 → 7.00)
    pct = round(pct, 2)
    if abs(pct - round(pct)) < 0.005:
        pct = float(round(pct))
    return pct


def rebuild_catalog_from_invoices(
    customer_id: int,
    *,
    cutoff: str = DEFAULT_CUTOFF,
    created_by: int | None = None,
) -> dict:
    """Upsert invoice-sourced catalog rows; preserve admin_changed overrides."""
    ensure_schema()
    from database import get_connection

    cutoff = (cutoff or DEFAULT_CUTOFF).strip()[:10]
    inserted = updated = skipped_admin = 0
    with get_connection() as conn:
        lines = _latest_invoice_lines(conn, customer_id, cutoff)
        for ln in lines:
            pid = int(ln["product_id"])
            rate = float(ln.get("rate") or 0)
            disc = _discount_pct_from_line(ln)
            inv_date = str(ln.get("invoice_date") or _today())[:10]
            inv_id = ln.get("invoice_id")
            existing = conn.execute(
                """SELECT id, admin_changed, source FROM distributor_catalog_items
                   WHERE customer_id=? AND product_id=?""",
                (customer_id, pid),
            ).fetchone()
            if existing:
                if int(existing["admin_changed"] or 0) == 1:
                    # Keep staff override; still refresh invoice audit pointers
                    conn.execute(
                        """UPDATE distributor_catalog_items
                           SET last_invoice_id=?, last_invoice_date=?
                           WHERE id=?""",
                        (inv_id, inv_date, existing["id"]),
                    )
                    skipped_admin += 1
                    continue
                conn.execute(
                    """UPDATE distributor_catalog_items SET
                        rate=?, discount_pct=?, effective_from=?,
                        source='invoice', is_active=1,
                        last_invoice_id=?, last_invoice_date=?,
                        changed_at=?, changed_by=?
                       WHERE id=?""",
                    (
                        rate, disc, inv_date, inv_id, inv_date,
                        _now(), created_by, existing["id"],
                    ),
                )
                updated += 1
            else:
                conn.execute(
                    """INSERT INTO distributor_catalog_items(
                        customer_id, product_id, rate, discount_pct, min_qty,
                        effective_from, source, admin_changed,
                        last_invoice_id, last_invoice_date, is_active,
                        changed_at, changed_by)
                       VALUES(?,?,?,?,1,?, 'invoice', 0, ?, ?, 1, ?, ?)""",
                    (
                        customer_id, pid, rate, disc, inv_date,
                        inv_id, inv_date, _now(), created_by,
                    ),
                )
                inserted += 1
    return {
        "customer_id": customer_id,
        "cutoff": cutoff,
        "products": len(lines),
        "inserted": inserted,
        "updated": updated,
        "skipped_admin": skipped_admin,
    }


def rebuild_all_distributors(
    *,
    cutoff: str = DEFAULT_CUTOFF,
    created_by: int | None = None,
) -> list[dict]:
    results = []
    for c in list_distributor_customers(active_only=True):
        results.append(
            rebuild_catalog_from_invoices(
                c["id"], cutoff=cutoff, created_by=created_by,
            )
        )
    return results


def upsert_catalog_item(
    customer_id: int,
    product_id: int,
    *,
    rate: float,
    discount_pct: float = 0,
    min_qty: float = 1,
    effective_from: str | None = None,
    admin_note: str = "",
    is_active: bool = True,
    created_by: int | None = None,
    notify: bool = True,
) -> int:
    """Admin add/edit — marks admin_changed and optionally notifies distributor."""
    ensure_schema()
    from database import get_connection, row_to_dict
    from erp_core import notifications as notify_mod

    eff = (effective_from or _today())[:10]
    rate = float(rate or 0)
    discount_pct = round(float(discount_pct or 0), 2)
    if abs(discount_pct - round(discount_pct)) < 0.005:
        discount_pct = float(round(discount_pct))
    min_qty = float(min_qty or 1)

    with get_connection() as conn:
        prod = row_to_dict(conn.execute(
            "SELECT code, name FROM products WHERE id=?", (product_id,)
        ).fetchone())
        if not prod:
            raise ValueError("Product not found.")
        existing = conn.execute(
            "SELECT id FROM distributor_catalog_items WHERE customer_id=? AND product_id=?",
            (customer_id, product_id),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE distributor_catalog_items SET
                    rate=?, discount_pct=?, min_qty=?, effective_from=?,
                    source='admin', admin_changed=1, admin_note=?,
                    is_active=?, changed_at=?, changed_by=?
                   WHERE id=?""",
                (
                    rate, discount_pct, min_qty, eff,
                    admin_note or None, int(bool(is_active)),
                    _now(), created_by, existing[0],
                ),
            )
            rid = int(existing[0])
            action = "updated"
        else:
            cur = conn.execute(
                """INSERT INTO distributor_catalog_items(
                    customer_id, product_id, rate, discount_pct, min_qty,
                    effective_from, source, admin_changed, admin_note,
                    is_active, changed_at, changed_by)
                   VALUES(?,?,?,?,?, ?, 'admin', 1, ?, ?, ?, ?)""",
                (
                    customer_id, product_id, rate, discount_pct, min_qty, eff,
                    admin_note or None, int(bool(is_active)),
                    _now(), created_by,
                ),
            )
            rid = int(cur.lastrowid)
            action = "added"

    if notify:
        notify_mod.notify_distributor(
            customer_id,
            "catalog_price",
            "Price updated by Admin" if action == "updated" else "Product added to your catalogue",
            (
                f"{prod.get('code')} — {prod.get('name')}: "
                f"Rs. {rate:,.2f} (disc {discount_pct:.2f}%) from {eff}. "
                f"Changed by Admin."
            ),
            ref_type="distributor_catalog_item",
            ref_id=rid,
        )
    return rid


def set_catalog_active(
    customer_id: int,
    product_id: int,
    is_active: bool,
    *,
    changed_by: int | None = None,
) -> None:
    ensure_schema()
    from database import get_connection
    with get_connection() as conn:
        conn.execute(
            """UPDATE distributor_catalog_items
               SET is_active=?, changed_at=?, changed_by=?, admin_changed=1, source='admin'
               WHERE customer_id=? AND product_id=?""",
            (int(bool(is_active)), _now(), changed_by, customer_id, product_id),
        )
