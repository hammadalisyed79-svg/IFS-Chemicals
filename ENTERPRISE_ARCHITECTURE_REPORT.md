# ENTERPRISE ARCHITECTURE REPORT — V16.0

**IFS Industrial ERP**  
**Version:** V16.0 Enterprise Platform Modernization  
**Date:** 2026-07-03  

---

## Executive summary

V16 transforms the monolithic Streamlit/SQLite ERP into a **layered commercial platform** suitable for multi-company deployment, while preserving the existing V15 UI and workflows.

| Verdict | Status |
|---------|--------|
| Architecture refactor | **Foundation complete** |
| REST API `/api/v1/` | **Operational** |
| Automated health score | **100% (82/82)** |
| Production certification | **Conditional pass** — see PRODUCTION_CERTIFICATION.md |

---

## Layered architecture

```
presentation/     → Streamlit UI (erp_ui bridged)
application/      → Use cases, AppConfig, CustomerService, etc.
domain/           → Events, tenant context
infrastructure/   → DB adapter, cache, jobs, events, logging, metrics
services/         → Document repository, import engine
reports/          → Report designer
security/         → JWT authentication
api/              → FastAPI REST + OpenAPI
integrations/     → Vendor-agnostic connector framework
migrations/       → Schema version modules (db_v16.py, …)
tests/            → Unit, integration, API, portal tests
```

**Rule:** New code calls `application.services` — not `database.py` directly. Legacy `erp_ui/` remains operational during transition.

---

## Cross-cutting concerns

| Concern | Implementation |
|---------|----------------|
| Event bus | `infrastructure/events/bus.py` → `erp_domain_events` |
| Background jobs | `infrastructure/jobs/worker.py` → `erp_job_queue` |
| Configuration | `application/config.py` → `erp_config` + env vars |
| Caching | `infrastructure/cache/platform_cache.py` + `db_cache` |
| Observability | JSON logs, `erp_app_metrics`, `erp_slow_queries` |
| Multi-company | `erp_companies`, `erp_branches`, `company_id`/`branch_id` columns |
| Documents | `services/document_repository.py` + version table |

---

## Deployment topology

| Component | Port | Access |
|-----------|------|--------|
| Streamlit ERP | 8501 | localhost / Nginx |
| Distributor portal | 8502 | localhost / Nginx `/portal` |
| REST API | 8601 | localhost / Nginx `/api` |

---

## Migration path

- **SQLite:** production today
- **PostgreSQL / MySQL / SQL Server:** adapter stubs in `infrastructure/database/adapter.py`
- SQL translation helper for future migration scripts

---

## Technical debt (acknowledged)

- `database.py` / `db_v3.py` still contain business logic — incremental extraction to `application/`
- Full branch-wise numbering not yet enforced on all document types
- Load testing baseline only (see LOAD_TEST_REPORT.md)

---

## Scores

| Area | Score |
|------|------:|
| Architecture clarity | 78 |
| API completeness | 72 |
| Multi-tenancy readiness | 65 |
| Integration framework | 70 |
| Test coverage | 68 |
| Documentation | 85 |
| **Overall platform** | **73** |
