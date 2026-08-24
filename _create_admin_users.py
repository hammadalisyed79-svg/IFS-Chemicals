from erp_core.v15_security import hash_password_secure
import database

USERS = [
    ("shabab", "Shabab"),
    ("usman", "Usman"),
    ("mudassar", "Mudassar"),
    ("hammad", "Hammad"),
]
PASSWORD = "Login@1786"
results = []

for username, full_name in USERS:
    try:
        with database.get_connection() as conn:
            row = database._find_user_row(conn, username)
        if row:
            user_id = row["id"] if hasattr(row, "keys") else row[0]
            # Update password without clearing must_change; then force must_change_password=1
            database.change_user_password(int(user_id), PASSWORD, clear_must_change=False)
            with database.get_connection() as conn:
                conn.execute(
                    "UPDATE users SET must_change_password=1, role=?, full_name=? WHERE id=?",
                    ("admin", full_name, int(user_id)),
                )
            results.append((username, "success", "updated existing"))
        else:
            database.add_user(
                username,
                PASSWORD,
                full_name,
                role="admin",
                must_change_password=1,
            )
            results.append((username, "success", "created"))
    except Exception as e:
        results.append((username, "fail", str(e)))

print("=== RESULTS ===")
for u, status, msg in results:
    print(f"{u}: {status} ({msg})")

print("=== VERIFICATION SELECT ===")
with database.get_connection() as conn:
    cur = conn.execute(
        """
        SELECT id, username, full_name, role, must_change_password,
               CASE WHEN password_hash IS NOT NULL AND length(password_hash) > 0 THEN 'set' ELSE 'empty' END AS pwd_status
        FROM users
        WHERE lower(username) IN ('shabab','usman','mudassar','hammad')
        ORDER BY username
        """
    )
    cols = [d[0] for d in cur.description]
    print("|".join(cols))
    for r in cur.fetchall():
        if hasattr(r, "keys"):
            print("|".join(str(r[c]) for c in cols))
        else:
            print("|".join(str(x) for x in r))
