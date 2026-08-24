"""Shared DB helpers for IFS Chemicals manufacturing."""

from __future__ import annotations

import re

from database import get_connection, rows_to_list, now


def _next_no(conn, prefix: str, table: str, col: str) -> str:
    row = conn.execute(f"SELECT {col} FROM {table} ORDER BY id DESC LIMIT 1").fetchone()
    if row and row[0]:
        m = re.search(r"(\d+)$", str(row[0]))
        n = int(m.group(1)) + 1 if m else 1
    else:
        n = 1
    return f"{prefix}-{n:05d}"


def list_batch_tickets(process_type: str | None = None, company_id: int = 1) -> list[dict]:
    sql = """SELECT bt.*, m.name AS machine_name, e.full_name AS operator_name
             FROM ifs_batch_tickets bt
             LEFT JOIN machines m ON bt.machine_id = m.id
             LEFT JOIN employees e ON bt.operator_id = e.id
             WHERE bt.company_id=?"""
    params: list = [company_id]
    if process_type:
        sql += " AND bt.process_type=?"
        params.append(process_type)
    sql += " ORDER BY bt.id DESC"
    with get_connection() as conn:
        return rows_to_list(conn.execute(sql, params).fetchall())


def get_batch_ticket(ticket_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """SELECT bt.*, m.name AS machine_name, e.full_name AS operator_name,
                      fm.formula_code, fm.name AS formula_name
               FROM ifs_batch_tickets bt
               LEFT JOIN machines m ON bt.machine_id = m.id
               LEFT JOIN employees e ON bt.operator_id = e.id
               LEFT JOIN ifs_formula_master fm ON bt.formula_id = fm.id
               WHERE bt.id=?""",
            (ticket_id,),
        ).fetchone()
        return dict(row) if row else None


def create_batch_ticket(data: dict, user_id: int | None = None) -> int:
    with get_connection() as conn:
        ticket_no = _next_no(conn, "BT", "ifs_batch_tickets", "ticket_no")
        cur = conn.execute(
            """INSERT INTO ifs_batch_tickets(
                ticket_no, production_order_id, formula_id, batch_no, process_type,
                planned_qty, operator_id, shift, machine_id, warehouse_id,
                status, company_id, branch_id, created_by, started_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                ticket_no,
                data.get("production_order_id"),
                data.get("formula_id"),
                data["batch_no"],
                data["process_type"],
                float(data["planned_qty"]),
                data.get("operator_id"),
                data.get("shift"),
                data.get("machine_id"),
                data.get("warehouse_id"),
                "open",
                data.get("company_id", 1),
                data.get("branch_id"),
                user_id,
                now(),
            ),
        )
        return cur.lastrowid


def update_batch_ticket(ticket_id: int, fields: dict) -> None:
    allowed = {
        "actual_qty", "expected_consumption", "actual_consumption", "variance_qty",
        "yield_pct", "loss_pct", "status", "qc_status", "is_rework", "is_rejected",
        "production_time_min", "downtime_min", "completed_at", "production_order_id",
    }
    sets = []
    vals = []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return
    vals.append(ticket_id)
    with get_connection() as conn:
        conn.execute(f"UPDATE ifs_batch_tickets SET {','.join(sets)} WHERE id=?", vals)


def add_trace(batch_ticket_id: int, batch_no: str, product_id: int, direction: str,
              qty: float, reference_type: str | None = None, reference_id: int | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO ifs_batch_trace(batch_ticket_id,batch_no,product_id,direction,qty,reference_type,reference_id)
               VALUES(?,?,?,?,?,?,?)""",
            (batch_ticket_id, batch_no, product_id, direction, qty, reference_type, reference_id),
        )
