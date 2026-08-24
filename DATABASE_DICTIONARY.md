# Database Dictionary — V16.0

**Engine:** SQLite (default) · **File:** `ifs_erp.db`  
**Migrations:** `db_v3.py` … `db_v16.py` via `database.init_db()`

---

## V16 platform tables

### erp_companies
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Company ID |
| code | TEXT UNIQUE | Company code |
| name | TEXT | Display name |
| currency | TEXT | Default currency |
| is_active | INTEGER | Active flag |

### erp_branches
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Branch ID |
| company_id | FK | Parent company |
| code | TEXT | Branch code (unique per company) |
| is_head_office | INTEGER | HQ flag |

### erp_config
Sectioned configuration: `(section, key, value, company_id)`.

Sections: `database`, `email`, `sms`, `portal`, `security`, `tax`, `printing`, `approval`, `cache`.

### erp_documents / erp_document_versions
Document repository with version control. Categories: invoice, purchase_order, qc_report, coa, image, pdf, contract, employee.

### erp_job_queue
Background jobs: `job_type`, `payload` (JSON), `status`, `attempts`, retry support.

### erp_domain_events
Event store: `event_type`, `aggregate_type`, `aggregate_id`, `payload`, `processed`.

### erp_integration_connectors
External system connectors: `connector_type`, `config_json`.

### erp_report_designs
Saved report layouts: `layout_json`, `filters_json`, `role_codes`.

### erp_import_batches
Import audit trail with row counts and error log.

### erp_app_metrics / erp_slow_queries
Observability storage.

---

## Tenancy columns (V16)

Added to core tables: `company_id`, `branch_id` (default 1).

Tables: customers, suppliers, products, warehouses, sales_invoices, purchase_invoices, sales_orders, purchase_orders, chart_of_accounts, employees, portal_orders.

---

## V15 tables (retained)

portal_orders, price_lists, erp_notifications, login_attempts, role_permission_matrix, …

---

## Legacy core

See `schema.sql`, `schema_v3.sql` for full ERP schema (100+ tables).

---

## Indexes (V16)

- `idx_jobs_status` on erp_job_queue
- `idx_events_type` on erp_domain_events
- `idx_documents_ref` on erp_documents
- `idx_config_section` on erp_config
