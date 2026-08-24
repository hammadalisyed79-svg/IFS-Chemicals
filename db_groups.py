"""Custom groups for products, customers, and suppliers (department / division / etc.)."""

from __future__ import annotations

ENTITY_TYPES = ("product", "customer", "supplier", "account")
ENTITY_LABELS = {
    "product": "Product",
    "customer": "Customer",
    "supplier": "Supplier",
    "account": "Chart Account",
}
ENTITY_TABLES = {
    "product": "products",
    "customer": "customers",
    "supplier": "suppliers",
    "account": "chart_of_accounts",
}
MEMBERS_GRID_TITLE = {
    "product": "Group Items",
    "customer": "Group Accounts",
    "supplier": "Group Accounts",
    "account": "Group GL Accounts",
}
CODE_PREFIX = {
    "product": "PG",
    "customer": "CG",
    "supplier": "SG",
    "account": "AG",
}


def _col_exists(conn, table, col):
    return col in [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _table_exists(conn, name):
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,),
        ).fetchone()
    )


def _master_groups_sql():
    return """CREATE TABLE IF NOT EXISTS master_groups (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type  TEXT NOT NULL CHECK(entity_type IN ('product','customer','supplier','account')),
            code         TEXT NOT NULL,
            name         TEXT NOT NULL,
            parent_id    INTEGER REFERENCES master_groups(id),
            notes        TEXT,
            sort_order   INTEGER DEFAULT 0,
            is_active    INTEGER DEFAULT 1,
            created_by   INTEGER REFERENCES users(id),
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            modified_by  INTEGER REFERENCES users(id),
            modified_at  TEXT,
            UNIQUE(entity_type, code)
        )"""


def _recreate_master_groups_for_account_type(conn):
    """SQLite: expand entity_type CHECK to include chart accounts."""
    for stale in ("master_groups_old", "master_groups_new"):
        if _table_exists(conn, stale):
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute(f"DROP TABLE IF EXISTS {stale}")
            conn.execute("PRAGMA foreign_keys=ON")
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='master_groups'"
    ).fetchone()
    ddl = (row[0] or "") if row else ""
    if "'account'" in ddl:
        return
    conn.execute(
        """CREATE TABLE master_groups_new (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type  TEXT NOT NULL CHECK(entity_type IN ('product','customer','supplier','account')),
            code         TEXT NOT NULL,
            name         TEXT NOT NULL,
            parent_id    INTEGER,
            notes        TEXT,
            sort_order   INTEGER DEFAULT 0,
            is_active    INTEGER DEFAULT 1,
            created_by   INTEGER,
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            modified_by  INTEGER,
            modified_at  TEXT,
            UNIQUE(entity_type, code)
        )"""
    )
    conn.execute("UPDATE master_groups SET parent_id=NULL WHERE parent_id IS NOT NULL")
    conn.execute("INSERT INTO master_groups_new SELECT * FROM master_groups")
    conn.executescript(
        """
        PRAGMA foreign_keys=OFF;
        DROP TABLE IF EXISTS master_groups;
        ALTER TABLE master_groups_new RENAME TO master_groups;
        PRAGMA foreign_keys=ON;
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_master_groups_entity ON master_groups(entity_type, is_active)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_master_groups_parent ON master_groups(parent_id)"
    )


def apply_master_groups(conn, db_module=None):
    """Schema v10+: master_groups + group_id on masters and chart of accounts."""
    from db_v3 import _schema_ver

    conn.execute(_master_groups_sql())
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_master_groups_entity ON master_groups(entity_type, is_active)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_master_groups_parent ON master_groups(parent_id)"
    )
    for table in ("products", "customers", "suppliers", "chart_of_accounts"):
        if _table_exists(conn, table) and not _col_exists(conn, table, "group_id"):
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN group_id INTEGER REFERENCES master_groups(id)"
            )
        if _table_exists(conn, table):
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table}_group ON {table}(group_id)"
            )

    if _schema_ver(conn) < 10:
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('schema_version','10') "
            "ON CONFLICT(key) DO UPDATE SET value='10'"
        )
    if _schema_ver(conn) < 12:
        _recreate_master_groups_for_account_type(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('schema_version','12') "
            "ON CONFLICT(key) DO UPDATE SET value='12'"
        )


def get_master_groups(entity_type, search=None, parent_id=None, active_only=False):
    from database import get_connection, rows_to_list

    if entity_type not in ENTITY_TYPES:
        return []
    q = """SELECT g.*, p.name AS parent_name
           FROM master_groups g
           LEFT JOIN master_groups p ON g.parent_id = p.id
           WHERE g.entity_type = ?"""
    p = [entity_type]
    if active_only:
        q += " AND g.is_active = 1"
    if parent_id is not None:
        q += " AND g.parent_id = ?"
        p.append(parent_id)
    elif parent_id is False:
        q += " AND g.parent_id IS NULL"
    if search:
        like = f"%{search.strip()}%"
        q += " AND (g.code LIKE ? OR g.name LIKE ? OR COALESCE(g.notes,'') LIKE ?)"
        p.extend([like, like, like])
    q += " ORDER BY g.sort_order, g.name"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


def get_master_group(group_id):
    from database import get_connection, row_to_dict

    with get_connection() as conn:
        return row_to_dict(conn.execute(
            """SELECT g.*, p.name AS parent_name
               FROM master_groups g
               LEFT JOIN master_groups p ON g.parent_id = p.id
               WHERE g.id = ?""",
            (group_id,),
        ).fetchone())


def add_master_group(data, user_id=None):
    from database import get_connection, next_code, _now

    entity_type = data["entity_type"]
    if entity_type not in ENTITY_TYPES:
        raise ValueError("Invalid group type.")
    prefix = CODE_PREFIX[entity_type]
    with get_connection() as conn:
        parent_id = data.get("parent_id") or None
        if parent_id:
            par = conn.execute(
                "SELECT entity_type FROM master_groups WHERE id=?", (parent_id,),
            ).fetchone()
            if not par or par["entity_type"] != entity_type:
                raise ValueError("Parent group must be the same type.")
        code = (data.get("code") or "").strip() or next_code(prefix, "master_groups")
        cur = conn.execute(
            """INSERT INTO master_groups(entity_type, code, name, parent_id, notes, sort_order, created_by)
               VALUES(?,?,?,?,?,?,?)""",
            (
                entity_type, code, data["name"].strip(), parent_id,
                data.get("notes"), int(data.get("sort_order") or 0), user_id,
            ),
        )
        return cur.lastrowid


def update_master_group(group_id, data, user_id=None):
    from database import get_connection, _now

    with get_connection() as conn:
        row = conn.execute("SELECT entity_type FROM master_groups WHERE id=?", (group_id,)).fetchone()
        if not row:
            raise ValueError("Group not found.")
        parent_id = data.get("parent_id") or None
        if parent_id == group_id:
            raise ValueError("A group cannot be its own parent.")
        if parent_id:
            par = conn.execute(
                "SELECT entity_type FROM master_groups WHERE id=?", (parent_id,),
            ).fetchone()
            if not par or par["entity_type"] != row["entity_type"]:
                raise ValueError("Parent group must be the same type.")
        conn.execute(
            """UPDATE master_groups SET code=?, name=?, parent_id=?, notes=?, sort_order=?,
               is_active=?, modified_by=?, modified_at=? WHERE id=?""",
            (
                data["code"].strip(), data["name"].strip(), parent_id,
                data.get("notes"), int(data.get("sort_order") or 0),
                int(data.get("is_active", 1)), user_id, _now(), group_id,
            ),
        )


def delete_master_group(group_id):
    from database import get_connection

    with get_connection() as conn:
        g = conn.execute("SELECT entity_type FROM master_groups WHERE id=?", (group_id,)).fetchone()
        if not g:
            return
        child = conn.execute(
            "SELECT COUNT(*) FROM master_groups WHERE parent_id=?", (group_id,),
        ).fetchone()[0]
        if child:
            raise ValueError("Remove or reassign child groups first.")
        et = g["entity_type"]
        table = ENTITY_TABLES[et]
        used = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE group_id=?", (group_id,),
        ).fetchone()[0]
        if used:
            raise ValueError(f"Cannot delete — {used} {et}(s) still use this group.")
        conn.execute("DELETE FROM master_groups WHERE id=?", (group_id,))


def group_options(entity_type, include_none=True, active_only=True):
    """Selectbox options: label -> id."""
    rows = get_master_groups(entity_type, active_only=active_only)
    opts = {}
    if include_none:
        opts["(No group)"] = None
    for r in rows:
        indent = ""
        if r.get("parent_name"):
            indent = "  └ "
        opts[f"{indent}{r['code']} — {r['name']}"] = r["id"]
    return opts


def group_label(group_id):
    if not group_id:
        return ""
    g = get_master_group(group_id)
    return f"{g['code']} — {g['name']}" if g else ""


def get_group_members(group_id):
    """Accounts or items assigned to this group (IFS-style membership list)."""
    from database import get_connection, rows_to_list

    g = get_master_group(group_id)
    if not g:
        return []
    et = g["entity_type"]
    with get_connection() as conn:
        if et == "product":
            return rows_to_list(conn.execute(
                """SELECT p.id, p.code, p.name, p.product_type AS item_type,
                          pc.name AS category
                   FROM products p
                   LEFT JOIN product_categories pc ON p.category_id = pc.id
                   WHERE p.group_id = ?
                   ORDER BY p.code""",
                (group_id,),
            ).fetchall())
        if et == "account":
            return rows_to_list(conn.execute(
                """SELECT a.id, a.code, a.name, g.group_type AS account_type
                   FROM chart_of_accounts a
                   JOIN account_groups g ON a.account_group_id = g.id
                   WHERE a.group_id = ? AND a.is_active = 1
                   ORDER BY a.code""",
                (group_id,),
            ).fetchall())
        table = ENTITY_TABLES[et]
        return rows_to_list(conn.execute(
            f"SELECT id, code, name FROM {table} WHERE group_id = ? ORDER BY code",
            (group_id,),
        ).fetchall())


def get_entities_for_group_add(entity_type, group_id, search=None, limit=2500):
    """Masters not already in this group (available to add)."""
    from database import get_connection, rows_to_list

    if entity_type not in ENTITY_TYPES:
        return []
    table = ENTITY_TABLES[entity_type]
    q = f"SELECT id, code, name, group_id FROM {table} WHERE is_active = 1 AND (group_id IS NULL OR group_id != ?)"
    p = [group_id]
    if search:
        like = f"%{search.strip()}%"
        q += " AND (code LIKE ? OR name LIKE ?)"
        p.extend([like, like])
    if entity_type == "product":
        q = """SELECT p.id, p.code, p.name, p.group_id, p.product_type AS item_type
               FROM products p
               WHERE p.is_active = 1 AND (p.group_id IS NULL OR p.group_id != ?)"""
        p = [group_id]
        if search:
            like = f"%{search.strip()}%"
            q += " AND (p.code LIKE ? OR p.name LIKE ?)"
            p.extend([like, like])
    elif entity_type == "account":
        q = """SELECT a.id, a.code, a.name, a.group_id, g.group_type AS item_type
               FROM chart_of_accounts a
               JOIN account_groups g ON a.account_group_id = g.id
               WHERE a.is_active = 1 AND (a.group_id IS NULL OR a.group_id != ?)"""
        p = [group_id]
        if search:
            like = f"%{search.strip()}%"
            q += " AND (a.code LIKE ? OR a.name LIKE ?)"
            p.extend([like, like])
    q += " ORDER BY code LIMIT ?"
    p.append(int(limit))
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


def assign_entity_to_group(entity_type, entity_id, group_id, user_id=None):
    assign_entities_to_group(entity_type, [entity_id], group_id, user_id)


def assign_entities_to_group(entity_type, entity_ids, group_id, user_id=None):
    """Assign many customers, suppliers, or products to one group in one transaction."""
    from database import get_connection, _now

    if entity_type not in ENTITY_TYPES:
        raise ValueError("Invalid entity type.")
    if not entity_ids:
        return 0
    g = get_master_group(group_id)
    if not g or g["entity_type"] != entity_type:
        raise ValueError("Group type does not match.")
    table = ENTITY_TABLES[entity_type]
    ids = list({int(i) for i in entity_ids if i})
    ts = _now()
    with get_connection() as conn:
        for eid in ids:
            row = conn.execute(f"SELECT id FROM {table} WHERE id=?", (eid,)).fetchone()
            if not row:
                raise ValueError(f"Record id {eid} not found.")
        conn.executemany(
            f"UPDATE {table} SET group_id=?, modified_by=?, modified_at=? WHERE id=?",
            [(group_id, user_id, ts, eid) for eid in ids],
        )
    return len(ids)


def resolve_entity_ids_by_codes(entity_type, codes):
    """Map account/item codes (list of strings) to record ids."""
    from database import get_connection

    if entity_type not in ENTITY_TYPES:
        return [], []
    table = ENTITY_TABLES[entity_type]
    normalized = []
    seen = set()
    for raw in codes:
        c = (raw or "").strip().upper()
        if c and c not in seen:
            seen.add(c)
            normalized.append(c)
    if not normalized:
        return [], []
    found_ids, missing = [], []
    with get_connection() as conn:
        for code in normalized:
            row = conn.execute(
                f"SELECT id FROM {table} WHERE UPPER(code)=? AND is_active=1",
                (code,),
            ).fetchone()
            if row:
                found_ids.append(row["id"])
            else:
                missing.append(code)
    return found_ids, missing


def remove_entity_from_group(entity_type, entity_id, user_id=None):
    remove_entities_from_group(entity_type, [entity_id], user_id)


def remove_entities_from_group(entity_type, entity_ids, user_id=None):
    from database import get_connection, _now

    if entity_type not in ENTITY_TYPES:
        raise ValueError("Invalid entity type.")
    ids = list({int(i) for i in entity_ids if i})
    if not ids:
        return 0
    table = ENTITY_TABLES[entity_type]
    ts = _now()
    with get_connection() as conn:
        conn.executemany(
            f"UPDATE {table} SET group_id=NULL, modified_by=?, modified_at=? WHERE id=?",
            [(user_id, ts, eid) for eid in ids],
        )
    return len(ids)
