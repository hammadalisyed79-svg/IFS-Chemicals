"""Set SEASONS EDIBLE OIL LIMITED (100589) party + COA opening to NIL."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import database as db
from database import _now, invalidate

CODE = "100589"
TARGET_OB = 0.0

with db.get_connection() as conn:
    cust = conn.execute(
        "SELECT id, code, name, opening_balance, current_balance FROM customers WHERE code=?",
        (CODE,),
    ).fetchone()
    if not cust:
        raise SystemExit(f"Customer {CODE} not found")
    cust = dict(cust)
    old_ob = float(cust["opening_balance"] or 0)
    old_cb = float(cust["current_balance"] or 0)
    diff = TARGET_OB - old_ob
    new_cb = round(old_cb + diff, 2)

    conn.execute(
        """UPDATE customers
           SET opening_balance=?, current_balance=?, modified_at=?
           WHERE id=?""",
        (TARGET_OB, new_cb, _now(), cust["id"]),
    )

    coa = conn.execute(
        "SELECT id, opening_balance, current_balance FROM chart_of_accounts WHERE code=?",
        (CODE,),
    ).fetchone()
    if coa:
        coa_ob = float(coa["opening_balance"] or 0)
        coa_cb = float(coa["current_balance"] or 0)
        conn.execute(
            """UPDATE chart_of_accounts
               SET opening_balance=?, current_balance=?, modified_at=?
               WHERE id=?""",
            (TARGET_OB, round(coa_cb + (TARGET_OB - coa_ob), 2), _now(), coa["id"]),
        )

    try:
        from db_audit import log_event
        log_event(
            "customers", cust["id"], "update", module="Masters",
            document_no=CODE,
            summary=f"Opening balance set to NIL (was {old_ob:,.2f}) — SEASONS EDIBLE OIL LIMITED",
        )
    except Exception:
        pass

    c2 = dict(conn.execute(
        "SELECT code, name, opening_balance, current_balance FROM customers WHERE id=?",
        (cust["id"],),
    ).fetchone())
    a2 = conn.execute(
        "SELECT code, opening_balance, current_balance FROM chart_of_accounts WHERE code=?",
        (CODE,),
    ).fetchone()

invalidate("customers")

print("BEFORE OB/CB:", f"{old_ob:,.2f}", f"{old_cb:,.2f}")
print("AFTER customer:", c2)
print("AFTER COA:", dict(a2) if a2 else None)

party, entries = db.get_customer_ledger_detailed(cust["id"], None, None)
summary = party.get("ledger_summary") or {}
print("Ledger opening:", party.get("opening_balance"))
print("Ledger summary:", summary)
if entries:
    last = entries[-1]
    print("Last row:", last.get("type"), last.get("balance"), last.get("balance_side") or last.get("bal_side"))
