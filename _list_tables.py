import database
database.init_db()
with database.get_connection() as conn:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1").fetchall()
    for r in rows:
        print(r[0] if not hasattr(r, 'keys') else (r['name'] if 'name' in r.keys() else r[0]))
