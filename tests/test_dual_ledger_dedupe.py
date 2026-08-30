"""Regression: combined dual-role ledger must keep same-book multi-lines and linked JVs."""
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


def test_combined_keeps_same_book_multiline_and_linked_jv():
    path = Path(tempfile.gettempdir()) / f"erp_ledger_dedupe_{uuid.uuid4().hex}.db"
    os.environ["IFS_DB_PATH"] = str(path)
    db.DB_PATH = path
    db.reset_runtime_state()
    db.init_db()
    today = date.today().isoformat()
    try:
        with db.get_connection() as conn:
            from database import _ensure_fmye_party_entries_table
            _ensure_fmye_party_entries_table(conn)
            conn.execute(
                "INSERT INTO customers(code,name,opening_balance,current_balance,is_active) VALUES(?,?,?,?,1)",
                ("D100", "Dual Cust", 0, 0),
            )
            conn.execute(
                "INSERT INTO suppliers(code,name,opening_balance,current_balance,is_active) VALUES(?,?,?,?,1)",
                ("D100", "Dual Supp", 0, 0),
            )
            cid = conn.execute("SELECT id FROM customers WHERE code='D100'").fetchone()[0]
            sid = conn.execute("SELECT id FROM suppliers WHERE code='D100'").fetchone()[0]
            # Shared COA for party code
            grp = conn.execute(
                "SELECT id FROM account_groups WHERE group_type='asset' LIMIT 1"
            ).fetchone()
            if not grp:
                conn.execute(
                    "INSERT INTO account_groups(code,name,group_type) VALUES('A','Assets','asset')"
                )
                gid = conn.execute("SELECT id FROM account_groups WHERE code='A'").fetchone()[0]
            else:
                gid = grp[0]
            conn.execute(
                "INSERT INTO chart_of_accounts(code,name,account_group_id,is_active) VALUES(?,?,?,1)",
                ("D100", "Dual Party COA", gid),
            )
            aid = conn.execute("SELECT id FROM chart_of_accounts WHERE code='D100'").fetchone()[0]
            # Two identical FMYE-style customer lines (same ref/amount/narration)
            for _ in range(2):
                conn.execute(
                    """INSERT INTO fmye_party_entries(
                           party_type, party_id, entry_date, document_no, description,
                           debit, credit, voucher_type
                       ) VALUES (?,?,?,?,?,?,?,?)""",
                    ("customer", cid, today, "JVR-X1", "SAME LINE", 1000.0, 0.0, "JVR"),
                )
            # Supplier-only COA journal (must appear in combined customer view)
            conn.execute(
                """INSERT INTO general_ledger(
                       entry_date, account_id, debit, credit, description,
                       reference_type, reference_no, created_at
                   ) VALUES (?,?,?,?,?,?,?,?)""",
                (today, aid, 0.0, 250.0, "Supp only JV", "journal", "JV-SUP1", today),
            )

        p_own, e_own = db.get_customer_ledger(cid, include_linked=False)
        p_comb, e_comb = db.get_customer_ledger(cid, include_linked=True)
        p_sown, _ = db.get_supplier_ledger(sid, include_linked=False)
        # Customer own keeps shared party-code COA; supplier own skips it (Outstanding nets once).
        assert abs(float(p_own["ledger_summary"]["closing"]) - 1750.0) < 0.05, p_own["ledger_summary"]
        assert abs(float(p_sown["ledger_summary"]["closing"]) - 0.0) < 0.05, p_sown["ledger_summary"]
        # Combined = 2000 FMYE + (-250) COA once after cross-book dedupe
        assert abs(float(p_comb["ledger_summary"]["closing"]) - 1750.0) < 0.05, p_comb["ledger_summary"]
        jvr_lines = [e for e in e_comb if e.get("ref") == "JVR-X1"]
        assert len(jvr_lines) == 2, f"same-book multi-line collapsed: {jvr_lines}"
        print("PASS combined keeps same-book multi-lines and linked JV")
    finally:
        _cleanup(path)


if __name__ == "__main__":
    # fmye_party_entries may need schema ensure — call via ledger which ensures
    test_combined_keeps_same_book_multiline_and_linked_jv()
