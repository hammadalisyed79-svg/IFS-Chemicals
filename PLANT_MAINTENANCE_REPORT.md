# Plant Maintenance Report — V17.1

**Date:** 2026-07-01

## Features

- Preventive maintenance schedules (`ifs_pm_schedules`)
- Breakdown tickets (`ifs_breakdown_tickets`)
- Downtime analysis with MTTR (`PlantMaintenanceService.downtime_analysis`)

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
