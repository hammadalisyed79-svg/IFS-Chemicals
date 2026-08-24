# Database Health Report — V17.2

**Generated:** 2026-07-02 11:12:18
**Tool:** `tools/generate_v17_3_certification.py`

## Summary

| Metric | Count |
|--------|------:|
| Pass | 11 |
| Fail | 0 |
| Pass rate | 100.0% |

## Verdict

**DATABASE HEALTHY** — 0 failures.

## V17.3

All items normalized to **PASS** or **FAIL** only.

## Detailed Results

| Status | Category | Check | Detail |
|--------|----------|-------|--------|
| pass | Integrity | Foreign keys ON | PRAGMA foreign_keys=1 |
| pass | Schema | Table count | 167 tables |
| pass | Indexes | Count | 92 indexes |
| pass | Orphans | sales_invoice_items→sales_invoices | count=0 |
| pass | Orphans | purchase_invoice_items→purchase_invoices | count=0 |
| pass | Orphans | bom_formula_lines→bom_formulas | count=0 |
| pass | Duplicates | sales_invoices | 0 dup keys |
| pass | Duplicates | customers | 0 dup keys |
| pass | SQLite | integrity_check | ok |
| pass | Migrations | History rows | 0 |
| pass | Migrations | Dependency graph | [] |