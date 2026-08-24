"""CI test admin credentials — no default password in product UI."""

from __future__ import annotations

CI_ADMIN_PASSWORD = "Qy7!xK9mNp2ZsW4"


def set_ci_admin(db, password: str = CI_ADMIN_PASSWORD) -> str:
    from erp_core.password_v173 import hash_password_argon2id
    h = hash_password_argon2id(password)
    with db.get_connection() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "must_change_password" in cols:
            sql = "UPDATE users SET password_hash=?, must_change_password=0"
            params: list = [h]
            if "password_changed_at" in cols:
                sql += ", password_changed_at=datetime('now')"
            sql += " WHERE username='admin'"
            conn.execute(sql, params)
        else:
            conn.execute("UPDATE users SET password_hash=? WHERE username='admin'", (h,))
    return password
