# V17 Release Notes

**IFS Industrial ERP V17.0** — Enterprise Core Refactoring & Extensibility  
**Date:** 2026-07-04  
**Previous:** V16.0 Enterprise Platform Modernization  

## Highlights

### Technical debt program
- Automated debt scanner (`tools/debt_scanner.py`) → `TECHNICAL_DEBT_REPORT.md`
- Application layer expanded: rules, workflows, scripts, tenant enforcement
- UI/API directed to `application.services` (migration ongoing)

### Plugin framework
- `plugins/sdk.py` — extension SDK
- `plugins/` discovery folder with sample plugin
- Registers: menus, reports, jobs, API routes, events, workflows, validation, print templates

### Event-driven ERP
- Expanded event vocabulary (`domain/events.py`)
- Multi-subscriber dispatch, DB subscriptions, webhooks, plugin handlers

### Rule engine
- Configurable rules in `erp_business_rules`
- Categories: credit_limit, discount, tax, inventory, price

### Workflow designer
- JSON state machines in `erp_workflow_definitions`
- Admin-definable states, transitions, approvers, notifications

### Script engine
- Sandboxed AST-validated scripts (`application/scripts/sandbox.py`)
- Triggers: before/after save, post, print

### API maturity
- Customer full CRUD + pagination
- Rate limiting, webhooks, `/metrics` Prometheus
- Request/trace IDs, tenant middleware

### Multi-tenancy
- `application/tenant.py` — enforcement + coverage report
- API header `X-Company-ID` / `X-Branch-ID`

### Migration engine
- `infrastructure/migrations/engine.py` — dependency graph, history, verification

### Query optimizer
- `infrastructure/query_optimizer/analyzer.py` → `QUERY_OPTIMIZATION_REPORT.md`

### Observability
- Prometheus metrics, trace/request IDs, structured logs

### CI/CD
- GitHub Actions: `.github/workflows/ci.yml`

### Packaging
- `packaging/build_portable.bat`, `install/upgrade.py`

## Upgrade

```bash
python install/upgrade.py
python tools/generate_v17_reports.py
run_tests.bat
```

## Constraints honored
- No new business modules
- No UI redesign
- No workflow changes for end users
