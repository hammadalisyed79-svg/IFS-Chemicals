# UAT Tracking — V17.2

**Generated:** 2026-07-02 11:12:18
**Tool:** `tools/generate_v17_3_certification.py`

## Summary

| Metric | Count |
|--------|------:|
| Pass | 3 |
| Fail | 0 |
| Pass rate | 100.0% |

## UAT Status Summary

- pending: 22

## Department Matrix

| Sales | 4 screens | pending |
| Purchase | 3 screens | pending |
| Inventory | 3 screens | pending |
| Production | 4 screens | pending |
| Finance | 3 screens | pending |
| HR | 3 screens | pending |
| Admin | 3 screens | pending |

## Instructions

Departments execute scenarios manually; update `erp_uat_runs.status` to pass/fail. No UI changes in V17.2 — tracking via database + this report.

## V17.3

All items normalized to **PASS** or **FAIL** only.

## Detailed Results

| Status | Category | Check | Detail |
|--------|----------|-------|--------|
| pass | UAT | Scenarios seeded | 23 scenarios |
| pass | UAT Mode | erp_uat_scenarios table | V17.2 migration |
| pass | UAT Mode | Department-wise tracking | 7 departments |