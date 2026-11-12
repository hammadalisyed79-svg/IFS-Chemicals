"""CUS* (and other) customers get a matching chart account for Cash Book / GL."""

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
from db_v3 import (  # noqa: E402
    _party_subledger_code,
    backfill_missing_party_chart_accounts,
)


def _cleanup(path: Path) -> None:
    db.reset_runtime_state()
    for suffix in ("", "-wal", "-shm"):
        p = Path(f"{path}{suffix}") if suffix else path
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass


def _fresh_db():
    path = Path(tempfile.gettempdir()) / f"erp_cus_coa_{uuid.uuid4().hex}.db"
    os.environ["IFS_DB_PATH"] = str(path)
    db.DB_PATH = path
    db.reset_runtime_state()
    db.init_db()
    return path


def test_add_customer_creates_cus_chart_account():
    path = _fresh_db()
    try:
        cid = db.add_customer({"code": "CUS200302", "name": "KAMS FOODS GUJRANWALA", "opening_balance": 0})
        accs = {str(a["code"]).strip(): a for a in db.get_accounts(active_only=True)}
        assert "CUS200302" in accs
        assert "KAMS FOODS GUJRANWALA" in (accs["CUS200302"]["name"] or "")
        with db.get_connection() as conn:
            code = _party_subledger_code(conn, "customer", cid)
        assert code == "CUS200302"
    finally:
        _cleanup(path)


def test_backfill_moves_ar_control_gl_to_party():
    path = _fresh_db()
    try:
        with db.get_connection() as conn:
            conn.execute(
                """INSERT INTO customers(code, name, opening_balance, current_balance, is_active)
                   VALUES ('CUS001','PAKISTAN WASHING POWDER',0,1184000,1)"""
            )
            cid = conn.execute("SELECT id FROM customers WHERE code='CUS001'").fetchone()[0]
            ar = conn.execute("SELECT id FROM chart_of_accounts WHERE code='1200'").fetchone()[0]
            conn.execute(
                """INSERT INTO sales_invoices(
                       document_no, invoice_date, customer_id, subtotal, total, paid_amount, status
                   ) VALUES ('SAL-T1','2026-01-15',?,1184000,1184000,0,'approved')""",
                (cid,),
            )
            iid = conn.execute("SELECT id FROM sales_invoices WHERE document_no='SAL-T1'").fetchone()[0]
            conn.execute(
                """INSERT INTO general_ledger(
                       entry_date, account_id, debit, credit, description,
                       reference_type, reference_id, reference_no
                   ) VALUES ('2026-01-15',?,1184000,0,'Sales invoice','sales_invoice',?,'SAL-T1')""",
                (ar, iid),
            )
            stats = backfill_missing_party_chart_accounts(conn)
        assert stats["created"] >= 1
        accs = {str(a["code"]).strip() for a in db.get_accounts(active_only=True)}
        assert "CUS001" in accs
        with db.get_connection() as conn:
            party_id = conn.execute(
                "SELECT id FROM chart_of_accounts WHERE code='CUS001'"
            ).fetchone()[0]
            gl = conn.execute(
                "SELECT account_id, debit FROM general_ledger WHERE reference_no='SAL-T1'"
            ).fetchone()
            assert int(gl["account_id"]) == int(party_id)
            assert float(gl["debit"]) == 1184000
            unknown = conn.execute(
                "SELECT 1 FROM chart_of_accounts WHERE UPPER(TRIM(code))='UNKNOWN'"
            ).fetchone()
            assert unknown is None
    finally:
        _cleanup(path)


def test_unknown_party_is_not_given_a_chart_account():
    path = _fresh_db()
    try:
        db.add_customer({"code": "UNKNOWN", "name": "UNKNOWN PARTY"})
        codes = {str(a["code"]).strip().upper() for a in db.get_accounts()}
        assert "UNKNOWN" not in codes
    finally:
        _cleanup(path)
