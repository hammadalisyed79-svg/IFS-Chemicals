# CHANGELOG — V16.0

## V16.0 — Enterprise Platform Modernization (2026-07-03)

### Added — Architecture
- Layered platform: `presentation/`, `application/`, `domain/`, `infrastructure/`, `services/`, `reports/`, `security/`, `api/`, `integrations/`, `migrations/`
- Application services facade (`application/services.py`)
- Domain event bus (`infrastructure/events/`)
- Background job queue (`infrastructure/jobs/`)
- Structured JSON logging (`logs/ifs_platform.log`)
- Platform cache with domain invalidation

### Added — API
- FastAPI REST API `/api/v1/` with JWT auth
- Swagger UI at `/api/v1/docs`
- Endpoints: Customers, Suppliers, Products, Inventory, Sales, Purchase, Finance, Production, HR, Portal, Notifications, Health

### Added — Multi-company / branch
- `erp_companies`, `erp_branches`, `erp_user_companies`
- `company_id` / `branch_id` on core tables
- Default company + head office seeded

### Added — Platform services
- Document repository with versioning (`services/document_repository.py`)
- Import engine with batch audit (`services/import_engine.py`)
- Report designer storage (`reports/designer.py`)
- Integration connector framework (Shopify, WooCommerce, WhatsApp, bank APIs, etc.)

### Added — Configuration
- `erp_config` sectioned settings (database, email, SMS, security, tax, …)
- Environment variable override `IFS_<SECTION>_<KEY>`

### Added — Database abstraction
- `infrastructure/database/adapter.py` — SQLite + stubs for PostgreSQL/MySQL/SQL Server

### Added — Installer
- `install/windows_install.bat`, `install/linux_install.sh`, `install/upgrade.py`
- `RUN_API.bat`

### Added — Tests & docs
- `tests/test_v16_platform.py`, `tests/test_api_v1.py`
- Enterprise architecture, API, database dictionary, installation, upgrade guides
- PRODUCTION_CERTIFICATION.md, SECURITY_AUDIT_V16.md, LOAD_TEST_REPORT.md

### Changed
- `erp_version` → V16.0
- Health Check 2.0 — 82 checks including V16 platform validation
- `requirements.txt` — fastapi, uvicorn, python-jose, python-multipart

### Unchanged
- Streamlit UI (`app.py`, `erp_ui/`) — fully operational
- V15 distributor portal and security features
- SQLite as default production database
