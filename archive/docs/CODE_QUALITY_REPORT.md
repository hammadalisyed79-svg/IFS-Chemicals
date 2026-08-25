# Code Quality Report — V17.2

**Generated:** 2026-07-02 11:12:18
**Tool:** `tools/generate_v17_3_certification.py`

## Summary

| Metric | Count |
|--------|------:|
| Pass | 1 |
| Fail | 16 |
| Pass rate | 5.9% |

## Large Functions (>80 lines)

- `database.py:save_sale` — 166 lines
- `database.py:_migrate_legacy_data` — 165 lines
- `database.py:save_purchase` — 145 lines
- `db_v3.py:get_fiscal_close_checklist` — 96 lines
- `database.py:_append_customer_invoice_detail` — 88 lines
- `database.py:_append_supplier_invoice_detail` — 88 lines
- `db_v3.py:apply_v3` — 86 lines

## SQL Statement Counts

- SELECT: 859
- INSERT: 337
- UPDATE: 237
- DELETE: 77

## UI Direct DB

**453** patterns in erp_ui/

## Avg Complexity (db layers)

5.0 across 322 functions in database.py + db_v3.py

## V17.3

All items normalized to **PASS** or **FAIL** only.

## Detailed Results

| Status | Category | Check | Detail |
|--------|----------|-------|--------|
| fail | Complexity | database.py:_migrate_legacy_data | cyclomatic≈30 |
| fail | Complexity | database.py:search_purchases | cyclomatic≈16 |
| fail | Complexity | database.py:save_purchase | cyclomatic≈29 |
| fail | Complexity | database.py:search_sales_invoices | cyclomatic≈16 |
| fail | Complexity | database.py:save_sale | cyclomatic≈38 |
| fail | Complexity | database.py:_party_transfer_ledger_rows | cyclomatic≈16 |
| fail | Complexity | database.py:_append_customer_invoice_detail | cyclomatic≈24 |
| fail | Complexity | database.py:_append_supplier_invoice_detail | cyclomatic≈24 |
| fail | Complexity | database.py:_append_customer_other_ledger | cyclomatic≈16 |
| fail | Complexity | database.py:_append_supplier_other_ledger | cyclomatic≈16 |
| fail | Complexity | db_v3.py:update_production_order | cyclomatic≈22 |
| fail | Complexity | db_v3.py:rollback_production_completion | cyclomatic≈16 |
| fail | Complexity | db_v3.py:production_order_stock_check | cyclomatic≈20 |
| fail | Complexity | db_v3.py:get_finance_voucher | cyclomatic≈16 |
| fail | Complexity | db_v3.py:save_finance_attachment | cyclomatic≈16 |
| pass | Slow queries | Query log | 0 entries |
| fail | Duplicate Code | UI→DB coupling | 453 calls |