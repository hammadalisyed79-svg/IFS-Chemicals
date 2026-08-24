"""Create product group 'cylinders' and assign all CLY* items."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import database as db
from db_groups import (
    add_master_group,
    assign_entities_to_group,
    get_master_groups,
)


def main():
    groups = get_master_groups("product", search="cylinders")
    group = None
    for g in groups:
        if (g.get("name") or "").strip().lower() == "cylinders":
            group = g
            break
    if not group:
        # also match close names
        for g in get_master_groups("product"):
            n = (g.get("name") or "").strip().lower()
            if n in ("cylinders", "cylinder"):
                group = g
                break

    if group:
        gid = group["id"]
        print(f"Using existing group id={gid} code={group.get('code')} name={group.get('name')}")
    else:
        gid = add_master_group(
            {
                "entity_type": "product",
                "code": "CYLINDERS",
                "name": "cylinders",
                "notes": "Auto-grouped: all items with code starting CLY",
            },
            user_id=None,
        )
        print(f"Created group id={gid} code=CYLINDERS name=cylinders")

    with db.get_connection() as conn:
        rows = conn.execute(
            """SELECT id, code, name, group_id, is_active
               FROM products
               WHERE UPPER(TRIM(code)) LIKE 'CLY%'
               ORDER BY code"""
        ).fetchall()
        ids = [r["id"] for r in rows]
        print(f"CLY* products found: {len(ids)}")
        if rows:
            for r in rows[:10]:
                print(f"  {r['code']} | {r['name']} | group_id={r['group_id']} active={r['is_active']}")
            if len(rows) > 10:
                print(f"  ... and {len(rows) - 10} more")

    if not ids:
        print("Nothing to assign.")
        return

    n = assign_entities_to_group("product", ids, gid)
    print(f"Assigned {n} product(s) to group 'cylinders' (id={gid})")

    with db.get_connection() as conn:
        chk = conn.execute(
            """SELECT COUNT(*) AS n FROM products
               WHERE UPPER(TRIM(code)) LIKE 'CLY%' AND group_id=?""",
            (gid,),
        ).fetchone()["n"]
        other = conn.execute(
            """SELECT COUNT(*) AS n FROM products
               WHERE UPPER(TRIM(code)) LIKE 'CLY%' AND (group_id IS NULL OR group_id!=?)""",
            (gid,),
        ).fetchone()["n"]
        print(f"Verify: in cylinders={chk}, CLY not in group={other}")


if __name__ == "__main__":
    main()
