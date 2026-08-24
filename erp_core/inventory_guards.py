"""V14 RC1 — inventory movement guards."""

from __future__ import annotations


def validate_stock_movement(
    conn,
    product_id: int,
    warehouse_id: int,
    qty_change: float,
    *,
    batch_no: str | None = None,
    user_id: int | None = None,
) -> None:
    """Raise ValueError if movement violates inventory rules."""
    import database as db

    if qty_change >= 0:
        return

    prod = conn.execute(
        "SELECT id, code, name, is_active FROM products WHERE id=?", (product_id,),
    ).fetchone()
    if not prod:
        raise ValueError("Item not found.")
    if prod["is_active"] in (0, False, "0"):
        raise ValueError(f"Item {prod['code']} is inactive — cannot post movement.")

    wh = conn.execute(
        "SELECT id, name, is_active, is_closed FROM warehouses WHERE id=?", (warehouse_id,),
    ).fetchone()
    if not wh:
        raise ValueError("Warehouse not found.")
    if wh["is_active"] in (0, False, "0"):
        raise ValueError(f"Warehouse {wh['name']} is inactive.")
    if wh["is_closed"] in (1, True, "1"):
        raise ValueError(f"Warehouse {wh['name']} is closed for posting.")

    row = conn.execute(
        "SELECT COALESCE(quantity,0) FROM warehouse_stock WHERE warehouse_id=? AND product_id=?",
        (warehouse_id, product_id),
    ).fetchone()
    on_hand = float(row[0] if row else 0)
    if on_hand + qty_change < -0.0001:
        # Temporary: allow_negative_stock=1 skips insufficient-stock blocks for all users
        # (re-enable enforcement later after invoice/stock balancing).
        allow = db.get_setting("allow_negative_stock", "0") == "1"
        if allow:
            return
        raise ValueError(
            f"Insufficient stock for {prod['code']}: on hand {on_hand:,.3f}, "
            f"required {abs(qty_change):,.3f}."
        )

    if batch_no:
        dup = conn.execute(
            """SELECT id FROM product_batches
               WHERE batch_no=? AND product_id=? AND warehouse_id!=?""",
            (batch_no, product_id, warehouse_id),
        ).fetchone()
        if dup:
            raise ValueError(
                f"Batch {batch_no} already exists in another warehouse — warehouse mismatch."
            )
