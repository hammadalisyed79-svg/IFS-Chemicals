"""Single factory simulation day — subprocess isolation to avoid SQLite locks."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


def main(day: int):
    import database as db
    path = os.environ.get("IFS_FACTORY_DB")
    if not path:
        raise SystemExit("IFS_FACTORY_DB not set")
    db.DB_PATH = __import__("pathlib").Path(path)
    from domain.tenant import TenantContext
    from application.manufacturing.spray_dryer import SprayDryerService
    from application.manufacturing.batch import BatchManufacturingService
    tenant = TenantContext(company_id=1)
    sd = SprayDryerService(tenant)
    batch_svc = BatchManufacturingService(tenant)
    bn = f"SIM-D{day:02d}"
    with db.get_connection() as conn:
        wh = conn.execute("SELECT id FROM warehouses LIMIT 1").fetchone()[0]
        fid = conn.execute("SELECT id FROM ifs_formula_master LIMIT 1").fetchone()
        fid = fid[0] if fid else None
    sd_id = sd.start_batch({"batch_no": bn, "planned_qty": 100, "shift": "A", "formula_id": fid})
    with db.get_connection() as conn:
        conn.execute("UPDATE ifs_batch_tickets SET warehouse_id=? WHERE batch_no=?", (wh, bn))
    row = next(r for r in sd.list_batches() if r.get("batch_no") == bn)
    batch_svc.issue_materials(row["batch_ticket_id"], user_id=1)
    sd.complete_batch(sd_id, 95, 3.5, 0.35, 5, user_id=1)
    print(f"day {day} ok")


if __name__ == "__main__":
    main(int(sys.argv[1]))
