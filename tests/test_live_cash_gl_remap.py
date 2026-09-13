"""Live cash GL must use 000000 — never legacy 1000 — for both Dr and Cr."""
from database import get_connection
from db_v3 import post_gl, post_gl_account_id, resolve_cash_account_id, AC


def test_ac_cash_default_is_live():
    assert AC["cash"] == "000000"


def test_post_gl_code_1000_remaps_debit_and_credit():
    with get_connection() as conn:
        live_id = resolve_cash_account_id(conn)
        legacy = conn.execute(
            "SELECT id FROM chart_of_accounts WHERE code='1000'"
        ).fetchone()
        assert live_id, "live cash account missing"
        assert legacy, "legacy 1000 missing"
        assert int(live_id) != int(legacy[0])

        marker = "TEST_LIVE_CASH_REMAP"
        conn.execute(
            "DELETE FROM general_ledger WHERE description LIKE ?",
            (marker + "%",),
        )

        post_gl(
            conn, "2026-09-13", "1000", 111.0, 0.0,
            f"{marker} debit", "test_live_cash", 1, "TEST-DR", None,
        )
        post_gl(
            conn, "2026-09-13", "1000", 0.0, 222.0,
            f"{marker} credit", "test_live_cash", 2, "TEST-CR", None,
        )
        post_gl_account_id(
            conn, "2026-09-13", int(legacy[0]), 333.0, 0.0,
            f"{marker} id-debit", "test_live_cash", 3, "TEST-IDR", None,
        )
        post_gl_account_id(
            conn, "2026-09-13", int(legacy[0]), 0.0, 444.0,
            f"{marker} id-credit", "test_live_cash", 4, "TEST-ICR", None,
        )

        rows = conn.execute(
            """SELECT a.code, gl.debit, gl.credit, gl.description
               FROM general_ledger gl
               JOIN chart_of_accounts a ON a.id=gl.account_id
               WHERE gl.description LIKE ?
               ORDER BY gl.id""",
            (marker + "%",),
        ).fetchall()
        assert len(rows) == 4
        for r in rows:
            assert r["code"] == "000000", dict(r)

        # Cleanup test rows (and reverse COA balance side-effects)
        for r in rows:
            if float(r["debit"] or 0):
                conn.execute(
                    "UPDATE chart_of_accounts SET current_balance=current_balance-? WHERE id=?",
                    (float(r["debit"]), live_id),
                )
            if float(r["credit"] or 0):
                conn.execute(
                    "UPDATE chart_of_accounts SET current_balance=current_balance+? WHERE id=?",
                    (float(r["credit"]), live_id),
                )
        conn.execute(
            "DELETE FROM general_ledger WHERE description LIKE ?",
            (marker + "%",),
        )
