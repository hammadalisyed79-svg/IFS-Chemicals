# Known Issues — V17.3

Only verified open issues are listed. Fixed items removed after Health Check 2.0 pass.

## Open (from last health run)

- None — inventory guard skipped when `allow_negative_stock=1`; portal dispatch town required on submit only.

## Notes

- Playwright e2e skips when Chromium is not installed (`playwright install`).
- Party master balances: run **Administration → ERP Health Check → Audit & Fix All Customer/Supplier Ledgers** if outstanding reports disagree with ledgers.