"""Toll manufacturing — customer formula, RM, packaging, billing."""

from __future__ import annotations

from application.services import BaseService
from application.manufacturing.batch import BatchManufacturingService
from database import get_connection, rows_to_list
from application.manufacturing.repository import _next_no


class TollManufacturingService(BaseService):
    def list_agreements(self) -> list[dict]:
        with get_connection() as conn:
            return rows_to_list(conn.execute(
                """SELECT ta.*, c.name AS customer_name, fm.formula_code
                   FROM ifs_toll_agreements ta
                   JOIN customers c ON ta.customer_id = c.id
                   LEFT JOIN ifs_formula_master fm ON ta.formula_id = fm.id
                   WHERE ta.company_id=? ORDER BY ta.id DESC""",
                (self.tenant.company_id,),
            ).fetchall())

    def save_agreement(self, data: dict) -> int:
        with get_connection() as conn:
            if data.get("id"):
                conn.execute(
                    """UPDATE ifs_toll_agreements SET customer_id=?, formula_id=?, customer_rm=?, company_rm=?,
                       customer_packaging=?, company_packaging=?, manufacturing_charge=?, charge_uom=?,
                       effective_from=?, effective_to=?, status=? WHERE id=?""",
                    (data["customer_id"], data.get("formula_id"), data.get("customer_rm", 0),
                     data.get("company_rm", 1), data.get("customer_packaging", 0),
                     data.get("company_packaging", 1), data.get("manufacturing_charge", 0),
                     data.get("charge_uom", "kg"), data.get("effective_from"), data.get("effective_to"),
                     data.get("status", "active"), data["id"]),
                )
                return data["id"]
            agreement_no = _next_no(conn, "TOLL", "ifs_toll_agreements", "agreement_no")
            cur = conn.execute(
                """INSERT INTO ifs_toll_agreements(
                    agreement_no, customer_id, formula_id, customer_rm, company_rm,
                    customer_packaging, company_packaging, manufacturing_charge, charge_uom,
                    effective_from, effective_to, company_id
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (agreement_no, data["customer_id"], data.get("formula_id"),
                 data.get("customer_rm", 0), data.get("company_rm", 1),
                 data.get("customer_packaging", 0), data.get("company_packaging", 1),
                 data.get("manufacturing_charge", 0), data.get("charge_uom", "kg"),
                 data.get("effective_from"), data.get("effective_to"), self.tenant.company_id),
            )
            return cur.lastrowid

    def start_toll_production(self, agreement_id: int, data: dict, user_id: int | None = None) -> int:
        data["process_type"] = "toll"
        data["formula_id"] = data.get("formula_id") or self._agreement_formula(agreement_id)
        tid = BatchManufacturingService(self.tenant).create_ticket(data, user_id)
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO ifs_toll_production(agreement_id, batch_ticket_id) VALUES(?,?)",
                (agreement_id, tid),
            )
        return tid

    def bill_production(self, toll_production_id: int, billed_qty: float) -> float:
        with get_connection() as conn:
            row = conn.execute(
                """SELECT tp.agreement_id, ta.manufacturing_charge, ta.charge_uom
                   FROM ifs_toll_production tp JOIN ifs_toll_agreements ta ON tp.agreement_id = ta.id
                   WHERE tp.id=?""",
                (toll_production_id,),
            ).fetchone()
            if not row:
                raise ValueError("Toll production not found")
            amount = billed_qty * float(row[1] or 0)
            conn.execute(
                "UPDATE ifs_toll_production SET billed_qty=?, billed_amount=?, billing_status='billed' WHERE id=?",
                (billed_qty, amount, toll_production_id),
            )
            return amount

    def _agreement_formula(self, agreement_id: int) -> int | None:
        with get_connection() as conn:
            row = conn.execute("SELECT formula_id FROM ifs_toll_agreements WHERE id=?", (agreement_id,)).fetchone()
            return row[0] if row else None
