# CI/CD Setup Guide — V17

## GitHub Actions

Workflow file: `.github/workflows/ci.yml`

### Triggers
- Push to `main`, `master`, `develop`
- Pull requests to `main`, `master`

### Jobs

**test**
1. Install `requirements.txt`
2. Verify migration dependency graph
3. Run `database.init_db()`
4. Run all test suites
5. Generate V17 reports
6. Run debt scanner

**lint**
- `python -m compileall` on platform packages

## Local equivalent

```batch
run_tests.bat
python tools/generate_v17_reports.py
python -c "from infrastructure.migrations.engine import verify_graph; ok,e=verify_graph(); print(ok,e)"
```

## Release packaging

```batch
packaging\build_portable.bat
```

Produces `dist/ifs-erp-v17-portable/`

## Upgrade in CI

Add step after tests:
```yaml
- run: python install/upgrade.py
```
