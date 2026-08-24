"""Industrial dashboards — plant, production, quality, maintenance, energy, warehouse, costing, CEO."""

from __future__ import annotations

from application.services import BaseService
from application.manufacturing.reports import IndustrialReportService
from application.manufacturing.energy import EnergyService
from application.manufacturing.maintenance import PlantMaintenanceService
from application.manufacturing.costing import IndustrialCostingService
from database import get_connection


class IndustrialDashboardService(BaseService):
    def plant_dashboard(self) -> dict:
        with get_connection() as conn:
            active = conn.execute(
                "SELECT COUNT(*) FROM ifs_batch_tickets WHERE company_id=? AND status IN ('open','issued','in_progress')",
                (self.tenant.company_id,),
            ).fetchone()[0]
            completed_today = conn.execute(
                """SELECT COUNT(*) FROM ifs_batch_tickets WHERE company_id=? AND status='completed'
                   AND date(completed_at)=date('now')""",
                (self.tenant.company_id,),
            ).fetchone()[0]
        return {
            "active_batches": active,
            "completed_today": completed_today,
            "machine_utilization": IndustrialReportService(self.tenant).machine_utilization(),
        }

    def production_dashboard(self) -> dict:
        rpt = IndustrialReportService(self.tenant)
        return {
            "yield_by_process": rpt.yield_analysis(),
            "daily_production": rpt.daily_production(),
            "register_count": len(rpt.production_register()),
        }

    def quality_dashboard(self) -> dict:
        with get_connection() as conn:
            passed = conn.execute(
                "SELECT COUNT(*) FROM ifs_qc_inspections WHERE company_id=? AND result='passed'",
                (self.tenant.company_id,),
            ).fetchone()[0]
            failed = conn.execute(
                "SELECT COUNT(*) FROM ifs_qc_inspections WHERE company_id=? AND result='failed'",
                (self.tenant.company_id,),
            ).fetchone()[0]
            hold = conn.execute(
                "SELECT COUNT(*) FROM ifs_batch_tickets WHERE company_id=? AND qc_status='hold'",
                (self.tenant.company_id,),
            ).fetchone()[0]
        return {"passed": passed, "failed": failed, "qc_hold_batches": hold}

    def maintenance_dashboard(self) -> dict:
        return PlantMaintenanceService(self.tenant).downtime_analysis()

    def energy_dashboard(self) -> dict:
        return {"utilities": EnergyService(self.tenant).summary()}

    def warehouse_dashboard(self) -> dict:
        from application.manufacturing.warehouse import IndustrialWarehouseService
        return {"zones": IndustrialWarehouseService(self.tenant).list_zones()}

    def costing_dashboard(self) -> dict:
        return {"variance": IndustrialCostingService(self.tenant).variance_report()[:20]}

    def ceo_dashboard(self) -> dict:
        return {
            "plant": self.plant_dashboard(),
            "production": self.production_dashboard(),
            "quality": self.quality_dashboard(),
            "energy": self.energy_dashboard(),
            "costing": self.costing_dashboard(),
        }
