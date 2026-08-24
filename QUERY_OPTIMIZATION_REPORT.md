# Query Optimization Report

**Slow queries logged:** 0
**Duplicate SQL patterns:** 20
**Missing index candidates:** 1
**N+1 hints (erp_ui):** 1

## Recommendations
- Add 1 recommended indexes
- Review 1 potential N+1 patterns in erp_ui
- Consolidate 20 duplicate SQL patterns

## Suggested indexes
```sql
CREATE INDEX IF NOT EXISTS idx_sales_invoices_sale_date ON sales_invoices(sale_date)
```

## N+1 review files
- erp_ui\health_check.py