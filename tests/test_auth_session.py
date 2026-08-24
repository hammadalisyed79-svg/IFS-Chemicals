"""Session persistence across browser refresh."""

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


def test_session_token_restored_from_state_key():
    db, path = _temp_db()
    try:
        from tests._bootstrap import set_ci_admin, CI_ADMIN_PASSWORD
        set_ci_admin(db)
        user = db.authenticate("admin", CI_ADMIN_PASSWORD)
        assert user
        token = db.create_user_session(user["id"], 7)
        restored = db.get_user_by_session_token(token)
        assert restored and restored["username"] == "admin"
        print("PASS session token restores user from database")
    finally:
        os.unlink(path)


def test_clear_session_deletes_token():
    db, path = _temp_db()
    try:
        from tests._bootstrap import set_ci_admin, CI_ADMIN_PASSWORD
        set_ci_admin(db)
        user = db.authenticate("admin", CI_ADMIN_PASSWORD)
        token = db.create_user_session(user["id"], 7)
        db.delete_user_session(token)
        assert db.get_user_by_session_token(token) is None
        print("PASS deleted session token invalid")
    finally:
        os.unlink(path)


def test_single_session_replaces_previous():
    db, path = _temp_db()
    try:
        from tests._bootstrap import set_ci_admin, CI_ADMIN_PASSWORD
        set_ci_admin(db)
        user = db.authenticate("admin", CI_ADMIN_PASSWORD)
        first = db.create_user_session(user["id"], 7)
        second = db.create_user_session(user["id"], 7)
        assert first != second
        assert db.get_user_by_session_token(first) is None
        assert db.get_user_by_session_token(second)["username"] == "admin"
        print("PASS second login revokes first session")
    finally:
        os.unlink(path)


def test_idle_timeout_expires_session():
    db, path = _temp_db()
    try:
        from datetime import datetime, timedelta
        from tests._bootstrap import set_ci_admin, CI_ADMIN_PASSWORD
        set_ci_admin(db)
        db.set_setting("session_idle_minutes", "15")
        user = db.authenticate("admin", CI_ADMIN_PASSWORD)
        token = db.create_user_session(user["id"], 7)
        stale = (datetime.now() - timedelta(minutes=16)).strftime("%Y-%m-%d %H:%M:%S")
        with db.get_connection() as conn:
            conn.execute(
                "UPDATE user_sessions SET last_activity_at=? WHERE token=?",
                (stale, token),
            )
        assert db.get_user_by_session_token(token) is None
        from erp_core.v15_security import last_session_fail_reason
        assert last_session_fail_reason() == "idle"
        print("PASS idle timeout expires session after 15 minutes")
    finally:
        os.unlink(path)


if __name__ == "__main__":
    test_session_token_restored_from_state_key()
    test_clear_session_deletes_token()
    test_single_session_replaces_previous()
    test_idle_timeout_expires_session()
