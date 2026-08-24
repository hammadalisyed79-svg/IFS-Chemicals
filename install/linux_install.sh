#!/bin/bash
# IFS ERP V16 Linux deployment helper
set -e
cd "$(dirname "$0")/.."
echo "=== IFS Industrial ERP V16 Linux Install ==="
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python -c "import database as db; db.init_db(); import erp_version; print('Migrated to', erp_version.APP_VERSION)"
echo "See DEPLOYMENT_SERVER_GUIDE.md for Nginx/systemd setup."
