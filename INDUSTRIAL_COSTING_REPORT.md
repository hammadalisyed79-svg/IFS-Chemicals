# Industrial Costing Report — V17.1

**Date:** 2026-07-01

## Cost Components

Material, Labour, Machine, Utility, Overhead, Factory Overhead, Packing, Freight.

## Outputs

`cost_per_kg`, `cost_per_carton`, `cost_per_bottle` in `ifs_cost_rollup`.

## Service

`IndustrialCostingService.calculate(batch_ticket_id)` — rolls up from production order + energy readings.

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
