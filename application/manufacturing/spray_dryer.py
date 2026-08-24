"""Spray dryer production — detergent powder manufacturing."""

from __future__ import annotations

from application.services import BaseService
from application.manufacturing.batch import BatchManufacturingService
from database import get_connection, rows_to_list, now
from infrastructure.events.bus import publish_simple
from domain import events as E

SPRAY_STAGES = (
    "raw_material_charging", "slurry_preparation", "slurry_tank", "homogenization",
    "spray_drying", "bulk_collection", "sieving", "post_dosing", "perfume_addition", "packing",
)


class SprayDryerService(BaseService):
    def list_batches(self) -> list[dict]:
        with get_connection() as conn:
            return rows_to_list(conn.execute(
                """SELECT sd.*, bt.ticket_no, bt.batch_no, bt.shift, bt.operator_id
                   FROM ifs_spray_dryer_batches sd
                   JOIN ifs_batch_tickets bt ON sd.batch_ticket_id = bt.id
                   WHERE bt.company_id=? ORDER BY sd.id DESC""",
                (self.tenant.company_id,),
            ).fetchall())

    def start_batch(self, data: dict, user_id: int | None = None) -> int:
        batch_svc = BatchManufacturingService(self.tenant)
        data.setdefault("process_type", "spray_dryer")
        tid = batch_svc.create_ticket(data, user_id)
        with get_connection() as conn:
            cur = conn.execute(
                """INSERT INTO ifs_spray_dryer_batches(
                    batch_ticket_id, recipe_id, slurry_tank, stage, status
                ) VALUES(?,?,?,?,?)""",
                (tid, data.get("formula_id"), data.get("slurry_tank"), "raw_material_charging", "in_progress"),
            )
            sd_id = cur.lastrowid
            conn.execute(
                "INSERT INTO ifs_spray_dryer_stages(spray_batch_id, stage_name, started_at, operator_id) VALUES(?,?,?,?)",
                (sd_id, "raw_material_charging", now(), user_id),
            )
        publish_simple(E.SPRAY_DRYER_STARTED, aggregate_type="spray_dryer", aggregate_id=sd_id, user_id=user_id)
        return sd_id

    def advance_stage(self, spray_batch_id: int, stage_name: str, user_id: int | None = None) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE ifs_spray_dryer_stages SET completed_at=? WHERE spray_batch_id=? AND completed_at IS NULL",
                (now(), spray_batch_id),
            )
            conn.execute(
                "INSERT INTO ifs_spray_dryer_stages(spray_batch_id, stage_name, started_at, operator_id) VALUES(?,?,?,?)",
                (spray_batch_id, stage_name, now(), user_id),
            )
            conn.execute(
                "UPDATE ifs_spray_dryer_batches SET stage=? WHERE id=?", (stage_name, spray_batch_id),
            )

    def log_temperature(self, spray_batch_id: int, hot_air: float, outlet: float) -> None:
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO ifs_spray_dryer_temp_log(spray_batch_id, hot_air_temp_c, outlet_temp_c)
                   VALUES(?,?,?)""",
                (spray_batch_id, hot_air, outlet),
            )
            conn.execute(
                "UPDATE ifs_spray_dryer_batches SET hot_air_temp_c=?, outlet_temp_c=? WHERE id=?",
                (hot_air, outlet, spray_batch_id),
            )

    def record_utilities(self, spray_batch_id: int, steam_kg: float = 0, gas_m3: float = 0,
                         electricity_kwh: float = 0) -> None:
        tid = None
        with get_connection() as conn:
            conn.execute(
                """UPDATE ifs_spray_dryer_batches SET steam_kg=steam_kg+?, gas_m3=gas_m3+?, electricity_kwh=electricity_kwh+?
                   WHERE id=?""",
                (steam_kg, gas_m3, electricity_kwh, spray_batch_id),
            )
            row = conn.execute(
                "SELECT batch_ticket_id FROM ifs_spray_dryer_batches WHERE id=?", (spray_batch_id,)
            ).fetchone()
            tid = row[0] if row else None
        if tid:
            from application.manufacturing.energy import EnergyService
            es = EnergyService(self.tenant)
            if steam_kg:
                es.record(tid, "steam", steam_kg, "kg")
            if gas_m3:
                es.record(tid, "gas", gas_m3, "m3")
            if electricity_kwh:
                es.record(tid, "electricity", electricity_kwh, "kWh")

    def complete_batch(self, spray_batch_id: int, yield_qty: float, moisture_pct: float,
                       bulk_density: float, production_loss: float = 0, wastage_qty: float = 0,
                       qc_status: str = "Pending", user_id: int | None = None) -> dict:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT batch_ticket_id FROM ifs_spray_dryer_batches WHERE id=?", (spray_batch_id,)
            ).fetchone()
            if not row:
                raise ValueError("Spray dryer batch not found")
            tid = row[0]
            conn.execute(
                """UPDATE ifs_spray_dryer_batches SET yield_qty=?, moisture_pct=?, bulk_density=?,
                   production_loss=?, stage='packing', status='completed' WHERE id=?""",
                (yield_qty, moisture_pct, bulk_density, production_loss, spray_batch_id),
            )
        batch_svc = BatchManufacturingService(self.tenant)
        result = batch_svc.complete_batch(tid, yield_qty, wastage_qty, qc_status, user_id)
        publish_simple(E.SPRAY_DRYER_COMPLETED, aggregate_type="spray_dryer", aggregate_id=spray_batch_id,
                       user_id=user_id, payload={"yield_qty": yield_qty, "moisture_pct": moisture_pct})
        return result

    def get_batch_detail(self, spray_batch_id: int) -> dict | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM ifs_spray_dryer_batches WHERE id=?", (spray_batch_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["stages"] = rows_to_list(conn.execute(
                "SELECT * FROM ifs_spray_dryer_stages WHERE spray_batch_id=? ORDER BY id", (spray_batch_id,)
            ).fetchall())
            d["temp_log"] = rows_to_list(conn.execute(
                "SELECT * FROM ifs_spray_dryer_temp_log WHERE spray_batch_id=? ORDER BY logged_at", (spray_batch_id,)
            ).fetchall())
            return d
