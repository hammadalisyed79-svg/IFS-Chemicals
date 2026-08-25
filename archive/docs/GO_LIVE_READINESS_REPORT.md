# Go-Live Readiness Report — V17.2

**Generated:** 2026-07-01 21:42:03
**Tool:** `tools/generate_v17_2_reports.py`

## Summary

| Metric | Count |
|--------|------:|
| Pass | 6 |
| Fail | 1 |
| Not certified / Skip | 0 |
| Pass rate (excl. skip) | 85.7% |

## Release Gate

| Functional Tests | PASS | functional: 21.0% pass, 0 fail |
| Finance Certified | PASS | finance: 50.0% pass, 0 fail |
| Manufacturing Certified | PASS | manufacturing: 100.0% pass, 0 fail |
| Warehouse Certified | PASS | warehouse: 85.7% pass, 0 fail |
| Security Certified | **FAIL** | security: 64.3% pass, 1 fail |
| Performance | PASS | performance: 85.7% pass, 0 fail |
| Database Healthy | PASS | database: 100.0% pass, 0 fail |

## Verdict

## NOT PRODUCTION READY

**6/7** gates passed.

- **Security Certified**: pass_rate=64.3% fails=1

## Detailed Results

| Status | Category | Check | Detail |
|--------|----------|-------|--------|
| pass | Gate | Functional Tests | functional: 21.0% pass, 0 fail |
| pass | Gate | Finance Certified | finance: 50.0% pass, 0 fail |
| pass | Gate | Manufacturing Certified | manufacturing: 100.0% pass, 0 fail |
| pass | Gate | Warehouse Certified | warehouse: 85.7% pass, 0 fail |
| fail | Gate | Security Certified | security: 64.3% pass, 1 fail |
| pass | Gate | Performance | performance: 85.7% pass, 0 fail |
| pass | Gate | Database Healthy | database: 100.0% pass, 0 fail |