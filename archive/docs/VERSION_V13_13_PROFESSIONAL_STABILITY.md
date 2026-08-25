# IFS Industrial ERP — V13.13 Professional Stability & Workflow Completion

**Release:** V13.13  
**Codename:** Professional Stability & Workflow Completion  
**Build:** 20260701  
**Previous:** V13.12  

## Overview

V13.13 upgrades the existing IFS Industrial ERP codebase with unified transaction validation, a central Draft / Pending Documents Center, workflow status columns, improved tax invoice charges, and a built-in ERP Health Check — without resetting live data.

## Key Changes

### 1. Global Transaction Validation (`erp_core/transaction_validation.py`)
- Customer required on sales documents; supplier required on purchase documents; warehouse on stock documents
- At least one line; item, qty > 0, rate > 0 where applicable
- Discount / tax negativity blocked
- Enforced on save (sales/purchase invoices and returns) and on invoice submit/approve workflow

### 2. Draft / Pending Documents Center (`erp_ui/draft_center.py`)
- Administration → **Draft Center**
- Tabs: All, Sales, Purchase, Inventory, Production
- Open, Delete, Approve, Print Preview actions
- Backed by `erp_draft_registry` table (auto-sync on invoice save)

### 3. Status & Workflow Columns (`db_v13_13.py`)
- Safe migration: `migrate_v13_13_professional_workflow_completion()`
- Adds `approval_status`, `updated_by/at`, `printed_count`, `last_printed_at` to transactional tables
- Sales/purchase charge fields: freight, loading, other charges, round off, grand weight
- Purchase: supplier bill no, claim input tax
- Never drops or resets user data

### 4. Sales / Purchase Tax Invoice UI
- Freight, loading, other charges, round off in tax summary
- Charges included in net total via `tax_engine.py`

### 5. Line Editing (`erp_ui/helpers.py`)
- Select line → edit qty/rate → Update or Remove
- Totals footer recalculates on change

### 6. ERP Health Check (`erp_ui/health_check.py`)
- Administration → **ERP Health Check**
- Validates login, mandatory party rules, blank invoice blocking, totals, draft registry, cash/bank book queries

### 7. Version Identity (`erp_version.py`)
- App title: **IFS Industrial ERP V13.13 Professional Stability & Workflow Completion**

## Database Migration

Migration runs automatically on startup via `db_v3.apply_v3()` → `migrate_v13_13_professional_workflow_completion()`.

Manual run (preserves data):

```python
import database as db
from db_v13_13 import migrate_v13_13_professional_workflow_completion
with db.get_connection() as conn:
    migrate_v13_13_professional_workflow_completion(conn, db)
    conn.commit()
```

## Login

- Username: `admin`
- Password: `admin123`

## Launch

```bat
RUN_SOFTWARE.bat
```

## Remaining Roadmap (post V13.13)

- Full lifecycle lock on all document types (orders, GRN, stock transfer, production)
- Unified atomic finance posting wrapper for all voucher types
- Cash/Bank book export CSV and drill-down enhancements
- HR payroll duplicate-month guard and finance posting
- Production module completion (BOM issue, WIP, QC, FG receipt)
- Keyboard shortcuts (F2, Ctrl+S, Ctrl+P, Ctrl+N)
- Extended audit trail on approve/post/print for all modules
