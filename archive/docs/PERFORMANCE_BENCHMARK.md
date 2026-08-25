# Performance Benchmark — V17.2

**Generated:** 2026-07-02 11:12:18
**Tool:** `tools/generate_v17_3_certification.py`

## Summary

| Metric | Count |
|--------|------:|
| Pass | 7 |
| Fail | 0 |
| Pass rate | 100.0% |

## Metrics

- **startup_init_db_ms**: 1070.7
- **seed_ms**: 13.7
- **search_ms**: 87.52
- **cash_book_ms**: 9.15
- **trial_balance_ms**: 4.02
- **dashboard_ms**: 35.3
- **memory_mb**: 129.5

## Note

Set `PERF_SCALE=full` for target volumes (100k invoices — may take 30+ min). Default `quick` scale used for CI evidence.

## Verdict

**PERFORMANCE PASSED** at scale `quick`.

## V17.3

All items normalized to **PASS** or **FAIL** only.

## Detailed Results

| Status | Category | Check | Detail |
|--------|----------|-------|--------|
| pass | Startup | init_db | 1070.7ms |
| pass | Seed | Scale=quick | products=50 movements=500 gl_cap=5000 |
| pass | Search | enterprise_search | 87.52ms |
| pass | Reports | Cash book | 9.15ms |
| pass | Reports | Trial balance | 4.02ms |
| pass | Dashboard | CEO industrial | 35.3ms |
| pass | Memory | RSS | 129.5 MB |