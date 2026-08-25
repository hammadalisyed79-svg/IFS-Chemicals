# IFS Industrial ERP — V13.14 Enterprise Workflow & Integration

**Release:** V13.14  
**Codename:** Enterprise Workflow & Integration  
**Build:** 20260702  
**Previous:** V13.13  

## Objective

V13.14 integrates existing commercial modules under one enterprise framework. No new ERP shell — the same desktop UI with consistent document lifecycle, search, open center, validation, printing, audit, and health checks.

## Part 1 — Global Document Framework

**Module:** `erp_core/transaction_engine.py`

All major document types register one `DocumentSpec` with shared hooks:

- Validation (via `erp_core/transaction_validation.py`)
- Search, get, save, delete, submit, approve, post
- Navigation target (group + screen)
- Editable status rules

Registered types include sales/purchase invoices & returns, orders, quotations, delivery notes, GRN, journal vouchers, production orders.

## Part 2 — Enterprise Search

**Modules:** `erp_core/enterprise_search.py`, `erp_ui/enterprise_search.py`

- Toolbar search on CEO Desktop and every module topbar
- Searches documents (invoices, orders, GRN, etc.) and masters (customer, supplier, item, employee, vehicle, machine, account)
- Click result → navigate and open document

## Part 3 — Document Open Center

**Module:** `erp_ui/document_hub.py`

Sales Invoices and Purchase Invoices include **Open Existing** tab:

- Open · Edit Draft · Duplicate · Delete Draft · Approve · Post · Print

Other document types use the same hub via `render_document_hub(doc_type, key_prefix)`.

## Part 4 — Line Entry Engine

**Module:** `erp_ui/line_entry_engine.py`

Unified grid wrapper over `smart_line_item_editor`:

- Insert, copy, paste, move up/down, duplicate row
- Stock availability warning when enabled
- Automatic totals refresh (inherited from tax engine)

## Part 5–7 — Masters, Accounting, Inventory

- Master screens unchanged; audit via `erp_core/services/audit_service.py`
- Posting service: `erp_core/services/posting.py`
- Real-time stock buckets: `erp_core/inventory_service.py` (available, reserved, ordered, in production, QC hold, damaged, returned)

## Part 8 — Approval Engine

**Module:** `erp_core/approval_engine.py`

- Table `erp_approval_rules` — configurable by document type, amount, warehouse, department, role, user, level
- Default rules seeded for sales/purchase invoices

## Part 9–10 — Print & PDF

**Module:** `erp_core/print_engine.py`

- Print log (`erp_print_log`), draft/reprint watermarks, signature block helpers
- Existing `document_print.py` / `report_print.py` unchanged; print count persisted when columns exist

## Part 11 — Dashboards

Business Overview dashboard retains CEO KPIs (today sales/purchases, cash, receivables, payables, inventory, production, attendance).

## Part 12 — Report Center

- Favorites (`erp_favorite_reports`)
- Recent reports (`erp_recent_reports`)
- Tree + search (existing catalog)

## Part 13 — Audit

- Extended `audit_log` columns: `machine_name`, `ip_address`, `old_values`, `new_values`
- `erp_core/services/audit_service.py` for enriched events

## Part 14–15 — Background Services & Performance

**Module:** `erp_core/maintenance.py`

On startup (when `auto_backup_on_start=1`):

- Auto backup, PRAGMA optimize, log cleanup, temp cleanup

## Part 16 — Error Handling

**Module:** `erp_core/error_handler.py`

- All module pages wrapped in try/except in `app.py`
- User-friendly message + `erp_error_log` entry
- Admin sees developer diagnostics expander

## Part 17–18 — Code Standardization

Shared packages under `erp_core/` and `erp_core/services/`.

## Part 19–20 — Enterprise Health Check

**Module:** `erp_ui/health_check.py`

- **Run Health Check** — core validation + schema
- **Run Enterprise QC (full)** — menus, scaffold scan, reports, approval rules
- Writes `HEALTH_CHECK_REPORT.md` on run

## Database Migration

```python
from db_v13_14 import migrate_v13_14_enterprise_workflow_integration
with db.get_connection() as conn:
    migrate_v13_14_enterprise_workflow_integration(conn, db)
```

Runs automatically via `db_v3.apply_v3()`.

## Launch

```bat
RUN_SOFTWARE.bat
```

Login: `admin` / `admin123`
