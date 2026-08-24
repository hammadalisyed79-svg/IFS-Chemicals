"""30-day factory simulation — subprocess per day for SQLite safety."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


def main():
    import database as db
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db.DB_PATH = __import__("pathlib").Path(path)
    db.reset_runtime_state()
    db.init_db()
    env = {**os.environ, "IFS_FACTORY_DB": path}
    try:
        with db.get_connection() as conn:
            conn.execute("INSERT INTO products(code,name,product_type,is_active) VALUES('RM-SIM','RM','raw',1)")
            conn.execute("INSERT INTO products(code,name,product_type,is_active) VALUES('FG-SIM','FG','finished',1)")
            rm = conn.execute("SELECT id FROM products WHERE code='RM-SIM'").fetchone()[0]
            fg = conn.execute("SELECT id FROM products WHERE code='FG-SIM'").fetchone()[0]
            wh = conn.execute("SELECT id FROM warehouses LIMIT 1").fetchone()[0]
            conn.execute("INSERT OR REPLACE INTO warehouse_stock(warehouse_id,product_id,quantity) VALUES(?,?,500000)", (wh, rm))
        from db_v3 import save_bom, approve_bom
        bom_id = save_bom({"finished_product_id": fg, "version_no": "1.0", "standard_output_qty": 100},
                          [{"raw_product_id": rm, "quantity": 40, "standard_cost": 1.0}])
        approve_bom(bom_id, 1)
        from application.manufacturing.formulation import FormulationService
        from domain.tenant import TenantContext
        FormulationService(TenantContext()).save_formula({
            "formula_code": "SIM-F1", "name": "Sim", "product_id": fg,
            "standard_batch_qty": 100, "lines": [{"product_id": rm, "pct": 100, "standard_cost": 1}],
        })

        errors = []
        for day in range(1, 31):
            r = subprocess.run(
                [sys.executable, os.path.join(ROOT, "tools", "v17_3", "factory_day.py"), str(day)],
                env=env, capture_output=True, text=True, cwd=ROOT,
            )
            if r.returncode != 0:
                errors.append(f"day {day}: {r.stderr[-200:]}")

        with db.get_connection() as conn:
            batches = conn.execute("SELECT COUNT(*) FROM ifs_batch_tickets WHERE status='completed'").fetchone()[0]
            dr, cr = conn.execute("SELECT COALESCE(SUM(debit),0), COALESCE(SUM(credit),0) FROM general_ledger").fetchone()

        if errors:
            print("FAIL factory simulation")
            for e in errors[:5]:
                print(e)
            sys.exit(1)
        if batches < 28:
            print(f"FAIL only {batches}/30 batches completed")
            sys.exit(1)
        if abs(float(dr) - float(cr)) > 1.0:
            print(f"FAIL GL imbalance {dr} vs {cr}")
            sys.exit(1)
        from db_v3 import get_trial_balance
        get_trial_balance()
        print(f"PASS 30-day simulation: {batches} batches, GL balanced")
    finally:
        os.unlink(path)


if __name__ == "__main__":
    main()
