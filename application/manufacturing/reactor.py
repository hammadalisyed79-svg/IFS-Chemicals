"""Chemical reactor — liquid mixing, heating, cooling, reaction."""

from __future__ import annotations

from application.services import BaseService
from application.manufacturing.batch import BatchManufacturingService
from database import get_connection, rows_to_list, now
from infrastructure.events.bus import publish_simple
from domain import events as E

REACTOR_STAGES = ("mixing", "heating", "cooling", "reaction", "agitation", "transfer", "holding", "packing")


class ReactorService(BaseService):
    def list_batches(self) -> list[dict]:
        with get_connection() as conn:
            return rows_to_list(conn.execute(
                """SELECT rb.*, bt.ticket_no, bt.batch_no
                   FROM ifs_reactor_batches rb
                   JOIN ifs_batch_tickets bt ON rb.batch_ticket_id = bt.id
                   WHERE bt.company_id=? ORDER BY rb.id DESC""",
                (self.tenant.company_id,),
            ).fetchall())

    def start_batch(self, data: dict, user_id: int | None = None) -> int:
        batch_svc = BatchManufacturingService(self.tenant)
        data.setdefault("process_type", "reactor")
        tid = batch_svc.create_ticket(data, user_id)
        with get_connection() as conn:
            cur = conn.execute(
                """INSERT INTO ifs_reactor_batches(batch_ticket_id, reactor_code, stage, status)
                   VALUES(?,?,?,?)""",
                (tid, data.get("reactor_code", "R-01"), "mixing", "in_progress"),
            )
            return cur.lastrowid

    def log_reading(self, reactor_batch_id: int, **kwargs) -> None:
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO ifs_reactor_readings(
                    reactor_batch_id, temperature_c, pressure_bar, rpm, ph, viscosity_cp, density
                ) VALUES(?,?,?,?,?,?,?)""",
                (
                    reactor_batch_id,
                    kwargs.get("temperature_c"),
                    kwargs.get("pressure_bar"),
                    kwargs.get("rpm"),
                    kwargs.get("ph"),
                    kwargs.get("viscosity_cp"),
                    kwargs.get("density"),
                ),
            )

    def advance_stage(self, reactor_batch_id: int, stage: str) -> None:
        with get_connection() as conn:
            conn.execute("UPDATE ifs_reactor_batches SET stage=? WHERE id=?", (stage, reactor_batch_id))

    def complete_batch(self, reactor_batch_id: int, actual_qty: float, reaction_time_min: float = 0,
                       qc_status: str = "Pending", user_id: int | None = None) -> dict:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT batch_ticket_id FROM ifs_reactor_batches WHERE id=?", (reactor_batch_id,)
            ).fetchone()
            if not row:
                raise ValueError("Reactor batch not found")
            tid = row[0]
            conn.execute(
                "UPDATE ifs_reactor_batches SET status='completed', reaction_time_min=?, stage='packing' WHERE id=?",
                (reaction_time_min, reactor_batch_id),
            )
        result = BatchManufacturingService(self.tenant).complete_batch(tid, actual_qty, 0, qc_status, user_id)
        publish_simple(E.REACTOR_COMPLETED, aggregate_type="reactor", aggregate_id=reactor_batch_id, user_id=user_id)
        return result
