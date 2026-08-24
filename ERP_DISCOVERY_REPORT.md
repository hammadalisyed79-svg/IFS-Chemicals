# ERP Discovery Report — V17.2

**Generated:** 2026-07-02 11:12:18
**Tool:** `tools/generate_v17_3_certification.py`

## Summary

| Metric | Count |
|--------|------:|
| Pass | 99 |
| Fail | 24 |
| Pass rate | 80.5% |

## API Routes

**24** endpoints in `api/main.py`

## Application Layer

**23** Python modules under `application/`

## Events

**31** domain events in `domain/events.py`

## Plugins

**1** plugin packages in `plugins/`

## Migrations

**10** nodes in migration graph

## Background Jobs

**1** job modules

## UI Page Functions

**86** `page_*` functions in `erp_ui/`

## Technical Debt Signal

**453** direct DB call patterns in `erp_ui/` (business logic not fully in application layer)

## Reports

**0** report profiles registered

## Implemented vs Gaps

| Area | Implemented | Gaps |
|------|------------:|------|
| Screens (nav) | 75 | 0 missing routes |
| PAGES entries | 100 | 23 hidden/alias |
| API endpoints | 24 | Partial CRUD (customers only full) |
| Industrial modules | 15 | Service-layer certified; UI print/export not automated |


## V17.3

All items normalized to **PASS** or **FAIL** only.

## Detailed Results

| Status | Category | Check | Detail |
|--------|----------|-------|--------|
| pass | Screen | Industrial Dashboards | Routed in PAGES |
| pass | Screen | Quotations | Routed in PAGES |
| pass | Screen | Production Orders | Routed in PAGES |
| pass | Screen | Corrugated Production | Routed in PAGES |
| pass | Screen | Industrial Warehouse | Routed in PAGES |
| pass | Screen | Dashboard | Routed in PAGES |
| pass | Screen | Sale Approval | Routed in PAGES |
| pass | Screen | Customer Receipt | Routed in PAGES |
| pass | Screen | Draft Center | Routed in PAGES |
| pass | Screen | PET Bottle Blowing | Routed in PAGES |
| pass | Screen | Weight Entry | Routed in PAGES |
| pass | Screen | Weight Reports | Routed in PAGES |
| pass | Screen | Stock | Routed in PAGES |
| pass | Screen | Employee Ledger | Routed in PAGES |
| pass | Screen | Sales Returns | Routed in PAGES |
| pass | Screen | Business Overview | Routed in PAGES |
| pass | Screen | Toll Manufacturing | Routed in PAGES |
| pass | Screen | Price Lists | Routed in PAGES |
| pass | Screen | Reports Center | Routed in PAGES |
| pass | Screen | QC Laboratory | Routed in PAGES |
| pass | Screen | Industrial Reports | Routed in PAGES |
| pass | Screen | Employee Advances | Routed in PAGES |
| pass | Screen | Spray Dryer | Routed in PAGES |
| pass | Screen | Cash Book | Routed in PAGES |
| pass | Screen | Gate Pass Entry | Routed in PAGES |
| pass | Screen | Attendance | Routed in PAGES |
| pass | Screen | Distributor Orders | Routed in PAGES |
| pass | Screen | Roles & Permissions | Routed in PAGES |
| pass | Screen | Purchase Orders | Routed in PAGES |
| pass | Screen | Sales Orders | Routed in PAGES |
| pass | Screen | Batch Manufacturing | Routed in PAGES |
| pass | Screen | Journal Voucher | Routed in PAGES |
| pass | Screen | Plant Maintenance | Routed in PAGES |
| pass | Screen | Supplier Ledger | Routed in PAGES |
| pass | Screen | Holidays | Routed in PAGES |
| pass | Screen | Purchase Invoices | Routed in PAGES |
| pass | Screen | Suppliers | Routed in PAGES |
| pass | Screen | GRN | Routed in PAGES |
| pass | Screen | Supplier Payment | Routed in PAGES |
| pass | Screen | Sales Invoices | Routed in PAGES |
| pass | Screen | Chemical Reactor | Routed in PAGES |
| pass | Screen | Gravure / Packaging | Routed in PAGES |
| pass | Screen | Trial Balance | Routed in PAGES |
| pass | Screen | Payroll | Routed in PAGES |
| pass | Screen | Audit Log | Routed in PAGES |
| pass | Screen | Warehouses | Routed in PAGES |
| pass | Screen | Profit & Loss Report | Routed in PAGES |
| pass | Screen | Employees | Routed in PAGES |
| pass | Screen | Customers | Routed in PAGES |
| pass | Screen | Stock Report | Routed in PAGES |
| pass | Screen | BOM | Routed in PAGES |
| pass | Screen | Expense Payment | Routed in PAGES |
| pass | Screen | Balance Sheet | Routed in PAGES |
| pass | Screen | User Management | Routed in PAGES |
| pass | Screen | Customer Ledger | Routed in PAGES |
| pass | Screen | Approval Designer | Routed in PAGES |
| pass | Screen | ERP Health Check | Routed in PAGES |
| pass | Screen | Leave Management | Routed in PAGES |
| pass | Screen | Mobile Approvals | Routed in PAGES |
| pass | Screen | Stock Adjustments | Routed in PAGES |
| pass | Screen | Party Transfer | Routed in PAGES |
| pass | Screen | Bank Book | Routed in PAGES |
| pass | Screen | Fiscal Year Closing | Routed in PAGES |
| pass | Screen | System Settings | Routed in PAGES |
| pass | Screen | Machines | Routed in PAGES |
| pass | Screen | Purchase Returns | Routed in PAGES |
| pass | Screen | Purchase Approval | Routed in PAGES |
| pass | Screen | Energy Management | Routed in PAGES |
| pass | Screen | Backup & Restore | Routed in PAGES |
| pass | Screen | Industrial Costing | Routed in PAGES |
| pass | Screen | Products | Routed in PAGES |
| pass | Screen | Chart of Accounts | Routed in PAGES |
| pass | Screen | Job Cards | Routed in PAGES |
| pass | Screen | Formula Master | Routed in PAGES |
| pass | Screen | Account & Item Groups | Routed in PAGES |
| fail | Screen | Batch Stock | In PAGES but not in NAV_GROUPS (hidden/alias) |
| fail | Screen | Custom Groups | In PAGES but not in NAV_GROUPS (hidden/alias) |
| fail | Screen | Customer Outstanding | In PAGES but not in NAV_GROUPS (hidden/alias) |
| fail | Screen | Delivery Notes | In PAGES but not in NAV_GROUPS (hidden/alias) |
| fail | Screen | Employee Master | In PAGES but not in NAV_GROUPS (hidden/alias) |
| fail | Screen | Gate Pass Reports | In PAGES but not in NAV_GROUPS (hidden/alias) |
| fail | Screen | General Ledger | In PAGES but not in NAV_GROUPS (hidden/alias) |
| fail | Screen | HR Reports | In PAGES but not in NAV_GROUPS (hidden/alias) |
| fail | Screen | Inventory | In PAGES but not in NAV_GROUPS (hidden/alias) |
| fail | Screen | Payment Terms | In PAGES but not in NAV_GROUPS (hidden/alias) |
| fail | Screen | Product Categories | In PAGES but not in NAV_GROUPS (hidden/alias) |
| fail | Screen | Purchase Requisition | In PAGES but not in NAV_GROUPS (hidden/alias) |
| fail | Screen | Purchase Return | In PAGES but not in NAV_GROUPS (hidden/alias) |
| fail | Screen | Purchases | In PAGES but not in NAV_GROUPS (hidden/alias) |
| fail | Screen | Sale Return | In PAGES but not in NAV_GROUPS (hidden/alias) |
| fail | Screen | Sales | In PAGES but not in NAV_GROUPS (hidden/alias) |
| fail | Screen | Stock Transfers | In PAGES but not in NAV_GROUPS (hidden/alias) |
| fail | Screen | Supplier Outstanding | In PAGES but not in NAV_GROUPS (hidden/alias) |
| fail | Screen | Tax Rates | In PAGES but not in NAV_GROUPS (hidden/alias) |
| fail | Screen | Tax Report | In PAGES but not in NAV_GROUPS (hidden/alias) |
| fail | Screen | Units of Measure | In PAGES but not in NAV_GROUPS (hidden/alias) |
| fail | Screen | Vehicles | In PAGES but not in NAV_GROUPS (hidden/alias) |
| fail | Screen | Weight Slips | In PAGES but not in NAV_GROUPS (hidden/alias) |
| pass | API | POST /api/v1/auth/token | Declared |
| pass | API | GET /api/v1/health | Declared |
| pass | API | GET /metrics | Declared |
| pass | API | GET /api/v1/customers | Declared |
| pass | API | GET /api/v1/customers/{customer_id} | Declared |
| pass | API | POST /api/v1/customers | Declared |
| pass | API | PUT /api/v1/customers/{customer_id} | Declared |
| pass | API | DELETE /api/v1/customers/{customer_id} | Declared |
| pass | API | GET /api/v1/suppliers | Declared |
| pass | API | GET /api/v1/products | Declared |
| pass | API | GET /api/v1/inventory | Declared |
| pass | API | GET /api/v1/sales/invoices | Declared |
| pass | API | GET /api/v1/purchase/invoices | Declared |
| pass | API | GET /api/v1/finance/trial-balance | Declared |
| pass | API | GET /api/v1/production/orders | Declared |
| pass | API | GET /api/v1/hr/employees | Declared |
| pass | API | GET /api/v1/notifications | Declared |
| pass | API | GET /api/v1/companies | Declared |
| pass | API | GET /api/v1/rules | Declared |
| pass | API | GET /api/v1/workflows | Declared |
| pass | API | GET /api/v1/plugins | Declared |
| pass | API | GET /api/v1/tenant/coverage | Declared |
| pass | API | POST /api/v1/webhooks | Declared |
| pass | API | POST /api/v1/jobs/process | Declared |
| fail | Architecture | UI direct DB access | 453 patterns — migration incomplete |