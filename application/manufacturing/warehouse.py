"""Industrial warehouse — zones, transfers, cycle count, FIFO/FEFO."""

from __future__ import annotations

from application.services import BaseService
from database import get_connection, rows_to_list
from application.manufacturing.repository import _next_no


ZONE_TYPES = ("raw_material", "packaging", "wip", "finished_goods", "rejected", "scrap")


class IndustrialWarehouseService(BaseService):
    def list_zones(self) -> list[dict]:
        with get_connection() as conn:
            return rows_to_list(conn.execute(
                """SELECT wz.*, w.name AS warehouse_name
                   FROM ifs_warehouse_zones wz JOIN warehouses w ON wz.warehouse_id = w.id
                   WHERE wz.company_id=?""",
                (self.tenant.company_id,),
            ).fetchall())

    def assign_zone(self, warehouse_id: int, zone_type: str, fifo: bool = True, fefo: bool = False) -> None:
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO ifs_warehouse_zones(warehouse_id, zone_type, fifo_enforced, fefo_enforced, company_id)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(warehouse_id, zone_type) DO UPDATE SET fifo_enforced=excluded.fifo_enforced,
                   fefo_enforced=excluded.fefo_enforced""",
                (warehouse_id, zone_type, 1 if fifo else 0, 1 if fefo else 0, self.tenant.company_id),
            )

    def inter_warehouse_transfer(self, product_id: int, from_wh: int, to_wh: int, qty: float,
                                batch_no: str | None = None, user_id: int | None = None) -> None:
        import database as db
        with db.get_connection() as conn:
            db._adjust_warehouse_stock(conn, product_id, from_wh, -qty)
            db._adjust_warehouse_stock(conn, product_id, to_wh, qty)
            db._record_movement(conn, product_id, from_wh, "out", qty, "transfer", None, "IW-OUT", user_id)
            db._record_movement(conn, product_id, to_wh, "in", qty, "transfer", None, "IW-IN", user_id)
            if batch_no:
                from db_v3 import _apply_product_batch_delta
                _apply_product_batch_delta(conn, batch_no, product_id, from_wh, -qty, user_id)
                _apply_product_batch_delta(conn, batch_no, product_id, to_wh, qty, user_id)

    def create_cycle_count(self, warehouse_id: int, zone_type: str | None, count_date: str,
                           user_id: int | None = None) -> int:
        with get_connection() as conn:
            count_no = _next_no(conn, "CC", "ifs_cycle_counts", "count_no")
            cur = conn.execute(
                """INSERT INTO ifs_cycle_counts(count_no, warehouse_id, zone_type, count_date, counted_by, company_id)
                   VALUES(?,?,?,?,?,?)""",
                (count_no, warehouse_id, zone_type, count_date, user_id, self.tenant.company_id),
            )
            return cur.lastrowid

    def record_count_line(self, cycle_count_id: int, product_id: int, system_qty: float,
                          counted_qty: float, batch_no: str | None = None) -> None:
        variance = counted_qty - system_qty
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO ifs_cycle_count_lines(cycle_count_id, product_id, batch_no, system_qty, counted_qty, variance_qty)
                   VALUES(?,?,?,?,?,?)""",
                (cycle_count_id, product_id, batch_no, system_qty, counted_qty, variance),
            )

    def batch_traceability(self, batch_no: str) -> list[dict]:
        with get_connection() as conn:
            return rows_to_list(conn.execute(
                """SELECT bt.*, p.name AS product_name FROM ifs_batch_trace bt
                   JOIN products p ON bt.product_id = p.id
                   WHERE bt.batch_no=? ORDER BY bt.recorded_at""",
                (batch_no,),
            ).fetchall())

    def fifo_pick_list(self, product_id: int, warehouse_id: int, qty_needed: float) -> list[dict]:
        """FEFO/FIFO pick from product_batches ordered by expiry then created."""
        with get_connection() as conn:
            batches = rows_to_list(conn.execute(
                """SELECT batch_no, quantity, expiry_date, created_at FROM product_batches
                   WHERE product_id=? AND warehouse_id=? AND quantity > 0
                   ORDER BY COALESCE(expiry_date, '9999-12-31'), created_at""",
                (product_id, warehouse_id),
            ).fetchall())
            picks = []
            remaining = qty_needed
            for b in batches:
                if remaining <= 0:
                    break
                take = min(float(b["quantity"]), remaining)
                picks.append({"batch_no": b["batch_no"], "qty": take})
                remaining -= take
            return picks

    def weighted_average_cost(self, product_id: int, warehouse_id: int) -> float:
        from erp_core.inventory_valuation import get_weighted_average_cost
        with get_connection() as conn:
            pp = conn.execute(
                "SELECT COALESCE(purchase_price,0) FROM products WHERE id=?", (product_id,)
            ).fetchone()
            fallback = float(pp[0] if pp else 0)
            return get_weighted_average_cost(conn, warehouse_id, product_id, fallback)
