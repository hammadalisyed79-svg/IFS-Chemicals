# Developer Guide — V16.0

## Project layout

| Layer | Path | Responsibility |
|-------|------|----------------|
| Presentation | `erp_ui/`, `presentation/` | Streamlit UI only |
| Application | `application/` | Services, config, use cases |
| Domain | `domain/` | Events, tenant context |
| Infrastructure | `infrastructure/` | DB adapter, cache, jobs, events, logs |
| Services | `services/` | Documents, imports |
| API | `api/main.py` | REST endpoints |
| Security | `security/` | JWT |
| Integrations | `integrations/` | Connectors |
| Migrations | `db_v16.py`, `migrations/` | Schema versions |

## Adding a feature (platform rules)

1. Business logic → `application/services.py` or new `application/<module>_service.py`
2. Publish events → `infrastructure.events.bus.publish_simple()`
3. UI → call service only
4. API route → thin wrapper over service
5. Schema change → new `db_v17.py` + hook in `db_v3.apply_v3()`

## Running locally

```bash
streamlit run app.py
uvicorn api.main:app --reload --port 8600
python -m infrastructure.jobs.worker  # call process_jobs() from script/cron
```

## Testing

```bash
run_tests.bat
```

## Important: `database.py`

Do **not** create a `database/` Python package — it shadows `database.py`. Use `migrations/` for schema documentation.
