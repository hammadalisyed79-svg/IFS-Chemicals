"""QC laboratory — incoming, in-process, finished goods."""

from __future__ import annotations

from application.services import BaseService
from database import get_connection, rows_to_list, now
from application.manufacturing.repository import _next_no
from infrastructure.events.bus import publish_simple
from domain import events as E


class QCLabService(BaseService):
    def list_specs(self, inspection_type: str | None = None) -> list[dict]:
        sql = "SELECT * FROM ifs_qc_specs WHERE company_id=? AND is_active=1"
        params: list = [self.tenant.company_id]
        if inspection_type:
            sql += " AND inspection_type=?"
            params.append(inspection_type)
        with get_connection() as conn:
            rows = rows_to_list(conn.execute(sql, params).fetchall())
            for r in rows:
                r["parameters"] = rows_to_list(conn.execute(
                    "SELECT * FROM ifs_qc_parameters WHERE spec_id=?", (r["id"],)
                ).fetchall())
            return rows

    def create_inspection(self, data: dict, user_id: int | None = None) -> int:
        with get_connection() as conn:
            insp_no = _next_no(conn, "QC", "ifs_qc_inspections", "inspection_no")
            cur = conn.execute(
                """INSERT INTO ifs_qc_inspections(
                    inspection_no, inspection_type, batch_ticket_id, product_id, batch_no,
                    status, is_retest, company_id, inspected_by
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    insp_no, data["inspection_type"], data.get("batch_ticket_id"),
                    data.get("product_id"), data.get("batch_no"), "pending",
                    data.get("is_retest", 0), self.tenant.company_id, user_id,
                ),
            )
            return cur.lastrowid

    def record_results(self, inspection_id: int, results: list[dict]) -> dict:
        all_pass = True
        with get_connection() as conn:
            for r in results:
                passed = 1
                if r.get("min_value") is not None and float(r["measured_value"]) < float(r["min_value"]):
                    passed = 0
                if r.get("max_value") is not None and float(r["measured_value"]) > float(r["max_value"]):
                    passed = 0
                if not passed:
                    all_pass = False
                conn.execute(
                    """INSERT INTO ifs_qc_results(inspection_id, parameter_id, param_name, measured_value, passed)
                       VALUES(?,?,?,?,?)""",
                    (inspection_id, r.get("parameter_id"), r["param_name"], r["measured_value"], passed),
                )
            result = "passed" if all_pass else "failed"
            conn.execute(
                "UPDATE ifs_qc_inspections SET result=?, status='completed' WHERE id=?",
                (result, inspection_id),
            )
            insp = conn.execute(
                "SELECT batch_ticket_id FROM ifs_qc_inspections WHERE id=?", (inspection_id,)
            ).fetchone()
            if insp and insp[0]:
                from application.manufacturing import repository as repo
                repo.update_batch_ticket(insp[0], {"qc_status": result})
        publish_simple(E.QC_INSPECTION_COMPLETED, aggregate_type="qc_inspection", aggregate_id=inspection_id,
                       payload={"result": result})
        return {"result": result, "passed": all_pass}

    def approve_coa(self, inspection_id: int, user_id: int | None = None) -> str:
        with get_connection() as conn:
            coa_no = _next_no(conn, "COA", "ifs_qc_inspections", "coa_no")
            conn.execute(
                "UPDATE ifs_qc_inspections SET coa_no=?, approved_by=?, approved_at=?, status='approved' WHERE id=?",
                (coa_no, user_id, now(), inspection_id),
            )
        publish_simple(E.QC_COA_APPROVED, aggregate_type="qc_inspection", aggregate_id=inspection_id, user_id=user_id)
        return coa_no

    def reject(self, inspection_id: int, reason: str, user_id: int | None = None) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE ifs_qc_inspections SET status='rejected', rejection_reason=?, result='failed' WHERE id=?",
                (reason, inspection_id),
            )
            insp = conn.execute(
                "SELECT batch_ticket_id FROM ifs_qc_inspections WHERE id=?", (inspection_id,)
            ).fetchone()
            if insp and insp[0]:
                from application.manufacturing.batch import BatchManufacturingService
                BatchManufacturingService(self.tenant).reject_batch(insp[0], reason)

    def list_inspections(self, inspection_type: str | None = None) -> list[dict]:
        sql = "SELECT * FROM ifs_qc_inspections WHERE company_id=?"
        params: list = [self.tenant.company_id]
        if inspection_type:
            sql += " AND inspection_type=?"
            params.append(inspection_type)
        sql += " ORDER BY id DESC"
        with get_connection() as conn:
            return rows_to_list(conn.execute(sql, params).fetchall())
