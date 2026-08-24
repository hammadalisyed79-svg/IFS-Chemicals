"""PET bottle blowing production."""

from __future__ import annotations

from application.services import BaseService
from application.manufacturing.batch import BatchManufacturingService
from database import get_connection, rows_to_list
from infrastructure.events.bus import publish_simple
from domain import events as E

PET_STAGES = ("preform_issue", "heating", "blowing", "cooling", "inspection", "packing")


class PetBlowingService(BaseService):
    def list_runs(self) -> list[dict]:
        with get_connection() as conn:
            return rows_to_list(conn.execute(
                """SELECT pb.*, bt.ticket_no, bt.batch_no, p.name AS preform_name
                   FROM ifs_pet_blowing_runs pb
                   JOIN ifs_batch_tickets bt ON pb.batch_ticket_id = bt.id
                   LEFT JOIN products p ON pb.preform_product_id = p.id
                   WHERE bt.company_id=? ORDER BY pb.id DESC""",
                (self.tenant.company_id,),
            ).fetchall())

    def start_run(self, data: dict, user_id: int | None = None) -> int:
        batch_svc = BatchManufacturingService(self.tenant)
        data.setdefault("process_type", "pet_blowing")
        tid = batch_svc.create_ticket(data, user_id)
        with get_connection() as conn:
            cur = conn.execute(
                """INSERT INTO ifs_pet_blowing_runs(
                    batch_ticket_id, preform_product_id, bottle_weight_g, cavity_count, stage, status
                ) VALUES(?,?,?,?,?,?)""",
                (tid, data.get("preform_product_id"), data.get("bottle_weight_g"),
                 data.get("cavity_count", 1), "preform_issue", "in_progress"),
            )
            return cur.lastrowid

    def advance_stage(self, run_id: int, stage: str, cycle_time_sec: float | None = None) -> None:
        with get_connection() as conn:
            if cycle_time_sec is not None:
                conn.execute(
                    "UPDATE ifs_pet_blowing_runs SET stage=?, cycle_time_sec=? WHERE id=?",
                    (stage, cycle_time_sec, run_id),
                )
            else:
                conn.execute("UPDATE ifs_pet_blowing_runs SET stage=? WHERE id=?", (stage, run_id))

    def complete_run(self, run_id: int, actual_qty: float, reject_pct: float = 0,
                     user_id: int | None = None) -> dict:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT batch_ticket_id FROM ifs_pet_blowing_runs WHERE id=?", (run_id,)
            ).fetchone()
            if not row:
                raise ValueError("PET blowing run not found")
            tid = row[0]
            conn.execute(
                "UPDATE ifs_pet_blowing_runs SET reject_pct=?, status='completed', stage='packing' WHERE id=?",
                (reject_pct, run_id),
            )
        result = BatchManufacturingService(self.tenant).complete_batch(tid, actual_qty, 0, "Pending", user_id)
        publish_simple(E.PET_BLOWING_COMPLETED, aggregate_type="pet_blowing", aggregate_id=run_id, user_id=user_id)
        return result
