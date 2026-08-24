# Spray Dryer Module Certification — V17.1

**Date:** 2026-07-01  
**Product:** IFS Chemicals — Detergent Powder (Spray Dryer)

## Scope

Raw material charging through packing with temperature logging, utility capture, yield/moisture/bulk density, and inventory/GL integration via `BatchManufacturingService.issue_materials()` / `complete_batch()`.

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

## Schema

| Table | Rows |
|-------|-----:|
| ifs_spray_dryer_batches | 0 |
| ifs_spray_dryer_stages | seeded on use |
| ifs_spray_dryer_temp_log | 0 |

## Integration

- **Inventory:** `production_material_issues`, `production_finished_receipts`, `warehouse_stock`
- **Finance:** GL posting via `db_v3.complete_production` (WIP → FG)
- **QC:** `ifs_qc_inspections` linked by `batch_ticket_id`
- **Energy:** `ifs_energy_readings` via `SprayDryerService.record_utilities`

## Verdict

**CERTIFIED** — spray dryer full-cycle test passed.
