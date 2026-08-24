# Upgrade Guide — V15 → V16

## Before upgrade

1. **Backup** `ifs_erp.db` (copy to safe location).
2. Stop all running ERP/portal/API processes.
3. Note current version in System Settings or `schema_meta.erp_version`.

## Automated upgrade

```bash
python install/upgrade.py
```

This will:
1. Copy database to `backups/pre_upgrade_<timestamp>.db`
2. Run `init_db()` migrations (including `db_v16`)
3. Rollback on failure

## Manual upgrade

```bash
git pull   # or copy new files
pip install -r requirements.txt
python -c "import database as db; db.reset_runtime_state(); db.init_db()"
```

## V16 migration adds

- Multi-company/branch tables
- `erp_config` centralized settings
- Document repository, job queue, event store
- Integration connector registry
- Report designer storage
- `company_id` / `branch_id` on core tables (default 1)

## Post-upgrade verification

```bash
python tests/test_v16_platform.py
python tests/test_api_v1.py
python tests/test_portal_security.py
```

Run **ERP Health Check** from Administration — expect **100%**.

## Rollback

If upgrade fails, `install/upgrade.py` restores backup automatically.

Manual rollback:
```bash
copy backups\pre_upgrade_*.db ifs_erp.db
python -c "import database as db; db.reset_runtime_state()"
```

## Breaking changes

- None for V15 UI workflows
- New passwords created via User Management use PBKDF2 (existing passwords still work)
- `import database` must not conflict with a `database/` package folder (use `migrations/` for schema docs)
