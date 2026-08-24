"""V17.1 industrial manufacturing certification tests."""

from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _temp_db():
    import database as db
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db.DB_PATH = __import__("pathlib").Path(path)
    db.reset_runtime_state()
    db.init_db()
    return db, path


def _seed_product(db, code="RM-01", name="Soda Ash", ptype="raw"):
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO products(code,name,product_type,is_active) VALUES(?,?,?,1)",
            (code, name, ptype),
        )
        return conn.execute("SELECT id FROM products WHERE code=?", (code,)).fetchone()[0]


def _seed_finished(db, code="FG-DET", name="Detergent Powder"):
    return _seed_product(db, code, name, "finished")


def test_v17_1_tables():
    db, path = _temp_db()
    try:
        tables = (
            "ifs_formula_master", "ifs_batch_tickets", "ifs_spray_dryer_batches",
            "ifs_reactor_batches", "ifs_corrugated_runs", "ifs_gravure_runs",
            "ifs_pet_blowing_runs", "ifs_qc_inspections", "ifs_pm_schedules",
            "ifs_energy_readings", "ifs_cost_rollup", "ifs_toll_agreements",
            "ifs_warehouse_zones", "ifs_integration_devices",
        )
        with db.get_connection() as conn:
            for t in tables:
                assert conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone(), t
        print("PASS v17.1 tables")
    finally:
        os.unlink(path)


def test_formulation_and_scaling():
    db, path = _temp_db()
    try:
        rm = _seed_product(db)
        fg = _seed_finished(db)
        from application.manufacturing.formulation import FormulationService
        from domain.tenant import TenantContext
        svc = FormulationService(TenantContext(company_id=1))
        fid = svc.save_formula({
            "formula_code": "DET-01", "name": "Detergent Base", "formula_type": "commercial",
            "product_id": fg, "standard_batch_qty": 1000, "lines": [
                {"product_id": rm, "pct": 40, "standard_cost": 0.5},
                {"product_id": rm, "pct": 60, "standard_cost": 0.3},
            ],
        })
        scaled = svc.scale_formula(fid, 2000)
        assert len(scaled) == 2
        assert scaled[0]["scaled_qty"] == 800.0
        print("PASS formulation scaling")
    finally:
        os.unlink(path)


def test_spray_dryer_full_cycle():
    db, path = _temp_db()
    try:
        rm = _seed_product(db)
        fg = _seed_finished(db)
        from db_v3 import save_bom, approve_bom
        bom_id = save_bom({
            "finished_product_id": fg, "version_no": "1.0", "composition_type": "detergent",
            "standard_output_qty": 100,
        }, [{"raw_product_id": rm, "quantity": 40, "wastage_pct": 2, "standard_cost": 1.0}])
        approve_bom(bom_id, 1)
        from application.manufacturing.spray_dryer import SprayDryerService
        from application.manufacturing.formulation import FormulationService
        from domain.tenant import TenantContext
        tenant = TenantContext(company_id=1)
        fs = FormulationService(tenant)
        fid = fs.save_formula({
            "formula_code": "SD-01", "name": "Spray Dry Formula", "product_id": fg,
            "standard_batch_qty": 100, "lines": [{"product_id": rm, "pct": 100, "standard_cost": 1}],
        })
        sd = SprayDryerService(tenant)
        sd_id = sd.start_batch({
            "batch_no": "SD-BATCH-001", "planned_qty": 100, "formula_id": fid, "shift": "A",
        })
        sd.log_temperature(sd_id, 180, 85)
        sd.record_utilities(sd_id, steam_kg=50, gas_m3=10, electricity_kwh=200)
        detail = sd.get_batch_detail(sd_id)
        assert detail is not None
        assert len(detail.get("temp_log", [])) >= 1
        with db.get_connection() as conn:
            wh = conn.execute("SELECT id FROM warehouses LIMIT 1").fetchone()[0]
            conn.execute(
                "UPDATE ifs_batch_tickets SET warehouse_id=? WHERE batch_no=?", (wh, "SD-BATCH-001")
            )
            conn.execute(
                "INSERT OR REPLACE INTO warehouse_stock(warehouse_id,product_id,quantity) VALUES(?,?,?)",
                (wh, rm, 10000),
            )
        from application.manufacturing.batch import BatchManufacturingService
        row = sd.list_batches()[0]
        BatchManufacturingService(tenant).issue_materials(row["batch_ticket_id"], user_id=1)
        result = sd.complete_batch(sd_id, 95, 3.5, 0.35, 5, user_id=1)
        assert result["yield_pct"] > 0
        with db.get_connection() as conn:
            po = conn.execute(
                "SELECT status FROM production_orders WHERE batch_no=?", ("SD-BATCH-001",)
            ).fetchone()
            assert po and po[0] == "completed"
            stock = conn.execute(
                "SELECT quantity FROM warehouse_stock ws JOIN products p ON ws.product_id=p.id WHERE p.code=?",
                ("FG-DET",),
            ).fetchone()
            assert stock and float(stock[0]) >= 95
        print("PASS spray dryer full cycle")
    finally:
        os.unlink(path)


def test_qc_lab():
    db, path = _temp_db()
    try:
        from application.manufacturing.qc_lab import QCLabService
        from domain.tenant import TenantContext
        svc = QCLabService(TenantContext(company_id=1))
        specs = svc.list_specs("finished_goods")
        assert len(specs) >= 1
        iid = svc.create_inspection({"inspection_type": "finished_goods", "batch_no": "TEST-01"})
        params = specs[0]["parameters"][:2]
        results = [{
            "parameter_id": p["id"], "param_name": p["param_name"],
            "measured_value": p["target_value"], "min_value": p["min_value"], "max_value": p["max_value"],
        } for p in params]
        r = svc.record_results(iid, results)
        assert r["passed"]
        coa = svc.approve_coa(iid, 1)
        assert coa.startswith("COA")
        print("PASS QC lab")
    finally:
        os.unlink(path)


def test_integration_adapters():
    db, path = _temp_db()
    try:
        from integrations.industrial.base import load_adapter
        from integrations.industrial.plc import GenericPLCAdapter
        adapter = load_adapter("PLC-01")
        assert isinstance(adapter, GenericPLCAdapter)
        adapter.connect()
        reading = adapter.read()
        assert reading.reading_type == "plc_register"
        rid = adapter.persist_reading()
        assert rid > 0
        print("PASS integration adapters")
    finally:
        os.unlink(path)


def test_corrugated_gravure_pet():
    db, path = _temp_db()
    try:
        from domain.tenant import TenantContext
        tenant = TenantContext(company_id=1)
        from application.manufacturing.corrugated import CorrugatedService
        from application.manufacturing.gravure import GravureService
        from application.manufacturing.pet_blowing import PetBlowingService
        cr = CorrugatedService(tenant).start_run({
            "batch_no": "CG-001", "paper_gsm": 150, "flute_type": "B", "planned_qty": 500,
        })
        assert cr > 0
        gv = GravureService(tenant)
        cyl = gv.save_cylinder({"cylinder_code": "CYL-001", "repeat_length_mm": 500})
        gr = gv.start_run({"batch_no": "GV-001", "cylinder_id": cyl, "planned_qty": 200})
        assert gr > 0
        pet = PetBlowingService(tenant).start_run({
            "batch_no": "PET-001", "planned_qty": 5000, "cavity_count": 8,
        })
        assert pet > 0
        print("PASS corrugated gravure pet modules")
    finally:
        os.unlink(path)


def test_maintenance_energy_costing():
    db, path = _temp_db()
    try:
        from domain.tenant import TenantContext
        tenant = TenantContext(company_id=1)
        with __import__("database").get_connection() as conn:
            conn.execute("INSERT INTO machines(code,name,capacity) VALUES('M1','Line 1',1000)")
            mid = conn.execute("SELECT id FROM machines WHERE code='M1'").fetchone()[0]
        from application.manufacturing.maintenance import PlantMaintenanceService
        pm = PlantMaintenanceService(tenant)
        sid = pm.save_pm_schedule({"machine_id": mid, "schedule_type": "preventive", "frequency_days": 30})
        assert sid > 0
        from application.manufacturing.energy import EnergyService
        EnergyService(tenant).record(None, "steam", 100, "kg", machine_id=mid)
        from application.manufacturing.batch import BatchManufacturingService
        tid = BatchManufacturingService(tenant).create_ticket({
            "batch_no": "COST-01", "process_type": "spray_dryer", "planned_qty": 100,
        })
        from application.manufacturing.costing import IndustrialCostingService
        cost = IndustrialCostingService(tenant).calculate(tid)
        assert "total_cost" in cost
        print("PASS maintenance energy costing")
    finally:
        os.unlink(path)


def test_toll_and_warehouse():
    db, path = _temp_db()
    try:
        import database as dbmod
        from domain.tenant import TenantContext
        tenant = TenantContext(company_id=1)
        with dbmod.get_connection() as conn:
            conn.execute(
                "INSERT INTO customers(code,name,is_active) VALUES('C-TOLL','Toll Customer',1)"
            )
            cid = conn.execute("SELECT id FROM customers WHERE code='C-TOLL'").fetchone()[0]
        from application.manufacturing.toll import TollManufacturingService
        toll = TollManufacturingService(tenant)
        aid = toll.save_agreement({"customer_id": cid, "manufacturing_charge": 5.0})
        tid = toll.start_toll_production(aid, {"batch_no": "TOLL-01", "planned_qty": 200})
        assert tid > 0
        from application.manufacturing.warehouse import IndustrialWarehouseService
        wh_svc = IndustrialWarehouseService(tenant)
        zones = wh_svc.list_zones()
        assert len(zones) >= 1
        print("PASS toll and warehouse")
    finally:
        os.unlink(path)


def test_dashboards_and_reports():
    db, path = _temp_db()
    try:
        from domain.tenant import TenantContext
        tenant = TenantContext(company_id=1)
        from application.manufacturing.dashboards import IndustrialDashboardService
        from application.manufacturing.reports import IndustrialReportService
        dash = IndustrialDashboardService(tenant).ceo_dashboard()
        assert "plant" in dash
        rpt = IndustrialReportService(tenant).production_register()
        assert isinstance(rpt, list)
        print("PASS dashboards and reports")
    finally:
        os.unlink(path)


if __name__ == "__main__":
    test_v17_1_tables()
    test_formulation_and_scaling()
    test_spray_dryer_full_cycle()
    test_qc_lab()
    test_integration_adapters()
    test_corrugated_gravure_pet()
    test_maintenance_energy_costing()
    test_toll_and_warehouse()
    test_dashboards_and_reports()
    print("All V17.1 manufacturing tests passed.")
