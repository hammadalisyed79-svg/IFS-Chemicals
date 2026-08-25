# Disaster Recovery Guide — V16.0

## Backup strategy

| Asset | Location | Frequency |
|-------|----------|-----------|
| Database | `ifs_erp.db` | Daily minimum |
| Documents | `data/documents/` | With DB backup |
| Config | `erp_config` in DB | Included in DB |
| Logs | `logs/` | Optional archive |

Auto-backup on startup when `auto_backup_on_start=1`.

Manual backup: Administration → Backup & Restore, or copy `ifs_erp.db` to `backups/`.

## Recovery procedure

1. Stop ERP, portal, and API processes.
2. Restore `ifs_erp.db` from latest `backups/` file.
3. Restore `data/documents/` if document repository was used.
4. Run `python -c "import database as db; db.reset_runtime_state(); db.init_db()"`.
5. Verify via Health Check and `run_tests.bat`.

## Upgrade failure rollback

`python install/upgrade.py` automatically restores pre-upgrade backup on migration failure.

## RTO / RPO targets (recommended)

| Metric | Pilot | Enterprise |
|--------|-------|------------|
| RPO | 24 hours | 1 hour |
| RTO | 4 hours | 1 hour |

## Off-site backup

Copy `backups/*.db` to separate server or cloud storage daily. Never expose `.db` files via HTTP.
