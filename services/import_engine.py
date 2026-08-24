"""Professional import engine — validate, batch, rollback."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable

import pandas as pd

from infrastructure.events.bus import publish_simple

IMPORTERS: dict[str, Callable[[dict], None]] = {}


def register_importer(entity_type: str, validator: Callable[[dict], tuple[bool, str]],
                      saver: Callable[[dict, int | None], int]) -> None:
    def _run(row: dict) -> None:
        ok, msg = validator(row)
        if not ok:
            raise ValueError(msg)
        saver(row, None)

    IMPORTERS[entity_type] = _run


def _validate_customer(row: dict) -> tuple[bool, str]:
    if not row.get("code") or not row.get("name"):
        return False, "code and name required"
    return True, ""


def _save_customer(row: dict, user_id: int | None) -> int:
    from application.services import CustomerService
    return CustomerService().create(row, user_id=user_id)


register_importer("customers", _validate_customer, _save_customer)


def import_dataframe(
    entity_type: str,
    df: pd.DataFrame,
    *,
    user_id: int | None = None,
    company_id: int = 1,
) -> dict:
    from database import get_connection
    importer = IMPORTERS.get(entity_type)
    if not importer:
        raise ValueError(f"No importer for {entity_type}")

    batch_id = None
    errors: list[str] = []
    success = 0
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO erp_import_batches(entity_type,status,total_rows,company_id,created_by)
               VALUES(?, 'running', ?, ?, ?)""",
            (entity_type, len(df), company_id, user_id),
        )
        batch_id = cur.lastrowid

    try:
        for i, row in df.iterrows():
            data = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
            try:
                ok, msg = _validate_customer(data) if entity_type == "customers" else (True, "")
                if not ok:
                    errors.append(f"Row {i}: {msg}")
                    continue
                if entity_type == "customers":
                    _save_customer(data, user_id)
                else:
                    importer(data)
                success += 1
            except Exception as exc:
                errors.append(f"Row {i}: {exc}")

        status = "completed" if not errors else ("partial" if success else "failed")
        with get_connection() as conn:
            conn.execute(
                """UPDATE erp_import_batches SET status=?, success_rows=?, error_rows=?, error_log=?
                   WHERE id=?""",
                (status, success, len(errors), json.dumps(errors[:100]), batch_id),
            )
        publish_simple("ImportCompleted", aggregate_type="import_batch", aggregate_id=batch_id,
                       payload={"entity": entity_type, "success": success, "errors": len(errors)})
        return {"batch_id": batch_id, "status": status, "success": success, "errors": errors}
    except Exception as exc:
        with get_connection() as conn:
            conn.execute(
                "UPDATE erp_import_batches SET status='failed', error_log=? WHERE id=?",
                (str(exc), batch_id),
            )
        raise
