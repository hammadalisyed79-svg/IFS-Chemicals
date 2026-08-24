"""IFS Chemicals — manufacturing services facade."""

from application.manufacturing.formulation import FormulationService
from application.manufacturing.batch import BatchManufacturingService
from application.manufacturing.spray_dryer import SprayDryerService
from application.manufacturing.reactor import ReactorService
from application.manufacturing.corrugated import CorrugatedService
from application.manufacturing.gravure import GravureService
from application.manufacturing.pet_blowing import PetBlowingService
from application.manufacturing.qc_lab import QCLabService
from application.manufacturing.maintenance import PlantMaintenanceService
from application.manufacturing.energy import EnergyService
from application.manufacturing.costing import IndustrialCostingService
from application.manufacturing.toll import TollManufacturingService
from application.manufacturing.warehouse import IndustrialWarehouseService
from application.manufacturing.reports import IndustrialReportService
from application.manufacturing.dashboards import IndustrialDashboardService

__all__ = [
    "FormulationService",
    "BatchManufacturingService",
    "SprayDryerService",
    "ReactorService",
    "CorrugatedService",
    "GravureService",
    "PetBlowingService",
    "QCLabService",
    "PlantMaintenanceService",
    "EnergyService",
    "IndustrialCostingService",
    "TollManufacturingService",
    "IndustrialWarehouseService",
    "IndustrialReportService",
    "IndustrialDashboardService",
]
