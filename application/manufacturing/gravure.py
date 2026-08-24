"""Gravure / flexible packaging production."""

from __future__ import annotations

from application.services import BaseService
from application.manufacturing.batch import BatchManufacturingService
from database import get_connection, rows_to_list, now
from infrastructure.events.bus import publish_simple
from domain import events as E

GRAVURE_STAGES = ("printing", "lamination", "slitting", "rewinding", "packing")


class GravureService(BaseService):
    def list_cylinders(self) -> list[dict]:
        with get_connection() as conn:
            return rows_to_list(conn.execute(
                "SELECT * FROM ifs_cylinder_master WHERE company_id=? ORDER BY cylinder_code",
                (self.tenant.company_id,),
            ).fetchall())

    def save_cylinder(self, data: dict) -> int:
        with get_connection() as conn:
            if data.get("id"):
                conn.execute(
                    "UPDATE ifs_cylinder_master SET artwork_revision=?, repeat_length_mm=?, status=? WHERE id=?",
                    (data.get("artwork_revision"), data.get("repeat_length_mm"), data.get("status", "active"), data["id"]),
                )
                return data["id"]
            cur = conn.execute(
                """INSERT INTO ifs_cylinder_master(cylinder_code, artwork_revision, repeat_length_mm, company_id)
                   VALUES(?,?,?,?)""",
                (data["cylinder_code"], data.get("artwork_revision"), data.get("repeat_length_mm"), self.tenant.company_id),
            )
            return cur.lastrowid

    def list_runs(self) -> list[dict]:
        with get_connection() as conn:
            return rows_to_list(conn.execute(
                """SELECT gr.*, bt.ticket_no, cm.cylinder_code
                   FROM ifs_gravure_runs gr
                   JOIN ifs_batch_tickets bt ON gr.batch_ticket_id = bt.id
                   LEFT JOIN ifs_cylinder_master cm ON gr.cylinder_id = cm.id
                   WHERE bt.company_id=? ORDER BY gr.id DESC""",
                (self.tenant.company_id,),
            ).fetchall())

    def start_run(self, data: dict, user_id: int | None = None) -> int:
        batch_svc = BatchManufacturingService(self.tenant)
        data.setdefault("process_type", data.get("process_type", "gravure"))
        tid = batch_svc.create_ticket(data, user_id)
        with get_connection() as conn:
            cur = conn.execute(
                """INSERT INTO ifs_gravure_runs(
                    batch_ticket_id, cylinder_id, film_micron, stage, status
                ) VALUES(?,?,?,?,?)""",
                (tid, data.get("cylinder_id"), data.get("film_micron"), "printing", "in_progress"),
            )
            return cur.lastrowid

    def record_consumption(self, run_id: int, ink_kg: float = 0, solvent_kg: float = 0, film_kg: float = 0) -> None:
        with get_connection() as conn:
            conn.execute(
                """UPDATE ifs_gravure_runs SET ink_kg=ink_kg+?, solvent_kg=solvent_kg+?, film_kg=film_kg+?
                   WHERE id=?""",
                (ink_kg, solvent_kg, film_kg, run_id),
            )

    def complete_run(self, run_id: int, actual_qty: float, waste_pct: float = 0,
                     printing_speed: float = 0, user_id: int | None = None) -> dict:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT batch_ticket_id FROM ifs_gravure_runs WHERE id=?", (run_id,)
            ).fetchone()
            if not row:
                raise ValueError("Gravure run not found")
            tid = row[0]
            conn.execute(
                """UPDATE ifs_gravure_runs SET waste_pct=?, printing_speed_mpm=?, status='completed', stage='packing'
                   WHERE id=?""",
                (waste_pct, printing_speed, run_id),
            )
        result = BatchManufacturingService(self.tenant).complete_batch(tid, actual_qty, 0, "Pending", user_id)
        publish_simple(E.GRAVURE_COMPLETED, aggregate_type="gravure", aggregate_id=run_id, user_id=user_id)
        return result
