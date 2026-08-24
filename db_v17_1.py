"""V17.1 — IFS Chemicals industrial manufacturing modules."""

from __future__ import annotations

import json


def _table_exists(conn, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _col_exists(conn, table: str, col: str) -> bool:
    if not _table_exists(conn, table):
        return False
    return col in [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _add_col(conn, table: str, col: str, ddl: str) -> None:
    if _table_exists(conn, table) and not _col_exists(conn, table, col):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


def _meta_get(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM schema_meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def _meta_set(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO schema_meta(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def migrate_v17_1_manufacturing(conn, db_module=None) -> None:
    from erp_version import SCHEMA_V17_1_KEY, SCHEMA_V17_1_VALUE

    if _meta_get(conn, SCHEMA_V17_1_KEY) == SCHEMA_V17_1_VALUE:
        return

    # ── Formulation management ──────────────────────────────────────────
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_formula_master (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            formula_code TEXT NOT NULL,
            name TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1,
            formula_type TEXT NOT NULL DEFAULT 'commercial',
            product_id INTEGER,
            effective_from TEXT,
            effective_to TEXT,
            status TEXT DEFAULT 'draft',
            approved_by INTEGER,
            approved_at TEXT,
            standard_batch_qty REAL DEFAULT 1000,
            tolerance_pct REAL DEFAULT 2,
            total_cost REAL DEFAULT 0,
            notes TEXT,
            company_id INTEGER DEFAULT 1,
            branch_id INTEGER,
            created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(formula_code, revision, company_id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_formula_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            formula_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            pct REAL NOT NULL,
            tolerance_pct REAL DEFAULT 2,
            qty_per_batch REAL,
            standard_cost REAL DEFAULT 0,
            line_cost REAL DEFAULT 0,
            sequence_no INTEGER DEFAULT 0,
            FOREIGN KEY(formula_id) REFERENCES ifs_formula_master(id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_formula_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            formula_id INTEGER NOT NULL,
            revision INTEGER NOT NULL,
            snapshot_json TEXT NOT NULL,
            changed_by INTEGER,
            changed_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    # ── Batch manufacturing ticket ──────────────────────────────────────
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_batch_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_no TEXT NOT NULL UNIQUE,
            production_order_id INTEGER,
            formula_id INTEGER,
            batch_no TEXT NOT NULL,
            process_type TEXT NOT NULL,
            planned_qty REAL NOT NULL,
            actual_qty REAL DEFAULT 0,
            expected_consumption REAL DEFAULT 0,
            actual_consumption REAL DEFAULT 0,
            variance_qty REAL DEFAULT 0,
            yield_pct REAL DEFAULT 0,
            loss_pct REAL DEFAULT 0,
            status TEXT DEFAULT 'open',
            qc_status TEXT DEFAULT 'pending',
            is_rework INTEGER DEFAULT 0,
            is_rejected INTEGER DEFAULT 0,
            operator_id INTEGER,
            shift TEXT,
            machine_id INTEGER,
            warehouse_id INTEGER,
            started_at TEXT,
            completed_at TEXT,
            production_time_min REAL DEFAULT 0,
            downtime_min REAL DEFAULT 0,
            notes TEXT,
            company_id INTEGER DEFAULT 1,
            branch_id INTEGER,
            created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_batch_reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_ticket_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            warehouse_id INTEGER,
            reserved_qty REAL NOT NULL,
            issued_qty REAL DEFAULT 0,
            status TEXT DEFAULT 'reserved',
            FOREIGN KEY(batch_ticket_id) REFERENCES ifs_batch_tickets(id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_batch_trace (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_ticket_id INTEGER NOT NULL,
            batch_no TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            direction TEXT NOT NULL,
            qty REAL NOT NULL,
            reference_type TEXT,
            reference_id INTEGER,
            recorded_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    # ── Spray dryer ─────────────────────────────────────────────────────
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_spray_dryer_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_ticket_id INTEGER NOT NULL,
            recipe_id INTEGER,
            slurry_tank TEXT,
            hot_air_temp_c REAL,
            outlet_temp_c REAL,
            moisture_pct REAL,
            bulk_density REAL,
            yield_qty REAL DEFAULT 0,
            production_loss REAL DEFAULT 0,
            steam_kg REAL DEFAULT 0,
            gas_m3 REAL DEFAULT 0,
            electricity_kwh REAL DEFAULT 0,
            stage TEXT DEFAULT 'charging',
            status TEXT DEFAULT 'in_progress',
            FOREIGN KEY(batch_ticket_id) REFERENCES ifs_batch_tickets(id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_spray_dryer_stages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            spray_batch_id INTEGER NOT NULL,
            stage_name TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            operator_id INTEGER,
            notes TEXT,
            FOREIGN KEY(spray_batch_id) REFERENCES ifs_spray_dryer_batches(id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_spray_dryer_temp_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            spray_batch_id INTEGER NOT NULL,
            logged_at TEXT DEFAULT CURRENT_TIMESTAMP,
            hot_air_temp_c REAL,
            outlet_temp_c REAL,
            FOREIGN KEY(spray_batch_id) REFERENCES ifs_spray_dryer_batches(id)
        )"""
    )

    # ── Chemical reactor ────────────────────────────────────────────────
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_reactor_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_ticket_id INTEGER NOT NULL,
            reactor_code TEXT,
            stage TEXT DEFAULT 'mixing',
            status TEXT DEFAULT 'in_progress',
            reaction_time_min REAL DEFAULT 0,
            FOREIGN KEY(batch_ticket_id) REFERENCES ifs_batch_tickets(id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_reactor_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reactor_batch_id INTEGER NOT NULL,
            logged_at TEXT DEFAULT CURRENT_TIMESTAMP,
            temperature_c REAL,
            pressure_bar REAL,
            rpm REAL,
            ph REAL,
            viscosity_cp REAL,
            density REAL,
            FOREIGN KEY(reactor_batch_id) REFERENCES ifs_reactor_batches(id)
        )"""
    )

    # ── Corrugated box ──────────────────────────────────────────────────
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_corrugated_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_ticket_id INTEGER NOT NULL,
            paper_gsm REAL,
            flute_type TEXT,
            board_size TEXT,
            waste_pct REAL DEFAULT 0,
            production_speed_mpm REAL DEFAULT 0,
            stage TEXT DEFAULT 'paper_issue',
            status TEXT DEFAULT 'in_progress',
            FOREIGN KEY(batch_ticket_id) REFERENCES ifs_batch_tickets(id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_corrugated_stages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            stage_name TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            operator_id INTEGER,
            FOREIGN KEY(run_id) REFERENCES ifs_corrugated_runs(id)
        )"""
    )

    # ── Gravure / flexible packaging ────────────────────────────────────
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_cylinder_master (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cylinder_code TEXT NOT NULL UNIQUE,
            artwork_revision TEXT,
            repeat_length_mm REAL,
            status TEXT DEFAULT 'active',
            company_id INTEGER DEFAULT 1
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_gravure_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_ticket_id INTEGER NOT NULL,
            cylinder_id INTEGER,
            film_micron REAL,
            ink_kg REAL DEFAULT 0,
            solvent_kg REAL DEFAULT 0,
            film_kg REAL DEFAULT 0,
            printing_speed_mpm REAL DEFAULT 0,
            waste_pct REAL DEFAULT 0,
            stage TEXT DEFAULT 'printing',
            status TEXT DEFAULT 'in_progress',
            FOREIGN KEY(batch_ticket_id) REFERENCES ifs_batch_tickets(id),
            FOREIGN KEY(cylinder_id) REFERENCES ifs_cylinder_master(id)
        )"""
    )

    # ── PET bottle blowing ──────────────────────────────────────────────
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_pet_blowing_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_ticket_id INTEGER NOT NULL,
            preform_product_id INTEGER,
            bottle_weight_g REAL,
            cycle_time_sec REAL,
            cavity_count INTEGER DEFAULT 1,
            reject_pct REAL DEFAULT 0,
            stage TEXT DEFAULT 'preform_issue',
            status TEXT DEFAULT 'in_progress',
            FOREIGN KEY(batch_ticket_id) REFERENCES ifs_batch_tickets(id)
        )"""
    )

    # ── QC laboratory ─────────────────────────────────────────────────
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_qc_specs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            spec_code TEXT NOT NULL,
            spec_name TEXT NOT NULL,
            inspection_type TEXT NOT NULL,
            company_id INTEGER DEFAULT 1,
            is_active INTEGER DEFAULT 1,
            UNIQUE(spec_code, company_id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_qc_parameters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            spec_id INTEGER NOT NULL,
            param_name TEXT NOT NULL,
            min_value REAL,
            max_value REAL,
            target_value REAL,
            uom TEXT,
            FOREIGN KEY(spec_id) REFERENCES ifs_qc_specs(id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_qc_inspections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inspection_no TEXT NOT NULL UNIQUE,
            inspection_type TEXT NOT NULL,
            batch_ticket_id INTEGER,
            product_id INTEGER,
            batch_no TEXT,
            status TEXT DEFAULT 'pending',
            result TEXT,
            approved_by INTEGER,
            approved_at TEXT,
            rejection_reason TEXT,
            is_retest INTEGER DEFAULT 0,
            retention_sample_ref TEXT,
            coa_no TEXT,
            company_id INTEGER DEFAULT 1,
            inspected_by INTEGER,
            inspected_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_qc_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inspection_id INTEGER NOT NULL,
            parameter_id INTEGER,
            param_name TEXT NOT NULL,
            measured_value REAL,
            passed INTEGER,
            FOREIGN KEY(inspection_id) REFERENCES ifs_qc_inspections(id)
        )"""
    )

    # ── Plant maintenance ───────────────────────────────────────────────
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_pm_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            machine_id INTEGER NOT NULL,
            schedule_type TEXT NOT NULL,
            frequency_days INTEGER DEFAULT 30,
            last_done_at TEXT,
            next_due_at TEXT,
            lubrication_points TEXT,
            spare_parts_json TEXT,
            company_id INTEGER DEFAULT 1,
            is_active INTEGER DEFAULT 1
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_breakdown_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_no TEXT NOT NULL UNIQUE,
            machine_id INTEGER NOT NULL,
            reported_at TEXT DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT,
            downtime_min REAL DEFAULT 0,
            technician_id INTEGER,
            cause TEXT,
            action_taken TEXT,
            status TEXT DEFAULT 'open',
            company_id INTEGER DEFAULT 1
        )"""
    )

    # ── Energy management ───────────────────────────────────────────────
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_energy_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_ticket_id INTEGER,
            machine_id INTEGER,
            department TEXT,
            utility_type TEXT NOT NULL,
            quantity REAL NOT NULL,
            uom TEXT NOT NULL,
            unit_cost REAL DEFAULT 0,
            total_cost REAL DEFAULT 0,
            recorded_at TEXT DEFAULT CURRENT_TIMESTAMP,
            company_id INTEGER DEFAULT 1
        )"""
    )

    # ── Industrial costing ──────────────────────────────────────────────
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_cost_rollup (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_ticket_id INTEGER NOT NULL,
            material_cost REAL DEFAULT 0,
            labour_cost REAL DEFAULT 0,
            machine_cost REAL DEFAULT 0,
            utility_cost REAL DEFAULT 0,
            overhead_cost REAL DEFAULT 0,
            factory_overhead REAL DEFAULT 0,
            packing_cost REAL DEFAULT 0,
            freight_cost REAL DEFAULT 0,
            total_cost REAL DEFAULT 0,
            cost_per_kg REAL DEFAULT 0,
            cost_per_carton REAL DEFAULT 0,
            cost_per_bottle REAL DEFAULT 0,
            calculated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(batch_ticket_id)
        )"""
    )

    # ── Toll manufacturing ────────────────────────────────────────────────
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_toll_agreements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agreement_no TEXT NOT NULL UNIQUE,
            customer_id INTEGER NOT NULL,
            formula_id INTEGER,
            customer_rm INTEGER DEFAULT 0,
            company_rm INTEGER DEFAULT 1,
            customer_packaging INTEGER DEFAULT 0,
            company_packaging INTEGER DEFAULT 1,
            manufacturing_charge REAL DEFAULT 0,
            charge_uom TEXT DEFAULT 'kg',
            effective_from TEXT,
            effective_to TEXT,
            status TEXT DEFAULT 'active',
            company_id INTEGER DEFAULT 1
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_toll_production (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agreement_id INTEGER NOT NULL,
            batch_ticket_id INTEGER NOT NULL,
            billed_qty REAL DEFAULT 0,
            billed_amount REAL DEFAULT 0,
            billing_status TEXT DEFAULT 'pending',
            FOREIGN KEY(agreement_id) REFERENCES ifs_toll_agreements(id),
            FOREIGN KEY(batch_ticket_id) REFERENCES ifs_batch_tickets(id)
        )"""
    )

    # ── Industrial warehouse zones ──────────────────────────────────────
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_warehouse_zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            warehouse_id INTEGER NOT NULL,
            zone_type TEXT NOT NULL,
            fifo_enforced INTEGER DEFAULT 1,
            fefo_enforced INTEGER DEFAULT 0,
            company_id INTEGER DEFAULT 1,
            UNIQUE(warehouse_id, zone_type)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_cycle_counts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            count_no TEXT NOT NULL UNIQUE,
            warehouse_id INTEGER NOT NULL,
            zone_type TEXT,
            count_date TEXT NOT NULL,
            status TEXT DEFAULT 'draft',
            counted_by INTEGER,
            company_id INTEGER DEFAULT 1
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_cycle_count_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_count_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            batch_no TEXT,
            system_qty REAL,
            counted_qty REAL,
            variance_qty REAL,
            FOREIGN KEY(cycle_count_id) REFERENCES ifs_cycle_counts(id)
        )"""
    )

    # ── Production downtime ─────────────────────────────────────────────
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_production_downtime (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_ticket_id INTEGER,
            machine_id INTEGER,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            duration_min REAL DEFAULT 0,
            reason TEXT,
            category TEXT DEFAULT 'unplanned'
        )"""
    )

    # ── Industrial integration registry ─────────────────────────────────
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_integration_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_code TEXT NOT NULL UNIQUE,
            device_type TEXT NOT NULL,
            adapter_class TEXT NOT NULL,
            config_json TEXT,
            is_active INTEGER DEFAULT 1,
            company_id INTEGER DEFAULT 1
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ifs_integration_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            reading_type TEXT NOT NULL,
            value_json TEXT NOT NULL,
            batch_ticket_id INTEGER,
            received_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(device_id) REFERENCES ifs_integration_devices(id)
        )"""
    )

    # Extend production_orders for industrial link
    _add_col(conn, "production_orders", "ifs_batch_ticket_id", "INTEGER")
    _add_col(conn, "production_orders", "process_type", "TEXT")
    _add_col(conn, "bom_formulas", "ifs_formula_id", "INTEGER")

    _seed_v17_1(conn)
    _meta_set(conn, SCHEMA_V17_1_KEY, SCHEMA_V17_1_VALUE)
    _meta_set(conn, "erp_version", "V17.1")


def _seed_v17_1(conn) -> None:
    """Seed QC specs, warehouse zones, integration adapters."""
    # QC specs for detergent powder
    if not conn.execute("SELECT 1 FROM ifs_qc_specs LIMIT 1").fetchone():
        conn.execute(
            """INSERT INTO ifs_qc_specs(spec_code,spec_name,inspection_type,company_id)
               VALUES('QC-FG-DET','Detergent Powder FG','finished_goods',1),
                      ('QC-IP-SLURRY','Slurry In-Process','in_process',1),
                      ('QC-INC-RM','Incoming Raw Material','incoming',1)"""
        )
        spec_fg = conn.execute("SELECT id FROM ifs_qc_specs WHERE spec_code='QC-FG-DET'").fetchone()[0]
        for name, mn, mx, tgt, uom in [
            ("Moisture %", 2.0, 5.0, 3.5, "%"),
            ("Bulk Density", 0.25, 0.45, 0.35, "g/ml"),
            ("pH", 7.0, 10.0, 9.0, ""),
            ("Active Matter %", 12.0, 20.0, 15.0, "%"),
        ]:
            conn.execute(
                """INSERT INTO ifs_qc_parameters(spec_id,param_name,min_value,max_value,target_value,uom)
                   VALUES(?,?,?,?,?,?)""",
                (spec_fg, name, mn, mx, tgt, uom),
            )

    # Warehouse zones from existing warehouses
    wh_rows = conn.execute("SELECT id FROM warehouses WHERE is_active=1").fetchall()
    zone_types = ("raw_material", "packaging", "wip", "finished_goods", "rejected", "scrap")
    for wh in wh_rows[:1]:
        for zt in zone_types:
            fifo = 1 if zt in ("raw_material", "finished_goods") else 0
            conn.execute(
                """INSERT OR IGNORE INTO ifs_warehouse_zones(warehouse_id,zone_type,fifo_enforced,fefo_enforced,company_id)
                   VALUES(?,?,?,?,?)""",
                (wh[0], zt, fifo, 0, 1),
            )

    # Generic integration device stubs (no vendor lock-in)
    adapters = [
        ("PLC-01", "plc", "integrations.industrial.plc.GenericPLCAdapter"),
        ("SCADA-01", "scada", "integrations.industrial.scada.GenericSCADAAdapter"),
        ("SCALE-01", "weighing_scale", "integrations.industrial.scale.GenericScaleAdapter"),
        ("BARCODE-01", "barcode_scanner", "integrations.industrial.scanner.GenericBarcodeAdapter"),
        ("QR-01", "qr_scanner", "integrations.industrial.scanner.GenericQRAdapter"),
        ("LABEL-01", "label_printer", "integrations.industrial.printer.GenericLabelPrinterAdapter"),
        ("THERMAL-01", "thermal_printer", "integrations.industrial.printer.GenericThermalPrinterAdapter"),
        ("SENSOR-01", "industrial_sensor", "integrations.industrial.sensor.GenericSensorAdapter"),
    ]
    for code, dtype, adapter in adapters:
        conn.execute(
            """INSERT OR IGNORE INTO ifs_integration_devices(device_code,device_type,adapter_class,config_json)
               VALUES(?,?,?,?)""",
            (code, dtype, adapter, json.dumps({"protocol": "generic", "host": "localhost"})),
        )

    # Default workflow for formula approval
    wf = conn.execute(
        "SELECT 1 FROM erp_workflow_definitions WHERE code='formula_approval' AND company_id=1"
    ).fetchone()
    if not wf:
        conn.execute(
            """INSERT INTO erp_workflow_definitions(code,name,doc_type,definition_json,company_id)
               VALUES('formula_approval','Formula Approval','ifs_formula',?,1)""",
            (json.dumps({
                "initial": "draft",
                "states": ["draft", "submitted", "approved", "rejected"],
                "transitions": [
                    {"from": "draft", "action": "submit", "to": "submitted"},
                    {"from": "submitted", "action": "approve", "to": "approved", "approver_role": "Production"},
                    {"from": "submitted", "action": "reject", "to": "rejected"},
                ],
            }),),
        )
