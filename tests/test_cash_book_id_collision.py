"""Regression: Cash Book must never hide sale receipts via settlement id collision."""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from datetime import date
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import database as db  # noqa: E402


def _cleanup(path: Path) -> None:
    db.reset_runtime_state()
    for suffix in ("", "-wal", "-shm"):
        p = Path(f"{path}{suffix}") if suffix else path
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass


def test_cash_book_ignores_settlement_payment_id_collision():
    """Settlement cash_entry_id for a CP must not hide a CR that reuses the same integer id."""
    path = Path(tempfile.gettempdir()) / f"erp_cash_collide_{uuid.uuid4().hex}.db"
    os.environ["IFS_DB_PATH"] = str(path)
    db.DB_PATH = path
    db.reset_runtime_state()
    db.init_db()
    today = date.today().isoformat()
    try:
        with db.get_connection() as conn:
            from db_v3 import _ensure_cash_advances_schema
            _ensure_cash_advances_schema(conn)
            acct = conn.execute(
                "SELECT id FROM chart_of_accounts WHERE is_active=1 LIMIT 1"
            ).fetchone()
            assert acct, "need chart account"
            conn.execute(
                """INSERT INTO cash_advances(
                       document_no, issue_date, person_name, amount, outstanding_amount,
                       advance_account_id, status, created_at
                   ) VALUES (?,?,?,?,?,?,?,?)""",
                ("CA-TEST", today, "Tester", 500.0, 500.0, acct[0], "open", today),
            )
            adv_id = conn.execute(
                "SELECT id FROM cash_advances WHERE document_no='CA-TEST'"
            ).fetchone()[0]
            conn.execute(
                """INSERT INTO cash_payments(
                       document_no, payment_date, description, reference_no, amount, created_at
                   ) VALUES (?,?,?,?,?,?)""",
                ("CP-COLLIDE-1", today, "Settle bill CA-1", "CAS-TEST-L1", 500.0, today),
            )
            pay_id = conn.execute(
                "SELECT id FROM cash_payments WHERE document_no='CP-COLLIDE-1'"
            ).fetchone()[0]
            conn.execute(
                """INSERT INTO cash_advance_settlements(
                       document_no, advance_id, settle_date, bills_total, cash_returned,
                       cash_entry_id, cash_entry_source, cash_doc_no, created_at
                   ) VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    "CAS-TEST", adv_id, today, 500.0, 0.0,
                    pay_id, "cash_payment", "CP-COLLIDE-1", today,
                ),
            )
            # Same integer id as the payment row (production collision class).
            conn.execute(
                """INSERT INTO cash_receipts(
                       id, document_no, receipt_date, description, reference_no, amount, created_at
                   ) VALUES (?,?,?,?,?,?,?)""",
                (pay_id, "CR-SALE-1", today, "Cash sale", "SAL-TEST-1", 1000.0, today),
            )
            got = db.cash_book_receipts_sum(conn, from_date=today, to_date=today)

        book = db.get_cash_book(today, today)
        docs = {r.get("document_no") for r in book if r.get("entry_source") == "cash_receipt"}
        assert "CR-SALE-1" in docs, f"sale receipt hidden from cash book: {docs}"
        assert abs(got - 1000.0) < 0.01, f"receipts sum hid sale CR: {got}"

        # Exclude SQL must not contain bare settlement cash_entry_id against receipts.
        sql = db._cash_advance_return_receipt_exclude_sql()
        assert "cash_entry_id" not in sql, "bare cash_entry_id exclude is unsafe"
        print("PASS cash book ignores settlement payment id collision")
    finally:
        _cleanup(path)


if __name__ == "__main__":
    test_cash_book_ignores_settlement_payment_id_collision()
