# Gravure / Flexible Packaging Module Report — V17.1

**Date:** 2026-07-01

## Features

- Cylinder master with artwork revision
- Ink, solvent, film consumption tracking
- Stages: printing, lamination, slitting, rewinding, packing
- Process types: `gravure`, `flexible_packaging`

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

## Tables

- `ifs_cylinder_master`, `ifs_gravure_runs`
