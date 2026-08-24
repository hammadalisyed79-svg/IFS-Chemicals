"""Industrial manufacturing reports."""

from __future__ import annotations

from application.services import BaseService
from database import get_connection, rows_to_list


class IndustrialReportService(BaseService):
    def daily_production(self, prod_date: str | None = None) -> list[dict]:
        sql = """SELECT bt.*, cr.total_cost, cr.cost_per_kg
                 FROM ifs_batch_tickets bt
                 LEFT JOIN ifs_cost_rollup cr ON bt.id = cr.batch_ticket_id
                 WHERE bt.company_id=? AND bt.status='completed'"""
        params: list = [self.tenant.company_id]
        if prod_date:
            sql += " AND date(bt.completed_at)=?"
            params.append(prod_date)
        sql += " ORDER BY bt.completed_at DESC"
        with get_connection() as conn:
            return rows_to_list(conn.execute(sql, params).fetchall())

    def machine_utilization(self) -> list[dict]:
        with get_connection() as conn:
            return rows_to_list(conn.execute(
                """SELECT m.name, m.code,
                          COUNT(bt.id) AS batch_count,
                          COALESCE(SUM(bt.production_time_min),0) AS prod_min,
                          COALESCE(SUM(bt.downtime_min),0) AS down_min
                   FROM machines m
                   LEFT JOIN ifs_batch_tickets bt ON bt.machine_id = m.id AND bt.company_id=?
                   GROUP BY m.id""",
                (self.tenant.company_id,),
            ).fetchall())

    def utility_consumption(self) -> list[dict]:
        from application.manufacturing.energy import EnergyService
        return EnergyService(self.tenant).summary()

    def yield_analysis(self) -> list[dict]:
        with get_connection() as conn:
            return rows_to_list(conn.execute(
                """SELECT process_type, AVG(yield_pct) AS avg_yield, AVG(loss_pct) AS avg_loss,
                          COUNT(*) AS batch_count
                   FROM ifs_batch_tickets WHERE company_id=? AND status='completed'
                   GROUP BY process_type""",
                (self.tenant.company_id,),
            ).fetchall())

    def batch_history(self, batch_no: str) -> dict:
        with get_connection() as conn:
            ticket = conn.execute(
                "SELECT * FROM ifs_batch_tickets WHERE batch_no=? AND company_id=?",
                (batch_no, self.tenant.company_id),
            ).fetchone()
            if not ticket:
                return {}
            tid = ticket["id"]
            return {
                "ticket": dict(ticket),
                "trace": rows_to_list(conn.execute(
                    "SELECT * FROM ifs_batch_trace WHERE batch_ticket_id=?", (tid,)
                ).fetchall()),
                "cost": dict(conn.execute(
                    "SELECT * FROM ifs_cost_rollup WHERE batch_ticket_id=?", (tid,)
                ).fetchone() or {}),
                "qc": rows_to_list(conn.execute(
                    "SELECT * FROM ifs_qc_inspections WHERE batch_ticket_id=?", (tid,)
                ).fetchall()),
            }

    def production_register(self) -> list[dict]:
        with get_connection() as conn:
            return rows_to_list(conn.execute(
                """SELECT bt.ticket_no, bt.batch_no, bt.process_type, bt.planned_qty, bt.actual_qty,
                          bt.yield_pct, bt.shift, bt.status, bt.completed_at, m.name AS machine
                   FROM ifs_batch_tickets bt LEFT JOIN machines m ON bt.machine_id = m.id
                   WHERE bt.company_id=? ORDER BY bt.id DESC LIMIT 500""",
                (self.tenant.company_id,),
            ).fetchall())

    def maintenance_report(self) -> dict:
        from application.manufacturing.maintenance import PlantMaintenanceService
        return PlantMaintenanceService(self.tenant).downtime_analysis()
