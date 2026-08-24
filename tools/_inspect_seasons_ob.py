import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import database as db

with db.get_connection() as conn:
    c = conn.execute(
        """SELECT id, code, name, opening_balance, current_balance
           FROM customers WHERE code=? OR UPPER(name) LIKE '%SEASONS EDIBLE%'""",
        ("100589",),
    ).fetchone()
    print("customer:", dict(c) if c else None)

    # matching COA?
    coa = conn.execute(
        "SELECT id, code, name, opening_balance, current_balance FROM chart_of_accounts WHERE code=?",
        ("100589",),
    ).fetchone()
    print("coa:", dict(coa) if coa else None)
