"""Formulation management — revision control, scaling, cost roll-up."""

from __future__ import annotations

import json

from application.services import BaseService
from database import get_connection, rows_to_list, now
from infrastructure.events.bus import publish_simple
from domain import events as E


FORMULA_TYPES = ("pilot", "commercial", "production")


class FormulationService(BaseService):
    def list_formulas(self, formula_type: str | None = None) -> list[dict]:
        sql = "SELECT * FROM ifs_formula_master WHERE company_id=?"
        params: list = [self.tenant.company_id]
        if formula_type:
            sql += " AND formula_type=?"
            params.append(formula_type)
        sql += " ORDER BY formula_code, revision DESC"
        with get_connection() as conn:
            return rows_to_list(conn.execute(sql, params).fetchall())

    def get_formula(self, formula_id: int) -> dict | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM ifs_formula_master WHERE id=?", (formula_id,)).fetchone()
            if not row:
                return None
            f = dict(row)
            f["lines"] = rows_to_list(conn.execute(
                """SELECT fl.*, p.name AS product_name, p.code AS product_code
                   FROM ifs_formula_lines fl JOIN products p ON fl.product_id=p.id
                   WHERE fl.formula_id=? ORDER BY fl.sequence_no""",
                (formula_id,),
            ).fetchall())
            return f

    def save_formula(self, data: dict, user_id: int | None = None) -> int:
        lines = data.pop("lines", [])
        with get_connection() as conn:
            if data.get("id"):
                fid = data["id"]
                conn.execute(
                    """UPDATE ifs_formula_master SET name=?, formula_type=?, product_id=?,
                       effective_from=?, tolerance_pct=?, standard_batch_qty=?, notes=?, status=?
                       WHERE id=?""",
                    (
                        data["name"], data.get("formula_type", "commercial"),
                        data.get("product_id"), data.get("effective_from"),
                        float(data.get("tolerance_pct", 2)),
                        float(data.get("standard_batch_qty", 1000)),
                        data.get("notes"), data.get("status", "draft"), fid,
                    ),
                )
                conn.execute("DELETE FROM ifs_formula_lines WHERE formula_id=?", (fid,))
            else:
                rev = conn.execute(
                    "SELECT COALESCE(MAX(revision),0)+1 FROM ifs_formula_master WHERE formula_code=? AND company_id=?",
                    (data["formula_code"], self.tenant.company_id),
                ).fetchone()[0]
                cur = conn.execute(
                    """INSERT INTO ifs_formula_master(
                        formula_code, name, revision, formula_type, product_id, effective_from,
                        tolerance_pct, standard_batch_qty, notes, status, company_id, created_by
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        data["formula_code"], data["name"], rev,
                        data.get("formula_type", "commercial"), data.get("product_id"),
                        data.get("effective_from"), float(data.get("tolerance_pct", 2)),
                        float(data.get("standard_batch_qty", 1000)),
                        data.get("notes"), "draft", self.tenant.company_id, user_id,
                    ),
                )
                fid = cur.lastrowid
            total_cost = 0.0
            batch_qty = float(data.get("standard_batch_qty", 1000))
            for i, ln in enumerate(lines):
                pct = float(ln.get("pct", 0))
                qty = batch_qty * pct / 100.0
                std = float(ln.get("standard_cost", 0))
                lc = qty * std
                total_cost += lc
                conn.execute(
                    """INSERT INTO ifs_formula_lines(
                        formula_id, product_id, pct, tolerance_pct, qty_per_batch, standard_cost, line_cost, sequence_no
                    ) VALUES(?,?,?,?,?,?,?,?)""",
                    (fid, ln["product_id"], pct, float(ln.get("tolerance_pct", 2)),
                     qty, std, lc, i + 1),
                )
            conn.execute("UPDATE ifs_formula_master SET total_cost=? WHERE id=?", (total_cost, fid))
            snap = json.dumps({"formula_id": fid, "lines": lines, "total_cost": total_cost})
            conn.execute(
                "INSERT INTO ifs_formula_history(formula_id, revision, snapshot_json, changed_by) VALUES(?,?,?,?)",
                (fid, data.get("revision", 1), snap, user_id),
            )
        publish_simple(E.FORMULA_SAVED, aggregate_type="ifs_formula", aggregate_id=fid, user_id=user_id,
                       company_id=self.tenant.company_id)
        return fid

    def scale_formula(self, formula_id: int, target_qty: float) -> list[dict]:
        f = self.get_formula(formula_id)
        if not f:
            raise ValueError("Formula not found")
        base = float(f.get("standard_batch_qty") or 1000)
        factor = target_qty / base if base else 1.0
        scaled = []
        for ln in f.get("lines") or []:
            scaled.append({
                **ln,
                "scaled_qty": float(ln.get("qty_per_batch") or 0) * factor,
                "tolerance_qty": float(ln.get("qty_per_batch") or 0) * factor * float(ln.get("tolerance_pct", 2)) / 100,
            })
        return scaled

    def approve_formula(self, formula_id: int, user_id: int | None = None) -> None:
        from application.workflows.designer import can_transition, apply_transition
        f = self.get_formula(formula_id)
        if not f:
            raise ValueError("Formula not found")
        status = f.get("status") or "draft"
        if status == "draft":
            apply_transition("ifs_formula", status, "submit", {})
            status = "submitted"
        ok, _ = can_transition("ifs_formula", status, "approve")
        if not ok:
            raise ValueError(f"Cannot approve from status {status}")
        with get_connection() as conn:
            conn.execute(
                "UPDATE ifs_formula_master SET status='approved', approved_by=?, approved_at=? WHERE id=?",
                (user_id, now(), formula_id),
            )
        publish_simple(E.FORMULA_APPROVED, aggregate_type="ifs_formula", aggregate_id=formula_id, user_id=user_id)
