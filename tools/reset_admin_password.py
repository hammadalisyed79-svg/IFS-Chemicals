"""Reset the admin password (V17.3 — default admin123 is no longer valid).

Usage:
    python tools/reset_admin_password.py
    python tools/reset_admin_password.py --password "YourNewPass!234"

Writes the new password once to ADMIN_BOOTSTRAP.txt in the project root (gitignored).
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_FILE = ROOT / "ADMIN_BOOTSTRAP.txt"


def _generate_password() -> str:
    """Policy-compliant random password (12+ chars, upper, lower, digit, special)."""
    base = secrets.token_urlsafe(12)
    return f"IFS!{base[:4]}aZ9#{secrets.token_hex(2)}"


def unlock_account(username: str = "admin") -> None:
    """Clear failed-login lockout for a user."""
    import database as db

    db.init_db()
    with db.get_connection() as conn:
        row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if not row:
            raise ValueError(f"user '{username}' not found")
        conn.execute(
            "UPDATE users SET failed_login_count=0, locked_until=NULL WHERE id=?",
            (row[0],),
        )


def reset_admin_password(username: str = "admin", password: str | None = None) -> str:
    """Reset admin password, clear lockout; return the new plaintext password."""
    import database as db
    from erp_core.password_v173 import hash_password_argon2id, validate_password_policy

    db.init_db()
    password = password or _generate_password()
    ok, msg = validate_password_policy(password, username)
    if not ok:
        raise ValueError(msg)

    h = hash_password_argon2id(password)
    with db.get_connection() as conn:
        row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if not row:
            raise ValueError(f"user '{username}' not found")
        user_id = row[0]
        cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        sql = "UPDATE users SET password_hash=?, must_change_password=0, failed_login_count=0, locked_until=NULL"
        params: list = [h]
        if "password_changed_at" in cols:
            sql += ", password_changed_at=datetime('now')"
        sql += " WHERE id=?"
        params.append(user_id)
        conn.execute(sql, params)
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='schema_meta'").fetchone():
            conn.execute(
                "INSERT INTO schema_meta(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                ("bootstrap_admin_password", password),
            )

    OUT_FILE.write_text(
        f"IFS Industrial ERP — admin login\n\n"
        f"Username: {username}\n"
        f"Password: {password}\n\n"
        f"Delete this file after signing in.\n",
        encoding="utf-8",
    )
    return password


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset IFS ERP admin password")
    parser.add_argument("--password", help="Set this password (must meet policy)")
    parser.add_argument("--username", default="admin")
    parser.add_argument(
        "--unlock-only",
        action="store_true",
        help="Clear account lockout without changing the password",
    )
    args = parser.parse_args()

    try:
        if args.unlock_only:
            unlock_account(args.username)
            print(f"Account lock cleared for '{args.username}'. You may sign in again.")
            return 0
        password = reset_admin_password(args.username, args.password)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"Admin password reset for user '{args.username}' (lockout cleared).")
    print(f"Credentials saved to: {OUT_FILE}")
    print("Sign in at http://localhost:8501 then delete ADMIN_BOOTSTRAP.txt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
