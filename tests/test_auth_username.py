"""Case-insensitive username handling."""

from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _temp_db():
    import database as db
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db.DB_PATH = __import__("pathlib").Path(path)
    db.reset_runtime_state()
    db.init_db()
    return db, path


def test_login_username_case_insensitive():
    db, path = _temp_db()
    try:
        from tests._bootstrap import set_ci_admin, CI_ADMIN_PASSWORD
        set_ci_admin(db)
        db.add_user("Abdullah", "Pass1234!", "Abdullah User", role="user", created_by=1)
        for variant in ("abdullah", "ABDULLAH", "AbDuLlAh"):
            user = db.authenticate(variant, "Pass1234!")
            assert user and user.get("username") == "Abdullah", variant
        assert db.authenticate("Abdullah", "wrong") is None
        print("PASS login username case insensitive")
    finally:
        os.unlink(path)


def test_add_user_rejects_case_duplicate():
    db, path = _temp_db()
    try:
        db.add_user("Usman", "Pass1234!", "Usman One", role="user", created_by=1)
        try:
            db.add_user("usman", "Pass1234!", "Usman Two", role="user", created_by=1)
            raise AssertionError("Expected duplicate username error")
        except ValueError as e:
            assert "case sensitive" in str(e).lower() or "already exists" in str(e).lower()
        print("PASS add user rejects case duplicate")
    finally:
        os.unlink(path)


if __name__ == "__main__":
    test_login_username_case_insensitive()
    test_add_user_rejects_case_duplicate()
