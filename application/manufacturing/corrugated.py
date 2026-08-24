"""Corrugated box production."""

from __future__ import annotations

from application.services import BaseService
from application.manufacturing.batch import BatchManufacturingService
from database import get_connection, rows_to_list, now
from infrastructure.events.bus import publish_simple
from domain import events as E

CORRUGATED_STAGES = (
    "paper_issue", "corrugation", "board_making", "printing", "slotting",
    "die_cutting", "folder_gluer", "bundling", "dispatch",
)


class CorrugatedService(BaseService):
    def list_runs(self) -> list[dict]:
        with get_connection() as conn:
            return rows_to_list(conn.execute(
                """SELECT cr.*, bt.ticket_no, bt.batch_no
                   FROM ifs_corrugated_runs cr
                   JOIN ifs_batch_tickets bt ON cr.batch_ticket_id = bt.id
                   WHERE bt.company_id=? ORDER BY cr.id DESC""",
                (self.tenant.company_id,),
            ).fetchall())

    def start_run(self, data: dict, user_id: int | None = None) -> int:
        batch_svc = BatchManufacturingService(self.tenant)
        data.setdefault("process_type", "corrugated")
        tid = batch_svc.create_ticket(data, user_id)
        with get_connection() as conn:
            cur = conn.execute(
                """INSERT INTO ifs_corrugated_runs(
                    batch_ticket_id, paper_gsm, flute_type, board_size, stage, status
                ) VALUES(?,?,?,?,?,?)""",
                (tid, data.get("paper_gsm"), data.get("flute_type"), data.get("board_size"),
                 "paper_issue", "in_progress"),
            )
            run_id = cur.lastrowid
            conn.execute(
                "INSERT INTO ifs_corrugated_stages(run_id, stage_name, started_at, operator_id) VALUES(?,?,?,?)",
                (run_id, "paper_issue", now(), user_id),
            )
            return run_id

    def advance_stage(self, run_id: int, stage: str, user_id: int | None = None) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE ifs_corrugated_stages SET completed_at=? WHERE run_id=? AND completed_at IS NULL",
                (now(), run_id),
            )
            conn.execute(
                "INSERT INTO ifs_corrugated_stages(run_id, stage_name, started_at, operator_id) VALUES(?,?,?,?)",
                (run_id, stage, now(), user_id),
            )
            conn.execute("UPDATE ifs_corrugated_runs SET stage=? WHERE id=?", (stage, run_id))

    def complete_run(self, run_id: int, actual_qty: float, waste_pct: float = 0,
                     production_speed: float = 0, user_id: int | None = None) -> dict:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT batch_ticket_id FROM ifs_corrugated_runs WHERE id=?", (run_id,)
            ).fetchone()
            if not row:
                raise ValueError("Corrugated run not found")
            tid = row[0]
            conn.execute(
                "UPDATE ifs_corrugated_runs SET waste_pct=?, production_speed_mpm=?, status='completed', stage='dispatch' WHERE id=?",
                (waste_pct, production_speed, run_id),
            )
        result = BatchManufacturingService(self.tenant).complete_batch(tid, actual_qty, 0, "Pending", user_id)
        publish_simple(E.CORRUGATED_COMPLETED, aggregate_type="corrugated", aggregate_id=run_id, user_id=user_id)
        return result
