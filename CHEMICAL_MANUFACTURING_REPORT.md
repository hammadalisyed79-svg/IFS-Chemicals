# Chemical Manufacturing Report — V17.1

**Date:** 2026-07-01

## Modules

| Module | Service | Process Types |
|--------|---------|---------------|
| Formulation | `FormulationService` | pilot, commercial, production |
| Batch Mfg | `BatchManufacturingService` | all process types |
| Spray Dryer | `SprayDryerService` | spray_dryer |
| Reactor | `ReactorService` | reactor, liquid_detergent, toilet_cleaner |
| Toll | `TollManufacturingService` | toll |

## Target Industries

Detergent Powder, Dishwash Bar, Liquid Detergents, Toilet Cleaner, Industrial Chemicals, Toll Manufacturing.

## Evidence

Test suite: `tests/test_v17_1_manufacturing.py` — PASS

```
PASS v17.1 tables
PASS formulation scaling
PASS spray dryer full cycle
PASS QC lab
PASS integration adapters
PASS corrugated gravure pet modules
PASS maintenance energy costing
PASS toll and warehouse
PASS dashboards and reports
All V17.1 manufacturing tests passed.
```

## Data Layer

- `ifs_batch_tickets`: 0 rows
- `ifs_breakdown_tickets`: 0 rows
- `ifs_corrugated_runs`: 0 rows
- `ifs_cost_rollup`: 0 rows
- `ifs_energy_readings`: 0 rows
- `ifs_formula_master`: 0 rows
- `ifs_gravure_runs`: 0 rows
- `ifs_integration_devices`: 8 rows
- `ifs_pet_blowing_runs`: 0 rows
- `ifs_pm_schedules`: 0 rows
- `ifs_qc_inspections`: 0 rows
- `ifs_reactor_batches`: 0 rows
- `ifs_spray_dryer_batches`: 0 rows
- `ifs_spray_dryer_temp_log`: 0 rows
- `ifs_toll_agreements`: 0 rows
- `ifs_warehouse_zones`: 6 rows
