# Installation Guide — V16.0

## Requirements

- Python 3.10+
- Windows Server or Linux
- 4 GB RAM minimum (8 GB recommended)

## Windows

```batch
install\windows_install.bat
```

Or manually:

```batch
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python -c "import database as db; db.init_db()"
```

**Run:**
- `RUN_SOFTWARE.bat` — Internal ERP
- `RUN_PORTAL.bat` — Distributor portal
- `RUN_API.bat` — REST API

## Linux

```bash
chmod +x install/linux_install.sh
./install/linux_install.sh
```

Production: follow `DEPLOYMENT_SERVER_GUIDE.md` (Nginx, systemd, UFW, SSL).

## First login

Default admin exists from seed. **Change password immediately** (8+ chars, letter + digit).

## Multi-company setup

1. ERP auto-creates company `DEFAULT` and branch `HO` on migration.
2. Add companies via API `GET/POST` (future) or SQL `erp_companies`.
3. Assign users in `erp_user_companies`.
4. Set `users.default_company_id` / `default_branch_id`.

## Data directory

| Path | Purpose |
|------|---------|
| `ifs_erp.db` | SQLite database |
| `data/documents/` | Document repository files |
| `backups/` | Auto and manual backups |
| `logs/` | Platform JSON logs |
