"""V13.14 — real-time inventory buckets."""

from __future__ import annotations


def stock_position(product_id: int, warehouse_id: int | None = None) -> dict:
    """Available, reserved, ordered, in production, QC hold, damaged, returned."""
    from database import get_connection, _default_warehouse_id

    with get_connection() as conn:
        wh = warehouse_id or _default_warehouse_id(conn)
        on_hand = conn.execute(
            "SELECT COALESCE(quantity,0) FROM warehouse_stock WHERE warehouse_id=? AND product_id=?",
            (wh, product_id),
        ).fetchone()
        on_hand = float(on_hand[0] if on_hand else 0)

        reserved = 0.0
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='sales_order_items'").fetchone():
            r = conn.execute(
                """SELECT COALESCE(SUM(soi.quantity - COALESCE(soi.delivered_qty,0)),0)
                   FROM sales_order_items soi
                   JOIN sales_orders so ON so.id=soi.order_id
                   WHERE soi.product_id=? AND so.status IN ('open','partial')
                   AND (so.warehouse_id=? OR so.warehouse_id IS NULL)""",
                (product_id, wh),
            ).fetchone()
            reserved = float(r[0] if r else 0)

        ordered = 0.0
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='purchase_order_items'").fetchone():
            r = conn.execute(
                """SELECT COALESCE(SUM(poi.quantity - COALESCE(poi.received_qty,0)),0)
                   FROM purchase_order_items poi
                   JOIN purchase_orders po ON po.id=poi.order_id
                   WHERE poi.product_id=? AND po.status IN ('open','partial')""",
                (product_id,),
            ).fetchone()
            ordered = float(r[0] if r else 0)

        in_production = 0.0
        qc_hold = 0.0
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='production_orders'").fetchone():
            r = conn.execute(
                """SELECT COALESCE(SUM(planned_qty - COALESCE(actual_qty,0)),0)
                   FROM production_orders
                   WHERE finished_product_id=? AND status IN ('draft','issued')""",
                (product_id,),
            ).fetchone()
            in_production = float(r[0] if r else 0)
            r2 = conn.execute(
                """SELECT COALESCE(SUM(planned_qty),0) FROM production_orders
                   WHERE finished_product_id=? AND qc_status='Pending' AND status!='cancelled'""",
                (product_id,),
            ).fetchone()
            qc_hold = float(r2[0] if r2 else 0)

        damaged = 0.0
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='stock_adjustment_items'").fetchone():
            r = conn.execute(
                """SELECT COALESCE(SUM(ABS(sai.quantity)),0)
                   FROM stock_adjustment_items sai
                   JOIN stock_adjustments sa ON sa.id=sai.adjustment_id
                   WHERE sai.product_id=? AND sa.adjustment_type='damage'""",
                (product_id,),
            ).fetchone()
            damaged = float(r[0] if r else 0)

        returned = 0.0
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='sales_returns'").fetchone():
            r = conn.execute(
                """SELECT COALESCE(SUM(sri.quantity),0)
                   FROM sales_return_items sri
                   JOIN sales_returns sr ON sr.id=sri.return_id
                   WHERE sri.product_id=? AND sr.status='posted'""",
                (product_id,),
            ).fetchone()
            returned = float(r[0] if r else 0)

        available = max(0.0, on_hand - reserved)

        return {
            "warehouse_id": wh,
            "product_id": product_id,
            "on_hand": on_hand,
            "available": available,
            "reserved": reserved,
            "ordered": ordered,
            "in_production": in_production,
            "qc_hold": qc_hold,
            "damaged": damaged,
            "returned": returned,
        }
