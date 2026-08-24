"""Batch manufacturing — tickets, reservation, issue, variance, traceability."""

from __future__ import annotations

from application.services import BaseService
from application.manufacturing import repository as repo
from database import get_connection, rows_to_list, now
from infrastructure.events.bus import publish_simple
from domain import events as E


PROCESS_TYPES = (
    "spray_dryer", "dishwash_bar", "liquid_detergent", "toilet_cleaner",
    "industrial_chemical", "corrugated", "gravure", "flexible_packaging",
    "pet_blowing", "toll", "reactor",
)


class BatchManufacturingService(BaseService):
    def list_tickets(self, process_type: str | None = None) -> list[dict]:
        return repo.list_batch_tickets(process_type, self.tenant.company_id)

    def get_ticket(self, ticket_id: int) -> dict | None:
        t = repo.get_batch_ticket(ticket_id)
        if not t:
            return None
        with get_connection() as conn:
            t["reservations"] = rows_to_list(conn.execute(
                "SELECT * FROM ifs_batch_reservations WHERE batch_ticket_id=?", (ticket_id,)
            ).fetchall())
            t["trace"] = rows_to_list(conn.execute(
                "SELECT * FROM ifs_batch_trace WHERE batch_ticket_id=? ORDER BY recorded_at", (ticket_id,)
            ).fetchall())
        return t

    def create_ticket(self, data: dict, user_id: int | None = None) -> int:
        data["company_id"] = self.tenant.company_id
        tid = repo.create_batch_ticket(data, user_id)
        publish_simple(E.BATCH_TICKET_CREATED, aggregate_type="batch_ticket", aggregate_id=tid,
                       user_id=user_id, company_id=self.tenant.company_id,
                       payload={"process_type": data.get("process_type"), "batch_no": data.get("batch_no")})
        return tid

    def reserve_materials(self, ticket_id: int, lines: list[dict]) -> None:
        with get_connection() as conn:
            for ln in lines:
                conn.execute(
                    """INSERT INTO ifs_batch_reservations(batch_ticket_id, product_id, warehouse_id, reserved_qty)
                       VALUES(?,?,?,?)""",
                    (ticket_id, ln["product_id"], ln.get("warehouse_id"), float(ln["qty"])),
                )

    def issue_materials(self, ticket_id: int, user_id: int | None = None) -> dict:
        """Issue RM to production — integrates with production_orders + inventory."""
        from db_v3 import save_production_order, issue_production_materials, get_bom_list
        ticket = self.get_ticket(ticket_id)
        if not ticket:
            raise ValueError("Batch ticket not found")
        po_id = ticket.get("production_order_id")
        finished_product_id = None
        if not po_id:
            bom_id = None
            if ticket.get("formula_id"):
                with get_connection() as conn:
                    f = conn.execute(
                        "SELECT product_id FROM ifs_formula_master WHERE id=?", (ticket["formula_id"],)
                    ).fetchone()
                    if f:
                        finished_product_id = f[0]
                if finished_product_id:
                    boms = [b for b in get_bom_list() if b.get("finished_product_id") == finished_product_id]
                    if boms:
                        bom_id = boms[0]["id"]
            po_data = {
                "order_date": str(now())[:10],
                "bom_id": bom_id,
                "finished_product_id": finished_product_id,
                "planned_qty": ticket["planned_qty"],
                "batch_no": ticket["batch_no"],
                "warehouse_id": ticket.get("warehouse_id"),
                "machine_id": ticket.get("machine_id"),
                "production_type": ticket.get("process_type"),
            }
            po_id = save_production_order(po_data, user_id)
            repo.update_batch_ticket(ticket_id, {"production_order_id": po_id})
        issue_production_materials(po_id, user_id=user_id)
        actual_cons = 0.0
        with get_connection() as conn:
            actual_cons = conn.execute(
                "SELECT COALESCE(SUM(amount),0) FROM production_material_issues WHERE production_order_id=?",
                (po_id,),
            ).fetchone()[0]
            conn.execute(
                "UPDATE ifs_batch_reservations SET status='issued', issued_qty=reserved_qty WHERE batch_ticket_id=?",
                (ticket_id,),
            )
        repo.update_batch_ticket(ticket_id, {
            "status": "issued",
            "actual_consumption": float(actual_cons or 0),
            "production_order_id": po_id,
        })
        publish_simple(E.PRODUCTION_ISSUED, aggregate_type="production_order", aggregate_id=po_id, user_id=user_id)
        return {"production_order_id": po_id, "actual_consumption": float(actual_cons or 0)}

    def complete_batch(self, ticket_id: int, actual_qty: float, wastage_qty: float = 0,
                       qc_status: str = "Pending", user_id: int | None = None) -> dict:
        from db_v3 import complete_production
        ticket = self.get_ticket(ticket_id)
        if not ticket:
            raise ValueError("Batch ticket not found")
        po_id = ticket.get("production_order_id")
        if not po_id:
            raise ValueError("Issue materials before completing batch")
        complete_production(po_id, actual_qty, wastage_qty, qc_status, user_id)
        planned = float(ticket.get("planned_qty") or 1)
        yield_pct = (actual_qty / planned * 100) if planned else 0
        loss_pct = max(0, 100 - yield_pct)
        variance = actual_qty - planned
        repo.update_batch_ticket(ticket_id, {
            "status": "completed",
            "actual_qty": actual_qty,
            "yield_pct": round(yield_pct, 2),
            "loss_pct": round(loss_pct, 2),
            "variance_qty": variance,
            "qc_status": qc_status.lower(),
            "completed_at": now(),
        })
        from application.manufacturing.costing import IndustrialCostingService
        IndustrialCostingService(self.tenant).calculate(ticket_id)
        publish_simple(E.PRODUCTION_COMPLETED, aggregate_type="batch_ticket", aggregate_id=ticket_id, user_id=user_id,
                       payload={"actual_qty": actual_qty, "yield_pct": yield_pct})
        return {"yield_pct": yield_pct, "loss_pct": loss_pct, "variance": variance}

    def hold_qc(self, ticket_id: int) -> None:
        repo.update_batch_ticket(ticket_id, {"qc_status": "hold", "status": "qc_hold"})

    def reject_batch(self, ticket_id: int, reason: str = "") -> None:
        repo.update_batch_ticket(ticket_id, {"is_rejected": 1, "status": "rejected", "qc_status": "failed"})
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO ifs_production_downtime(batch_ticket_id, started_at, reason, category) VALUES(?,?,?,?)",
                (ticket_id, now(), reason or "Batch rejected", "quality"),
            )

    def rework_batch(self, ticket_id: int) -> int:
        ticket = self.get_ticket(ticket_id)
        if not ticket:
            raise ValueError("Batch ticket not found")
        data = {
            "batch_no": f"{ticket['batch_no']}-RW",
            "process_type": ticket["process_type"],
            "planned_qty": ticket.get("actual_qty") or ticket["planned_qty"],
            "formula_id": ticket.get("formula_id"),
            "machine_id": ticket.get("machine_id"),
            "warehouse_id": ticket.get("warehouse_id"),
        }
        new_id = self.create_ticket(data)
        repo.update_batch_ticket(new_id, {"is_rework": 1})
        return new_id
