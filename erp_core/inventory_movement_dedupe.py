"""Dedupe invoice/return inventory movements (re-approve without deleting old rows)."""

from __future__ import annotations

SCHEMA_KEY = "invoice_movement_dedupe_v1"

DOC_SPECS = (
    ("sales_invoice", "sales_invoices", "sales_invoice_items", "invoice_id", "invoice_date"),
    ("purchase_invoice", "purchase_invoices", "purchase_invoice_items", "invoice_id", "invoice_date"),
    ("sales_return", "sales_returns", "sales_return_items", "return_id", "return_date"),
    ("purchase_return", "purchase_returns", "purchase_return_items", "return_id", "return_date"),
)


def plan_movement_keeps(line_qty_by_product: dict[int, float], movements: list[dict]) -> list[int]:
    """Keep movements that match invoice lines; drop later re-posts.

    Prefer one exact qty match per product (oldest), then fill leftover from oldest rows.
    Never keep a second full-size re-post when a matching row already exists.
    """
    remaining = {int(pid): round(float(qty or 0), 4) for pid, qty in line_qty_by_product.items()}
    original = dict(remaining)
    keep: list[int] = []
    used: set[int] = set()
    for pid, need in list(remaining.items()):
        if need <= 0.0001:
            continue
        for mv in movements:
            mid = int(mv["id"])
            if mid in used:
                continue
            if int(mv["product_id"]) != pid:
                continue
            qty = round(float(mv.get("quantity") or 0), 4)
            if abs(qty - need) < 0.0001:
                keep.append(mid)
                used.add(mid)
                remaining[pid] = 0.0
                break
    for mv in movements:
        mid = int(mv["id"])
        if mid in used:
            continue
        pid = int(mv["product_id"])
        qty = round(float(mv.get("quantity") or 0), 4)
        need = remaining.get(pid, 0.0)
        if need <= 0.0001:
            continue
        if qty <= need + 0.0001:
            keep.append(mid)
            used.add(mid)
            remaining[pid] = round(need - qty, 4)
        elif abs(remaining.get(pid, 0.0) - original.get(pid, 0.0)) < 0.0001:
            keep.append(mid)
            used.add(mid)
            remaining[pid] = 0.0
    return keep


def line_qty_map(rows) -> dict[int, float]:
    out: dict[int, float] = {}
    for r in rows or []:
        pid = int(r["product_id"])
        out[pid] = round(out.get(pid, 0.0) + float(r["quantity"] or 0), 4)
    return out


def apply_invoice_movement_dedupe(conn, *, force: bool = False) -> dict:
    """Idempotent: delete extra movements, do not change warehouse_stock."""
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_meta'"
    ).fetchone():
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT)"
        )
    row = conn.execute(
        "SELECT value FROM schema_meta WHERE key=?", (SCHEMA_KEY,)
    ).fetchone()
    if (not force) and row and str(row[0]) == "1":
        return {"skipped": True, "deleted": 0, "invoices": 0}

    deleted = 0
    invoices = 0
    dated = 0
    for ref, header, items, fk, date_col in DOC_SPECS:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (items,)
        ).fetchone():
            continue
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (header,)
        ).fetchone():
            continue
        ids = [
            int(r[0])
            for r in conn.execute(
                """SELECT DISTINCT reference_id FROM inventory_movements
                   WHERE reference_type=? AND reference_id IS NOT NULL""",
                (ref,),
            )
        ]
        for iid in ids:
            lines = conn.execute(
                f"SELECT product_id, quantity FROM {items} WHERE {fk}=?",
                (iid,),
            ).fetchall()
            needed = line_qty_map(lines)
            mvs = conn.execute(
                """SELECT id, product_id, quantity, movement_date
                   FROM inventory_movements
                   WHERE reference_type=? AND reference_id=?
                   ORDER BY id""",
                (ref, iid),
            ).fetchall()
            if not mvs:
                continue
            mv_dicts = [dict(m) for m in mvs]
            keep_ids = set(plan_movement_keeps(needed, mv_dicts))
            extra_ids = [int(m["id"]) for m in mvs if int(m["id"]) not in keep_ids]
            if extra_ids:
                invoices += 1
                conn.execute(
                    f"DELETE FROM inventory_movements WHERE id IN ({','.join('?' * len(extra_ids))})",
                    extra_ids,
                )
                deleted += len(extra_ids)
                inv = conn.execute(
                    f"SELECT {date_col} AS doc_date FROM {header} WHERE id=?",
                    (iid,),
                ).fetchone()
                doc_date = str(inv["doc_date"] or "")[:10] if inv else ""
                if doc_date and keep_ids:
                    cur = conn.execute(
                        f"""UPDATE inventory_movements
                            SET movement_date=?
                            WHERE id IN ({','.join('?' * len(keep_ids))})
                              AND movement_date != ?""",
                        [doc_date, *keep_ids, doc_date],
                    )
                    dated += cur.rowcount or 0

    conn.execute(
        "INSERT INTO schema_meta(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (SCHEMA_KEY, "1"),
    )
    return {"skipped": False, "deleted": deleted, "invoices": invoices, "dates_aligned": dated}
