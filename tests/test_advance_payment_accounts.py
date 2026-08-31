"""Cash advance GL uses ADVANCE PAYMENT OTHERS; 100180 reserved for employees."""
import os

import pytest


@pytest.fixture()
def db_mod(tmp_path):
    path = tmp_path / "adv.db"
    os.environ["IFS_DB_PATH"] = str(path)
    import database as db
    import db_v3

    db.DB_PATH = path
    with db.get_connection() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS account_groups(
                   id INTEGER PRIMARY KEY, code TEXT, name TEXT, group_type TEXT, is_active INTEGER DEFAULT 1)"""
        )
        conn.execute(
            "INSERT INTO account_groups(id, code, name, group_type) VALUES (1,'AG','Assets','asset')"
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS chart_of_accounts(
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   code TEXT UNIQUE, name TEXT, account_group_id INTEGER,
                   opening_balance REAL DEFAULT 0, current_balance REAL DEFAULT 0,
                   is_active INTEGER DEFAULT 1, company_id INTEGER, branch_id INTEGER,
                   created_by INTEGER)"""
        )
        conn.execute(
            """INSERT INTO chart_of_accounts(code, name, account_group_id, is_active, company_id, branch_id)
               VALUES ('100180','ADVANCE PAYMENTS',1,1,1,1)"""
        )
    yield db, db_v3


def test_cash_advance_resolves_to_others_not_100180(db_mod):
    db, db_v3 = db_mod
    with db.get_connection() as conn:
        aid = db_v3.resolve_cash_advance_account_id(conn)
        row = conn.execute(
            "SELECT code, name FROM chart_of_accounts WHERE id=?", (aid,)
        ).fetchone()
        assert row["code"] == "100193"
        assert "OTHER" in row["name"].upper()
        emp = conn.execute(
            "SELECT id FROM chart_of_accounts WHERE code='100180'"
        ).fetchone()
        assert int(aid) != int(emp["id"])


def test_hr_employee_advance_uses_100180():
    import db_hr

    assert db_hr.HR_AC["employee_advance"] == "100180"
