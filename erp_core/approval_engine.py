"""V14 RC1 — approval engine with history, delegation, escalation."""

from __future__ import annotations

from datetime import datetime


def get_approval_rules(doc_type: str, *, amount: float = 0, warehouse_id=None, department=None) -> list[dict]:
    from database import get_connection

    with get_connection() as conn:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='erp_approval_rules'"
        ).fetchone():
            return []
        rows = conn.execute(
            """SELECT * FROM erp_approval_rules
               WHERE active=1 AND doc_type=?
               AND (min_amount IS NULL OR min_amount <= ?)
               AND (max_amount IS NULL OR max_amount >= ?)
               AND (warehouse_id IS NULL OR warehouse_id = ? OR ? IS NULL)
               AND (department IS NULL OR department = ? OR ? IS NULL)
               ORDER BY approval_level, id""",
            (doc_type, float(amount or 0), float(amount or 0),
             warehouse_id, warehouse_id, department, department),
        ).fetchall()
        return [dict(r) for r in rows]


def get_delegated_approver(user_id: int, doc_type: str) -> int | None:
    from database import get_connection

    today = datetime.now().strftime("%Y-%m-%d")
    with get_connection() as conn:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='erp_approval_delegation'"
        ).fetchone():
            return None
        row = conn.execute(
            """SELECT to_user_id FROM erp_approval_delegation
               WHERE from_user_id=? AND active=1
               AND (doc_type IS NULL OR doc_type=?)
               AND (valid_from IS NULL OR valid_from <= ?)
               AND (valid_to IS NULL OR valid_to >= ?)
               ORDER BY id DESC LIMIT 1""",
            (user_id, doc_type, today, today),
        ).fetchone()
        return row[0] if row else None


def user_can_approve(user: dict, doc_type: str, *, amount: float = 0, level: int = 1) -> bool:
    if not user:
        return False
    uid = user.get("id")
    delegate = get_delegated_approver(uid, doc_type) if uid else None
    if delegate:
        user = dict(user)
        user["id"] = delegate
    if user.get("role") == "admin":
        return True
    rules = get_approval_rules(doc_type, amount=amount)
    if not rules:
        return user.get("role") in ("admin", "manager")
    for rule in rules:
        if int(rule.get("approval_level") or 1) != level:
            continue
        if rule.get("user_id") and rule["user_id"] == user.get("id"):
            return True
        if rule.get("role") and rule["role"] == user.get("role"):
            return True
        if rule.get("delegate_to_user_id") and rule["delegate_to_user_id"] == user.get("id"):
            return True
    return False


def required_approval_levels(doc_type: str, *, amount: float = 0) -> int:
    rules = get_approval_rules(doc_type, amount=amount)
    if not rules:
        return 1
    return max(int(r.get("approval_level") or 1) for r in rules)


def record_approval_history(
    doc_type: str,
    doc_table: str,
    record_id: int,
    document_no: str,
    action: str,
    user_id: int | None,
    comments: str = "",
    *,
    level: int = 1,
    delegated_from: int | None = None,
) -> None:
    from database import get_connection

    with get_connection() as conn:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='erp_approval_history'"
        ).fetchone():
            return
        conn.execute(
            """INSERT INTO erp_approval_history
               (doc_type, doc_table, record_id, document_no, approval_level,
                action, comments, acted_by, delegated_from)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (doc_type, doc_table, record_id, document_no, level,
             action, comments or "", user_id, delegated_from),
        )
    try:
        from db_audit import log_event
        log_event(
            doc_table, record_id, action, user_id=user_id,
            document_no=document_no, module="Approval",
            summary=f"{action.title()} {doc_type} {document_no}" + (f": {comments}" if comments else ""),
        )
    except Exception:
        pass


def get_approval_history(doc_type: str, record_id: int) -> list[dict]:
    from database import get_connection, rows_to_list

    with get_connection() as conn:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='erp_approval_history'"
        ).fetchone():
            return []
        return rows_to_list(conn.execute(
            """SELECT h.*, u.full_name AS acted_by_name
               FROM erp_approval_history h
               LEFT JOIN users u ON u.id=h.acted_by
               WHERE h.doc_type=? AND h.record_id=?
               ORDER BY h.acted_at DESC, h.id DESC""",
            (doc_type, record_id),
        ).fetchall())


def save_approval_rule(data: dict, rule_id: int | None = None) -> int:
    from database import get_connection

    with get_connection() as conn:
        if rule_id:
            conn.execute(
                """UPDATE erp_approval_rules SET name=?, doc_type=?, department=?,
                   min_amount=?, max_amount=?, warehouse_id=?, role=?, user_id=?,
                   approval_level=?, active=?, escalate_after_hours=?, delegate_to_user_id=?,
                   comments_required=? WHERE id=?""",
                (
                    data["name"], data["doc_type"], data.get("department"),
                    data.get("min_amount", 0), data.get("max_amount"),
                    data.get("warehouse_id"), data.get("role"), data.get("user_id"),
                    data.get("approval_level", 1), data.get("active", 1),
                    data.get("escalate_after_hours"), data.get("delegate_to_user_id"),
                    data.get("comments_required", 0), rule_id,
                ),
            )
            return rule_id
        cur = conn.execute(
            """INSERT INTO erp_approval_rules
               (name, doc_type, department, min_amount, max_amount, warehouse_id,
                role, user_id, approval_level, active, escalate_after_hours,
                delegate_to_user_id, comments_required, created_by)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                data["name"], data["doc_type"], data.get("department"),
                data.get("min_amount", 0), data.get("max_amount"),
                data.get("warehouse_id"), data.get("role"), data.get("user_id"),
                data.get("approval_level", 1), data.get("active", 1),
                data.get("escalate_after_hours"), data.get("delegate_to_user_id"),
                data.get("comments_required", 0), data.get("created_by"),
            ),
        )
        return cur.lastrowid


def list_approval_rules() -> list[dict]:
    from database import get_connection, rows_to_list

    with get_connection() as conn:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='erp_approval_rules'"
        ).fetchone():
            return []
        return rows_to_list(conn.execute(
            "SELECT * FROM erp_approval_rules ORDER BY doc_type, approval_level, id"
        ).fetchall())
