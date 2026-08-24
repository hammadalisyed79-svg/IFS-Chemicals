"""Weighted-average inventory valuation (V17.3 warehouse certification)."""

from __future__ import annotations


def _ensure_table(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS warehouse_product_avg_cost (
            warehouse_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            avg_cost REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (warehouse_id, product_id)
        )"""
    )


def apply_inbound_cost(
    conn,
    warehouse_id: int,
    product_id: int,
    qty: float,
    unit_cost: float,
) -> float:
    """Update weighted average cost after an inbound movement."""
    _ensure_table(conn)
    qty = float(qty)
    unit_cost = float(unit_cost)
    if qty <= 0:
        return get_weighted_average_cost(conn, warehouse_id, product_id, unit_cost)

    stock_row = conn.execute(
        "SELECT COALESCE(quantity,0) FROM warehouse_stock WHERE warehouse_id=? AND product_id=?",
        (warehouse_id, product_id),
    ).fetchone()
    old_qty = float(stock_row[0] if stock_row else 0)
    row = conn.execute(
        "SELECT avg_cost FROM warehouse_product_avg_cost WHERE warehouse_id=? AND product_id=?",
        (warehouse_id, product_id),
    ).fetchone()
    old_avg = float(row[0]) if row else unit_cost
    new_qty = old_qty + qty
    new_avg = unit_cost if new_qty <= 0 else ((old_qty * old_avg) + (qty * unit_cost)) / new_qty
    conn.execute(
        """INSERT INTO warehouse_product_avg_cost(warehouse_id, product_id, avg_cost)
           VALUES(?,?,?)
           ON CONFLICT(warehouse_id, product_id) DO UPDATE SET avg_cost=excluded.avg_cost""",
        (warehouse_id, product_id, new_avg),
    )
    return new_avg


def get_weighted_average_cost(
    conn,
    warehouse_id: int,
    product_id: int,
    fallback: float = 0.0,
) -> float:
    _ensure_table(conn)
    row = conn.execute(
        "SELECT avg_cost FROM warehouse_product_avg_cost WHERE warehouse_id=? AND product_id=?",
        (warehouse_id, product_id),
    ).fetchone()
    if row:
        return float(row[0])
    return float(fallback or 0)
