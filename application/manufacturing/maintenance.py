"""Plant maintenance — PM, breakdown, MTBF/MTTR."""

from __future__ import annotations

from application.services import BaseService
from database import get_connection, rows_to_list, now
from application.manufacturing.repository import _next_no


class PlantMaintenanceService(BaseService):
    def list_pm_schedules(self) -> list[dict]:
        with get_connection() as conn:
            return rows_to_list(conn.execute(
                """SELECT pm.*, m.name AS machine_name, m.code AS machine_code
                   FROM ifs_pm_schedules pm JOIN machines m ON pm.machine_id = m.id
                   WHERE pm.company_id=? AND pm.is_active=1""",
                (self.tenant.company_id,),
            ).fetchall())

    def save_pm_schedule(self, data: dict) -> int:
        with get_connection() as conn:
            if data.get("id"):
                conn.execute(
                    """UPDATE ifs_pm_schedules SET schedule_type=?, frequency_days=?, lubrication_points=?,
                       spare_parts_json=?, next_due_at=? WHERE id=?""",
                    (data["schedule_type"], data.get("frequency_days", 30),
                     data.get("lubrication_points"), data.get("spare_parts_json"),
                     data.get("next_due_at"), data["id"]),
                )
                return data["id"]
            cur = conn.execute(
                """INSERT INTO ifs_pm_schedules(machine_id, schedule_type, frequency_days, lubrication_points,
                   spare_parts_json, next_due_at, company_id) VALUES(?,?,?,?,?,?,?)""",
                (data["machine_id"], data["schedule_type"], data.get("frequency_days", 30),
                 data.get("lubrication_points"), data.get("spare_parts_json"),
                 data.get("next_due_at"), self.tenant.company_id),
            )
            return cur.lastrowid

    def record_pm_done(self, schedule_id: int) -> None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT frequency_days FROM ifs_pm_schedules WHERE id=?", (schedule_id,)
            ).fetchone()
            freq = row[0] if row else 30
            conn.execute(
                "UPDATE ifs_pm_schedules SET last_done_at=?, next_due_at=date('now', '+' || ? || ' days') WHERE id=?",
                (now(), freq, schedule_id),
            )

    def create_breakdown(self, machine_id: int, cause: str, technician_id: int | None = None) -> int:
        with get_connection() as conn:
            ticket_no = _next_no(conn, "BD", "ifs_breakdown_tickets", "ticket_no")
            cur = conn.execute(
                """INSERT INTO ifs_breakdown_tickets(ticket_no, machine_id, cause, technician_id, company_id)
                   VALUES(?,?,?,?,?)""",
                (ticket_no, machine_id, cause, technician_id, self.tenant.company_id),
            )
            return cur.lastrowid

    def resolve_breakdown(self, ticket_id: int, action: str, downtime_min: float) -> None:
        with get_connection() as conn:
            conn.execute(
                """UPDATE ifs_breakdown_tickets SET resolved_at=?, downtime_min=?, action_taken=?, status='resolved'
                   WHERE id=?""",
                (now(), downtime_min, action, ticket_id),
            )

    def downtime_analysis(self) -> dict:
        with get_connection() as conn:
            bd = conn.execute(
                """SELECT COUNT(*) AS cnt, COALESCE(SUM(downtime_min),0) AS total_min, machine_id
                   FROM ifs_breakdown_tickets WHERE company_id=? AND status='resolved'
                   GROUP BY machine_id""",
                (self.tenant.company_id,),
            ).fetchall()
            prod = conn.execute(
                """SELECT COALESCE(SUM(downtime_min),0) FROM ifs_batch_tickets
                   WHERE company_id=? AND status='completed'""",
                (self.tenant.company_id,),
            ).fetchone()[0]
            machines = rows_to_list(bd)
            mtbf_mttr = []
            for m in machines:
                cnt = m["cnt"] or 1
                mttr = float(m["total_min"] or 0) / cnt
                mtbf_mttr.append({
                    "machine_id": m["machine_id"],
                    "breakdown_count": cnt,
                    "total_downtime_min": m["total_min"],
                    "mttr_min": round(mttr, 1),
                })
            return {"breakdown_by_machine": mtbf_mttr, "production_downtime_min": float(prod or 0)}
