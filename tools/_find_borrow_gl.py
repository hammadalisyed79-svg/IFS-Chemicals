import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import database as db

with db.get_connection() as conn:
    rows = conn.execute(
        """SELECT a.code, a.name, g.group_type
           FROM chart_of_accounts a
           JOIN account_groups g ON a.account_group_id=g.id
           WHERE a.is_active=1 AND (
             UPPER(a.name) LIKE '%BORROW%'
             OR UPPER(a.name) LIKE '%LOAN%'
             OR UPPER(a.name) LIKE '%SHORT%'
             OR a.code IN ('200180','300180','100180')
           )
           ORDER BY a.code LIMIT 40"""
    ).fetchall()
    for r in rows:
        print(dict(r))
