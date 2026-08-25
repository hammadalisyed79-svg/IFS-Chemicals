# Finance Certification Report — V17.3

**Generated:** 2026-07-02 11:12:18
**Tool:** `tools/generate_v17_3_certification.py`

## Summary

| Metric | Count |
|--------|------:|
| Pass | 11 |
| Fail | 5 |
| Pass rate | 68.8% |

## Verdict

**NOT CERTIFIED** — 11 pass, 5 fail (PASS/FAIL only).

## V17.3

All items normalized to **PASS** or **FAIL** only.

## Detailed Results

| Status | Category | Check | Detail |
|--------|----------|-------|--------|
| pass | Sales Invoice | Create | id=1 |
| pass | Sales Invoice | Submit | submit_sale_invoice |
| pass | Sales Invoice | Approve | approve_sale_invoice |
| pass | Sales Invoice | Post GL | post_sales_invoice_gl |
| pass | Purchase Invoice | Create | id=1 |
| fail | Journal Voucher | Create/Post | No stable automated JV path in CI suite |
| pass | Trial Balance | Generate | 28 rows |
| pass | GL | Debit/Credit balance | debit=360.00 credit=360.00 |
| pass | Cash Book | Standalone GL | Cash entry API present |
| pass | Bank Book | Standalone GL | Bank book query available |
| fail | Payroll Posting | GL integration | No automated payroll GL test |
| fail | Credit Note | Full lifecycle | Not in automated suite |
| fail | Debit Note | Full lifecycle | Not in automated suite |
| fail | Cash Flow | Report | No cash flow report automated |
| pass | Stock Adjustment | Post | 498.0→501.0 |
| pass | Production Posting | GL | See MANUFACTURING_CERTIFICATION.md |