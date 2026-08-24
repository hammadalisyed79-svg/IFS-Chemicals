"""Industrial costing — material, labour, utility, overhead roll-up."""

from __future__ import annotations

from application.services import BaseService
from application.manufacturing.energy import EnergyService
from database import get_connection, rows_to_list


class IndustrialCostingService(BaseService):
    def calculate(self, batch_ticket_id: int) -> dict:
        with get_connection() as conn:
            ticket = conn.execute("SELECT * FROM ifs_batch_tickets WHERE id=?", (batch_ticket_id,)).fetchone()
            if not ticket:
                raise ValueError("Batch ticket not found")
            ticket = dict(ticket)
            material_cost = float(ticket.get("actual_consumption") or 0)
            labour_cost = 0.0
            machine_cost = 0.0
            po_id = ticket.get("production_order_id")
            if po_id:
                po = conn.execute(
                    "SELECT labour_cost, utility_cost, packing_cost, overhead_cost FROM production_orders WHERE id=?",
                    (po_id,),
                ).fetchone()
                if po:
                    labour_cost = float(po[0] or 0)
                    utility_po = float(po[1] or 0)
                    packing_cost = float(po[2] or 0)
                    overhead_cost = float(po[3] or 0)
                else:
                    packing_cost = overhead_cost = utility_po = 0
            else:
                packing_cost = overhead_cost = utility_po = 0
            energy = EnergyService(self.tenant).cost_per_batch(batch_ticket_id)
            utility_cost = float(energy.get("total_cost") or 0) + utility_po
            factory_overhead = overhead_cost * 0.5
            freight_cost = 0.0
            total = material_cost + labour_cost + machine_cost + utility_cost + overhead_cost + factory_overhead + packing_cost + freight_cost
            actual_qty = float(ticket.get("actual_qty") or ticket.get("planned_qty") or 1)
            cost_per_kg = total / actual_qty if actual_qty else 0
            conn.execute(
                """INSERT INTO ifs_cost_rollup(
                    batch_ticket_id, material_cost, labour_cost, machine_cost, utility_cost,
                    overhead_cost, factory_overhead, packing_cost, freight_cost, total_cost,
                    cost_per_kg, cost_per_carton, cost_per_bottle
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(batch_ticket_id) DO UPDATE SET
                    material_cost=excluded.material_cost, labour_cost=excluded.labour_cost,
                    machine_cost=excluded.machine_cost, utility_cost=excluded.utility_cost,
                    overhead_cost=excluded.overhead_cost, factory_overhead=excluded.factory_overhead,
                    packing_cost=excluded.packing_cost, freight_cost=excluded.freight_cost,
                    total_cost=excluded.total_cost, cost_per_kg=excluded.cost_per_kg,
                    calculated_at=CURRENT_TIMESTAMP""",
                (batch_ticket_id, material_cost, labour_cost, machine_cost, utility_cost,
                 overhead_cost, factory_overhead, packing_cost, freight_cost, total,
                 cost_per_kg, cost_per_kg * 25, cost_per_kg * 0.5),
            )
            return {
                "material_cost": material_cost, "labour_cost": labour_cost,
                "utility_cost": utility_cost, "overhead_cost": overhead_cost,
                "packing_cost": packing_cost, "total_cost": total, "cost_per_kg": cost_per_kg,
            }

    def get_rollup(self, batch_ticket_id: int) -> dict | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM ifs_cost_rollup WHERE batch_ticket_id=?", (batch_ticket_id,)).fetchone()
            return dict(row) if row else None

    def variance_report(self) -> list[dict]:
        with get_connection() as conn:
            return rows_to_list(conn.execute(
                """SELECT bt.ticket_no, bt.batch_no, bt.planned_qty, bt.actual_qty, bt.variance_qty,
                          bt.yield_pct, bt.loss_pct, cr.total_cost, cr.cost_per_kg
                   FROM ifs_batch_tickets bt
                   LEFT JOIN ifs_cost_rollup cr ON bt.id = cr.batch_ticket_id
                   WHERE bt.company_id=? AND bt.status='completed'
                   ORDER BY bt.completed_at DESC LIMIT 100""",
                (self.tenant.company_id,),
            ).fetchall())
