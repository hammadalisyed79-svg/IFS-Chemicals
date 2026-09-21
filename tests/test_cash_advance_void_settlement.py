"""Cash Book delete must reverse linked cash-advance settlements."""

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
import db_v3  # noqa: E402


def _cleanup(path: Path) -> None:
    db.reset_runtime_state()
    for suffix in ("", "-wal", "-shm"):
        p = Path(f"{path}{suffix}") if suffix else path
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass


def test_void_cash_payment_reverses_settlement():
    path = Path(tempfile.gettempdir()) / f"erp_ca_void_{uuid.uuid4().hex}.db"
    os.environ["IFS_DB_PATH"] = str(path)
    db.DB_PATH = path
    db.reset_runtime_state()
    db.init_db()
    today = date.today().isoformat()

    import db_cash_day
    db_cash_day.assert_cash_day_open = lambda *a, **k: None

    try:
        with db.get_connection() as conn:
            exp = conn.execute(
                """SELECT a.id FROM chart_of_accounts a
                   JOIN account_groups g ON a.account_group_id=g.id
                   WHERE a.is_active=1 AND g.group_type='expense'
                   LIMIT 1"""
            ).fetchone()
            assert exp, "need an expense GL account"
            exp_id = int(exp[0])

        issued = db_v3.issue_cash_advance(
            today, 5000, "Test Rider", purpose="unit test", user_id=1,
        )
        settled = db_v3.settle_cash_advance(
            issued["id"],
            today,
            [{"expense_account_id": exp_id, "narration": "Test bill", "amount": 5000}],
            user_id=1,
        )
        cp = settled.get("cash_doc_no")
        assert cp, "settlement should post a cash payment"
        with db.get_connection() as conn:
            pay = conn.execute(
                "SELECT id FROM cash_payments WHERE document_no=?", (cp,),
            ).fetchone()
            assert pay
            pay_id = int(pay[0])
            assert conn.execute(
                "SELECT status FROM cash_advances WHERE id=?", (issued["id"],),
            ).fetchone()[0] == "settled"

        result = db_v3.void_cash_bank_book_entry(
            "cash", pay_id, "debit", _skip_close_check=True,
        )
        assert result.get("reversed_settlements"), result

        with db.get_connection() as conn:
            assert conn.execute(
                "SELECT 1 FROM cash_payments WHERE id=?", (pay_id,),
            ).fetchone() is None
            assert conn.execute(
                "SELECT 1 FROM cash_advance_settlements WHERE id=?",
                (settled["id"],),
            ).fetchone() is None
            adv = dict(conn.execute(
                "SELECT status, outstanding_amount, settled_bills FROM cash_advances WHERE id=?",
                (issued["id"],),
            ).fetchone())
            assert adv["status"] == "open"
            assert abs(float(adv["outstanding_amount"]) - 5000.0) < 0.01
            assert abs(float(adv["settled_bills"])) < 0.01
            assert conn.execute(
                "SELECT COUNT(*) FROM general_ledger WHERE reference_no=?",
                (settled["document_no"],),
            ).fetchone()[0] == 0
    finally:
        _cleanup(path)


if __name__ == "__main__":
    test_void_cash_payment_reverses_settlement()
    print("PASS void cash payment reverses settlement")
