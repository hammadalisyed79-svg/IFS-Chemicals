"""Cash slip party balance must match Customer Ledger, not stored current_balance."""
from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import database as db  # noqa: E402
from db_v3 import get_finance_voucher  # noqa: E402
from erp_ui.document_print import _finance_voucher_body  # noqa: E402


def _cleanup(path: Path) -> None:
    db.reset_runtime_state()
    for suffix in ("", "-wal", "-shm"):
        p = Path(f"{path}{suffix}") if suffix else path
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass


def test_running_balance_after_ref_matches_ledger_row():
    entries = [
        {"date": "2026-01-01", "ref": "Opening", "balance": 3974550.56},
        {"date": "2026-11-10", "ref": "PT-0780", "balance": 3774550.56},
        {"date": "2026-11-14", "ref": "CR-127922", "balance": 3524550.56},
    ]
    assert db._running_balance_after_ref(entries, "CR-127922", "2026-11-14") == 3524550.56
    assert db._running_balance_before_ref(entries, "CR-127922", "2026-11-14") == 3774550.56
    assert db._running_balance_after_ref(entries, "MISSING", "2026-11-14") == 3524550.56


def test_cash_slip_uses_ledger_not_stale_current_balance():
    path = Path(tempfile.gettempdir()) / f"erp_cash_slip_{uuid.uuid4().hex}.db"
    os.environ["IFS_DB_PATH"] = str(path)
    db.DB_PATH = path
    db.reset_runtime_state()
    db.init_db()
    try:
        with db.get_connection() as conn:
            conn.execute(
                """INSERT INTO customers(code, name, opening_balance, current_balance, is_active)
                   VALUES (?,?,?,?,1)""",
                ("100014", "RAEES SODHRA WAZIRABAD", 3974550.56, 9999999.0),
            )
            cid = conn.execute("SELECT id FROM customers WHERE code='100014'").fetchone()[0]
            conn.execute(
                """INSERT INTO cash_receipts(
                       document_no, receipt_date, party_type, party_id,
                       description, amount, created_at
                   ) VALUES (?,?,?,?,?,?,?)""",
                ("CR-127922", "2026-11-14", "customer", cid,
                 "Cash Rcvd frm M Amir sb", 250000.0, "2026-11-14 10:00:00"),
            )
            rid = conn.execute(
                "SELECT id FROM cash_receipts WHERE document_no='CR-127922'"
            ).fetchone()[0]

        _, entries = db.get_customer_ledger(cid, include_linked=True)
        ledger_after = float(entries[-1]["balance"])
        assert abs(ledger_after - 3724550.56) < 0.02

        v = get_finance_voucher("cash_receipt", rid)
        assert v is not None
        assert abs(float(v["party_balance"]) - ledger_after) < 0.02
        assert v["party_balance_display"] == db._fmt_ledger_balance(ledger_after, kind="customer")
        assert abs(float(v["party_balance"]) - 9999999.0) > 1

        body, title, _, party_name = _finance_voucher_body(v)
        assert "RAEES SODHRA WAZIRABAD" in party_name
        assert "Customer Receipt" in title
        assert v["party_balance_display"] in body
        assert "9,999,999" not in body
    finally:
        _cleanup(path)
