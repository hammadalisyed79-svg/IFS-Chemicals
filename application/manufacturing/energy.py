"""Energy management — steam, gas, electricity, water."""

from __future__ import annotations

from application.services import BaseService
from database import get_connection, rows_to_list

UTILITY_TYPES = ("steam", "gas", "electricity", "diesel", "compressed_air", "water")
UNIT_COSTS = {"steam": 0.05, "gas": 0.35, "electricity": 0.12, "diesel": 1.1, "compressed_air": 0.02, "water": 0.01}


class EnergyService(BaseService):
    def record(self, batch_ticket_id: int | None, utility_type: str, quantity: float, uom: str,
               machine_id: int | None = None, department: str | None = None) -> int:
        unit_cost = UNIT_COSTS.get(utility_type, 0)
        total = quantity * unit_cost
        with get_connection() as conn:
            cur = conn.execute(
                """INSERT INTO ifs_energy_readings(
                    batch_ticket_id, machine_id, department, utility_type, quantity, uom, unit_cost, total_cost, company_id
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (batch_ticket_id, machine_id, department, utility_type, quantity, uom,
                 unit_cost, total, self.tenant.company_id),
            )
            return cur.lastrowid

    def cost_per_batch(self, batch_ticket_id: int) -> dict:
        with get_connection() as conn:
            rows = rows_to_list(conn.execute(
                """SELECT utility_type, SUM(quantity) AS qty, SUM(total_cost) AS cost
                   FROM ifs_energy_readings WHERE batch_ticket_id=? GROUP BY utility_type""",
                (batch_ticket_id,),
            ).fetchall())
            total = sum(float(r.get("cost") or 0) for r in rows)
            return {"utilities": rows, "total_cost": total}

    def cost_per_machine(self, machine_id: int) -> dict:
        with get_connection() as conn:
            rows = rows_to_list(conn.execute(
                """SELECT utility_type, SUM(quantity) AS qty, SUM(total_cost) AS cost
                   FROM ifs_energy_readings WHERE machine_id=? GROUP BY utility_type""",
                (machine_id,),
            ).fetchall())
            return {"utilities": rows, "total_cost": sum(float(r.get("cost") or 0) for r in rows)}

    def cost_per_department(self, department: str) -> dict:
        with get_connection() as conn:
            rows = rows_to_list(conn.execute(
                """SELECT utility_type, SUM(total_cost) AS cost FROM ifs_energy_readings
                   WHERE department=? AND company_id=? GROUP BY utility_type""",
                (department, self.tenant.company_id),
            ).fetchall())
            return {"department": department, "utilities": rows,
                    "total_cost": sum(float(r.get("cost") or 0) for r in rows)}

    def summary(self) -> list[dict]:
        with get_connection() as conn:
            return rows_to_list(conn.execute(
                """SELECT utility_type, SUM(quantity) AS qty, SUM(total_cost) AS cost
                   FROM ifs_energy_readings WHERE company_id=? GROUP BY utility_type""",
                (self.tenant.company_id,),
            ).fetchall())
